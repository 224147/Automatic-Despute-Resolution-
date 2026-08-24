"""Dispute classification service – LLM-based with deterministic fallback."""
from __future__ import annotations

import json
import re

from app.core.config import get_settings
from app.core.enums import DisputeCategory
from app.core.logging import get_logger
from app.schemas.schemas import ClassificationResult

logger = get_logger(__name__)

# Deterministic keyword rules for fast/fallback classification
_KEYWORD_RULES: list[tuple[DisputeCategory, list[str], str | None]] = [
    (DisputeCategory.UPI_FAILED, ["upi", "failed", "debit"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "failed", "deduct"], "UPI"),
    (DisputeCategory.UPI_PENDING, ["upi", "pending"], "UPI"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "cash", "not received"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "not dispense"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "debit"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "deduct"], "ATM"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["unauthorized", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["don't recognize", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["do not recognize", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["don't recognize", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["do not recognize", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["fraud", "card"], "CARD"),
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "payment", "failed"], "CARD"),
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "reversed"], "CARD"),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "not received"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "not credited"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "not"], None),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["neft"], "NEFT"),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["rtgs"], "RTGS"),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["imps"], "IMPS"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "incorrect"], "CREDIT_CARD"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "charge"], "CREDIT_CARD"),
    (DisputeCategory.WRONG_BANK_CHARGE, ["wrong", "charge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["wrong", "fee"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["incorrect", "charge"], None),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["loan", "emi"], "LOAN_EMI"),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["emi", "twice"], "LOAN_EMI"),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["emi", "double"], "LOAN_EMI"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "bill"], "CREDIT_CARD"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "incorrect"], "CREDIT_CARD"),
]

FRAUD_KEYWORDS = {"unauthorized", "fraud", "don't recognize", "do not recognize", "stolen", "hack"}


def _deterministic_classify(message: str) -> ClassificationResult | None:
    lower = message.lower()
    for category, keywords, txn_type in _KEYWORD_RULES:
        if all(kw in lower for kw in keywords):
            is_fraud = any(fk in lower for fk in FRAUD_KEYWORDS)
            urgency = "HIGH" if is_fraud else "MEDIUM"
            return ClassificationResult(
                dispute_category=category.value,
                transaction_type=txn_type,
                urgency=urgency,
                confidence=0.85,
                fraud_indicator=is_fraud,
            )
    return None


_CLASSIFICATION_PROMPT = """You are a banking dispute classifier. Classify the customer complaint into exactly one category.

Categories:
- UPI_FAILED: UPI transaction failed but amount debited
- UPI_PENDING: UPI transaction still pending
- ATM_CASH_NOT_RECEIVED: ATM did not dispense cash but account debited
- UNAUTHORIZED_CARD_TRANSACTION: Unrecognized/unauthorized card transaction
- CARD_PAYMENT_FAILED: Card payment failed or reversed but charged
- REFUND_NOT_RECEIVED: Refund not received for returned items/cancelled services
- NEFT_RTGS_IMPS_ISSUE: NEFT/RTGS/IMPS transfer issue
- WRONG_BANK_CHARGE: Incorrect bank fee or charge
- LOAN_EMI_DISPUTE: Loan EMI related dispute
- CREDIT_CARD_BILLING_DISPUTE: Credit card billing issue
- UNKNOWN: Cannot determine category

Respond ONLY with valid JSON:
{
    "dispute_category": "<category>",
    "transaction_type": "<UPI|ATM|CARD|NEFT|RTGS|IMPS|LOAN_EMI|CREDIT_CARD|OTHER|null>",
    "urgency": "<LOW|MEDIUM|HIGH|CRITICAL>",
    "confidence": <0.0 to 1.0>,
    "required_information": ["<list of missing info needed>"],
    "fraud_indicator": <true|false>
}

Customer complaint: {message}
"""


async def classify_dispute(message: str) -> ClassificationResult:
    # Try deterministic first
    det_result = _deterministic_classify(message)
    if det_result:
        logger.info("classification_deterministic", category=det_result.dispute_category)
        return det_result

    # LLM-based classification
    settings = get_settings()
    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.openai_api_key,
        )
        prompt = _CLASSIFICATION_PROMPT.format(message=message)
        response = await llm.ainvoke(prompt)
        content = response.content.strip()

        # Extract JSON from response
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            result = ClassificationResult(**data)
            logger.info("classification_llm", category=result.dispute_category, confidence=result.confidence)
            return result
    except Exception as e:
        logger.error("classification_llm_error", error=str(e))

    # Fallback to UNKNOWN
    return ClassificationResult(
        dispute_category=DisputeCategory.UNKNOWN.value,
        transaction_type=None,
        urgency="MEDIUM",
        confidence=0.0,
        required_information=["Unable to classify - needs human review"],
        fraud_indicator=False,
    )
