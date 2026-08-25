"""Append-only audit trail. Every case produces one JSON line."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from models import AgentResult, DecisionResult, DisputeCase

_DEFAULT_LOG_PATH = Path(__file__).parent / "audit_log.jsonl"


def log_decision(
    case: DisputeCase,
    evidence_complete: bool,
    agent_result: AgentResult | None,
    decision: DecisionResult,
    action_taken: str,
    config: dict,
    log_path: Path | str = _DEFAULT_LOG_PATH,
) -> dict:
    record = {
        "case_id": case.case_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "evidence_complete": evidence_complete,
        "agent_result": asdict(agent_result) if agent_result else None,
        "decision": asdict(decision),
        "action_taken": action_taken,
        "config_snapshot": {
            "AUTO_RESOLVE_MAX_USD": config["AUTO_RESOLVE_MAX_USD"],
            "MIN_CONFIDENCE": config["MIN_CONFIDENCE"],
            "ELIGIBLE_TYPES": config["ELIGIBLE_TYPES"],
        },
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return record
