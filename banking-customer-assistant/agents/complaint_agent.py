import hashlib
from datetime import datetime, timezone

from database.database import (
    create_complaint,
    find_idempotent,
    get_complaint,
    save_idempotency,
)
from events.dispatch import dispatch


def create(customer_id, description, session_id=""):
    """Idempotent complaint creation — an identical repeated description
    for the same customer returns the original complaint."""
    fingerprint = hashlib.sha1(description.strip().lower().encode()).hexdigest()[:12]
    idempotency_key = f"{customer_id}-{fingerprint}-COMPLAINT"

    existing_key = find_idempotent(idempotency_key)
    if existing_key:
        return {**get_complaint(existing_key["record_id"]), "idempotency_result": "REPLAYED"}

    complaint_id = f"CMP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{fingerprint[:6].upper()}"
    complaint = {
        "id": complaint_id,
        "customer_id": customer_id,
        "description": description,
        "status": "SUBMITTED",
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    create_complaint(complaint)
    save_idempotency(idempotency_key, complaint_id, "complaint")

    events = dispatch("complaint.created", {"complaint_id": complaint_id, "status": "SUBMITTED"}, customer_id, session_id)

    return {**complaint, "idempotency_result": "CREATED", "events": events}
