"""Tests for the rules engine."""
from __future__ import annotations

from app.rules.engine import evaluate_rules


class TestRulesEngine:
    def test_customer_not_verified_blocks(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="FAILED",
            customer_verified=False, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution
        assert result.required_human_review
        assert "CUSTOMER_NOT_VERIFIED" in result.reason_codes

    def test_fraud_indicator_escalates(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=True, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution
        assert result.risk_level == "CRITICAL"
        assert "FRAUD_INDICATOR_DETECTED" in result.reason_codes

    def test_no_policy_escalates(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=False,
        )
        assert not result.eligible_for_auto_resolution
        assert "NO_POLICY_FOUND" in result.reason_codes

    # ── UPI FAILED ──
    def test_upi_failed_low_amount_auto(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution
        assert result.recommended_action == "AUTO_REFUND"
        assert result.risk_level == "LOW"

    def test_upi_failed_medium_amount(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=50000, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution
        assert result.recommended_action == "REFUND_WITH_VERIFICATION"

    def test_upi_failed_high_amount_manual(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=200000, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution
        assert result.required_human_review

    def test_upi_failed_success_status_escalates(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="SUCCESS",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution

    # ── ATM ──
    def test_atm_low_amount_auto(self):
        result = evaluate_rules(
            category="ATM_CASH_NOT_RECEIVED", amount=10000, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution
        assert result.risk_level == "LOW"

    def test_atm_high_amount_manual(self):
        result = evaluate_rules(
            category="ATM_CASH_NOT_RECEIVED", amount=60000, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution
        assert result.required_human_review

    # ── UNAUTHORIZED CARD ──
    def test_unauthorized_card_never_auto(self):
        result = evaluate_rules(
            category="UNAUTHORIZED_CARD_TRANSACTION", amount=1000, transaction_status="SUCCESS",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution
        assert result.required_human_review
        assert result.recommended_action == "ESCALATE_FRAUD"

    def test_unauthorized_card_high_amount_critical(self):
        result = evaluate_rules(
            category="UNAUTHORIZED_CARD_TRANSACTION", amount=75000, transaction_status="SUCCESS",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.risk_level == "CRITICAL"

    # ── CARD FAILED ──
    def test_card_failed_low_auto(self):
        result = evaluate_rules(
            category="CARD_PAYMENT_FAILED", amount=5000, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution

    # ── REFUND ──
    def test_refund_overdue_auto(self):
        result = evaluate_rules(
            category="REFUND_NOT_RECEIVED", amount=3000, transaction_status="SUCCESS",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
            transaction_age_days=15,
        )
        assert result.eligible_for_auto_resolution

    # ── NEFT ──
    def test_neft_low_auto(self):
        result = evaluate_rules(
            category="NEFT_RTGS_IMPS_ISSUE", amount=20000, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution

    # ── WRONG CHARGE ──
    def test_wrong_charge_low_auto(self):
        result = evaluate_rules(
            category="WRONG_BANK_CHARGE", amount=200, transaction_status=None,
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution

    def test_wrong_charge_high_manual(self):
        result = evaluate_rules(
            category="WRONG_BANK_CHARGE", amount=10000, transaction_status=None,
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution

    # ── LOAN EMI ──
    def test_loan_emi_low_auto(self):
        result = evaluate_rules(
            category="LOAN_EMI_DISPUTE", amount=15000, transaction_status=None,
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution

    def test_loan_emi_high_escalate(self):
        result = evaluate_rules(
            category="LOAN_EMI_DISPUTE", amount=50000, transaction_status=None,
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution

    # ── CREDIT CARD BILLING ──
    def test_cc_billing_low_auto(self):
        result = evaluate_rules(
            category="CREDIT_CARD_BILLING_DISPUTE", amount=3000, transaction_status=None,
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution

    # ── UNKNOWN ──
    def test_unknown_escalates(self):
        result = evaluate_rules(
            category="UNKNOWN", amount=500, transaction_status=None,
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution

    # ── Repeated disputes ──
    def test_repeated_dispute_flag(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=6,
            fraud_indicator=False, policy_found=True,
        )
        assert "REPEATED_DISPUTE_FLAG" in result.reason_codes
