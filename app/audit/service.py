"""Audit trail service – immutable audit event generation."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ActorType
from app.core.logging import get_logger, request_id_var
from app.models.models import AuditLog

logger = get_logger(__name__)


async def log_audit_event(
    db: AsyncSession,
    *,
    event_type: str,
    event_description: str,
    actor_type: str = ActorType.SYSTEM.value,
    actor_id: str | None = None,
    dispute_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    previous_state: dict | None = None,
    new_state: dict | None = None,
    tool_action: str | None = None,
    policy_references: list[str] | None = None,
    decision_reason: str | None = None,
) -> AuditLog:
    audit = AuditLog(
        request_id=request_id_var.get(""),
        dispute_id=dispute_id,
        customer_id=customer_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        event_description=event_description,
        previous_state=previous_state,
        new_state=new_state,
        tool_action=tool_action,
        policy_references=policy_references,
        decision_reason=decision_reason,
    )
    db.add(audit)
    await db.flush()
    logger.info(
        "audit_event",
        event_type=event_type,
        dispute_id=str(dispute_id) if dispute_id else None,
    )
    return audit
