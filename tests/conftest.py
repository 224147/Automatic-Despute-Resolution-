"""Shared test fixtures."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.models.models import (
    Account,
    Base,
    Card,
    Customer,
    Dispute,
    Transaction,
)
from app.security.auth import hash_password

# Use in-memory SQLite for tests
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncSession:
    factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def sample_customer(db: AsyncSession) -> Customer:
    c = Customer(
        id=uuid.uuid4(),
        first_name="Test",
        last_name="User",
        email=f"test{uuid.uuid4().hex[:6]}@example.com",
        phone="+919876543210",
        hashed_password=hash_password("Test@1234"),
        verification_code="1234",
        role="CUSTOMER",
    )
    db.add(c)
    await db.flush()
    return c


@pytest_asyncio.fixture
async def sample_account(db: AsyncSession, sample_customer: Customer) -> Account:
    a = Account(
        id=uuid.uuid4(),
        customer_id=sample_customer.id,
        account_number="12345678901234",
        account_type="SAVINGS",
        balance=50000.0,
        status="ACTIVE",
    )
    db.add(a)
    await db.flush()
    return a


@pytest_asyncio.fixture
async def sample_transaction(db: AsyncSession, sample_account: Account) -> Transaction:
    t = Transaction(
        id=uuid.uuid4(),
        account_id=sample_account.id,
        transaction_ref=f"UPI{uuid.uuid4().hex[:9].upper()}",
        transaction_type="UPI",
        amount=500.0,
        status="FAILED",
        description="UPI payment to merchant",
        merchant="Test Merchant",
        transaction_date=datetime.now(timezone.utc),
    )
    db.add(t)
    await db.flush()
    return t


@pytest_asyncio.fixture
async def sample_card(db: AsyncSession, sample_customer: Customer) -> Card:
    card = Card(
        id=uuid.uuid4(),
        customer_id=sample_customer.id,
        card_number="4111222233334444",
        card_type="DEBIT",
        expiry_date="12/2028",
        status="ACTIVE",
    )
    db.add(card)
    await db.flush()
    return card
