"""Deterministic banking dispute rules engine – operates independently from the LLM."""
from __future__ import annotations

from app.core.enums import DisputeCategory, RiskLevel, TransactionStatus
from app.core.logging import get_logger
from app.schemas.schemas import RuleResult

logger = get_logger(__name__)

# Amount thresholds (INR)
_UPI_AUTO_LIMIT = 25000
_ATM_AUTO_LIMIT = 15000
_CARD_FAILED_AUTO_LIMIT = 10000
_NEFT_AUTO_LIMIT = 50000
_CHARGE_AUTO_LIMIT = 5000
_LOAN_AUTO_LIMIT = 25000
_CREDIT_CARD_AUTO_LIMIT = 5000


def evaluate_rules(
    category: str,
    amount: float | None,
    transaction_status: str | None,
    customer_verified: bool,
    previous_dispute_count: int,
    fraud_indicator: bool,
    policy_found: bool,
    transaction_age_days: int | None = None,
) -> RuleResult:
    """Evaluate deterministic rules for a dispute. The LLM must never override this."""

    reason_codes: list[str] = []

    # ── Gate checks ──
    if not customer_verified:
        return RuleResult(
            eligible_for_auto_resolution=False,
            recommended_action="ESCALATE",
            reason_codes=["CUSTOMER_NOT_VERIFIED"],
            required_human_review=True,
            risk_level=RiskLevel.HIGH.value,
        )

    if fraud_indicator:
        return RuleResult(
            eligible_for_auto_resolution=False,
            recommended_action="ESCALATE_FRAUD",
            reason_codes=["FRAUD_INDICATOR_DETECTED"],
            required_human_review=True,
            risk_level=RiskLevel.CRITICAL.value,
        )

    if not policy_found:
        return RuleResult(
            eligible_for_auto_resolution=False,
            recommended_action="ESCALATE",
            reason_codes=["NO_POLICY_FOUND"],
            required_human_review=True,
            risk_level=RiskLevel.MEDIUM.value,
        )

    if previous_dispute_count >= 5:
        reason_codes.append("REPEATED_DISPUTE_FLAG")

    safe_amount = amount or 0.0

    # ── Category-specific rules ──
    if category == DisputeCategory.UPI_FAILED.value:
        return _rule_upi_failed(safe_amount, transaction_status, reason_codes)

    if category == DisputeCategory.UPI_PENDING.value:
        return _rule_upi_pending(safe_amount, transaction_status, transaction_age_days, reason_codes)

    if category == DisputeCategory.ATM_CASH_NOT_RECEIVED.value:
        return _rule_atm_cash(safe_amount, transaction_status, reason_codes)

    if category == DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION.value:
        return _rule_unauthorized_card(safe_amount, reason_codes)

    if category == DisputeCategory.CARD_PAYMENT_FAILED.value:
        return _rule_card_failed(safe_amount, transaction_status, reason_codes)

    if category == DisputeCategory.REFUND_NOT_RECEIVED.value:
        return _rule_refund(safe_amount, transaction_age_days, reason_codes)

    if category == DisputeCategory.NEFT_RTGS_IMPS_ISSUE.value:
        return _rule_neft(safe_amount, transaction_status, reason_codes)

    if category == DisputeCategory.WRONG_BANK_CHARGE.value:
        return _rule_wrong_charge(safe_amount, reason_codes)

    if category == DisputeCategory.LOAN_EMI_DISPUTE.value:
        return _rule_loan_emi(safe_amount, reason_codes)

    if category == DisputeCategory.CREDIT_CARD_BILLING_DISPUTE.value:
        return _rule_credit_card_billing(safe_amount, reason_codes)

    # UNKNOWN or unhandled
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="ESCALATE",
        reason_codes=["UNKNOWN_CATEGORY"] + reason_codes,
        required_human_review=True,
        risk_level=RiskLevel.MEDIUM.value,
    )


def _rule_upi_failed(amount: float, txn_status: str | None, rc: list[str]) -> RuleResult:
    if txn_status not in (TransactionStatus.FAILED.value, TransactionStatus.REVERSED.value, None):
        rc.append("TRANSACTION_NOT_FAILED")
        return RuleResult(
            eligible_for_auto_resolution=False,
            recommended_action="ESCALATE",
            reason_codes=rc,
            required_human_review=True,
            risk_level=RiskLevel.MEDIUM.value,
        )
    if amount <= _UPI_AUTO_LIMIT:
        rc.append("UPI_WITHIN_AUTO_LIMIT")
        return RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="AUTO_REFUND",
            reason_codes=rc,
            risk_level=RiskLevel.LOW.value,
        )
    if amount <= 100000:
        rc.append("UPI_SYSTEM_VERIFY")
        return RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="REFUND_WITH_VERIFICATION",
            reason_codes=rc,
            risk_level=RiskLevel.MEDIUM.value,
        )
    rc.append("UPI_HIGH_VALUE")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="MANUAL_REVIEW",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.HIGH.value,
    )


