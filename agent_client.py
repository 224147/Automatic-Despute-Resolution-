"""The only module that calls the LLM (Groq). Classification and reasoning only —
no eligibility rules and no financial decisions live here.
"""
from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from models import AgentResult

load_dotenv()

VALID_DISPUTE_TYPES = {"exact_duplicate", "merchant_error", "suspected_fraud", "other"}

_SYSTEM_PROMPT = """You are a dispute classification assistant for a bank's dispute resolution system.

Given a customer's dispute description and transaction/merchant evidence, classify the dispute.

You must respond with ONLY a JSON object matching this schema, nothing else:
{
  "dispute_type": one of "exact_duplicate", "merchant_error", "suspected_fraud", "other",
  "confidence": a number between 0.0 and 1.0,
  "rationale": a short plain-English explanation
}

You classify and explain only. You do NOT decide whether a credit should be issued,
you do NOT make the final financial decision, and you must NOT override bank policy.
That decision is made separately by deterministic business rules.
"""


class AgentUnavailableError(Exception):
    """Raised when the LLM fails, times out, or returns an unusable response after retrying."""


def _build_user_message(
    description: str, transaction_evidence: dict[str, Any], merchant_evidence: dict[str, Any]
) -> str:
    return (
        f"Customer dispute description:\n{description}\n\n"
        f"Transaction evidence:\n{json.dumps(transaction_evidence, default=str)}\n\n"
        f"Merchant evidence:\n{json.dumps(merchant_evidence, default=str)}"
    )


def _parse_response(raw_text: str) -> AgentResult:
    data = json.loads(raw_text)

    dispute_type = data["dispute_type"]
    confidence = data["confidence"]
    rationale = data["rationale"]

    if dispute_type not in VALID_DISPUTE_TYPES:
        raise ValueError(f"unknown dispute_type: {dispute_type}")
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        raise ValueError(f"invalid confidence: {confidence}")
    if not isinstance(rationale, str) or not rationale:
        raise ValueError("missing rationale")

    return AgentResult(dispute_type=dispute_type, confidence=float(confidence), rationale=rationale)


def _call_llm(description: str, transaction_evidence: dict[str, Any], merchant_evidence: dict[str, Any]) -> str:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    completion = client.chat.completions.create(
        model=model,
        max_tokens=512,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(description, transaction_evidence, merchant_evidence)},
        ],
    )
    return completion.choices[0].message.content


def classify_dispute(
    description: str,
    transaction_evidence: dict[str, Any],
    merchant_evidence: dict[str, Any],
) -> AgentResult:
    """Classify a dispute via the LLM. Retries once on any failure; escalates via
    AgentUnavailableError if the second attempt also fails.
    """
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            raw_text = _call_llm(description, transaction_evidence, merchant_evidence)
            return _parse_response(raw_text)
        except Exception as exc:  # noqa: BLE001 - any failure mode triggers the same retry-once policy
            last_error = exc
            continue

    raise AgentUnavailableError("classification unavailable") from last_error
