from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


def mask_account_number(v: str) -> str:
    if len(v) > 4:
        return "X" * (len(v) - 4) + v[-4:]
    return v


def mask_card_number(v: str) -> str:
    if len(v) > 4:
        return "X" * (len(v) - 4) + v[-4:]
    return v


# ── Customer ──

class CustomerCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=8)


class CustomerResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    phone: str
    is_active: bool
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Account ──

class AccountResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    account_number: str
    account_type: str
    balance: float
    currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("account_number", mode="before")
    @classmethod
    def _mask_account(cls, v: str) -> str:
        return mask_account_number(v)


# ── Card ──

class CardResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    card_number: str
    card_type: str
    expiry_date: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("card_number", mode="before")
    @classmethod
    def _mask_card(cls, v: str) -> str:
        return mask_card_number(v)


# ── Transaction ──

class TransactionResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    transaction_ref: str
    transaction_type: str
    amount: float
    currency: str
    status: str
    description: str | None = None
    merchant: str | None = None
    counterparty: str | None = None
    refund_status: str | None = None
    transaction_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dispute ──

class DisputeCreate(BaseModel):
    customer_message: str = Field(min_length=10, max_length=5000)
    transaction_ref: str | None = None


class DisputeResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    transaction_id: uuid.UUID | None = None
    category: str
    status: str
    priority: str
    customer_message: str
    amount: float | None = None
    classification_confidence: float | None = None
    risk_score: float | None = None
    risk_level: str | None = None
    resolution_summary: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DisputeStatusResponse(BaseModel):
    dispute_id: uuid.UUID
    status: str
    category: str
    priority: str
    risk_level: str | None = None
    resolution_summary: str | None = None
    created_at: datetime
    updated_at: datetime


# ── Classification ──

class ClassificationResult(BaseModel):
    dispute_category: str
    transaction_type: str | None = None
    urgency: str = "MEDIUM"
    confidence: float
    required_information: list[str] = Field(default_factory=list)
    fraud_indicator: bool = False


# ── Rules Engine ──

class RuleResult(BaseModel):
    eligible_for_auto_resolution: bool
    recommended_action: str
    reason_codes: list[str] = Field(default_factory=list)
    required_human_review: bool = False
    risk_level: str = "LOW"


# ── Risk ──

class RiskResult(BaseModel):
    risk_score: float
    risk_level: str
    risk_factors: list[str] = Field(default_factory=list)
    recommended_action: str


# ── Resolution ──

class ResolutionResponse(BaseModel):
    id: uuid.UUID
    dispute_id: uuid.UUID
    resolution_type: str
    action_taken: str
    refund_amount: float | None = None
    reason_codes: list | None = None
    policy_references: list | None = None
    auto_resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Escalation ──

class EscalationCreate(BaseModel):
    reason: str
    priority: str = "MEDIUM"
    assigned_team: str | None = None


class EscalationResponse(BaseModel):
    id: uuid.UUID
    dispute_id: uuid.UUID
    reason: str
    priority: str
    status: str
    assigned_team: str | None = None
    assigned_agent_id: uuid.UUID | None = None
    sla_hours: int
    agent_notes: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EscalationAssign(BaseModel):
    agent_id: uuid.UUID
    team: str | None = None


class EscalationResolve(BaseModel):
    resolution_notes: str = Field(min_length=5)
    resolution_type: str = "MANUAL_RESOLUTION"
    refund_amount: float | None = None


# ── Auth ──

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ── RAG ──

class PolicyChunk(BaseModel):
    content: str
    policy_id: str | None = None
    document_name: str | None = None
    document_version: str | None = None
    category: str | None = None
    page: int | None = None
    section: str | None = None
    score: float | None = None


class RAGResponse(BaseModel):
    query: str
    chunks: list[PolicyChunk]
    found: bool = True


# ── Notification ──

class NotificationResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    dispute_id: uuid.UUID | None = None
    notification_type: str
    template_name: str
    subject: str | None = None
    status: str
    sent_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Audit ──

class AuditLogResponse(BaseModel):
    id: uuid.UUID
    request_id: str | None = None
    dispute_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    actor_type: str
    actor_id: str | None = None
    event_type: str
    event_description: str
    tool_action: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}
