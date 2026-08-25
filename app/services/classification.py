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
    # UPI
    (DisputeCategory.UPI_FAILED, ["upi", "failed", "debit"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "failed", "deduct"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "failed"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "debit"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "deduct"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "not received"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "not credited"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "money", "gone"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "amount", "debit"], "UPI"),
    (DisputeCategory.UPI_FAILED, ["upi", "amount", "deduct"], "UPI"),
    (DisputeCategory.UPI_PENDING, ["upi", "pending"], "UPI"),
    (DisputeCategory.UPI_PENDING, ["upi", "processing"], "UPI"),
    (DisputeCategory.UPI_PENDING, ["upi", "stuck"], "UPI"),
    # ATM
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "cash", "not received"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "not dispense"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "debit"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "deduct"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "not give"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "didn't get"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "did not get"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "no cash"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "cash not"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "money not"], "ATM"),
    (DisputeCategory.ATM_CASH_NOT_RECEIVED, ["atm", "withdraw", "fail"], "ATM"),
    # Unauthorized card
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["unauthorized", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["unauthorized", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["unauthorised", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["unauthorised", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["don't recognize", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["do not recognize", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["don't recognize", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["do not recognize", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["didn't make", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["did not make", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["fraud", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["fraud", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["stolen", "card"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["hack"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["unknown", "transaction"], "CARD"),
    (DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION, ["suspicious", "transaction"], "CARD"),
    # Card payment failed
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "payment", "failed"], "CARD"),
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "reversed"], "CARD"),
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "failed"], "CARD"),
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "declined", "charged"], "CARD"),
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "debit", "fail"], "CARD"),
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "deduct", "fail"], "CARD"),
    (DisputeCategory.CARD_PAYMENT_FAILED, ["card", "charged", "fail"], "CARD"),
    # Refund
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "not received"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "not credited"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "not"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "pending"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "hasn't"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["refund", "waiting"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["return", "refund"], None),
    (DisputeCategory.REFUND_NOT_RECEIVED, ["cancel", "refund"], None),
    # NEFT/RTGS/IMPS
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["neft"], "NEFT"),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["rtgs"], "RTGS"),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["imps"], "IMPS"),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["bank transfer", "fail"], None),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["fund transfer", "fail"], None),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["transfer", "fail", "debit"], None),
    (DisputeCategory.NEFT_RTGS_IMPS_ISSUE, ["transfer", "fail", "deduct"], None),
    # Credit card billing
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "incorrect"], "CREDIT_CARD"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "charge"], "CREDIT_CARD"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "bill"], "CREDIT_CARD"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "wrong"], "CREDIT_CARD"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "overcharg"], "CREDIT_CARD"),
    (DisputeCategory.CREDIT_CARD_BILLING_DISPUTE, ["credit card", "dispute"], "CREDIT_CARD"),
    # Loan EMI
    (DisputeCategory.LOAN_EMI_DISPUTE, ["loan", "emi"], "LOAN_EMI"),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["emi", "twice"], "LOAN_EMI"),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["emi", "double"], "LOAN_EMI"),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["emi", "extra"], "LOAN_EMI"),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["emi", "wrong"], "LOAN_EMI"),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["emi", "incorrect"], "LOAN_EMI"),
    (DisputeCategory.LOAN_EMI_DISPUTE, ["loan", "deduct"], "LOAN_EMI"),
    # Wrong bank charge
    (DisputeCategory.WRONG_BANK_CHARGE, ["wrong", "charge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["wrong", "fee"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["incorrect", "charge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["incorrect", "fee"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["extra", "charge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["unnecessary", "charge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["hidden", "charge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["charged", "twice"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["charged", "double"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["double", "charge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["duplicate", "charge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["charged", "two times"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["overcharge"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["charged", "more"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["charged", "extra"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["duplicate", "debit"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["duplicate", "deduct"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["debited", "twice"], None),
    (DisputeCategory.WRONG_BANK_CHARGE, ["deducted", "twice"], None),
]

FRAUD_KEYWORDS = {
    "unauthorized",
    "unauthorised",
    "fraud",
    "don't recognize",
    "do not recognize",
    "stolen",
    "hack",
    "suspicious",
}

# Map policy document names to dispute categories
_POLICY_CATEGORY_MAP = {
    "upi_policy": DisputeCategory.UPI_FAILED,
    "atm_policy": DisputeCategory.ATM_CASH_NOT_RECEIVED,
    "card_policy": DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION,
    "general_policy": DisputeCategory.UNKNOWN,
}

_CATEGORY_KEYWORDS_MAP = {
    "upi": DisputeCategory.UPI_FAILED,
    "atm": DisputeCategory.ATM_CASH_NOT_RECEIVED,
    "card": DisputeCategory.CARD_PAYMENT_FAILED,
    "credit card": DisputeCategory.CREDIT_CARD_BILLING_DISPUTE,
    "refund": DisputeCategory.REFUND_NOT_RECEIVED,
    "neft": DisputeCategory.NEFT_RTGS_IMPS_ISSUE,
    "rtgs": DisputeCategory.NEFT_RTGS_IMPS_ISSUE,
    "imps": DisputeCategory.NEFT_RTGS_IMPS_ISSUE,
    "emi": DisputeCategory.LOAN_EMI_DISPUTE,
    "loan": DisputeCategory.LOAN_EMI_DISPUTE,
    "charged twice": DisputeCategory.WRONG_BANK_CHARGE,
    "double charge": DisputeCategory.WRONG_BANK_CHARGE,
    "duplicate charge": DisputeCategory.WRONG_BANK_CHARGE,
    "overcharge": DisputeCategory.WRONG_BANK_CHARGE,
    "wrong charge": DisputeCategory.WRONG_BANK_CHARGE,
    "extra charge": DisputeCategory.WRONG_BANK_CHARGE,
    "charge": DisputeCategory.WRONG_BANK_CHARGE,
    "fee": DisputeCategory.WRONG_BANK_CHARGE,
}


def _classify_from_policy_chunks(message: str, chunks) -> ClassificationResult | None:
    """Classify using retrieved policy chunks by matching document source."""
    lower = message.lower()
    is_fraud = any(fk in lower for fk in FRAUD_KEYWORDS)

    # Check message keywords first (more reliable than hash-based document matching)
    for keyword, category in _CATEGORY_KEYWORDS_MAP.items():
        if keyword in lower:
            txn_type = keyword.upper() if keyword in ("upi", "atm", "neft", "rtgs", "imps") else None
            return ClassificationResult(
                dispute_category=category.value,
                transaction_type=txn_type,
                urgency="HIGH" if is_fraud else "MEDIUM",
                confidence=0.70,
                fraud_indicator=is_fraud,
            )

    # Fallback: match from policy document name
    for chunk in chunks:
        source = (chunk.document_name or "").lower().replace(".md", "")
        for key, category in _POLICY_CATEGORY_MAP.items():
            if key in source and category != DisputeCategory.UNKNOWN:
                txn_type = category.value.split("_")[0] if "_" in category.value else None
                return ClassificationResult(
                    dispute_category=category.value,
                    transaction_type=txn_type,
                    urgency="HIGH" if is_fraud else "MEDIUM",
                    confidence=0.60,
                    fraud_indicator=is_fraud,
                )

    return None


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


_CLASSIFICATION_PROMPT = """You are a banking dispute classifier.
Classify the customer complaint into exactly one category.

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

    # RAG-based classification: use local policy documents to find best category
    try:
        from app.rag.pipeline import retrieve_policies
        rag_result = await retrieve_policies(message, top_k=3)
        if rag_result.found and rag_result.chunks:
            rag_category = _classify_from_policy_chunks(message, rag_result.chunks)
            if rag_category:
                logger.info("classification_rag", category=rag_category.dispute_category)
                return rag_category
    except Exception as e:
        logger.error("classification_rag_error", error=str(e))

    # LLM-based classification (if API key available)
    settings = get_settings()
    try:
        llm = None
        if settings.llm_provider == "groq" and settings.groq_api_key:
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.groq_api_key,
            )
        elif settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.openai_api_key,
            )
        if llm:
            prompt = _CLASSIFICATION_PROMPT.format(message=message)
            response = await llm.ainvoke(prompt)
            content = response.content.strip()
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
