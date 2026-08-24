"""Tests for mock banking tools."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Customer, Account, Transaction, Dispute
from app.tools.banking import (
    authenticate_customer,
    check_previous_disputes,
    create_dispute,
    create_refund_request,
    escalate_dispute,
    get_customer,
    get_customer_accounts,
    get_customer_transactions,
    get_transaction,
    update_dispute,
)


@pytest.mark.asyncio
async def test_get_customer(db: AsyncSession, sample_customer: Customer):
    result = await get_customer(db, sample_customer.id)
    assert result is not None
    assert result.email == sample_customer.email


@pytest.mark.asyncio
async def test_get_customer_not_found(db: AsyncSession):
    result = await get_customer(db, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_customer_success(db: AsyncSession, sample_customer: Customer):
    result = await authenticate_customer(db, sample_customer.id, "1234")
    assert result is True


@pytest.mark.asyncio
async def test_authenticate_customer_fail(db: AsyncSession, sample_customer: Customer):
    result = await authenticate_customer(db, sample_customer.id, "wrong")
    assert result is False


@pytest.mark.asyncio
async def test_get_customer_accounts(db: AsyncSession, sample_customer: Customer, sample_account: Account):
    accounts = await get_customer_accounts(db, sample_customer.id)
    assert len(accounts) >= 1
    # Account number should be masked
    assert accounts[0].account_number.startswith("X")


@pytest.mark.asyncio
async def test_get_customer_transactions(
    db: AsyncSession, sample_customer: Customer, sample_account: Account, sample_transaction: Transaction
):
    txns = await get_customer_transactions(db, sample_customer.id)
    assert len(txns) >= 1


@pytest.mark.asyncio
async def test_get_transaction(db: AsyncSession, sample_transaction: Transaction):
    result = await get_transaction(db, sample_transaction.id)
    assert result is not None
    assert result.amount == 500.0


@pytest.mark.asyncio
async def test_create_and_update_dispute(db: AsyncSession, sample_customer: Customer):
    dispute = await create_dispute(
        db, customer_id=sample_customer.id,
        customer_message="Test dispute", category="UPI_FAILED",
    )
    assert dispute.id is not None
    assert dispute.status == "SUBMITTED"

    updated = await update_dispute(db, dispute.id, status="UNDER_REVIEW")
    assert updated.status == "UNDER_REVIEW"


@pytest.mark.asyncio
async def test_create_refund_request(db: AsyncSession, sample_customer: Customer):
    dispute = await create_dispute(
        db, customer_id=sample_customer.id,
        customer_message="Test refund", category="UPI_FAILED",
    )
    resolution = await create_refund_request(db, dispute.id, 500.0)
    assert resolution.refund_amount == 500.0
    assert resolution.resolution_type == "REFUND"


@pytest.mark.asyncio
async def test_escalate_dispute(db: AsyncSession, sample_customer: Customer):
    dispute = await create_dispute(
        db, customer_id=sample_customer.id,
        customer_message="Test escalation", category="UNAUTHORIZED_CARD_TRANSACTION",
    )
    esc = await escalate_dispute(db, dispute.id, "FRAUD_SUSPECTED", "CRITICAL")
    assert esc.reason == "FRAUD_SUSPECTED"
    assert esc.status == "OPEN"


@pytest.mark.asyncio
async def test_check_previous_disputes(db: AsyncSession, sample_customer: Customer):
    await create_dispute(
        db, customer_id=sample_customer.id,
        customer_message="Dispute 1", category="UPI_FAILED",
    )
    await create_dispute(
        db, customer_id=sample_customer.id,
        customer_message="Dispute 2", category="ATM_CASH_NOT_RECEIVED",
    )
    disputes = await check_previous_disputes(db, sample_customer.id)
    assert len(disputes) >= 2
