from decimal import Decimal

import pytest

from dispute_rules import evaluate_decision
from models import AgentResult, DisputeCase

CONFIG = {"AUTO_RESOLVE_MAX_USD": 50, "MIN_CONFIDENCE": 0.90, "ELIGIBLE_TYPES": ["exact_duplicate"]}


def make_case(amount_usd) -> DisputeCase:
    return DisputeCase(
        case_id="DISP-1",
        customer_id="CUST-1",
        transaction_id="TXN-1",
        description="test",
        amount_usd=Decimal(str(amount_usd)),
    )


def test_exact_duplicate_within_limits_auto_resolves():
    case = make_case(50)
    result = AgentResult(dispute_type="exact_duplicate", confidence=0.95, rationale="matches prior charge")
    decision = evaluate_decision(case, result, CONFIG)
    assert decision.decision == "auto_resolve"
    assert decision.reasons == []


def test_amount_over_threshold_escalates():
    case = make_case(50.01)
    result = AgentResult(dispute_type="exact_duplicate", confidence=0.95, rationale="matches prior charge")
    decision = evaluate_decision(case, result, CONFIG)
    assert decision.decision == "escalate"
    assert decision.reasons


def test_confidence_below_minimum_escalates():
    case = make_case(50)
    result = AgentResult(dispute_type="exact_duplicate", confidence=0.89, rationale="matches prior charge")
    decision = evaluate_decision(case, result, CONFIG)
    assert decision.decision == "escalate"


@pytest.mark.parametrize("dispute_type", ["merchant_error", "suspected_fraud", "other", "unknown"])
def test_non_eligible_types_escalate(dispute_type):
    case = make_case(10)
    result = AgentResult(dispute_type=dispute_type, confidence=0.99, rationale="x")
    decision = evaluate_decision(case, result, CONFIG)
    assert decision.decision == "escalate"


def test_missing_confidence_escalates():
    case = make_case(10)
    result = AgentResult(dispute_type="exact_duplicate", confidence=None, rationale="x")
    decision = evaluate_decision(case, result, CONFIG)
    assert decision.decision == "escalate"


def test_invalid_confidence_range_escalates():
    case = make_case(10)
    result = AgentResult(dispute_type="exact_duplicate", confidence=1.5, rationale="x")
    decision = evaluate_decision(case, result, CONFIG)
    assert decision.decision == "escalate"
