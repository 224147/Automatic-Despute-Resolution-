from rag.retrieval import answer_policy, THRESHOLD


def test_high_confidence_answers_from_retrieved_context():
    result = answer_policy("What is the minimum balance for a savings account?")
    assert result["confidence"] >= THRESHOLD
    assert result["route"] == "RAG Agent"
    assert result["source"] == "savings_policy.md"


def test_low_confidence_falls_back_without_calling_groq():
    result = answer_policy("What is the weather like today?")
    assert result["confidence"] < THRESHOLD
    assert result["route"] == "Fallback"
    assert result["source"] is None
