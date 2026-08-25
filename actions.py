"""Executes the actions that follow a decision. Payments are only ever reached
from issue_provisional_credit, which is only ever called for an auto_resolve decision.
"""
from __future__ import annotations

from typing import Any

from adapters import AnalystQueue, CaseManagement, ExternalAPIError, NotificationService, PaymentsAPI
from models import DisputeCase


class CaseRecordingError(Exception):
    """Raised when the case status can't be durably recorded. The triggering
    action (credit issuance or escalation assignment) must not proceed.
    """


def issue_provisional_credit(
    case: DisputeCase,
    case_mgmt: CaseManagement,
    payments: PaymentsAPI,
    notifications: NotificationService,
) -> str:
    try:
        case_mgmt.update_status(case.case_id, "resolved")
    except ExternalAPIError as exc:
        raise CaseRecordingError(f"could not record resolution for case {case.case_id}") from exc

    payments.issue_provisional_credit(case.case_id, case.amount_usd)
    notifications.notify_customer(case.customer_id, f"Your dispute {case.case_id} has been resolved and credited.")
    return "issue_provisional_credit"


def escalate_to_analyst(
    case: DisputeCase,
    evidence: dict[str, Any],
    rationale: str,
    case_mgmt: CaseManagement,
    analyst_queue: AnalystQueue,
    notifications: NotificationService,
) -> str:
    try:
        case_mgmt.update_status(case.case_id, "escalated")
    except ExternalAPIError as exc:
        raise CaseRecordingError(f"could not record escalation for case {case.case_id}") from exc

    analyst_queue.assign(case.case_id, evidence, rationale)
    notifications.notify_customer(case.customer_id, f"Your dispute {case.case_id} is under review.")
    return "escalate_to_analyst"
