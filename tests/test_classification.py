"""Tests for the dispute classification service."""
from __future__ import annotations

import pytest

from app.services.classification import _deterministic_classify, classify_dispute


class TestDeterministicClassification:
    def test_upi_failed(self):
        result = _deterministic_classify("My UPI transaction failed but Rs. 500 was deducted")
        assert result is not None
        assert result.dispute_category == "UPI_FAILED"
        assert result.fraud_indicator is False

    def test_upi_pending(self):
        result = _deterministic_classify("My UPI payment is still pending since yesterday")
        assert result is not None
        assert result.dispute_category == "UPI_PENDING"

    def test_atm_cash_not_received(self):
        result = _deterministic_classify("ATM did not give cash but amount was not received debited")
        assert result is not None
        assert result.dispute_category == "ATM_CASH_NOT_RECEIVED"

    def test_unauthorized_card(self):
        result = _deterministic_classify("I don't recognize this card transaction of Rs 5000")
        assert result is not None
        assert result.dispute_category == "UNAUTHORIZED_CARD_TRANSACTION"
        assert result.fraud_indicator is True

    def test_card_payment_failed(self):
        result = _deterministic_classify("My card payment failed but I was charged")
        assert result is not None
        assert result.dispute_category == "CARD_PAYMENT_FAILED"

    def test_refund_not_received(self):
        result = _deterministic_classify("I returned the item but refund not received")
        assert result is not None
        assert result.dispute_category == "REFUND_NOT_RECEIVED"

    def test_neft_issue(self):
        result = _deterministic_classify("My NEFT transfer failed but amount debited")
        assert result is not None
        assert result.dispute_category == "NEFT_RTGS_IMPS_ISSUE"

    def test_rtgs_issue(self):
        result = _deterministic_classify("RTGS transfer problem, money not reached")
        assert result is not None
        assert result.dispute_category == "NEFT_RTGS_IMPS_ISSUE"

    def test_imps_issue(self):
        result = _deterministic_classify("IMPS failed, money gone")
        assert result is not None
        assert result.dispute_category == "NEFT_RTGS_IMPS_ISSUE"

    def test_wrong_charge(self):
        result = _deterministic_classify("I was wrong charge bank fee of Rs 200")
        assert result is not None
        assert result.dispute_category == "WRONG_BANK_CHARGE"

    def test_loan_emi(self):
        result = _deterministic_classify("My loan EMI was debited twice this month")
        assert result is not None
        assert result.dispute_category == "LOAN_EMI_DISPUTE"

    def test_credit_card_billing(self):
        result = _deterministic_classify("My credit card bill shows incorrect charge")
        assert result is not None
        assert result.dispute_category == "CREDIT_CARD_BILLING_DISPUTE"

    def test_unknown_message(self):
        result = _deterministic_classify("I have a general question about my account")
        assert result is None

    def test_fraud_keywords_detected(self):
        result = _deterministic_classify("Unauthorized card transaction, I did not make this")
        assert result is not None
        assert result.fraud_indicator is True
        assert result.urgency == "HIGH"


@pytest.mark.asyncio
async def test_classify_dispute_fallback():
    """When LLM is not configured, should fall back to deterministic or UNKNOWN."""
    result = await classify_dispute("My UPI transaction failed but Rs. 500 was deducted")
    assert result.dispute_category == "UPI_FAILED"

    result_unknown = await classify_dispute("Something random happened with my banking stuff")
    # Should either be classified by LLM or fall back to UNKNOWN
    assert result_unknown.dispute_category is not None
