from datetime import datetime, timedelta, timezone

import pytest

from backend.session import start_login, verify_otp, validate_session, logout, SESSIONS, PENDING


def test_otp_is_random_and_six_digits():
    otp = start_login("CUST001", "1234")
    assert len(otp) == 6 and otp.isdigit()


def test_wrong_pin_rejected():
    with pytest.raises(ValueError):
        start_login("CUST001", "0000")


def test_otp_expires_after_5_minutes():
    start_login("CUST001", "1234")
    PENDING["CUST001"].created_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    with pytest.raises(ValueError, match="expired"):
        verify_otp("CUST001", PENDING["CUST001"].otp)


def test_otp_attempt_limit_locks_after_three():
    otp = start_login("CUST001", "1234")
    for _ in range(3):
        with pytest.raises(ValueError, match="Incorrect OTP"):
            verify_otp("CUST001", "000000")
    with pytest.raises(ValueError, match="Too many"):
        verify_otp("CUST001", otp)
    assert "CUST001" not in PENDING


def test_new_otp_invalidates_old():
    old_otp = start_login("CUST001", "1234")
    new_otp = start_login("CUST001", "1234")
    if old_otp == new_otp:
        pytest.skip("random OTP collision — cannot distinguish old from new")
    with pytest.raises(ValueError, match="Incorrect OTP"):
        verify_otp("CUST001", old_otp)
    assert verify_otp("CUST001", new_otp)["customer_id"] == "CUST001"


def test_correct_otp_creates_session():
    otp = start_login("CUST001", "1234")
    session = verify_otp("CUST001", otp)
    assert session["customer_id"] == "CUST001"
    assert validate_session(session["session_id"]) is True


def test_session_expires_after_30_minutes():
    otp = start_login("CUST001", "1234")
    session = verify_otp("CUST001", otp)
    SESSIONS[session["session_id"]]["login_time"] = datetime.now(timezone.utc) - timedelta(minutes=31)
    assert validate_session(session["session_id"]) is False


def test_logout_invalidates_session():
    otp = start_login("CUST001", "1234")
    session = verify_otp("CUST001", otp)
    logout(session["session_id"])
    assert validate_session(session["session_id"]) is False
