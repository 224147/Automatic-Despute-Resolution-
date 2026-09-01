import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from mock_banking.data import get_customer


@dataclass
class PendingOTP:
    customer_id: str
    otp: str
    created_at: datetime
    attempts: int = 0

SESSIONS = {}
PENDING = {}


def start_login(customer_id: str, pin: str):
    customer = get_customer(customer_id)
    if not customer or customer["pin"] != pin:
        raise ValueError("Invalid Customer ID or PIN")
    otp = f"{secrets.randbelow(1_000_000):06d}"
    PENDING[customer_id] = PendingOTP(customer_id, otp, datetime.now(timezone.utc))
    return otp


def verify_otp(customer_id: str, otp: str):
    pending = PENDING.get(customer_id)
    if not pending or datetime.now(timezone.utc) - pending.created_at > timedelta(minutes=5):
        raise ValueError("OTP expired. Please request a new OTP.")
    pending.attempts += 1
    if pending.attempts > 3:
        del PENDING[customer_id]
        raise ValueError("Too many OTP attempts. Please request a new OTP.")
    if pending.otp != otp:
        raise ValueError("Incorrect OTP")
    session_id = secrets.token_urlsafe(16)
    SESSIONS[session_id] = {"session_id": session_id, "customer_id": customer_id, "authenticated": True, "login_time": datetime.now(timezone.utc)}
    del PENDING[customer_id]
    return SESSIONS[session_id]


def validate_session(session_id: str, customer_id: str | None = None):
    session = SESSIONS.get(session_id)
    if not session or not session["authenticated"] or datetime.now(timezone.utc) - session["login_time"] > timedelta(minutes=30):
        return False
    return customer_id is None or session["customer_id"] == customer_id


def logout(session_id: str):
    SESSIONS.pop(session_id, None)
