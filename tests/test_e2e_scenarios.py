"""End-to-end test scenarios as described in Phase 16."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Account, Customer, Dispute, Transaction
from app.security.auth import hash_password
from app.services.classification import classify_dispute
from app.rules.engine import evaluate_rules
from app.services.risk import assess_risk


@pytest_asyncio.fixture
async def e2e_customer(db: AsyncSession) -> Customer:
    c = Customer(
        id=uuid.uuid4(), first_name="E2E", last_name="Tester",
        email=f"e2e_{uuid.uuid4().hex[:6]}@example.com",
        phone="+919876500000", hashed_password=hash_password("Test@1234"),
        verification_code="1234", role="CUSTOMER",
    )
    db.add(c)
    await db.flush()

    acc = Account(
        id=uuid.uuid4(), customer_id=c.id, account_number="9999888877776666",
        account_type="SAVINGS", balance=100000, status="ACTIVE",
    )
    db.add(acc)
    await db.flush()

    # Add some test transactions
    for txn_data in [
        ("UPI", 500, "FAILED", f"UPI{uuid.uuid4().hex[:9].upper()}"),
        ("ATM", 10000, "FAILED", f"ATM{uuid.uuid4().hex[:9].upper()}"),
        ("CARD", 75000, "SUCCESS", f"CAR{uuid.uuid4().hex[:9].upper()}"),
        ("UPI", 2000, "REFUNDED", f"UPI{uuid.uuid4().hex[:9].upper()}"),
    ]:
        t = Transaction(
            id=uuid.uuid4(), account_id=acc.id, transaction_ref=txn_data[3],
            transaction_type=txn_data[0], amount=txn_data[1], status=txn_data[2],
            description="E2E test transaction", transaction_date=datetime.now(timezone.utc),
        )
        db.add(t)
    await db.flush()
    return c


class TestScenario1_UPIFailed:
    """Customer: 'My UPI transaction failed but Rs. 500 was deducted.'"""

    @pytest.mark.asyncio
    async def test_classify_upi_failed(self):
        result = await classify_dispute("My UPI transaction failed but Rs. 500 was deducted.")
        assert result.dispute_category == "UPI_FAILED"
        assert result.confidence > 0.5

    def test_rules_auto_resolve(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution
        assert result.recommended_action == "AUTO_REFUND"

    def test_risk_low(self):
        result = assess_risk(
            amount=500, transaction_type="UPI", transaction_status="FAILED",
            dispute_category="UPI_FAILED", customer_dispute_frequency=0,
            fraud_indicator=False, customer_verified=True,
        )
        assert result["risk_level"] == "LOW"


class TestScenario2_ATM:
    """Customer: 'ATM did not give me cash but Rs. 10,000 was deducted.'"""

    @pytest.mark.asyncio
    async def test_classify_atm(self):
        result = await classify_dispute("ATM did not give me cash but Rs. 10,000 was deducted.")
        assert result.dispute_category == "ATM_CASH_NOT_RECEIVED"

    def test_rules_atm(self):
        result = evaluate_rules(
            category="ATM_CASH_NOT_RECEIVED", amount=10000, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert result.eligible_for_auto_resolution


class TestScenario3_UnauthorizedCard:
    """Customer: 'I don't recognize this Rs. 75,000 card transaction.'"""

    @pytest.mark.asyncio
    async def test_classify_unauthorized(self):
        result = await classify_dispute("I don't recognize this Rs. 75,000 card transaction.")
        assert result.dispute_category == "UNAUTHORIZED_CARD_TRANSACTION"
        assert result.fraud_indicator is True

    def test_rules_no_auto(self):
        result = evaluate_rules(
            category="UNAUTHORIZED_CARD_TRANSACTION", amount=75000,
            transaction_status="SUCCESS", customer_verified=True,
            previous_dispute_count=0, fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution
        assert result.required_human_review
        assert result.risk_level == "CRITICAL"

    def test_risk_high(self):
        result = assess_risk(
            amount=75000, transaction_type="CARD", transaction_status="SUCCESS",
            dispute_category="UNAUTHORIZED_CARD_TRANSACTION",
            customer_dispute_frequency=0, fraud_indicator=True,
            customer_verified=True,
        )
        assert result["risk_level"] in ("HIGH", "CRITICAL")


class TestScenario4_RefundNotReceived:
    """Customer: 'My refund has not arrived.'"""

    @pytest.mark.asyncio
    async def test_classify_refund(self):
        result = await classify_dispute("I returned the item but my refund has not arrived or received.")
        assert result.dispute_category == "REFUND_NOT_RECEIVED"

    def test_rules_refund_overdue(self):
        result = evaluate_rules(
            category="REFUND_NOT_RECEIVED", amount=2000,
            transaction_status="REFUNDED", customer_verified=True,
            previous_dispute_count=0, fraud_indicator=False,
            policy_found=True, transaction_age_days=15,
        )
        assert result.eligible_for_auto_resolution


class TestScenario5_AuthFailed:
    """Customer cannot authenticate."""

    def test_rules_block_unverified(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="FAILED",
            customer_verified=False, previous_dispute_count=0,
            fraud_indicator=False, policy_found=True,
        )
        assert not result.eligible_for_auto_resolution
        assert result.required_human_review
        assert "CUSTOMER_NOT_VERIFIED" in result.reason_codes


class TestScenario6_NoPolicyFound:
    """No applicable policy."""

    def test_rules_no_policy(self):
        result = evaluate_rules(
            category="UPI_FAILED", amount=500, transaction_status="FAILED",
            customer_verified=True, previous_dispute_count=0,
            fraud_indicator=False, policy_found=False,
        )
        assert not result.eligible_for_auto_resolution
        assert "NO_POLICY_FOUND" in result.reason_codes
