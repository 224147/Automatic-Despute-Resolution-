from mock_banking.data import get_account, get_transactions

def account_summary(customer_id): return get_account(customer_id)
def transactions(customer_id): return get_transactions(customer_id)


def answer_transaction_followup(message: str, context: dict | None):
    """Deterministic answers about transactions already shown this
    conversation (e.g. "which one was the biggest?", "when did that
    happen?"). Returns None if this message isn't a recognizable
    follow-up, or if there's no transaction context to answer from —
    callers should fall back to normal intent classification in that case.
    """
    if not context:
        return None
    last_transactions = context.get("last_transactions")
    if not last_transactions:
        return None

    t = message.lower()

    if any(phrase in t for phrase in ["biggest", "largest", "highest"]):
        txn = max(last_transactions, key=lambda x: x["amount"])
        return f"The {txn['merchant']} transaction for ₹{txn['amount']:,} was the largest.", {"last_transactions": last_transactions, "selected_transaction": txn}

    if any(phrase in t for phrase in ["smallest", "lowest", "cheapest"]):
        txn = min(last_transactions, key=lambda x: x["amount"])
        return f"The {txn['merchant']} transaction for ₹{txn['amount']:,} was the smallest.", {"last_transactions": last_transactions, "selected_transaction": txn}

    selected = context.get("selected_transaction")
    if any(phrase in t for phrase in ["when did", "when was", "what date", "what day"]):
        if not selected:
            return None
        return f"It happened on {selected['date']}.", {"last_transactions": last_transactions, "selected_transaction": selected}

    if any(phrase in t for phrase in ["how much was", "how much did", "what was the amount"]):
        if not selected:
            return None
        return f"It was ₹{selected['amount']:,}.", {"last_transactions": last_transactions, "selected_transaction": selected}

    return None
