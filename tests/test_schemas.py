"""Tests for Pydantic schemas – validation and masking."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.schemas.schemas import (
    AccountResponse,
    CardResponse,
    ClassificationResult,
    CustomerCreate,
    DisputeCreate,
    RiskResult,
    RuleResult,
    mask_account_number,
    mask_card_number,
)


class TestMasking:
    def test_mask_account_number(self):
        assert mask_account_number("12345678901234") == "XXXXXXXXXX1234"

    def test_mask_card_number(self):
        assert mask_card_number("4111222233334444") == "XXXXXXXXXXXX4444"

    def test_mask_short_number(self):
        assert mask_account_number("1234") == "1234"


class TestCustomerCreate:
    def test_valid(self):
        c = CustomerCreate(
            first_name="Test", last_name="User",
            email="test@example.com", phone="9876543210",
            password="StrongP@ss1",
        )
        assert c.first_name == "Test"

    def test_short_password_rejected(self):
        with pytest.raises(Exception):
            CustomerCreate(
                first_name="Test", last_name="User",
                email="test@example.com", phone="9876543210",
                password="short",
            )

    def test_invalid_email_rejected(self):
        with pytest.raises(Exception):
            CustomerCreate(
                first_name="Test", last_name="User",
                email="not-an-email", phone="9876543210",
                password="StrongP@ss1",
            )


class TestDisputeCreate:
    def test_valid(self):
        d = DisputeCreate(customer_message="My UPI failed but money debited Rs 500")
        assert len(d.customer_message) > 10

    def test_short_message_rejected(self):
        with pytest.raises(Exception):
            DisputeCreate(customer_message="short")


class TestClassificationResult:
    def test_valid(self):
        r = ClassificationResult(
            dispute_category="UPI_FAILED",
            confidence=0.9,
        )
        assert r.fraud_indicator is False
        assert r.urgency == "MEDIUM"


class TestRuleResult:
    def test_valid(self):
        r = RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="AUTO_REFUND",
        )
        assert r.risk_level == "LOW"


class TestRiskResult:
    def test_valid(self):
        r = RiskResult(
            risk_score=25.0,
            risk_level="LOW",
            risk_factors=["test"],
            recommended_action="PROCEED",
        )
        assert r.risk_score == 25.0
