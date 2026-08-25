"""LangGraph graph builder – wires nodes with conditional edges."""
from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from app.workflows.nodes import (
    DisputeState,
    assess_risk_node,
    audit_node,
    authenticate_customer_node,
    classify_dispute_node,
    escalation_node,
    evaluate_rules_node,
    execute_safe_action_node,
    identify_transaction_node,
    intake_node,
    notification_node,
    resolution_decision_node,
    retrieve_policy_node,
    verify_transaction_node,
)


def _route_after_classify(state: DisputeState) -> str:
    if state.get("classification_confidence", 0) < 0.5:
        return "escalation_node"
    if state.get("dispute_category") == "UNKNOWN":
        return "escalation_node"
    return "authenticate_customer_node"


def _route_after_auth(state: DisputeState) -> str:
    if not state.get("customer_verified", False):
        return "escalation_node"
    return "identify_transaction_node"


def _route_after_identify(state: DisputeState) -> str:
    if not state.get("transaction_verified", False) and not state.get("transaction_id"):
        # Proceed to policy retrieval even without a matched transaction
        return "retrieve_policy_node"
    return "verify_transaction_node"


def _route_after_decision(state: DisputeState) -> str:
    if state.get("resolution_decision") == "AUTO_RESOLVE":
        return "execute_safe_action_node"
    return "escalation_node"


def build_dispute_graph(db_session) -> StateGraph:
    """Build the compiled LangGraph workflow, binding db to every node."""

    graph = StateGraph(DisputeState)

    # Bind db session to each node
    graph.add_node("intake_node", partial(_wrap, intake_node, db_session))
    graph.add_node("classify_dispute_node", partial(_wrap, classify_dispute_node, db_session))
    graph.add_node("authenticate_customer_node", partial(_wrap, authenticate_customer_node, db_session))
    graph.add_node("identify_transaction_node", partial(_wrap, identify_transaction_node, db_session))
    graph.add_node("verify_transaction_node", partial(_wrap, verify_transaction_node, db_session))
    graph.add_node("retrieve_policy_node", partial(_wrap, retrieve_policy_node, db_session))
    graph.add_node("evaluate_rules_node", partial(_wrap, evaluate_rules_node, db_session))
    graph.add_node("assess_risk_node", partial(_wrap, assess_risk_node, db_session))
    graph.add_node("resolution_decision_node", partial(_wrap, resolution_decision_node, db_session))
    graph.add_node("execute_safe_action_node", partial(_wrap, execute_safe_action_node, db_session))
    graph.add_node("escalation_node", partial(_wrap, escalation_node, db_session))
    graph.add_node("notification_node", partial(_wrap, notification_node, db_session))
    graph.add_node("audit_node", partial(_wrap, audit_node, db_session))

    # Edges
    graph.set_entry_point("intake_node")
    graph.add_edge("intake_node", "classify_dispute_node")

    graph.add_conditional_edges("classify_dispute_node", _route_after_classify, {
        "authenticate_customer_node": "authenticate_customer_node",
        "escalation_node": "escalation_node",
    })

    graph.add_conditional_edges("authenticate_customer_node", _route_after_auth, {
        "identify_transaction_node": "identify_transaction_node",
        "escalation_node": "escalation_node",
    })

    graph.add_conditional_edges("identify_transaction_node", _route_after_identify, {
        "verify_transaction_node": "verify_transaction_node",
        "retrieve_policy_node": "retrieve_policy_node",
        "escalation_node": "escalation_node",
    })

    graph.add_edge("verify_transaction_node", "retrieve_policy_node")
    graph.add_edge("retrieve_policy_node", "evaluate_rules_node")
    graph.add_edge("evaluate_rules_node", "assess_risk_node")
    graph.add_edge("assess_risk_node", "resolution_decision_node")

    graph.add_conditional_edges("resolution_decision_node", _route_after_decision, {
        "execute_safe_action_node": "execute_safe_action_node",
        "escalation_node": "escalation_node",
    })

    graph.add_edge("execute_safe_action_node", "notification_node")
    graph.add_edge("escalation_node", "notification_node")
    graph.add_edge("notification_node", "audit_node")
    graph.add_edge("audit_node", END)

    return graph.compile()


async def _wrap(node_fn, db, state: DisputeState) -> dict:
    """Wrapper that passes db to node functions and handles errors."""
    try:
        return await node_fn(state, db)
    except Exception as e:
        from app.core.logging import get_logger
        logger = get_logger("workflow")
        logger.error("node_error", node=node_fn.__name__, error=str(e))
        errors = list(state.get("errors", []))
        errors.append(f"{node_fn.__name__}: {str(e)}")
        return {"errors": errors, "final_response": f"An error occurred during processing: {str(e)}"}
