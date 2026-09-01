import os

from database.database import add_audit
from notifications.email import preview_email, send_email
from notifications.sms import mock_send_sms

NOTIFIABLE_EVENTS = {"dispute.created", "complaint.created", "dispute.status.updated", "action.performed"}


def audit_consumer(event: dict):
    """Writes every event to the SQLite audit table — the durable record of what happened."""
    add_audit(
        event["event_id"],
        event["type"],
        event.get("customer_id", ""),
        event.get("session_id", ""),
        event.get("payload", {}),
    )
    return {"handled": True, "consumer": "Audit Consumer", "event_id": event["event_id"]}


def _notification_content(event: dict):
    """Builds the (reference, subject, body) shown in the mock email/SMS
    for each notifiable event type."""
    payload = event.get("payload", {})

    if event["type"] == "action.performed":
        last4 = payload.get("card_last4", "")
        status = payload.get("status", "")
        reference = f"Card ****{last4}"
        return reference, f"{reference} {status.title()}", f"Your card ending {last4} is now {status}."

    reference = payload.get("dispute_id") or payload.get("complaint_id") or ""
    status = payload.get("status", "Submitted")
    subject = f"{reference} Raised" if reference else "Update on your request"
    body = f"Your request has been successfully raised.\n\nTransaction: {payload.get('merchant', '')}\nAmount: ₹{payload.get('amount', 0):,.0f}\nStatus: {status}\nEstimated review: 3–7 business days"
    return reference, subject, body


def notification_consumer(event: dict):
    """Sends mock email + mock SMS. A notification failure never rolls back
    the action that already committed to SQLite/mock banking — this always
    runs after the fact, not inside the action's transaction."""
    if event["type"] not in NOTIFIABLE_EVENTS:
        return {"handled": True, "consumer": "Notification Consumer", "skipped": True}

    reference, subject, body = _notification_content(event)
    email_result = send_email(preview_email(subject, body))
    sms_result = mock_send_sms(os.getenv("DEMO_PHONE", "+91-90000-00000"), f"{reference}: {subject}")
    return {"handled": True, "consumer": "Notification Consumer", "email": email_result, "sms": sms_result}
