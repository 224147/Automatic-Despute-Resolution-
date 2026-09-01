import re

"""Deterministic slot extraction — regex only, never an LLM.

These values are hints for lookup; ownership/authorization is always
re-verified server-side against the session's customer_id regardless of
what is extracted here.
"""


def extract_last4(text: str):
    match = re.search(r"\b(\d{4})\b", text)
    return match.group(1) if match else None


def extract_amount(text: str):
    match = re.search(r"₹\s?([\d,]+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def extract_transaction_id(text: str):
    match = re.search(r"\bTXN\d+\b", text, re.IGNORECASE)
    return match.group(0).upper() if match else None
