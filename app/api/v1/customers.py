"""Customer and transaction API routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.database.session import get_db
from app.models.models import Customer
from app.schemas.schemas import AccountResponse, CustomerResponse, TransactionResponse
from app.security.auth import get_current_user
from app.tools.banking import (
    get_customer,
    get_customer_accounts,
    get_customer_transactions,
    get_transaction,
)

router = APIRouter(tags=["customers"])


@router.get("/customers/me", response_model=CustomerResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_user),
):
    cust = await get_customer(db, user.id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    return cust


@router.get("/customers/me/transactions", response_model=list[TransactionResponse])
async def list_my_transactions(
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_user),
):
    return await get_customer_transactions(db, user.id)


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer_info(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_user),
):
    if user.role == UserRole.CUSTOMER.value and user.id != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    cust = await get_customer(db, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    return cust


@router.get("/customers/{customer_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_user),
):
    if user.role == UserRole.CUSTOMER.value and user.id != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return await get_customer_accounts(db, customer_id)


@router.get("/customers/{customer_id}/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_user),
):
    if user.role == UserRole.CUSTOMER.value and user.id != customer_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return await get_customer_transactions(db, customer_id)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction_info(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Customer = Depends(get_current_user),
):
    txn = await get_transaction(db, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn
