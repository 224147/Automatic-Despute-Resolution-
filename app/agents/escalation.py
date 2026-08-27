"""Escalation Agent — escalates disputes to the appropriate human team with LLM-generated summary."""
from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.llm import get_llm
from app.agents.state import DisputeState
from app.core.enums import AuditEventType, EscalationReason
from app.core.logging import get_logger

logger = get_logger(__name__)

_ESCALATION_AGENT_PROMPT = """You are an Escalation Agent in a banking dispute resolution system.

Your job is to prepare a clear, concise summary for the human agent who will handle this dispute.

Include:
1. Why this dispute was escalated (risk level, fraud indicators, rule failures)
2. Key facts: category, amount, transaction details
3. What has been verified and what hasn't
4. Recommended priority and which team should handle it
5. Any specific concerns or red flags

Write a professional summary suitable for a banking support agent.
"""


async def escalation_agent_node(state: DisputeState, db) -> dict:
    """Escalate the dispute with an LLM-generated summary for the human agent."""
    from app.agents.tools import create_db_bound_tools
    from app.audit.service import log_audit_event

    logger.info("escalation_agent_start", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    db_tools = create_db_bound_tools(db)
    dispute_id = state["dispute_id"]
    reason = state.get("escalation_reason", EscalationReason.SYSTEM_ERROR.value)
    risk_level = state.get("risk_result", {}).get("risk_level", "MEDIUM")

    priority_map = {"LOW": "LOW", "MEDIUM": "MEDIUM", "HIGH": "HIGH", "CRITICAL": "CRITICAL"}
    priority = priority_map.get(risk_level, "MEDIUM")

    team = "FRAUD_TEAM" if reason in (
        EscalationReason.FRAUD_SUSPECTED.value, EscalationReason.HIGH_RISK.value
    ) else "DISPUTE_TEAM"

    sla = 24 if priority in ("HIGH", "CRITICAL") else 48

    # LLM generates a summary for the human agent (optional — works without it)
    escalation_reason = (
    f"Category: {state.get('dispute_category', 'UNKNOWN')}, "
    f"Amount: {state.get('transaction_amount', 'N/A')}, "
    f"Risk: {risk_level}"
)
    try:
        llm = get_llm()
        summary_response = await llm.ainvoke([
            SystemMessage(content=_ESCALATION_AGENT_PROMPT),
            HumanMessage(content=f"""Dispute details:
- Dispute ID: {dispute_id}
- Category: {state.get('dispute_category', 'UNKNOWN')}
- Amount: {state.get('transaction_amount', 'N/A')}
- Customer verified: {state.get('customer_verified', False)}
- Transaction verified: {state.get('transaction_verified', False)}
- Fraud indicator: {state.get('fraud_indicator', False)}
- Risk level: {risk_level}
- Risk score: {state.get('risk_result', {}).get('risk_score', 'N/A')}
- Risk factors: {state.get('risk_result', {}).get('risk_factors', [])}
- Rule result: {json.dumps(state.get('rule_result', {}))}
- Escalation reason: {reason}
- Customer message: "{state.get('customer_message', '')}"
- Audit trail: {audit_events}

Write a summary for the {team} agent."""),
        ])
        summary_text = summary_response.content
    except Exception as e:
        logger.warning("escalation_agent_llm_unavailable", error=str(e))

    # Create escalation record
    esc_json = await db_tools["escalate_dispute"].ainvoke({
        "dispute_id": dispute_id,
        "reason": reason,
        "priority": priority,
        "team": team,
        "sla_hours": str(sla),
    })
    esc_data = json.loads(esc_json)

    await log_audit_event(
        db,
        event_type=AuditEventType.ESCALATION.value,
        event_description=f"Escalation Agent: {reason}, team={team}, priority={priority}",
        dispute_id=uuid.UUID(dispute_id),
        customer_id=uuid.UUID(state["customer_id"]),
        new_state={"escalation_id": esc_data["escalation_id"], "reason": reason, "team": team,
                    "agent_summary": summary_text[:500]},
    )

    # Send notification
    extra = json.dumps({"category": state.get("dispute_category", "UNKNOWN"), "sla": str(sla)})
    await db_tools["send_notification"].ainvoke({
        "customer_id": state["customer_id"],
        "customer_name": state.get("customer_name", "Customer"),
        "dispute_id": dispute_id,
        "template_name": "escalated",
        "extra_vars": extra,
    })

    # Final audit
    await db_tools["log_audit"].ainvoke({
        "event_type": "WORKFLOW_COMPLETE",
        "description": f"Escalated to {team}: {reason}",
        "dispute_id": dispute_id,
        "customer_id": state["customer_id"],
    })

    audit_events.append(f"ESCALATE: {reason} -> {team}")
    audit_events.append("NOTIFY: escalated")
    audit_events.append("AUDIT: workflow complete")

    logger.info("escalation_agent_done", team=team, priority=priority)

    return {
        "action_result": {"escalation_id": esc_data["escalation_id"], "reason": reason, "team": team},
        "final_response": (
            f"Your dispute has been escalated to our {team.replace('_', ' ').title()} "
            f"for further review. Priority: {priority}. "
            f"Expected resolution within {sla} hours. "
            f"Reference: {dispute_id[:8]}"
        ),
        "audit_events": audit_events,
        "messages": [AIMessage(content=f"[Escalation Agent] {summary_text}")],
    }
