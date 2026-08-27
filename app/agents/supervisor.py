"""Supervisor agent — routes between specialist agents using LLM with deterministic fallback."""
from __future__ import annotations

import json

from app.agents.state import DisputeState
from app.core.logging import get_logger

logger = get_logger(__name__)

AGENT_NAMES = [
    "classification_agent",
    "verification_agent",
    "resolution_agent",
    "execution_agent",
    "escalation_agent",
]

_SUPERVISOR_PROMPT = """You are a supervisor coordinating a banking dispute resolution system.
You decide which specialist agent should act next based on the current state of the dispute.

Available agents:
- classification_agent: Classifies the dispute type and detects fraud indicators
- verification_agent: Verifies customer identity and finds the disputed transaction
- resolution_agent: Evaluates policies, rules, and risk to decide if auto-resolution is possible
- execution_agent: Executes safe actions (refund/credit) for auto-resolved disputes
- escalation_agent: Escalates complex/high-risk disputes to human agents

Current dispute state:
- dispute_id: {dispute_id}
- category: {category}
- confidence: {confidence}
- customer_verified: {customer_verified}
- transaction_verified: {transaction_verified}
- transaction_id: {transaction_id}
- policy_found: {policy_found}
- rule_result: {rule_result}
- risk_level: {risk_level}
- resolution_decision: {resolution_decision}
- errors: {errors}

Workflow rules:
1. If no dispute_id exists yet, the intake hasn't happened — but classification_agent handles intake too.
2. If dispute_category is empty or UNKNOWN with low confidence, route to classification_agent.
3. After classification, route to verification_agent to verify customer and find transaction.
4. After verification, route to resolution_agent to evaluate rules and risk.
5. If resolution_decision is AUTO_RESOLVE, route to execution_agent.
6. If resolution_decision is ESCALATE, or any critical issue, route to escalation_agent.
7. If all steps are complete (a final_response exists), respond with FINISH.

Respond with ONLY a JSON object:
{{"next": "<agent_name or FINISH>"}}
"""


async def supervisor_node(state: DisputeState) -> dict:
    """Decide which agent to call next. Tries LLM, falls back to deterministic routing."""
    # Try LLM-based routing first
    try:
        from app.agents.llm import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = get_llm()
        risk_level = state.get("risk_result", {}).get("risk_level", "")

        prompt = _SUPERVISOR_PROMPT.format(
            dispute_id=state.get("dispute_id", ""),
            category=state.get("dispute_category", ""),
            confidence=state.get("classification_confidence", 0),
            customer_verified=state.get("customer_verified", False),
            transaction_verified=state.get("transaction_verified", False),
            transaction_id=state.get("transaction_id", ""),
            policy_found=state.get("policy_found", False),
            rule_result=json.dumps(state.get("rule_result", {})),
            risk_level=risk_level,
            resolution_decision=state.get("resolution_decision", ""),
            errors=state.get("errors", []),
        )

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content="Based on the current state, which agent should act next?"),
        ])

        content = response.content.strip()
        json_match = __import__("re").search(r"\{.*\}", content, __import__("re").DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            next_agent = data.get("next", "FINISH")
        else:
            next_agent = _deterministic_routing(state)

        if next_agent not in AGENT_NAMES and next_agent != "FINISH":
            logger.warning("supervisor_invalid_agent", suggested=next_agent)
            next_agent = _deterministic_routing(state)

    except Exception as e:
        logger.warning("supervisor_llm_unavailable", error=str(e))
        next_agent = _deterministic_routing(state)

    logger.info("supervisor_decision", next_agent=next_agent)
    return {"next_agent": next_agent}


def _deterministic_routing(state: DisputeState) -> str:
    """Deterministic routing based on state — always works without LLM."""
    if not state.get("dispute_id"):
        return "classification_agent"
    if not state.get("dispute_category") or state.get("dispute_category") == "UNKNOWN":
        return "classification_agent"
    if not state.get("customer_verified"):
        return "verification_agent"
    if not state.get("rule_result"):
        return "resolution_agent"
    decision = state.get("resolution_decision", "")
    if decision == "AUTO_RESOLVE":
        return "execution_agent"
    if decision == "ESCALATE":
        return "escalation_agent"
    return "FINISH"
