from agents import dispute_agent
from mock_banking.data import get_transaction


def test_lookup_no_match():
    result = dispute_agent.lookup("CUST001", 99999)
    assert result["matches"] == []


def test_lookup_single_match():
    result = dispute_agent.lookup("CUST001", 4999)
    assert len(result["matches"]) == 1
    assert result["matches"][0]["id"] == "TXN982341"


def test_create_dispute_generates_id_and_status():
    txn = get_transaction("CUST001", "TXN982341")
    result = dispute_agent.create("CUST001", txn, "I don't recognize this charge")
    assert result["status"] == "SUBMITTED"
    assert result["id"].startswith("DSP-")
    assert result["idempotency_result"] == "CREATED"
    assert result["estimated_resolution"] == "3-7 business days"


def test_repeat_dispute_request_is_idempotent():
    txn = get_transaction("CUST001", "TXN982341")
    first = dispute_agent.create("CUST001", txn, "I don't recognize this charge")
    second = dispute_agent.create("CUST001", txn, "I don't recognize this charge")
    assert first["id"] == second["id"]
    assert second["idempotency_result"] == "REPLAYED"


def test_already_disputed_transaction_is_flagged():
    txn = get_transaction("CUST001", "TXN982341")
    dispute_agent.create("CUST001", txn, "First report")
    result = dispute_agent.create("CUST001", txn, "Different wording, same transaction")
    assert result["idempotency_result"] in ("REPLAYED", "ALREADY_DISPUTED")


def test_dispute_status_lists_created_disputes():
    txn = get_transaction("CUST001", "TXN982341")
    created = dispute_agent.create("CUST001", txn, "Unrecognized")
    disputes = dispute_agent.status("CUST001")
    assert any(d["id"] == created["id"] for d in disputes)
