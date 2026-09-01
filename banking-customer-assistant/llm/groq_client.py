import os

ALLOWED_INTENTS = {
    "balance", "transactions", "loan", "policy",
    "transaction_investigation", "dispute_status",
    "block_card", "unblock_card", "raise_complaint",
    "money_transfer",
}

_client = None
_client_checked = False


def _get_client():
    """Lazily build a Groq client. Returns None (never raises) if the API
    key is missing/invalid so the rest of the POC keeps working without it."""
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your-groq-key":
        return None
    try:
        from langchain_groq import ChatGroq
        _client = ChatGroq(model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"), api_key=api_key, temperature=0)
    except Exception:
        _client = None
    return _client


def classify_intent_llm(message: str):
    """Fallback intent disambiguation, used only when the deterministic
    keyword classifier can't decide. Groq may only pick a label from the
    fixed enum below — it never sets risk, authorization, or ownership;
    those always stay in security/risk_policy.py regardless of this output.
    """
    client = _get_client()
    if not client:
        return None
    prompt = (
        "Classify the banking customer message into exactly one of these labels: "
        f"{', '.join(sorted(ALLOWED_INTENTS))}, or 'fallback' if none apply. "
        "Reply with only the label, nothing else.\n\nMessage: " + message
    )
    try:
        result = client.invoke(prompt)
        label = result.content.strip().lower()
        return label if label in ALLOWED_INTENTS else None
    except Exception:
        return None


def generate_rag_answer(question: str, context: str, source: str):
    """Composes the final natural-language answer from retrieved KB context.
    Falls back to the raw retrieved text if Groq is unavailable."""
    client = _get_client()
    if not client:
        return context.strip()
    prompt = (
        "Answer the customer's banking policy question using ONLY the context below. "
        "Be concise (2-3 sentences). If the context doesn't answer the question, say so.\n\n"
        f"Context (from {source}):\n{context}\n\nQuestion: {question}"
    )
    try:
        result = client.invoke(prompt)
        return result.content.strip()
    except Exception:
        return context.strip()
