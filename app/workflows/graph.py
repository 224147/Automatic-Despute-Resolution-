"""LangGraph multi-agent graph — supervisor routes between specialist agents."""
from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from app.agents.classification import classification_agent_node
from app.agents.escalation import escalation_agent_node
from app.agents.execution import execution_agent_node
from app.agents.resolution import resolution_agent_node
from app.agents.state import DisputeState
from app.agents.supervisor import supervisor_node
from app.agents.verification import verification_agent_node
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_SUPERVISOR_LOOPS = 10


def _route_supervisor(state: DisputeState) -> str:
    """Route based on supervisor's decision."""
    next_agent = state.get("next_agent", "FINISH")
    if next_agent == "FINISH":
        return END
    return next_agent


def build_dispute_graph(db_session):
    """Build the compiled multi-agent LangGraph workflow."""

    graph = StateGraph(DisputeState)

    # Supervisor node (no db needed — pure LLM routing)
    graph.add_node("supervisor", _wrap_supervisor(supervisor_node))

    # Specialist agent nodes (each gets db session)
    graph.add_node("classification_agent", partial(_wrap_agent, classification_agent_node, db_session))
    graph.add_node("verification_agent", partial(_wrap_agent, verification_agent_node, db_session))
    graph.add_node("resolution_agent", partial(_wrap_agent, resolution_agent_node, db_session))
    graph.add_node("execution_agent", partial(_wrap_agent, execution_agent_node, db_session))
    graph.add_node("escalation_agent", partial(_wrap_agent, escalation_agent_node, db_session))

    # Entry: supervisor decides first
    graph.set_entry_point("supervisor")

    # Supervisor routes to the appropriate agent (or END)
    graph.add_conditional_edges("supervisor", _route_supervisor, {
        "classification_agent": "classification_agent",
        "verification_agent": "verification_agent",
        "resolution_agent": "resolution_agent",
        "execution_agent": "execution_agent",
        "escalation_agent": "escalation_agent",
        END: END,
    })

    # Every agent returns to supervisor for next decision
    for agent_name in [
        "classification_agent",
        "verification_agent",
        "resolution_agent",
        "execution_agent",
        "escalation_agent",
    ]:
        graph.add_edge(agent_name, "supervisor")

    return graph.compile()


def _wrap_supervisor(supervisor_fn):
    """Wrap supervisor with loop detection."""
    call_count = 0

    async def wrapped(state: DisputeState) -> dict:
        nonlocal call_count
        call_count += 1
        if call_count > MAX_SUPERVISOR_LOOPS:
            logger.warning("supervisor_loop_limit", count=call_count)
            return {"next_agent": "FINISH", "final_response": state.get("final_response", "Processing complete.")}
        # If a terminal agent already set final_response, we're done
        if state.get("final_response"):
            return {"next_agent": "FINISH"}
        try:
            return await supervisor_fn(state)
        except Exception as e:
            logger.error("supervisor_error", error=str(e))
            return {"next_agent": "FINISH", "final_response": f"An error occurred: {str(e)}"}

    return wrapped


async def _wrap_agent(agent_fn, db, state: DisputeState) -> dict:
    """Wrapper that passes db to agent functions and handles errors."""
    try:
        return await agent_fn(state, db)
    except Exception as e:
        logger.error("agent_error", agent=agent_fn.__name__, error=str(e))
        errors = list(state.get("errors", []))
        errors.append(f"{agent_fn.__name__}: {str(e)}")
        return {"errors": errors, "final_response": f"An error occurred during processing: {str(e)}"}
