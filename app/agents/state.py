"""Shared state definition for the multi-agent dispute resolution system."""
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


def _replace_list(left: list, right: list) -> list:
    """Reducer: replace the list entirely with the new value."""
    return right


class DisputeState(TypedDict, total=False):
    # Core identifiers
    customer_id: str
    dispute_id: str
    customer_message: str
    customer_name: str

    # Classification
    dispute_category: str
    transaction_type: str | None
    classification_confidence: float
    fraud_indicator: bool

    # Transaction
    transaction_id: str | None
    transaction_ref: str | None
    transaction_status: str | None
    transaction_amount: float | None
    transaction_age_days: int | None

    # Verification
    customer_verified: bool
    transaction_verified: bool

    # Policy & Rules
    retrieved_policies: list[dict]
    policy_found: bool
    rule_result: dict
    risk_result: dict

    # Decision
    resolution_decision: str
    action_result: dict
    escalation_required: bool
    escalation_reason: str | None

    # Output
    final_response: str
    errors: list[str]
    audit_events: list[str]

    # History
    previous_dispute_count: int

    # Agent messages (for LLM-powered agents)
    messages: Annotated[list[BaseMessage], add_messages]

    # Supervisor routing
    next_agent: str
