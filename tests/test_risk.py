"""Tests for risk assessment module."""
from __future__ import annotations

import pytest

from app.services.risk import assess_risk


class TestRiskAssessment:
    def test_low_risk_simple(self):
        result = assess_risk(
            amount=500, transaction_type="UPI", transaction_status="FAILED",
            dispute_category="UPI_FAILED", customer_dispute_frequency=0,
            fraud_indicator=False, customer_verified=True,
        )
        assert result["risk_level"] == "LOW"
        assert result["risk_score"] < 30

    def test_high_risk_unauthorized(self):
        result = assess_risk(
            amount=75000, transaction_type="CARD", transaction_status="SUCCESS",
            dispute_category="UNAUTHORIZED_CARD_TRANSACTION",
            customer_dispute_frequency=0, fraud_indicator=False,
            customer_verified=True,
        )
        assert result["risk_level"] in ("HIGH", "CRITICAL")

    def test_critical_risk_fraud(self):
        result = assess_risk(
            amount=100000, transaction_type="CARD", transaction_status="SUCCESS",
            dispute_category="UNAUTHORIZED_CARD_TRANSACTION",
            customer_dispute_frequency=3, fraud_indicator=True,
            customer_verified=False,
        )
        assert result["risk_level"] == "CRITICAL"
        assert result["risk_score"] >= 70

    def test_medium_risk_high_amount(self):
        result = assess_risk(
            amount=30000, transaction_type="ATM", transaction_status="FAILED",
            dispute_category="ATM_CASH_NOT_RECEIVED",
            customer_dispute_frequency=1, fraud_indicator=False,
            customer_verified=True,
        )
        assert result["risk_level"] in ("LOW", "MEDIUM")

    def test_risk_factors_populated(self):
        result = assess_risk(
            amount=200000, transaction_type="CARD", transaction_status="SUCCESS",
            dispute_category="UNAUTHORIZED_CARD_TRANSACTION",
            customer_dispute_frequency=6, fraud_indicator=True,
            customer_verified=False, transaction_age_days=45,
        )
        assert len(result["risk_factors"]) > 0
        assert result["risk_score"] > 0

    def test_transaction_age_factor(self):
        result = assess_risk(
            amount=1000, transaction_type="UPI", transaction_status="FAILED",
            dispute_category="UPI_FAILED", customer_dispute_frequency=0,
            fraud_indicator=False, customer_verified=True,
            transaction_age_days=35,
        )
        assert any("old transaction" in f.lower() for f in result["risk_factors"])

    def test_dispute_frequency_factor(self):
        result = assess_risk(
            amount=1000, transaction_type="UPI", transaction_status="FAILED",
            dispute_category="UPI_FAILED", customer_dispute_frequency=5,
            fraud_indicator=False, customer_verified=True,
        )
        assert any("frequency" in f.lower() for f in result["risk_factors"])
