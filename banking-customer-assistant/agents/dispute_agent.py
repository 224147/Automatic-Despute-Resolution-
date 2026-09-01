from datetime import datetime, timezone

from database.database import (
    create_dispute,
    find_dispute_by_transaction,
    find_idempotent,
    get_dispute,
    list_disputes,
    next_dispute_id,
    save_idempotency,
)
from events.dispatch import dispatch
from mock_banking.data import match_transactions

ESTIMATED_RESOLUTION = "3-7 business days"


def status(customer_id):
    return list_disputes(customer_id)


def by_id(dispute_id):
    return get_dispute(dispute_id)


def by_transaction(customer_id, transaction_id):
    return find_dispute_by_transaction(customer_id, transaction_id)


def lookup(customer_id, amount):
    if amount is None:
        return {"matches": []}
    return {"matches": match_transactions(customer_id, amount)}


def create(customer_id, transaction, issue, session_id=""):
    """Idempotent dispute creation.

    Repeating the exact same (customer, transaction) dispute request returns
    the original dispute instead of creating a second one.
    """
    idempotency_key = f"{customer_id}-{transaction['id']}-DISPUTE"

    existing_key = find_idempotent(idempotency_key)
    if existing_key:
        return {**get_dispute(existing_key["record_id"]), "idempotency_result": "REPLAYED", "estimated_resolution": ESTIMATED_RESOLUTION}

    existing_dispute = find_dispute_by_transaction(customer_id, transaction["id"])
    if existing_dispute:
        return {**existing_dispute, "idempotency_result": "ALREADY_DISPUTED", "estimated_resolution": ESTIMATED_RESOLUTION}

    dispute_id = next_dispute_id()
    dispute = {
        "id": dispute_id,
        "customer_id": customer_id,
        "transaction_id": transaction["id"],
        "amount": transaction["amount"],
        "merchant": transaction["merchant"],
        "status": "SUBMITTED",
        "issue": issue,
        "idempotency_key": idempotency_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    create_dispute(dispute)
    save_idempotency(idempotency_key, dispute_id, "dispute")

    events = dispatch(
        "dispute.created",
        {"dispute_id": dispute_id, "merchant": transaction["merchant"], "amount": transaction["amount"], "status": "SUBMITTED"},
        customer_id,
        session_id,
    )

    return {**dispute, "idempotency_result": "CREATED", "estimated_resolution": ESTIMATED_RESOLUTION, "events": events}
