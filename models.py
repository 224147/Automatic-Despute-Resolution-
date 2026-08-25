"""Data models for the dispute resolution POC."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class DisputeCase:
    case_id: str
    customer_id: str
    transaction_id: str
    description: str
    amount_usd: Decimal
    status: str = "received"  # received | resolved | escalated


@dataclass
class AgentResult:
    dispute_type: str  # exact_duplicate | merchant_error | suspected_fraud | other | unknown
    confidence: float | None
    rationale: str


@dataclass
class DecisionResult:
    decision: str  # auto_resolve | escalate
    reasons: list[str] = field(default_factory=list)
