import os


def mock_send_sms(phone: str, message: str):
    """SMS is always mocked — no real SMS/OTP provider integration."""
    status = "FAILED" if os.getenv("DEMO_SMS_FAILURE", "false").lower() == "true" else "QUEUED"
    return {"status": status, "to": phone, "message": message}
