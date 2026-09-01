from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def login(customer_id, pin):
    otp = client.post("/auth/login", json={"customer_id": customer_id, "pin": pin}).json()["demo_otp"]
    session = client.post("/auth/verify", json={"customer_id": customer_id, "otp": otp}).json()
    return session["session_id"]


def test_balance_requires_session_header():
    response = client.get("/me/balance")
    assert response.status_code == 422  # missing required header


def test_invalid_session_rejected():
    response = client.get("/me/balance", headers={"X-Session-Id": "not-a-real-session"})
    assert response.status_code == 401


def test_balance_reflects_own_session_only():
    session_id = login("CUST001", "1234")
    response = client.get("/me/balance", headers={"X-Session-Id": session_id})
    assert response.status_code == 200
    assert response.json()["balance"] == 75420.50


def test_cannot_block_another_customers_card():
    """CUST002's session must not be able to block CUST001's card (4321)."""
    session_id = login("CUST002", "2345")
    response = client.post("/cards/block", json={"last4": "4321"}, headers={"X-Session-Id": session_id})
    assert response.status_code == 404


def test_owner_can_block_own_card():
    session_id = login("CUST001", "1234")
    response = client.post("/cards/block", json={"last4": "4321"}, headers={"X-Session-Id": session_id})
    assert response.status_code == 200
    assert response.json()["status"] == "BLOCKED"
