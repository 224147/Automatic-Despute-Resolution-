from fastapi.testclient import TestClient

from backend.main import app
from database.database import save_idempotency
from mock_banking.data import block_card, card_for_customer, get_cards
from security.risk_policy import Risk, risk_for_intent

client = TestClient(app)


def login(customer_id, pin):
    otp = client.post("/auth/login", json={"customer_id": customer_id, "pin": pin}).json()["demo_otp"]
    session = client.post("/auth/verify", json={"customer_id": customer_id, "otp": otp}).json()
    return session["session_id"]


def test_customer_owns_card():
    assert card_for_customer("CUST001", "4321")[0] == "CARD4321"

def test_risk_policy_is_deterministic():
    assert risk_for_intent("block_card") == Risk.REVERSIBLE_ACTION
    assert risk_for_intent("money_transfer") == Risk.IRREVERSIBLE_ACTION

def test_card_state_persists():
    block_card("CARD4321")
    assert get_cards("CUST001")[0]["status"] == "BLOCKED"


def test_block_then_unblock_via_api_reflects_in_subsequent_lookups():
    """The mock banking API is the source of truth: a block must actually
    change status, and every following GET must see it — not a cached or
    stale value."""
    session_id = login("CUST001", "1234")
    headers = {"X-Session-Id": session_id}

    before = client.get("/me/cards", headers=headers).json()
    assert next(c for c in before if c["last4"] == "4321")["status"] == "ACTIVE"

    client.post("/cards/block", json={"last4": "4321"}, headers=headers)
    after_block = client.get("/me/cards", headers=headers).json()
    assert next(c for c in after_block if c["last4"] == "4321")["status"] == "BLOCKED"

    client.post("/cards/unblock", json={"last4": "4321"}, headers=headers)
    after_unblock = client.get("/me/cards", headers=headers).json()
    assert next(c for c in after_unblock if c["last4"] == "4321")["status"] == "ACTIVE"


def test_stale_idempotency_record_does_not_hide_a_real_state_change():
    """Regression test for a real bug: the idempotency ledger (SQLite) can
    outlive the in-memory mock card data (e.g. across a backend restart in
    dev). If a BLOCK idempotency record exists but the card is actually
    still ACTIVE, the endpoint must still perform the real mutation instead
    of blindly replaying a canned 'BLOCKED' response."""
    session_id = login("CUST001", "1234")
    headers = {"X-Session-Id": session_id}

    assert card_for_customer("CUST001", "4321")[1]["status"] == "ACTIVE"
    save_idempotency("CUST001-CARD4321-BLOCK", "CARD4321", "card_block")  # stale record, no real mutation

    response = client.post("/cards/block", json={"last4": "4321"}, headers=headers)
    assert response.json()["status"] == "BLOCKED"

    current = client.get("/me/cards", headers=headers).json()
    assert next(c for c in current if c["last4"] == "4321")["status"] == "BLOCKED"


def test_block_already_blocked_card_is_a_safe_no_op():
    session_id = login("CUST001", "1234")
    headers = {"X-Session-Id": session_id}

    first = client.post("/cards/block", json={"last4": "4321"}, headers=headers).json()
    second = client.post("/cards/block", json={"last4": "4321"}, headers=headers).json()

    assert first["idempotency_result"] == "CREATED"
    assert second["idempotency_result"] == "REPLAYED"
    assert first["status"] == second["status"] == "BLOCKED"
    assert get_cards("CUST001")[0]["status"] == "BLOCKED"
