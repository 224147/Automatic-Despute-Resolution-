"""Dispute API routes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.database.session import get_db
from app.models.models import Customer, Dispute
from app.schemas.schemas import (
    ClassificationResult,
    DisputeCreate,
    DisputeResponse,
    DisputeStatusResponse,
)
from app.security.auth import get_current_user, require_roles
from app.services.classification import classify_dispute
from app.services.dispute import run_dispute_workflow

router = APIRouter(prefix="/disputes", tags=["disputes"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_dispute(
    body: DisputeCreate,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_user),
):
    """Submit a new dispute and run the full resolution workflow."""
    result = await run_dispute_workflow(
        db,
        customer_id=user.id,
        customer_message=body.customer_message,
        transaction_ref=body.transaction_ref,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to process dispute"))
    return result


@router.post("/classify", response_model=ClassificationResult)
async def classify_only(
    body: DisputeCreate,
    _user: Customer = Depends(get_current_user),
):
    """Classify a complaint without creating a dispute."""
    return await classify_dispute(body.customer_message)


@router.get("/{dispute_id}", response_model=DisputeResponse)
async def get_dispute(
    dispute_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_user),
):
    result = await db.execute(select(Dispute).where(Dispute.id == dispute_id))
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    # Customers can only see their own disputes
    if user.role == UserRole.CUSTOMER.value and dispute.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return DisputeResponse.model_validate(dispute)


@router.get("/{dispute_id}/status", response_model=DisputeStatusResponse)
async def get_dispute_status(
    dispute_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(get_current_user),
):
    result = await db.execute(select(Dispute).where(Dispute.id == dispute_id))
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if user.role == UserRole.CUSTOMER.value and dispute.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return DisputeStatusResponse(
        dispute_id=dispute.id,
        status=dispute.status,
        category=dispute.category,
        priority=dispute.priority,
        risk_level=dispute.risk_level,
        resolution_summary=dispute.resolution_summary,
        created_at=dispute.created_at,
        updated_at=dispute.updated_at,
    )
