"""Tests for audit trail."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_audit_event
from app.models.models import AuditLog


@pytest.mark.asyncio
async def test_log_audit_event(db: AsyncSession):
    audit = await log_audit_event(
        db,
        event_type="CLASSIFICATION",
        event_description="Test classification event",
        actor_type="SYSTEM",
        dispute_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
    )
    assert audit.id is not None
    assert audit.event_type == "CLASSIFICATION"


@pytest.mark.asyncio
async def test_audit_no_sensitive_data(db: AsyncSession):
    audit = await log_audit_event(
        db,
        event_type="AUTHENTICATION",
        event_description="Customer authenticated",
        new_state={"verified": True},
    )
    # Should not contain any sensitive info in the log
    assert audit.event_description == "Customer authenticated"
    assert audit.new_state == {"verified": True}
