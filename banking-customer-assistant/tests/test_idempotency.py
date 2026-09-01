from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def login(customer_id, pin):
    otp = client.post("/auth/login", json={"customer_id": customer_id, "pin": pin}).json()["demo_otp"]
    session = client.post("/auth/verify", json={"customer_id": customer_id, "otp": otp}).json()
    return session["session_id"]


def test_repeat_card_block_is_idempotent_not_duplicated():
    session_id = login("CUST001", "1234")
    first = client.post("/cards/block", json={"last4": "4321"}, headers={"X-Session-Id": session_id}).json()
    second = client.post("/cards/block", json={"last4": "4321"}, headers={"X-Session-Id": session_id}).json()
    assert first["idempotency_result"] == "CREATED"
    assert second["idempotency_result"] == "REPLAYED"
    assert first["status"] == second["status"] == "BLOCKED"


def test_card_already_blocked_edge_case():
    session_id = login("CUST001", "1234")
    client.post("/cards/block", json={"last4": "4321"}, headers={"X-Session-Id": session_id})
    response = client.post("/chat", json={"message": "block my card ending 4321"}, headers={"X-Session-Id": session_id})
    body = response.json()
    assert body["current_step"] == "Already Blocked"


def test_expired_card_cannot_be_blocked():
    session_id = login("CUST002", "2345")
    response = client.post("/chat", json={"message": "please block card 9999"}, headers={"X-Session-Id": session_id})
    assert response.json()["current_step"] == "Card Expired"


def test_card_not_found_for_unknown_last4():
    session_id = login("CUST001", "1234")
    response = client.post("/chat", json={"message": "block card 0000"}, headers={"X-Session-Id": session_id})
    assert response.json()["current_step"] == "Card Not Found"
