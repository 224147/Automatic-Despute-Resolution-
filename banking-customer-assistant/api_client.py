import os

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# A persistent client reuses one connection instead of opening a fresh
# TCP connection for every call — each Streamlit rerun makes several of
# these calls, so this avoids repeated connection setup overhead.
_client = httpx.Client(base_url=BASE_URL, timeout=30)


def _raise_for_status(response: httpx.Response):
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise ValueError(detail)


def _headers(session_id: str) -> dict:
    return {"X-Session-Id": session_id}


def login(customer_id: str, pin: str) -> str:
    response = _client.post("/auth/login", json={"customer_id": customer_id, "pin": pin})
    _raise_for_status(response)
    return response.json()["demo_otp"]


def verify_otp(customer_id: str, otp: str) -> dict:
    response = _client.post("/auth/verify", json={"customer_id": customer_id, "otp": otp})
    _raise_for_status(response)
    return response.json()


def logout(session_id: str):
    _client.post("/auth/logout", headers=_headers(session_id))


def profile(session_id: str) -> dict:
    response = _client.get("/me/profile", headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def balance(session_id: str) -> dict:
    response = _client.get("/me/balance", headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def transactions(session_id: str) -> list:
    response = _client.get("/me/transactions", headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def cards(session_id: str) -> list:
    response = _client.get("/me/cards", headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def loan(session_id: str) -> dict:
    response = _client.get("/me/loan", headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def block_card(session_id: str, last4: str) -> dict:
    response = _client.post("/cards/block", json={"last4": last4}, headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def unblock_card(session_id: str, last4: str) -> dict:
    response = _client.post("/cards/unblock", json={"last4": last4}, headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def list_disputes(session_id: str) -> list:
    response = _client.get("/disputes", headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def create_dispute(session_id: str, transaction_id: str, issue: str) -> dict:
    response = _client.post("/disputes", json={"transaction_id": transaction_id, "issue": issue}, headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def create_complaint(session_id: str, description: str) -> dict:
    response = _client.post("/complaints", json={"description": description}, headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()


def chat(session_id: str, message: str, pending: dict | None = None, context: dict | None = None) -> dict:
    response = _client.post("/chat", json={"message": message, "pending": pending, "context": context}, headers=_headers(session_id))
    _raise_for_status(response)
    return response.json()
