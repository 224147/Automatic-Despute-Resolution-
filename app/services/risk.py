"""Risk/fraud assessment module – deterministic scoring, ML-ready interface."""
from __future__ import annotations

from app.core.enums import DisputeCategory, RiskLevel, TransactionType
from app.core.logging import get_logger

logger = get_logger(__name__)


def assess_risk(
    *,
    amount: float,
    transaction_type: str | None,
    transaction_status: str | None,
    dispute_category: str,
    customer_dispute_frequency: int,
    fraud_indicator: bool,
    customer_verified: bool,
    transaction_age_days: int | None = None,
) -> dict:
    """
    Deterministic risk scoring. Returns dict with risk_score, risk_level,
    risk_factors, recommended_action. Designed so an ML model (XGBoost etc.)
    can replace or augment this later.
    """
    score = 0.0
    factors: list[str] = []

    # ── Amount-based scoring ──
    if amount > 100000:
        score += 35
        factors.append(f"Very high amount: INR {amount:,.2f}")
    elif amount > 50000:
        score += 25
        factors.append(f"High amount: INR {amount:,.2f}")
    elif amount > 25000:
        score += 15
        factors.append(f"Medium-high amount: INR {amount:,.2f}")
    elif amount > 10000:
        score += 8
        factors.append(f"Medium amount: INR {amount:,.2f}")

    # ── Fraud indicator ──
    if fraud_indicator:
        score += 30
        factors.append("Fraud indicator present")

    # ── Authentication ──
    if not customer_verified:
        score += 20
        factors.append("Customer not verified")

    # ── Dispute frequency ──
    if customer_dispute_frequency >= 5:
        score += 15
        factors.append(f"High dispute frequency: {customer_dispute_frequency} in 90 days")
    elif customer_dispute_frequency >= 3:
        score += 8
        factors.append(f"Moderate dispute frequency: {customer_dispute_frequency} in 90 days")

    # ── Category-specific ──
    if dispute_category == DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION.value:
        score += 20
        factors.append("Unauthorized card transaction category")
    elif dispute_category == DisputeCategory.ATM_CASH_NOT_RECEIVED.value and amount > 25000:
        score += 10
        factors.append("High-value ATM dispute")

    # ── Transaction type ──
    if transaction_type in (TransactionType.CARD.value, TransactionType.CREDIT_CARD.value):
        score += 5
        factors.append("Card-based transaction")

    # ── Transaction age ──
    if transaction_age_days is not None:
        if transaction_age_days > 30:
            score += 10
            factors.append(f"Old transaction: {transaction_age_days} days")
        elif transaction_age_days > 14:
            score += 5
            factors.append(f"Moderately old transaction: {transaction_age_days} days")

    # ── Determine risk level ──
    score = min(score, 100.0)
    if score >= 70:
        level = RiskLevel.CRITICAL.value
        action = "BLOCK_AND_ESCALATE"
    elif score >= 50:
        level = RiskLevel.HIGH.value
        action = "ESCALATE_FOR_REVIEW"
    elif score >= 30:
        level = RiskLevel.MEDIUM.value
        action = "PROCEED_WITH_CAUTION"
    else:
        level = RiskLevel.LOW.value
        action = "PROCEED"

    logger.info(
        "risk_assessed",
        score=score, level=level,
        factors_count=len(factors),
        category=dispute_category,
    )

    return {
        "risk_score": round(score, 2),
        "risk_level": level,
        "risk_factors": factors,
        "recommended_action": action,
    }
