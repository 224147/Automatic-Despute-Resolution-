"""Classification Agent — classifies disputes, detects fraud, creates dispute record."""
from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.llm import get_llm
from app.agents.state import DisputeState
from app.core.enums import DisputeCategory, DisputeStatus
from app.core.logging import get_logger

logger = get_logger(__name__)

_CLASSIFICATION_AGENT_PROMPT = """You are a Classification Agent in a banking dispute resolution system.

Your responsibilities:
1. Create the dispute record if it doesn't exist yet
2. Classify the customer's complaint into a dispute category
3. Detect potential fraud indicators
4. Determine the transaction type

You have access to these tools:
- classify_dispute_tool: Classifies the complaint text
- retrieve_policies_tool: Retrieves relevant banking policies via RAG
- create_dispute: Creates a dispute record in the database
- log_audit: Logs audit events

Dispute categories: UPI_FAILED, UPI_PENDING, ATM_CASH_NOT_RECEIVED, UNAUTHORIZED_CARD_TRANSACTION,
CARD_PAYMENT_FAILED, REFUND_NOT_RECEIVED, NEFT_RTGS_IMPS_ISSUE, WRONG_BANK_CHARGE,
LOAN_EMI_DISPUTE, CREDIT_CARD_BILLING_DISPUTE, UNKNOWN

After analyzing, you MUST return a JSON summary of your findings.
"""


async def classification_agent_node(state: DisputeState, db) -> dict:
    """Classify the dispute and create the dispute record."""
    from app.agents.tools import (
    classify_dispute_tool,
    create_db_bound_tools,
    retrieve_policies_tool,
)
    from app.audit.service import log_audit_event
    from app.core.enums import AuditEventType

    logger.info("classification_agent_start", customer_id=state.get("customer_id"))
    audit_events = list(state.get("audit_events", []))
    errors = list(state.get("errors", []))

    customer_id = state.get("customer_id")
    message = state.get("customer_message", "")

    if not customer_id or not message:
        errors.append("Missing customer_id or message")
        return {"errors": errors, "resolution_decision": "ERROR"}

    # Step 1: Create dispute record
    db_tools = create_db_bound_tools(db)
    dispute_result = json.loads(await db_tools["create_dispute"].ainvoke({
        "customer_id": customer_id,
        "customer_message": message,
        "category": DisputeCategory.UNKNOWN.value,
    }))
    dispute_id = dispute_result["dispute_id"]
    audit_events.append(f"INTAKE: Dispute {dispute_id} created")

    # Step 2: Classify using the classification service (LLM + deterministic + RAG)
    classification_json = await classify_dispute_tool.ainvoke({"customer_message": message})
    classification = json.loads(classification_json)

    category = classification.get("dispute_category", DisputeCategory.UNKNOWN.value)
    confidence = classification.get("confidence", 0.0)
    fraud_indicator = classification.get("fraud_indicator", False)
    transaction_type = classification.get("transaction_type")

    # Step 3: Retrieve relevant policies
    query = f"{category} dispute policy"
    policies_json = await retrieve_policies_tool.ainvoke({"query": query})
    policies_data = json.loads(policies_json)

    # Step 4: Log audit
    await log_audit_event(
        db,
        event_type=AuditEventType.CLASSIFICATION.value,
        event_description=f"Classification Agent: {category} (confidence: {confidence})",
        dispute_id=uuid.UUID(dispute_id),
        customer_id=uuid.UUID(customer_id),
        new_state=classification,
    )

    # Step 5: Update dispute record
    from app.tools.banking import update_dispute
    await update_dispute(
        db, uuid.UUID(dispute_id),
        category=category,
        classification_confidence=confidence,
        status=DisputeStatus.UNDER_REVIEW.value,
    )

    # Step 6: LLM reasoning about the classification (optional — works without it)
    reasoning_text = f"Classified as {category} with confidence {confidence}"
    try:
        llm = get_llm()
        reasoning = await llm.ainvoke([
            SystemMessage(content=_CLASSIFICATION_AGENT_PROMPT),
            HumanMessage(content=f"""Customer complaint: "{message}"

Classification result: {classification_json}
Policies found: {policies_data.get('found', False)} ({policies_data.get('chunk_count', 0)} chunks)

Summarize your classification decision and any concerns."""),
        ])
        reasoning_text = reasoning.content
    except Exception as e:
        logger.warning("classification_agent_llm_unavailable", error=str(e))

    audit_events.append(f"CLASSIFY: {category} ({confidence}), fraud={fraud_indicator}")
    audit_events.append(f"POLICY: {'found' if policies_data.get('found') else 'NOT_FOUND'}")

    logger.info("classification_agent_done", category=category, confidence=confidence)

    return {
        "dispute_id": dispute_id,
        "dispute_category": category,
        "transaction_type": transaction_type,
        "classification_confidence": confidence,
        "fraud_indicator": fraud_indicator,
        "retrieved_policies": policies_data.get("chunks", []),
        "policy_found": policies_data.get("found", False),
        "audit_events": audit_events,
        "errors": errors,
        "messages": [AIMessage(content=f"[Classification Agent] {reasoning_text}")],
    }
