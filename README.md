# Automated Dispute Resolution — POC

A small POC that auto-resolves exactly one class of bank dispute — `exact_duplicate` —
under a strict deterministic policy, and escalates everything else to a human analyst.

Claude classifies and explains. Plain Python rules decide whether money moves.
Claude is never able to call the Payments API directly.

## Flow

1. Customer submits a dispute (`transaction_id`, `description`, `amount_usd`).
2. A case is created (or an existing open case for that `transaction_id` is reused).
3. Evidence is gathered from the Transaction API and Merchant API (read-only).
4. Evidence + description are sent to Claude, which returns:
   `{dispute_type, confidence, rationale}`.
5. `dispute_rules.evaluate_decision` applies deterministic policy from `config.yaml`.
   Auto-resolve only if **all** hold:
   - `dispute_type` is in `ELIGIBLE_TYPES` (only `exact_duplicate` today)
   - `amount_usd <= AUTO_RESOLVE_MAX_USD`
   - `confidence >= MIN_CONFIDENCE`
6. Auto-resolve → provisional credit issued, case marked `resolved`, customer notified.
   Any failed condition → case marked `escalated`, assigned to the Human Analyst Review
   Queue with evidence + Claude's rationale attached, customer notified it's under review.
7. Every case produces one audit record in `audit_log.jsonl`.

External API failures (Transaction/Merchant/Claude/Case Management) retry once, then
escalate — never auto-resolve — and are recorded in the audit log.

## Project layout

| File | Responsibility |
|---|---|
| `main.py` | Orchestrates the end-to-end flow |
| `adapters.py` | Transaction API, Merchant API, Case Management, Payments/Ledger, Analyst Queue, Notifications |
| `agent_client.py` | The only module that calls Claude; classification only, no eligibility rules |
| `dispute_rules.py` | Pure deterministic decision engine, no external calls |
| `actions.py` | Executes `issue_provisional_credit` / `escalate_to_analyst` |
| `audit_logger.py` | Append-only audit trail |
| `config.py` / `config.yaml` | Policy configuration |
| `models.py` | `DisputeCase`, `AgentResult`, `DecisionResult` |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cp .env.example .env         # add your ANTHROPIC_API_KEY
```

## Run

```bash
python main.py
```

## Test

```bash
pytest
```

Tests mock Claude and the external adapters — no real API calls or credentials needed.

## Invariants

- The Payments API is only ever reached from `actions.issue_provisional_credit`,
  which is only ever called when `dispute_rules.evaluate_decision` returns `auto_resolve`.
- Every failed eligibility condition results in escalation, never a partial approval.
- Claude never decides whether a credit is issued — it only classifies and explains.

## Scope

This is a POC, not a production system: no database, no queue, no containers — plain
Python modules with in-memory/mocked adapters, matching the size of the actual problem
being solved (one auto-eligible dispute type).
