"""Mock banking tools – controlled services the LLM calls instead of direct DB access."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    DisputeStatus,
    EscalationStatus,
    NotificationStatus,
)
from app.core.logging import get_logger
from app.models.models import (
    Account,
    Card,
    Customer,
    Dispute,
    DisputeEvent,
    Escalation,
    Notification,
    Resolution,
    Transaction,
)
from app.schemas.schemas import (
    AccountResponse,
    CustomerResponse,
    TransactionResponse,
)

logger = get_logger(__name__)


# ── Customer tools ──

async def get_customer(db: AsyncSession, customer_id: uuid.UUID) -> CustomerResponse | None:
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if c:
        return CustomerResponse.model_validate(c)
    return None


async def authenticate_customer(
    db: AsyncSession, customer_id: uuid.UUID, verification_code: str
) -> bool:
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    c = result.scalar_one_or_none()
    if not c:
        return False
    return c.verification_code == verification_code


async def get_customer_accounts(db: AsyncSession, customer_id: uuid.UUID) -> list[AccountResponse]:
    result = await db.execute(select(Account).where(Account.customer_id == customer_id))
    return [AccountResponse.model_validate(a) for a in result.scalars().all()]


async def get_customer_transactions(
    db: AsyncSession, customer_id: uuid.UUID, limit: int = 50
) -> list[TransactionResponse]:
    result = await db.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.customer_id == customer_id)
        .order_by(Transaction.transaction_date.desc())
        .limit(limit)
    )
    return [TransactionResponse.model_validate(t) for t in result.scalars().all()]


# ── Transaction tools ──

async def get_transaction(db: AsyncSession, transaction_id: uuid.UUID) -> TransactionResponse | None:
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    t = result.scalar_one_or_none()
    if t:
        return TransactionResponse.model_validate(t)
    return None


async def get_transaction_by_ref(db: AsyncSession, ref: str) -> TransactionResponse | None:
    result = await db.execute(select(Transaction).where(Transaction.transaction_ref == ref))
    t = result.scalar_one_or_none()
    if t:
        return TransactionResponse.model_validate(t)
    return None


async def check_transaction_status(db: AsyncSession, transaction_id: uuid.UUID) -> str | None:
    result = await db.execute(
        select(Transaction.status).where(Transaction.id == transaction_id)
    )
    row = result.scalar_one_or_none()
    return row


async def check_refund_status(db: AsyncSession, transaction_id: uuid.UUID) -> str | None:
    result = await db.execute(
        select(Transaction.refund_status).where(Transaction.id == transaction_id)
    )
    return result.scalar_one_or_none()


# ── Account / Card tools ──

async def check_account_status(db: AsyncSession, account_id: uuid.UUID) -> str | None:
    result = await db.execute(select(Account.status).where(Account.id == account_id))
    return result.scalar_one_or_none()


async def check_card_status(db: AsyncSession, card_id: uuid.UUID) -> str | None:
    result = await db.execute(select(Card.status).where(Card.id == card_id))
    return result.scalar_one_or_none()


# ── Dispute history ──

async def check_previous_disputes(db: AsyncSession, customer_id: uuid.UUID) -> list[Dispute]:
    result = await db.execute(
        select(Dispute).where(Dispute.customer_id == customer_id).order_by(Dispute.created_at.desc())
    )
    return list(result.scalars().all())


async def get_dispute_count_last_90_days(db: AsyncSession, customer_id: uuid.UUID) -> int:
    ninety_days_ago = datetime.now(UTC) - __import__("datetime").timedelta(days=90)
    result = await db.execute(
        select(func.count())
        .select_from(Dispute)
        .where(Dispute.customer_id == customer_id, Dispute.created_at >= ninety_days_ago)
    )
    return result.scalar_one()


# ── Dispute actions ──

async def create_dispute(
    db: AsyncSession,
    *,
    customer_id: uuid.UUID,
    customer_message: str,
    category: str,
    priority: str = "MEDIUM",
    transaction_id: uuid.UUID | None = None,
    amount: float | None = None,
    confidence: float | None = None,
) -> Dispute:
    dispute = Dispute(
        customer_id=customer_id,
        transaction_id=transaction_id,
        category=category,
        status=DisputeStatus.SUBMITTED.value,
        priority=priority,
        customer_message=customer_message,
        amount=amount,
        classification_confidence=confidence,
    )
    db.add(dispute)
    await db.flush()
    logger.info("dispute_created", dispute_id=str(dispute.id), category=category)
    return dispute


async def update_dispute(
    db: AsyncSession, dispute_id: uuid.UUID, **kwargs
) -> Dispute | None:
    result = await db.execute(select(Dispute).where(Dispute.id == dispute_id))
    dispute = result.scalar_one_or_none()
    if not dispute:
        return None
    for k, v in kwargs.items():
        if hasattr(dispute, k):
            setattr(dispute, k, v)
    await db.flush()
    return dispute


async def create_dispute_event(
    db: AsyncSession,
    dispute_id: uuid.UUID,
    event_type: str,
    description: str,
    actor_type: str,
    actor_id: str | None = None,
    metadata: dict | None = None,
) -> DisputeEvent:
    ev = DisputeEvent(
        dispute_id=dispute_id,
        event_type=event_type,
        description=description,
        actor_type=actor_type,
        actor_id=actor_id,
        metadata_json=metadata,
    )
    db.add(ev)
    await db.flush()
    return ev


async def create_resolution(
    db: AsyncSession,
    *,
    dispute_id: uuid.UUID,
    resolution_type: str,
    action_taken: str,
    refund_amount: float | None = None,
    reason_codes: list[str] | None = None,
    policy_references: list[str] | None = None,
    auto_resolved: bool = False,
) -> Resolution:
    res = Resolution(
        dispute_id=dispute_id,
        resolution_type=resolution_type,
        action_taken=action_taken,
        refund_amount=refund_amount,
        reason_codes=reason_codes,
        policy_references=policy_references,
        auto_resolved=auto_resolved,
    )
    db.add(res)
    await db.flush()
    return res


async def create_refund_request(
    db: AsyncSession, dispute_id: uuid.UUID, amount: float
) -> Resolution:
    return await create_resolution(
        db, dispute_id=dispute_id,
        resolution_type="REFUND",
        action_taken=f"Refund of INR {amount} initiated",
        refund_amount=amount,
        auto_resolved=True,
    )


async def create_provisional_credit_request(
    db: AsyncSession, dispute_id: uuid.UUID, amount: float
) -> Resolution:
    return await create_resolution(
        db, dispute_id=dispute_id,
        resolution_type="PROVISIONAL_CREDIT",
        action_taken=f"Provisional credit of INR {amount} applied",
        refund_amount=amount,
        auto_resolved=True,
    )


# ── Escalation ──

async def escalate_dispute(
    db: AsyncSession,
    dispute_id: uuid.UUID,
    reason: str,
    priority: str = "MEDIUM",
    assigned_team: str | None = None,
    sla_hours: int = 48,
) -> Escalation:
    esc = Escalation(
        dispute_id=dispute_id,
        reason=reason,
        priority=priority,
        status=EscalationStatus.OPEN.value,
        assigned_team=assigned_team or "DISPUTE_TEAM",
        sla_hours=sla_hours,
    )
    db.add(esc)
    await db.flush()
    # Also update dispute status
    await update_dispute(db, dispute_id, status=DisputeStatus.ESCALATED.value)
    logger.info("dispute_escalated", dispute_id=str(dispute_id), reason=reason)
    return esc


# ── Notification ──

async def send_customer_notification(
    db: AsyncSession,
    customer_id: uuid.UUID,
    dispute_id: uuid.UUID | None,
    notification_type: str,
    template_name: str,
    subject: str,
    body: str,
) -> Notification:
    notif = Notification(
        customer_id=customer_id,
        dispute_id=dispute_id,
        notification_type=notification_type,
        template_name=template_name,
        subject=subject,
        body=body,
        status=NotificationStatus.SENT.value,
        sent_at=datetime.now(UTC),
    )
    db.add(notif)
    await db.flush()
    logger.info("notification_sent", customer_id=str(customer_id), template=template_name)
    return notif
