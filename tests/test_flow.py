from decimal import Decimal
from unittest.mock import patch

import main
from adapters import (
    AnalystQueue,
    CaseManagement,
    ExternalAPIError,
    MerchantAPI,
    NotificationService,
    PaymentsAPI,
    TransactionAPI,
)
from agent_client import AgentUnavailableError
from main import Adapters, process_dispute
from models import AgentResult

CONFIG = {"AUTO_RESOLVE_MAX_USD": 50, "MIN_CONFIDENCE": 0.90, "ELIGIBLE_TYPES": ["exact_duplicate"]}


def build_adapters(transactions=None, merchants=None):
    return Adapters(
        transaction_api=TransactionAPI(transactions or {"TXN-1": {"merchant_id": "M-1", "amount_usd": Decimal("25")}}),
        merchant_api=MerchantAPI(merchants or {"M-1": {"name": "Example Merchant"}}),
        case_mgmt=CaseManagement(),
        payments=PaymentsAPI(),
        analyst_queue=AnalystQueue(),
        notifications=NotificationService(),
    )


def submit(adapters, amount=Decimal("25"), transaction_id="TXN-1", customer_id="CUST-1"):
    return process_dispute(
        customer_id=customer_id,
        transaction_id=transaction_id,
        description="charged twice",
        amount_usd=amount,
        adapters=adapters,
        config=CONFIG,
    )


def test_payments_not_called_on_escalation():
    adapters = build_adapters()
    with patch.object(main, "classify_dispute", return_value=AgentResult("suspected_fraud", 0.99, "looks off")):
        result = submit(adapters)
    assert result["decision"].decision == "escalate"
    assert adapters.payments.issued_credits == []


def test_payments_called_on_auto_resolution():
    adapters = build_adapters()
    agent_result = AgentResult("exact_duplicate", 0.95, "matches prior charge")
    with patch.object(main, "classify_dispute", return_value=agent_result):
        result = submit(adapters)
    assert result["decision"].decision == "auto_resolve"
    assert len(adapters.payments.issued_credits) == 1
    assert adapters.payments.issued_credits[0]["case_id"] == result["case"].case_id


def test_duplicate_transaction_reuses_existing_case():
    adapters = build_adapters()
    with patch.object(main, "classify_dispute", return_value=AgentResult("suspected_fraud", 0.99, "x")):
        first = submit(adapters)
        second = submit(adapters)
    assert first["case"].case_id == second["case"].case_id
    assert len(adapters.case_mgmt._cases) == 1
    assert first["is_new_case"] is True
    assert second["is_new_case"] is False


def test_different_customer_same_transaction_gets_separate_case():
    adapters = build_adapters()
    with patch.object(main, "classify_dispute", return_value=AgentResult("suspected_fraud", 0.99, "x")):
        first = submit(adapters, customer_id="CUST-1")
        second = submit(adapters, customer_id="CUST-2")
    assert first["case"].case_id != second["case"].case_id
    assert len(adapters.case_mgmt._cases) == 2
    assert first["is_new_case"] is True
    assert second["is_new_case"] is True


def test_transaction_api_failure_after_retry_escalates():
    adapters = build_adapters()
    with patch.object(TransactionAPI, "_fetch", side_effect=ExternalAPIError("down")):
        result = submit(adapters)
    assert result["decision"].decision == "escalate"
    assert adapters.payments.issued_credits == []


def test_merchant_api_failure_after_retry_escalates():
    adapters = build_adapters()
    with patch.object(MerchantAPI, "_fetch", side_effect=ExternalAPIError("down")):
        result = submit(adapters)
    assert result["decision"].decision == "escalate"
    assert adapters.payments.issued_credits == []


def test_claude_failure_after_retry_escalates():
    adapters = build_adapters()
    with patch.object(main, "classify_dispute", side_effect=AgentUnavailableError("classification unavailable")):
        result = submit(adapters)
    assert result["decision"].decision == "escalate"
    assert result["decision"].reasons == ["classification unavailable"]
    assert adapters.payments.issued_credits == []


def test_missing_evidence_escalates():
    adapters = build_adapters(transactions={})
    result = submit(adapters, transaction_id="TXN-UNKNOWN")
    assert result["decision"].decision == "escalate"
    assert adapters.payments.issued_credits == []
