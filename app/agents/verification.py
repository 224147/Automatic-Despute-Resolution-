"""Verification Agent — authenticates customer and locates the disputed transaction."""
from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.llm import get_llm
from app.agents.state import DisputeState
from app.core.logging import get_logger

logger = get_logger(__name__)

_VERIFICATION_AGENT_PROMPT = """You are a Verification Agent in a banking dispute resolution system.

Your responsibilities:
1. Verify the customer exists and is active in the system
2. Find the disputed transaction (by reference, amount, or type)
3. Confirm transaction details match the dispute

You have tools to look up customer records and search transactions.
Analyze the results and report whether verification succeeded or failed, and why.
"""


async def verification_agent_node(state: DisputeState, db) -> dict:
    """Verify customer identity and locate the disputed transaction."""
    from app.agents.tools import create_db_bound_tools
    from app.audit.service import log_audit_event
    from app.core.enums import AuditEventType

    logger.info("verification_agent_start", customer_id=state.get("customer_id"))
    audit_events = list(state.get("audit_events", []))

    db_tools = create_db_bound_tools(db)
    customer_id = state["customer_id"]

    # Step 1: Verify customer
    cust_json = await db_tools["lookup_customer"].ainvoke({"customer_id": customer_id})
    cust_data = json.loads(cust_json)
    customer_verified = cust_data.get("found", False) and cust_data.get("active", False)

    await log_audit_event(
        db,
        event_type=AuditEventType.AUTHENTICATION.value,
        event_description=f"Verification Agent: customer {'verified' if customer_verified else 'NOT verified'}",
        customer_id=uuid.UUID(customer_id),
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
    )
    audit_events.append(f"AUTH: {'verified' if customer_verified else 'failed'}")

    # Step 2: Find transaction
    txn_result = {
        "transaction_id": None,
        "transaction_status": None,
        "transaction_amount": state.get("transaction_amount"),
        "transaction_age_days": None,
        "transaction_verified": False,
    }

    # Try by reference first
    txn_ref = state.get("transaction_ref")
    if txn_ref:
        ref_json = await db_tools["lookup_transaction_by_ref"].ainvoke({"transaction_ref": txn_ref})
        ref_data = json.loads(ref_json)
        if ref_data.get("found"):
            txn_result = {
                "transaction_id": ref_data["transaction_id"],
                "transaction_status": ref_data["status"],
                "transaction_amount": ref_data["amount"],
                "transaction_age_days": ref_data["age_days"],
                "transaction_verified": True,
            }
            audit_events.append(f"TXN_FOUND: {ref_data['transaction_id']} via ref")

    # If no ref match, search by amount/type
    if not txn_result["transaction_verified"]:
        search_params = {"customer_id": customer_id}
        if state.get("transaction_amount"):
            search_params["amount"] = str(state["transaction_amount"])
        if state.get("transaction_type"):
            search_params["transaction_type"] = state["transaction_type"]

        search_json = await db_tools["search_customer_transactions"].ainvoke(search_params)
        search_data = json.loads(search_json)
        if search_data.get("count", 0) > 0:
            best = search_data["matches"][0]
            txn_result = {
                "transaction_id": best["transaction_id"],
                "transaction_status": best["status"],
                "transaction_amount": best["amount"],
                "transaction_age_days": best["age_days"],
                "transaction_verified": True,
            }
            audit_events.append(f"TXN_MATCHED: {best['transaction_id']}")
        else:
            audit_events.append("TXN_NOT_FOUND")

    if txn_result["transaction_verified"]:
        await log_audit_event(
            db,
            event_type=AuditEventType.TRANSACTION_LOOKUP.value,
            event_description=f"Verification Agent: transaction {txn_result['transaction_id']} verified",
            dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
            customer_id=uuid.UUID(customer_id),
        )

    # Step 3: Get dispute history
    history_json = await db_tools["get_dispute_history"].ainvoke({"customer_id": customer_id})
    history_data = json.loads(history_json)
    prev_count = history_data.get("dispute_count_90_days", 0)

    # Step 4: LLM reasoning (optional — works without it)
    reasoning_text = (
    f"Customer {'verified' if customer_verified else 'NOT verified'}, "
    f"transaction "
    f"{'found' if txn_result['transaction_verified'] else 'not found'}"
    )
    try:
        llm = get_llm()
        reasoning = await llm.ainvoke([
            SystemMessage(content=_VERIFICATION_AGENT_PROMPT),
            HumanMessage(content=f"""Verification results:
- Customer: {cust_json}
- Transaction found: {txn_result['transaction_verified']}
- Transaction details: {json.dumps(txn_result)}
- Previous disputes (90 days): {prev_count}
- Original complaint: "{state.get('customer_message', '')}"

Summarize verification findings and any concerns."""),
        ])
        reasoning_text = reasoning.content
    except Exception as e:
        logger.warning("verification_agent_llm_unavailable", error=str(e))

    logger.info(
        "verification_agent_done",
        customer_verified=customer_verified,
        txn_verified=txn_result["transaction_verified"],
    )

    return {
        "customer_verified": customer_verified,
        "transaction_id": txn_result["transaction_id"],
        "transaction_status": txn_result["transaction_status"],
        "transaction_amount": txn_result["transaction_amount"],
        "transaction_age_days": txn_result["transaction_age_days"],
        "transaction_verified": txn_result["transaction_verified"],
        "previous_dispute_count": prev_count,
        "audit_events": audit_events,
        "messages": [AIMessage(content=f"[Verification Agent] {reasoning_text}")],
    }
