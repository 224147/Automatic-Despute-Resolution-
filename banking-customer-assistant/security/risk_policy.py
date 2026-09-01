from enum import Enum


class Risk(str, Enum):
    READ = "READ"
    SENSITIVE_READ = "SENSITIVE_READ"
    REVERSIBLE_ACTION = "REVERSIBLE_ACTION"
    IRREVERSIBLE_ACTION = "IRREVERSIBLE_ACTION"

READ_INTENTS = {"balance", "transactions", "loan", "policy", "cards"}
SENSITIVE_INTENTS = {"transaction_investigation", "card_details", "dispute_status", "loan_details", "card_active_check"}
REVERSIBLE_INTENTS = {"block_card", "unblock_card", "raise_dispute", "raise_complaint", "replacement"}


def risk_for_intent(intent: str) -> Risk:
    if intent in READ_INTENTS:
        return Risk.READ
    if intent in SENSITIVE_INTENTS:
        return Risk.SENSITIVE_READ
    if intent in REVERSIBLE_INTENTS:
        return Risk.REVERSIBLE_ACTION
    if intent in {"money_transfer", "change_pin", "change_mobile", "close_account", "add_beneficiary"}:
        return Risk.IRREVERSIBLE_ACTION
    return Risk.SENSITIVE_READ


def requires_confirmation(risk: Risk) -> bool:
    return risk == Risk.REVERSIBLE_ACTION


def route_for_intent(intent: str) -> str:
    return {"balance": "Account Agent", "transactions": "Account Agent", "loan": "Loan Agent", "policy": "RAG Agent", "cards": "Card Agent", "card_active_check": "Card Agent", "transaction_investigation": "Dispute Agent", "dispute_status": "Dispute Agent", "block_card": "Card Agent", "unblock_card": "Card Agent", "raise_dispute": "Dispute Agent", "raise_complaint": "Complaint Agent"}.get(intent, "Fallback / Escalation")
