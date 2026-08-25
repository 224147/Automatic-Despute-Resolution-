from unittest.mock import patch

import pytest

import agent_client
from agent_client import AgentUnavailableError, classify_dispute


def test_malformed_response_retries_then_escalates():
    with patch.object(agent_client, "_call_llm", side_effect=["not json", "still not json"]):
        with pytest.raises(AgentUnavailableError):
            classify_dispute("desc", {}, {})


def test_missing_fields_retries_then_escalates():
    with patch.object(agent_client, "_call_llm", return_value='{"dispute_type": "exact_duplicate"}'):
        with pytest.raises(AgentUnavailableError):
            classify_dispute("desc", {}, {})


def test_invalid_confidence_retries_then_escalates():
    bad = '{"dispute_type": "exact_duplicate", "confidence": 5, "rationale": "x"}'
    with patch.object(agent_client, "_call_llm", return_value=bad):
        with pytest.raises(AgentUnavailableError):
            classify_dispute("desc", {}, {})


def test_unknown_dispute_type_retries_then_escalates():
    bad = '{"dispute_type": "not_real", "confidence": 0.9, "rationale": "x"}'
    with patch.object(agent_client, "_call_llm", return_value=bad):
        with pytest.raises(AgentUnavailableError):
            classify_dispute("desc", {}, {})


def test_success_on_first_attempt():
    good = '{"dispute_type": "exact_duplicate", "confidence": 0.95, "rationale": "matches prior charge"}'
    with patch.object(agent_client, "_call_llm", return_value=good) as mock_call:
        result = classify_dispute("desc", {}, {})
    assert result.dispute_type == "exact_duplicate"
    assert result.confidence == 0.95
    assert mock_call.call_count == 1


def test_recovers_on_second_attempt():
    good = '{"dispute_type": "exact_duplicate", "confidence": 0.95, "rationale": "matches prior charge"}'
    with patch.object(agent_client, "_call_llm", side_effect=["bad json", good]):
        result = classify_dispute("desc", {}, {})
    assert result.dispute_type == "exact_duplicate"
