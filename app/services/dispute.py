"""Dispute resolution orchestrator – runs the LangGraph workflow."""
from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.tools.banking import get_customer
from app.workflows.graph import build_dispute_graph
from app.workflows.nodes import DisputeState

logger = get_logger(__name__)


def _extract_amount(message: str) -> float | None:
    """Try to extract a monetary amount from the customer message."""
    patterns = [
        r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d+)?)",
        r"([\d,]+(?:\.\d+)?)\s*(?:rupees|rupay|rs|inr)",
        r"(?:amount|sum|value)\s*(?:of|is|was)?\s*(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d+)?)",
        r"([\d,]+(?:\.\d+)?)\s*(?:was|got|been)\s*(?:debit|deduct|charge)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                val = match.group(match.lastindex).replace(",", "")
                amount = float(val)
                if amount > 0:
                    return amount
            except (ValueError, IndexError):
                continue
    # Fallback: find any number >= 100 that looks like a monetary value
    numbers = re.findall(r"\b([\d,]+(?:\.\d+)?)\b", message)
    for n in numbers:
        try:
            val = float(n.replace(",", ""))
            if val >= 100:
                return val
        except ValueError:
            continue
    return None


async def run_dispute_workflow(
    db: AsyncSession,
    customer_id: uuid.UUID,
    customer_message: str,
    transaction_ref: str | None = None,
) -> dict:
    """Run the full dispute resolution workflow."""

    customer = await get_customer(db, customer_id)
    if not customer:
        return {
            "success": False,
            "error": "Customer not found",
            "final_response": "We could not find your customer record. Please contact support.",
        }

    amount = _extract_amount(customer_message)

    initial_state: DisputeState = {
        "customer_id": str(customer_id),
        "customer_message": customer_message,
        "customer_name": f"{customer.first_name} {customer.last_name}",
        "transaction_ref": transaction_ref,
        "transaction_amount": amount,
        "customer_verified": False,
        "transaction_verified": False,
        "fraud_indicator": False,
        "classification_confidence": 0.0,
        "policy_found": False,
        "escalation_required": False,
        "errors": [],
        "audit_events": [],
        "previous_dispute_count": 0,
        "retrieved_policies": [],
    }

    graph = build_dispute_graph(db)

    logger.info("workflow_start", customer_id=str(customer_id))
    final_state = await graph.ainvoke(initial_state)
    logger.info(
        "workflow_complete",
        customer_id=str(customer_id),
        dispute_id=final_state.get("dispute_id"),
        decision=final_state.get("resolution_decision"),
    )

    return {
        "success": True,
        "dispute_id": final_state.get("dispute_id"),
        "category": final_state.get("dispute_category"),
        "status": "AUTO_RESOLVED" if final_state.get("resolution_decision") == "AUTO_RESOLVE" else "ESCALATED",
        "risk_level": final_state.get("risk_result", {}).get("risk_level"),
        "final_response": final_state.get("final_response", "Your dispute is being processed."),
        "errors": final_state.get("errors", []),
    }