def _rule_upi_pending(
    amount: float, txn_status: str | None, age_days: int | None, rc: list[str]
) -> RuleResult:
    age = age_days or 0
    if amount <= 10000 and age >= 2:
        rc.append("UPI_PENDING_AUTO_REVERSE")
        return RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="AUTO_REFUND",
            reason_codes=rc,
            risk_level=RiskLevel.LOW.value,
        )
    rc.append("UPI_PENDING_ESCALATE")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="ESCALATE",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.MEDIUM.value,
    )


def _rule_atm_cash(amount: float, txn_status: str | None, rc: list[str]) -> RuleResult:
    if amount <= _ATM_AUTO_LIMIT:
        rc.append("ATM_WITHIN_AUTO_LIMIT")
        return RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="AUTO_REFUND",
            reason_codes=rc,
            risk_level=RiskLevel.LOW.value,
        )
    if amount <= 50000:
        rc.append("ATM_SYSTEM_VERIFY")
        return RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="REFUND_WITH_VERIFICATION",
            reason_codes=rc,
            risk_level=RiskLevel.MEDIUM.value,
        )
    rc.append("ATM_HIGH_VALUE")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="MANUAL_REVIEW",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.HIGH.value,
    )


def _rule_unauthorized_card(amount: float, rc: list[str]) -> RuleResult:
    # Unauthorized card transactions are NEVER auto-resolved per policy
    rc.append("UNAUTHORIZED_CARD_NO_AUTO")
    risk = RiskLevel.HIGH.value if amount <= 50000 else RiskLevel.CRITICAL.value
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="ESCALATE_FRAUD",
        reason_codes=rc,
        required_human_review=True,
        risk_level=risk,
    )


def _rule_card_failed(amount: float, txn_status: str | None, rc: list[str]) -> RuleResult:
    if txn_status in (TransactionStatus.FAILED.value, TransactionStatus.REVERSED.value):
        if amount <= _CARD_FAILED_AUTO_LIMIT:
            rc.append("CARD_FAILED_AUTO_REVERSE")
            return RuleResult(
                eligible_for_auto_resolution=True,
                recommended_action="AUTO_REFUND",
                reason_codes=rc,
                risk_level=RiskLevel.LOW.value,
            )
    rc.append("CARD_FAILED_MANUAL")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="MANUAL_REVIEW",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.MEDIUM.value,
    )


def _rule_refund(amount: float, age_days: int | None, rc: list[str]) -> RuleResult:
    age = age_days or 0
    if age > 10:
        rc.append("REFUND_OVERDUE")
        if amount <= _CHARGE_AUTO_LIMIT:
            return RuleResult(
                eligible_for_auto_resolution=True,
                recommended_action="AUTO_CREDIT",
                reason_codes=rc,
                risk_level=RiskLevel.LOW.value,
            )
    rc.append("REFUND_ESCALATE")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="ESCALATE",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.MEDIUM.value,
    )


def _rule_neft(amount: float, txn_status: str | None, rc: list[str]) -> RuleResult:
    if txn_status in (TransactionStatus.FAILED.value, TransactionStatus.REVERSED.value):
        if amount <= _NEFT_AUTO_LIMIT:
            rc.append("NEFT_AUTO_REVERSE")
            return RuleResult(
                eligible_for_auto_resolution=True,
                recommended_action="AUTO_REFUND",
                reason_codes=rc,
                risk_level=RiskLevel.LOW.value,
            )
    rc.append("NEFT_MANUAL")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="MANUAL_REVIEW",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.HIGH.value,
    )


def _rule_wrong_charge(amount: float, rc: list[str]) -> RuleResult:
    if amount <= _CHARGE_AUTO_LIMIT:
        rc.append("CHARGE_AUTO_REVERSE")
        return RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="AUTO_REFUND",
            reason_codes=rc,
            risk_level=RiskLevel.LOW.value,
        )
    rc.append("CHARGE_MANUAL")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="MANUAL_REVIEW",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.MEDIUM.value,
    )


def _rule_loan_emi(amount: float, rc: list[str]) -> RuleResult:
    if amount <= _LOAN_AUTO_LIMIT:
        rc.append("LOAN_EMI_AUTO")
        return RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="AUTO_REFUND",
            reason_codes=rc,
            risk_level=RiskLevel.LOW.value,
        )
    rc.append("LOAN_EMI_ESCALATE")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="ESCALATE",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.HIGH.value,
    )


def _rule_credit_card_billing(amount: float, rc: list[str]) -> RuleResult:
    if amount <= _CREDIT_CARD_AUTO_LIMIT:
        rc.append("CC_BILLING_AUTO")
        return RuleResult(
            eligible_for_auto_resolution=True,
            recommended_action="AUTO_REFUND",
            reason_codes=rc,
            risk_level=RiskLevel.LOW.value,
        )
    rc.append("CC_BILLING_MANUAL")
    return RuleResult(
        eligible_for_auto_resolution=False,
        recommended_action="MANUAL_REVIEW",
        reason_codes=rc,
        required_human_review=True,
        risk_level=RiskLevel.MEDIUM.value,
    )
