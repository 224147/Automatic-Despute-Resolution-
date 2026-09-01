from typing import Any, Optional, TypedDict


class GraphState(TypedDict, total=False):
    message: str
    customer_id: str
    intent: str
    risk: str
    route: str
    agent: str
    agent_result: Any
    response: Any
    rag_confidence: Optional[float]
    idempotency_key: Optional[str]
    idempotency_result: Optional[str]
    authorization: str
    ownership: str
    events: list
    current_step: str
    guardrail: str
    context: dict
