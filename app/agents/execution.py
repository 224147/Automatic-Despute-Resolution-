"""Execution Agent — performs safe automated actions (refund/credit) for auto-resolved disputes."""
from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage

from app.agents.state import DisputeState
from app.core.enums import ActorType, AuditEventType, DisputeStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


async def execution_agent_node(state: DisputeState, db) -> dict:
    """Execute the refund or provisional credit. This agent is deterministic (no LLM)."""
    from app.agents.tools import create_db_bound_tools
    from app.audit.service import log_audit_event

    logger.info("execution_agent_start", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    db_tools = create_db_bound_tools(db)
    dispute_id = state["dispute_id"]
    amount = state.get("transaction_amount") or 0
    action = state.get("rule_result", {}).get("recommended_action", "AUTO_REFUND")

    # Execute the appropriate action
    if action in ("AUTO_REFUND", "AUTO_CREDIT", "REFUND_WITH_VERIFICATION"):
        res_json = await db_tools["create_refund"].ainvoke({
            "dispute_id": dispute_id,
            "amount": str(amount),
        })
        res_data = json.loads(res_json)
        if amount > 0:
            action_taken = f"Refund of INR {amount:,.2f} initiated"
        else:
            action_taken = "Refund initiated (amount will be confirmed after transaction verification)"
    else:
        res_json = await db_tools["create_provisional_credit"].ainvoke({
            "dispute_id": dispute_id,
            "amount": str(amount),
        })
        res_data = json.loads(res_json)
        if amount > 0:
            action_taken = f"Provisional credit of INR {amount:,.2f} applied"
        else:
            action_taken = "Provisional credit applied (amount will be confirmed after transaction verification)"

    # Update dispute status
    await db_tools["update_dispute_status"].ainvoke({
        "dispute_id": dispute_id,
        "status": DisputeStatus.AUTO_RESOLVED.value,
        "resolution_summary": action_taken,
    })

    await log_audit_event(
        db,
        event_type=AuditEventType.RESOLUTION.value,
        event_description=action_taken,
        dispute_id=uuid.UUID(dispute_id),
        customer_id=uuid.UUID(state["customer_id"]),
        actor_type=ActorType.RULES_ENGINE.value,
        new_state={"resolution_id": res_data.get("resolution_id"), "action": action_taken},
        decision_reason=", ".join(state.get("rule_result", {}).get("reason_codes", [])),
    )

    # Send notification
    extra = json.dumps({
        "category": state.get("dispute_category", "UNKNOWN"),
        "action_taken": action_taken,
    })
    await db_tools["send_notification"].ainvoke({
        "customer_id": state["customer_id"],
        "customer_name": state.get("customer_name", "Customer"),
        "dispute_id": dispute_id,
        "template_name": "auto_resolution",
        "extra_vars": extra,
    })

    # Final audit
    await db_tools["log_audit"].ainvoke({
        "event_type": "WORKFLOW_COMPLETE",
        "description": f"Auto-resolved: {action_taken}",
        "dispute_id": dispute_id,
        "customer_id": state["customer_id"],
    })

    audit_events.append(f"ACTION: {action_taken}")
    audit_events.append("NOTIFY: auto_resolution")
    audit_events.append("AUDIT: workflow complete")

    logger.info("execution_agent_done", action=action_taken)

    return {
        "action_result": {"resolution_id": res_data.get("resolution_id"), "action": action_taken},
        "final_response": f"Your dispute has been resolved. {action_taken}. Reference: {dispute_id[:8]}",
        "audit_events": audit_events,
        "messages": [AIMessage(content=f"[Execution Agent] {action_taken}")],
    }
