"""Entry point. Orchestrates the end-to-end dispute flow."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from actions import CaseRecordingError, escalate_to_analyst, issue_provisional_credit
from adapters import (
    AnalystQueue,
    CaseManagement,
    ExternalAPIError,
    MerchantAPI,
    NotificationService,
    PaymentsAPI,
    TransactionAPI,
)
from agent_client import AgentUnavailableError, classify_dispute
from audit_logger import log_decision
from config import load_config
from dispute_rules import evaluate_decision
from models import AgentResult, DecisionResult, DisputeCase

logger = logging.getLogger(__name__)


class Adapters:
    def __init__(
        self,
        transaction_api: TransactionAPI,
        merchant_api: MerchantAPI,
        case_mgmt: CaseManagement,
        payments: PaymentsAPI,
        analyst_queue: AnalystQueue,
        notifications: NotificationService,
    ):
        self.transaction_api = transaction_api
        self.merchant_api = merchant_api
        self.case_mgmt = case_mgmt
        self.payments = payments
        self.analyst_queue = analyst_queue
        self.notifications = notifications


def _escalate(
    case: DisputeCase,
    reason: str,
    evidence: dict[str, Any],
    agent_result: AgentResult | None,
    adapters: Adapters,
    config: dict,
    is_new_case: bool,
) -> dict[str, Any]:
    decision = DecisionResult(decision="escalate", reasons=[reason])
    try:
        action_taken = escalate_to_analyst(
            case, evidence, reason, adapters.case_mgmt, adapters.analyst_queue, adapters.notifications
        )
    except CaseRecordingError:
        logger.error("ALERT: could not record escalation for case %s", case.case_id)
        action_taken = "escalation_not_recorded"

    log_decision(case, bool(evidence), agent_result, decision, action_taken, config)
    return {
        "case": case,
        "decision": decision,
        "action_taken": action_taken,
        "agent_result": agent_result,
        "is_new_case": is_new_case,
    }


def process_dispute(
    customer_id: str,
    transaction_id: str,
    description: str,
    amount_usd: Decimal,
    adapters: Adapters,
    config: dict | None = None,
) -> dict[str, Any]:
    config = config or load_config()

    case, is_new_case = adapters.case_mgmt.create_case(customer_id, transaction_id, description, amount_usd)

    try:
        transaction_evidence = adapters.transaction_api.get_transaction(transaction_id)
    except ExternalAPIError:
        return _escalate(case, "transaction evidence unavailable", {}, None, adapters, config, is_new_case)

    merchant_id = transaction_evidence.get("merchant_id")
    try:
        merchant_evidence = adapters.merchant_api.get_merchant(merchant_id)
    except ExternalAPIError:
        return _escalate(
            case,
            "merchant evidence unavailable",
            {"transaction": transaction_evidence},
            None,
            adapters,
            config,
            is_new_case,
        )

    evidence = {"transaction": transaction_evidence, "merchant": merchant_evidence}

    try:
        agent_result = classify_dispute(description, transaction_evidence, merchant_evidence)
    except AgentUnavailableError:
        return _escalate(case, "classification unavailable", evidence, None, adapters, config, is_new_case)

    decision = evaluate_decision(case, agent_result, config)

    try:
        if decision.decision == "auto_resolve":
            action_taken = issue_provisional_credit(case, adapters.case_mgmt, adapters.payments, adapters.notifications)
        else:
            action_taken = escalate_to_analyst(
                case,
                evidence,
                agent_result.rationale,
                adapters.case_mgmt,
                adapters.analyst_queue,
                adapters.notifications,
            )
    except CaseRecordingError:
        logger.error("ALERT: could not record decision for case %s", case.case_id)
        action_taken = "decision_not_recorded"

    log_decision(case, True, agent_result, decision, action_taken, config)
    return {
        "case": case,
        "decision": decision,
        "action_taken": action_taken,
        "agent_result": agent_result,
        "is_new_case": is_new_case,
    }


if __name__ == "__main__":
    demo_config = load_config()
    demo_adapters = Adapters(
        transaction_api=TransactionAPI(
            {"TXN-1": {"merchant_id": "M-1", "amount_usd": Decimal("25.00")}}
        ),
        merchant_api=MerchantAPI({"M-1": {"name": "Example Merchant"}}),
        case_mgmt=CaseManagement(),
        payments=PaymentsAPI(),
        analyst_queue=AnalystQueue(),
        notifications=NotificationService(),
    )
    result = process_dispute(
        customer_id="CUST-1",
        transaction_id="TXN-1",
        description="I was charged twice for the same purchase.",
        amount_usd=Decimal("25.00"),
        adapters=demo_adapters,
        config=demo_config,
    )
    print(result)
