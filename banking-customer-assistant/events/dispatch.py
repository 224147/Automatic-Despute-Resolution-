import uuid

from events.consumers import audit_consumer, notification_consumer
from events.publisher import publish


def dispatch(event_type: str, payload: dict, customer_id: str, session_id: str = ""):
    """Publish an event; if RabbitMQ is disabled or unreachable, run the
    audit/notification consumers directly in-process so the demo still works
    with zero broker setup. When a broker is up, `events/consumer_runner.py`
    picks the message up for real instead."""
    event = {
        "event_id": str(uuid.uuid4()),
        "type": event_type,
        "customer_id": customer_id,
        "session_id": session_id,
        "payload": payload,
    }
    published = publish(event_type, event)
    result = {"event_id": event["event_id"], "type": event_type, "published": published}
    if not published:
        result["audit"] = audit_consumer(event)
        result["notification"] = notification_consumer(event)
    return result
