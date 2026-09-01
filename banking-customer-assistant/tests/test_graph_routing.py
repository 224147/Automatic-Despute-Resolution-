from graph.workflow import classify_intent, route_decision, run_graph
from security.risk_policy import Risk, risk_for_intent, route_for_intent


def test_intent_to_risk_and_route_mapping():
    cases = {
        "balance": (Risk.READ, "Account Agent"),
        "transaction_investigation": (Risk.SENSITIVE_READ, "Dispute Agent"),
        "block_card": (Risk.REVERSIBLE_ACTION, "Card Agent"),
        "money_transfer": (Risk.IRREVERSIBLE_ACTION, "Fallback / Escalation"),
    }
    for intent, (expected_risk, expected_route) in cases.items():
        assert risk_for_intent(intent) == expected_risk
        assert route_for_intent(intent) == expected_route


def test_classify_intent_keyword_matching():
    assert classify_intent("What's my balance?") == "balance"
    assert classify_intent("Block my card ending 1234") == "block_card"
    assert classify_intent("I don't recognize this transaction") == "transaction_investigation"
    assert classify_intent("Transfer 5000 to Rahul") == "money_transfer"


def test_route_decision_dispute_branches_on_intent():
    assert route_decision({"route": "Dispute Agent", "intent": "dispute_status"}) == "dispute_status"
    assert route_decision({"route": "Dispute Agent", "intent": "transaction_investigation"}) == "dispute_investigate"


def test_full_graph_run_for_balance():
    result = run_graph("What's my balance?", "CUST001")
    assert result["intent"] == "balance"
    assert result["risk"] == "READ"
    assert result["agent"] == "Account Agent"
    assert result["guardrail"] == "PASSED"


def test_full_graph_refuses_money_transfer():
    result = run_graph("Transfer 50000 to Rahul", "CUST001")
    assert result["risk"] == "IRREVERSIBLE_ACTION"
    assert result["agent"] == "Fallback / Escalation"
    assert "can't perform money transfers" in result["response"]
