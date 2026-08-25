"""Integrations with external/existing systems. Business rules never live here."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from models import DisputeCase


class ExternalAPIError(Exception):
    """Raised when a read-only evidence source or system integration fails."""


def with_retry(fn, *args, **kwargs):
    """Call fn once, retry once on ExternalAPIError, then propagate."""
    try:
        return fn(*args, **kwargs)
    except ExternalAPIError:
        return fn(*args, **kwargs)


class TransactionAPI:
    """Read-only evidence source for transaction data."""

    def __init__(self, transactions: dict[str, dict[str, Any]] | None = None):
        self._transactions = transactions if transactions is not None else {}

    def _fetch(self, transaction_id: str) -> dict[str, Any]:
        record = self._transactions.get(transaction_id)
        if record is None:
            raise ExternalAPIError(f"transaction {transaction_id} not found")
        return record

    def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        return with_retry(self._fetch, transaction_id)

    def has_transaction(self, transaction_id: str) -> bool:
        return transaction_id in self._transactions


class MerchantAPI:
    """Read-only evidence source for merchant data."""

    def __init__(self, merchants: dict[str, dict[str, Any]] | None = None):
        self._merchants = merchants if merchants is not None else {}

    def _fetch(self, merchant_id: str) -> dict[str, Any]:
        record = self._merchants.get(merchant_id)
        if record is None:
            raise ExternalAPIError(f"merchant {merchant_id} not found")
        return record

    def get_merchant(self, merchant_id: str) -> dict[str, Any]:
        return with_retry(self._fetch, merchant_id)


class CaseManagement:
    """Tracks dispute cases. In-memory for the POC."""

    def __init__(self):
        self._cases: dict[str, DisputeCase] = {}

    def find_open_case_for_transaction(self, customer_id: str, transaction_id: str) -> DisputeCase | None:
        for case in self._cases.values():
            if (
                case.customer_id == customer_id
                and case.transaction_id == transaction_id
                and case.status != "resolved"
            ):
                return case
        return None

    def create_case(
        self, customer_id: str, transaction_id: str, description: str, amount_usd: Decimal
    ) -> tuple[DisputeCase, bool]:
        """Returns (case, is_new). is_new is False when an existing open case for
        this (customer_id, transaction_id) pair was reused instead of created —
        callers should surface that to the caller/user rather than hide it, since
        the reused case keeps its original amount/description, not the new ones.
        """
        existing = self.find_open_case_for_transaction(customer_id, transaction_id)
        if existing is not None:
            return existing, False

        case = DisputeCase(
            case_id=f"DISP-{uuid.uuid4().hex[:8]}",
            customer_id=customer_id,
            transaction_id=transaction_id,
            description=description,
            amount_usd=amount_usd,
            status="received",
        )
        self._cases[case.case_id] = case
        return case, True

    def _update_status(self, case_id: str, status: str) -> DisputeCase:
        case = self._cases.get(case_id)
        if case is None:
            raise ExternalAPIError(f"case {case_id} not found")
        case.status = status
        return case

    def update_status(self, case_id: str, status: str) -> DisputeCase:
        return with_retry(self._update_status, case_id, status)


class PaymentsAPI:
    """Payments/Ledger integration. Only ever called after auto_resolve is decided."""

    def __init__(self):
        self.issued_credits: list[dict[str, Any]] = []

    def _issue(self, case_id: str, amount_usd: Decimal) -> dict[str, Any]:
        credit = {"case_id": case_id, "amount_usd": amount_usd, "credit_id": f"CR-{uuid.uuid4().hex[:8]}"}
        self.issued_credits.append(credit)
        return credit

    def issue_provisional_credit(self, case_id: str, amount_usd: Decimal) -> dict[str, Any]:
        return with_retry(self._issue, case_id, amount_usd)


class NotificationService:
    def __init__(self):
        self.sent: list[dict[str, str]] = []

    def notify_customer(self, customer_id: str, message: str) -> None:
        self.sent.append({"customer_id": customer_id, "message": message})


class AnalystQueue:
    """Human Analyst Review Queue."""

    def __init__(self):
        self.assigned: list[dict[str, Any]] = []

    def assign(self, case_id: str, evidence: dict[str, Any], rationale: str) -> None:
        self.assigned.append({"case_id": case_id, "evidence": evidence, "rationale": rationale})
