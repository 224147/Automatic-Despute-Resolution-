from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    types,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import json as _json


class _JSONType(types.TypeDecorator):
    """Portable JSON column that works with SQLite and PostgreSQL."""
    impl = types.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return _json.dumps(value)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return _json.loads(value)
        return None


class _UUIDType(types.TypeDecorator):
    """Portable UUID stored as String(36), works with SQLite."""
    impl = types.String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return uuid.UUID(value) if not isinstance(value, uuid.UUID) else value
        return None


_UUID = _UUIDType()
JSON = _JSONType()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(30), default="CUSTOMER")
    verification_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    accounts: Mapped[list[Account]] = relationship(back_populates="customer", lazy="selectin")
    cards: Mapped[list[Card]] = relationship(back_populates="customer", lazy="selectin")
    disputes: Mapped[list[Dispute]] = relationship(back_populates="customer", lazy="selectin")


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("customers.id"), nullable=False, index=True
    )
    account_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    customer: Mapped[Customer] = relationship(back_populates="accounts")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="account", lazy="selectin")


class Card(Base, TimestampMixin):
    __tablename__ = "cards"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("customers.id"), nullable=False, index=True
    )
    card_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    card_type: Mapped[str] = mapped_column(String(20), nullable=False)  # DEBIT / CREDIT
    expiry_date: Mapped[str] = mapped_column(String(7), nullable=False)  # MM/YYYY
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    credit_limit: Mapped[float | None] = mapped_column(Float, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="cards")


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("accounts.id"), nullable=False, index=True
    )
    transaction_ref: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    card_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    refund_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_type", "transaction_type"),
    )


class Dispute(Base, TimestampMixin):
    __tablename__ = "disputes"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("customers.id"), nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("transactions.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="SUBMITTED", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    customer_message: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="disputes")
    events: Mapped[list[DisputeEvent]] = relationship(back_populates="dispute", lazy="selectin")
    resolution: Mapped[Resolution | None] = relationship(back_populates="dispute", uselist=False)
    escalation: Mapped[Escalation | None] = relationship(back_populates="dispute", uselist=False)


class DisputeEvent(Base, TimestampMixin):
    __tablename__ = "dispute_events"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("disputes.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    dispute: Mapped[Dispute] = relationship(back_populates="events")


class Resolution(Base, TimestampMixin):
    __tablename__ = "resolutions"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("disputes.id"), unique=True, nullable=False
    )
    resolution_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    refund_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    policy_references: Mapped[list | None] = mapped_column(JSON, nullable=True)
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    dispute: Mapped[Dispute] = relationship(back_populates="resolution")


class Escalation(Base, TimestampMixin):
    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("disputes.id"), unique=True, nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    assigned_team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    sla_hours: Mapped[int] = mapped_column(Integer, default=48)
    agent_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dispute: Mapped[Dispute] = relationship(back_populates="escalation")


class PolicyMetadata(Base, TimestampMixin):
    __tablename__ = "policy_metadata"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    dispute_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_description: Mapped[str] = mapped_column(Text, nullable=False)
    previous_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_references: Mapped[list | None] = mapped_column(JSON, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(_UUID, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        _UUID, ForeignKey("customers.id"), nullable=False, index=True
    )
    dispute_id: Mapped[uuid.UUID | None] = mapped_column(_UUID, nullable=True)
    notification_type: Mapped[str] = mapped_column(String(20), nullable=False)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
