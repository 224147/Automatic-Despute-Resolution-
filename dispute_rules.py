"""Deterministic dispute decision engine. No external calls, no LLM calls.

Claude classifies; this module is the only thing that decides whether money moves.
"""
from __future__ import annotations

from models import AgentResult, DecisionResult, DisputeCase


def evaluate_decision(case: DisputeCase, agent_result: AgentResult, config: dict) -> DecisionResult:
    reasons: list[str] = []

    eligible_types = config["ELIGIBLE_TYPES"]
    max_usd = config["AUTO_RESOLVE_MAX_USD"]
    min_confidence = config["MIN_CONFIDENCE"]

    if agent_result.dispute_type not in eligible_types:
        reasons.append(
            f"dispute_type '{agent_result.dispute_type}' is not auto-eligible "
            f"(eligible types: {eligible_types})"
        )

    if case.amount_usd > max_usd:
        reasons.append(f"amount_usd {case.amount_usd} exceeds AUTO_RESOLVE_MAX_USD {max_usd}")

    if agent_result.confidence is None or not (0.0 <= agent_result.confidence <= 1.0):
        reasons.append("confidence is missing or invalid")
    elif agent_result.confidence < min_confidence:
        reasons.append(f"confidence {agent_result.confidence} is below MIN_CONFIDENCE {min_confidence}")

    decision = "escalate" if reasons else "auto_resolve"
    return DecisionResult(decision=decision, reasons=reasons)
