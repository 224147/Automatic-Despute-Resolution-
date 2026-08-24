"""Escalation API routes."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_audit_event
from app.core.enums import AuditEventType, DisputeStatus, EscalationStatus, UserRole
from app.database.session import get_db
from app.models.models import Customer, Dispute, Escalation, Resolution
from app.schemas.schemas import (
    EscalationAssign,
    EscalationResolve,
    EscalationResponse,
)
from app.security.auth import require_roles

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get("", response_model=list[EscalationResponse])
async def list_escalations(
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(require_roles(UserRole.SUPPORT_AGENT, UserRole.DISPUTE_MANAGER, UserRole.ADMIN)),
):
    query = select(Escalation).order_by(Escalation.created_at.desc())
    if status_filter:
        query = query.where(Escalation.status == status_filter)
    result = await db.execute(query)
    return [EscalationResponse.model_validate(e) for e in result.scalars().all()]


@router.get("/{escalation_id}", response_model=EscalationResponse)
async def get_escalation(
    escalation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(require_roles(UserRole.SUPPORT_AGENT, UserRole.DISPUTE_MANAGER, UserRole.ADMIN)),
):
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    esc = result.scalar_one_or_none()
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return EscalationResponse.model_validate(esc)


@router.post("/{escalation_id}/assign", response_model=EscalationResponse)
async def assign_escalation(
    escalation_id: uuid.UUID,
    body: EscalationAssign,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(require_roles(UserRole.SUPPORT_AGENT, UserRole.DISPUTE_MANAGER, UserRole.ADMIN)),
):
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    esc = result.scalar_one_or_none()
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")

    esc.assigned_agent_id = body.agent_id
    esc.status = EscalationStatus.ASSIGNED.value
    if body.team:
        esc.assigned_team = body.team
    await db.flush()
    await db.refresh(esc)

    await log_audit_event(
        db,
        event_type=AuditEventType.HUMAN_AGENT_ACTION.value,
        event_description=f"Escalation assigned to agent {body.agent_id}",
        dispute_id=esc.dispute_id,
        actor_type="AGENT",
        actor_id=str(user.id),
    )

    return EscalationResponse.model_validate(esc)


@router.post("/{escalation_id}/resolve", response_model=EscalationResponse)
async def resolve_escalation(
    escalation_id: uuid.UUID,
    body: EscalationResolve,
    db: AsyncSession = Depends(get_db),
    user: Customer = Depends(require_roles(UserRole.SUPPORT_AGENT, UserRole.DISPUTE_MANAGER, UserRole.ADMIN)),
):
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    esc = result.scalar_one_or_none()
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")

    esc.status = EscalationStatus.RESOLVED.value
    esc.agent_notes = body.resolution_notes
    esc.resolved_at = datetime.now(UTC)
    await db.flush()

    # Update the dispute
    dispute_result = await db.execute(select(Dispute).where(Dispute.id == esc.dispute_id))
    dispute = dispute_result.scalar_one_or_none()
    if dispute:
        dispute.status = DisputeStatus.RESOLVED.value
        dispute.resolution_summary = body.resolution_notes
        dispute.resolved_at = datetime.now(UTC)

    # Create resolution record
    resolution = Resolution(
        dispute_id=esc.dispute_id,
        resolution_type=body.resolution_type,
        action_taken=body.resolution_notes,
        refund_amount=body.refund_amount,
        auto_resolved=False,
    )
    db.add(resolution)
    await db.flush()
    await db.refresh(esc)

    await log_audit_event(
        db,
        event_type=AuditEventType.RESOLUTION.value,
        event_description=f"Escalation resolved by agent: {body.resolution_notes[:100]}",
        dispute_id=esc.dispute_id,
        actor_type="AGENT",
        actor_id=str(user.id),
    )

    return EscalationResponse.model_validate(esc)
