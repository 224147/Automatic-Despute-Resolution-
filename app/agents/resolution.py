"""Resolution Agent — evaluates policies, rules, and risk to decide dispute outcome."""
from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.llm import get_llm
from app.agents.state import DisputeState
from app.core.enums import AuditEventType, EscalationReason, RiskLevel
from app.core.logging import get_logger

logger = get_logger(__name__)

_RESOLUTION_AGENT_PROMPT = """You are a Resolution Agent in a banking dispute resolution system.

Your responsibilities:
1. Evaluate the dispute against banking rules (auto-resolution eligibility)
2. Assess risk/fraud level
3. Make the final decision: AUTO_RESOLVE or ESCALATE

You have access to:
- evaluate_rules_tool: Checks eligibility based on category, amount, status
- assess_risk_tool: Scores risk based on amount, type, fraud indicators

Decision rules you MUST follow:
- HIGH or CRITICAL risk → always ESCALATE
- Customer not verified → always ESCALATE
- Fraud indicator → always ESCALATE
- Policy not found → always ESCALATE
- Rules say not eligible → ESCALATE
- Rules say eligible AND risk is LOW or MEDIUM → AUTO_RESOLVE

Analyze all evidence and explain your reasoning.
"""


async def resolution_agent_node(state: DisputeState, db) -> dict:
    """Evaluate rules and risk, decide on auto-resolve vs escalate."""
    from app.agents.tools import assess_risk_tool, evaluate_rules_tool
    from app.audit.service import log_audit_event

    logger.info("resolution_agent_start", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    # Step 1: Run rules engine
    rules_json = await evaluate_rules_tool.ainvoke({
        "category": state.get("dispute_category", "UNKNOWN"),
        "amount": str(state.get("transaction_amount") or ""),
        "transaction_status": state.get("transaction_status") or "",
        "customer_verified": str(state.get("customer_verified", False)),
        "previous_dispute_count": str(state.get("previous_dispute_count", 0)),
        "fraud_indicator": str(state.get("fraud_indicator", False)),
        "policy_found": str(state.get("policy_found", False)),
        "transaction_age_days": str(state.get("transaction_age_days") or ""),
    })
    rule_result = json.loads(rules_json)

    await log_audit_event(
        db,
        event_type=AuditEventType.RULE_EVALUATION.value,
        event_description=(
    f"Resolution Agent: "
    f"rules={rule_result.get('recommended_action')}, "
    f"eligible={rule_result.get('eligible_for_auto_resolution')}"
),
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
        customer_id=uuid.UUID(state["customer_id"]),
        new_state=rule_result,
        decision_reason=", ".join(rule_result.get("reason_codes", [])),
    )
    audit_events.append(
    f"RULES: {rule_result.get('recommended_action')} "
    f"(eligible={rule_result.get('eligible_for_auto_resolution')})"
)

    # Step 2: Assess risk
    risk_json = await assess_risk_tool.ainvoke({
        "amount": str(state.get("transaction_amount") or 0),
        "transaction_type": state.get("transaction_type") or "",
        "transaction_status": state.get("transaction_status") or "",
        "dispute_category": state.get("dispute_category", "UNKNOWN"),
        "customer_dispute_frequency": str(state.get("previous_dispute_count", 0)),
        "fraud_indicator": str(state.get("fraud_indicator", False)),
        "customer_verified": str(state.get("customer_verified", False)),
        "transaction_age_days": str(state.get("transaction_age_days") or ""),
    })
    risk_result = json.loads(risk_json)

    await log_audit_event(
        db,
        event_type=AuditEventType.RISK_ASSESSMENT.value,
        event_description=f"Resolution Agent: risk={risk_result['risk_level']} (score: {risk_result['risk_score']})",
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
        customer_id=uuid.UUID(state["customer_id"]),
        new_state=risk_result,
    )

    # Update dispute with risk info
    from app.tools.banking import update_dispute
    if state.get("dispute_id"):
        await update_dispute(
            db, uuid.UUID(state["dispute_id"]),
            risk_score=risk_result["risk_score"],
            risk_level=risk_result["risk_level"],
        )
    audit_events.append(f"RISK: {risk_result['risk_level']} ({risk_result['risk_score']})")

    # Step 3: Make decision
    risk_level = risk_result.get("risk_level", "MEDIUM")
    eligible = rule_result.get("eligible_for_auto_resolution", False)
    human_required = rule_result.get("required_human_review", False)

    if risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value):
        decision = "ESCALATE"
        esc_reason = EscalationReason.HIGH_RISK.value
    elif not state.get("customer_verified", False):
        decision = "ESCALATE"
        esc_reason = EscalationReason.CUSTOMER_NOT_VERIFIED.value
    elif state.get("fraud_indicator", False):
        decision = "ESCALATE"
        esc_reason = EscalationReason.FRAUD_SUSPECTED.value
    elif not state.get("policy_found", True):
        decision = "ESCALATE"
        esc_reason = EscalationReason.POLICY_NOT_FOUND.value
    elif human_required:
        decision = "ESCALATE"
        esc_reason = rule_result.get("reason_codes", ["RULE_NOT_ELIGIBLE"])[0]
    elif eligible and risk_level in (RiskLevel.LOW.value, RiskLevel.MEDIUM.value):
        decision = "AUTO_RESOLVE"
        esc_reason = None
    else:
        decision = "ESCALATE"
        esc_reason = EscalationReason.RULE_NOT_ELIGIBLE.value

    # Step 4: LLM reasoning about the decision (optional — works without it)
    reasoning_text = f"Decision: {decision}, reason: {esc_reason or 'Eligible for auto-resolution'}"
    try:
        llm = get_llm()
        reasoning = await llm.ainvoke([
            SystemMessage(content=_RESOLUTION_AGENT_PROMPT),
            HumanMessage(content=f"""Decision analysis:
- Category: {state.get('dispute_category')}
- Amount: {state.get('transaction_amount')}
- Rules result: {rules_json}
- Risk result: {risk_json}
- Customer verified: {state.get('customer_verified')}
- Fraud indicator: {state.get('fraud_indicator')}
- Policy found: {state.get('policy_found')}

My decision: {decision}
Reason: {esc_reason or 'Eligible for auto-resolution'}

Explain why this decision is correct."""),
        ])
        reasoning_text = reasoning.content
    except Exception as e:
        logger.warning("resolution_agent_llm_unavailable", error=str(e))

    audit_events.append(f"DECISION: {decision}")
    logger.info("resolution_agent_done", decision=decision, risk_level=risk_level)

    return {
        "rule_result": rule_result,
        "risk_result": risk_result,
        "resolution_decision": decision,
        "escalation_required": decision == "ESCALATE",
        "escalation_reason": esc_reason,
        "audit_events": audit_events,
        "messages": [AIMessage(content=f"[Resolution Agent] {reasoning_text}")],
    }
