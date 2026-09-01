from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    message: str
    customer_id: str
    intent: str
    risk: str
    route: str
    agent: str
    agent_result: Any
    response: Any
    rag_confidence: float | None
    idempotency_key: str | None
    idempotency_result: str | None
    authorization: str
    ownership: str
    events: list
    current_step: str
    guardrail: str
    context: dict
