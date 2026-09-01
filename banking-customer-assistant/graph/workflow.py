import re

from langgraph.graph import StateGraph, START, END

from graph.state import GraphState
from graph.extract import extract_last4, extract_amount, extract_transaction_id
from security.risk_policy import Risk, risk_for_intent, route_for_intent
from agents import account_agent, card_agent, loan_agent, rag_agent, dispute_agent, complaint_agent


DISPUTE_STATUS_PHRASES = [
    "dispute status", "status of my dispute", "status of dispute",
    "view dispute", "view my dispute", "see dispute", "see raised dispute",
    "raised dispute", "my dispute", "my disputes", "check dispute",
    "track dispute", "show dispute", "existing dispute",
]

DISPUTE_INVESTIGATION_PHRASES = [
    "dispute", "don't recognize", "dont recognize", "do not recognize",
    "didn't make", "didnt make", "not mine", "unrecognized",
    "unauthorized transaction", "charged twice", "charged me twice",
    "double charged", "duplicate charge", "duplicate transaction",
    "money was deducted", "amount was deducted", "amount deducted",
    "deducted but", "transaction failed", "payment failed",
]

# Intents specific/high-risk enough that a message classifying as one of
# these should interrupt a pending free-text workflow (e.g. mid-complaint
# description) rather than being swallowed as that workflow's answer.
INTERRUPT_INTENTS = {"money_transfer", "change_pin", "block_card", "unblock_card", "dispute_status"}


def classify_intent(text: str) -> str:
    t = text.lower()
    # Most specific patterns first — several keywords below are substrings
    # of each other ("minimum balance" contains "balance", "dispute" is
    # checked for both status lookups and new investigations), so order
    # matters here.
    if any(x in t for x in ["transfer", "send money", "beneficiary"]):
        return "money_transfer"
    if "pin" in t and any(x in t for x in ["change", "reset", "update", "forgot", "new"]):
        return "change_pin"
    if ("lost" in t or "stolen" in t) and "card" in t:
        return "block_card"
    # Word-boundary matches only — "block" is a substring of both "unblock"
    # and "blocking", so a plain "in t" check would misfire on "unblock my
    # card" (→ wrongly block_card) and on "card blocking policy" (→ wrongly
    # block_card instead of a policy question).
    if re.search(r"\bunblock(ed)?\b", t) and "card" in t:
        return "unblock_card"
    if any(phrase in t for phrase in ["policy", "minimum balance", "fee", "foreclos"]):
        return "policy"
    if re.search(r"\bblock(ed)?\b", t) and "card" in t:
        return "block_card"
    if "card" in t and "active" in t and re.search(r"\d{4}", t):
        return "card_active_check"
    if any(phrase in t for phrase in DISPUTE_STATUS_PHRASES):
        return "dispute_status"
    if any(phrase in t for phrase in DISPUTE_INVESTIGATION_PHRASES):
        return "transaction_investigation"
    if "complain" in t:
        return "raise_complaint"
    if "card" in t:
        return "cards"
    if "emi" in t or "loan" in t:
        return "loan"
    if any(phrase in t for phrase in ["balance", "how much money", "how much do i have", "money do i have", "money in my account", "available funds"]):
        return "balance"
    if "transaction" in t:
        return "transactions"
    return "fallback"


# ---- Nodes ----


def node_classify(state: GraphState) -> dict:
    intent = classify_intent(state["message"])
    if intent == "fallback":
        from llm.groq_client import classify_intent_llm

        llm_intent = classify_intent_llm(state["message"])
        if llm_intent:
            intent = llm_intent
    return {"intent": intent, "current_step": "Intent Classified"}


def node_risk(state: GraphState) -> dict:
    risk = risk_for_intent(state["intent"]).value
    route = route_for_intent(state["intent"])
    return {"risk": risk, "route": route, "current_step": "Risk Checked"}


def node_account(state: GraphState) -> dict:
    cid = state["customer_id"]
    if state["intent"] == "balance":
        account = account_agent.account_summary(cid)
        response = f"Your available {account['type'].lower()} balance is ₹{account['balance']:,.2f}."
        return {"agent": "Account Agent", "response": response, "current_step": "Completed"}
    txns = account_agent.transactions(cid)
    return {"agent": "Account Agent", "response": txns, "current_step": "Completed", "context": {"last_transactions": txns}}


def node_loan(state: GraphState) -> dict:
    loan = loan_agent.loan_summary(state["customer_id"])
    if not loan or loan.get("loan_type") == "No active loan":
        response = "You don't have an active loan on this account."
    else:
        response = (
            f"Your {loan['loan_type']} EMI is ₹{loan['emi']:,}, due {loan['next_due']}. "
            f"{loan['remaining']} instalments remain."
        )
    return {"agent": "Loan Agent", "response": response, "current_step": "Completed"}


def node_rag(state: GraphState) -> dict:
    result = rag_agent.answer(state["message"])
    return {
        "agent": "RAG Agent",
        "response": result["answer"],
        "rag_confidence": result.get("confidence"),
        "current_step": "Escalated" if result.get("conflict") else "Completed",
    }


def node_card(state: GraphState) -> dict:
    cid = state["customer_id"]
    if state["intent"] == "cards":
        return {"agent": "Card Agent", "response": card_agent.cards(cid), "current_step": "Completed"}

    last4 = extract_last4(state["message"])

    if state["intent"] == "card_active_check":
        if not last4:
            return {
                "agent": "Card Agent",
                "response": "Which card would you like to check? Please share the last 4 digits.",
                "current_step": "Awaiting Card Number",
            }
        card = card_agent.lookup(cid, last4)
        if not card:
            return {
                "agent": "Card Agent",
                "response": f"I couldn't find a card ending {last4} on your account.",
                "current_step": "Card Not Found",
            }
        if card["status"] == "ACTIVE":
            response = f"Yes. Your card ending {last4} is currently active."
        else:
            response = f"No. Your card ending {last4} is currently {card['status'].lower()}."
        return {"agent": "Card Agent", "response": response, "current_step": "Completed"}

    result = card_agent.handle(cid, state["intent"], last4)
    return {
        "agent": "Card Agent",
        "response": result["response"],
        "current_step": result["current_step"],
        "agent_result": result,
    }


def node_dispute_investigate(state: GraphState) -> dict:
    cid = state["customer_id"]
    amount = extract_amount(state["message"])

    if amount is not None:
        result = dispute_agent.lookup(cid, amount)
        matches = result["matches"]
        if not matches:
            return {
                "agent": "Dispute Agent",
                "response": "I couldn't find a transaction matching that amount on your account.",
                "current_step": "No Match",
            }
    else:
        # No amount stated (e.g. "I was charged twice", "the transaction
        # failed but money was deducted") — offer the customer's recent
        # transactions as candidates instead of refusing outright.
        matches = account_agent.transactions(cid)
        if not matches:
            return {
                "agent": "Dispute Agent",
                "response": "I couldn't find any transactions on your account to dispute.",
                "current_step": "No Match",
            }

    if len(matches) > 1:
        listing = "\n".join(
            f"- {t['merchant']} · ₹{t['amount']:,} · {t['date']} · {t['id']}" for t in matches
        )
        response = (
            "I found multiple matching transactions:\n\n"
            f"{listing}\n\nPlease reply with the transaction ID."
        )
        return {
            "agent": "Dispute Agent",
            "response": response,
            "current_step": "Multiple Matches",
            "agent_result": {"candidates": matches},
        }

    txn = matches[0]
    existing = dispute_agent.by_transaction(cid, txn["id")]
    if existing:
        return {
            "agent": "Dispute Agent",
            "response": f"This transaction already has an open dispute: {existing['id']} ({existing['status']}).",
            "current_step": "Already Disputed",
        }

    response = (
        "I found one matching transaction:\n\n"
        f"{txn['merchant']} · ₹{txn['amount']:,} · {txn['date']} · {txn['status']}\n"
        f"Transaction ID: {txn['id']}\n\nWhat seems to be wrong with this transaction?"
    )
    return {
        "agent": "Dispute Agent",
        "response": response,
        "current_step": "Awaiting Issue Type",
        "agent_result": {"transaction": txn},
    }


def node_dispute_status(state: GraphState) -> dict:
    disputes = dispute_agent.status(state["customer_id"])
    response = disputes if disputes else "I couldn't find an open dispute for your account."
    return {"agent": "Dispute Agent", "response": response, "current_step": "Completed"}


def node_complaint(state: GraphState) -> dict:
    return {
        "agent": "Complaint Agent",
        "response": "I can help file a complaint. Please describe the issue in your next message.",
        "current_step": "Awaiting Description",
    }


def node_fallback(state: GraphState) -> dict:
    intent = state["intent"]
    if intent == "money_transfer":
        response = (
            "I can't perform money transfers through this assistant. "
            "Please use the bank's secure banking channel."
        )
        step = "Refused - Irreversible Action"
    elif intent == "change_pin":
        response = (
            "I can't change your PIN through this assistant. "
            "Please use the bank's secure banking channel."
        )
        step = "Refused - Irreversible Action"
    else:
        response = (
            "I can help with banking-related questions such as accounts, "
            "transactions, cards, loans and disputes. Could you rephrase your "
            "question, or contact a bank representative for further help?"
        )
        step = "Unrouted"
        intent = "out_of_scope"
    return {"agent": "Fallback / Escalation", "response": response, "current_step": step, "intent": intent}


def node_guardrails(state: GraphState) -> dict:
    response = state.get("response")
    if response in (None, ""):
        response = "I couldn't safely process that request. Please contact a bank representative."
    return {"response": response, "guardrail": "PASSED"}


def route_decision(state: GraphState) -> str:
    route = state["route"]
    if route == "Dispute Agent":
        return "dispute_status" if state["intent"] == "dispute_status" else "dispute_investigate"
    return {
        "Account Agent": "account",
        "Loan Agent": "loan",
        "RAG Agent": "rag",
        "Card Agent": "card",
        "Complaint Agent": "complaint",
    }.get(route, "fallback")


def _build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("classify", node_classify)
    graph.add_node("risk", node_risk)
    graph.add_node("account", node_account)
    graph.add_node("loan", node_loan)
    graph.add_node("rag", node_rag)
    graph.add_node("card", node_card)
    graph.add_node("dispute_investigate", node_dispute_investigate)
    graph.add_node("dispute_status", node_dispute_status)
    graph.add_node("complaint", node_complaint)
    graph.add_node("fallback", node_fallback)
    graph.add_node("guardrails", node_guardrails)

    graph.add_edge(START, "classify")
    graph.add_edge("classify", "risk")
    graph.add_conditional_edges("risk", route_decision, {
        "account": "account",
        "loan": "loan",
        "rag": "rag",
        "card": "card",
        "dispute_investigate": "dispute_investigate",
        "dispute_status": "dispute_status",
        "complaint": "complaint",
        "fallback": "fallback",
    })
    for leaf in [
        "account",
        "loan",
        "rag",
        "card",
        "dispute_investigate",
        "dispute_status",
        "complaint",
        "fallback",
    ]:
        graph.add_edge(leaf, "guardrails")
    graph.add_edge("guardrails", END)
    return graph.compile()


_compiled = _build_graph()


def _run_classified(message: str, customer_id: str, context: dict | None = None) -> dict:
    """Fresh classify → risk → agent run (no pending workflow in progress).

    Before classifying, check whether this message is a deterministic
    follow-up about transactions we already showed this conversation
    ("which one was the biggest?") — answered from structured context, not
    by re-classifying or asking an LLM.
    """
    followup = account_agent.answer_transaction_followup(message, context)
    if followup:
        response, new_context = followup
        return {
            "agent": "Account Agent",
            "response": response,
            "current_step": "Completed",
            "intent": "transaction_followup",
            "risk": Risk.READ.value,
            "route": "Account Agent",
            "guardrail": "PASSED",
            "context": new_context,
        }
    state: GraphState = {"message": message, "customer_id": customer_id, "context": context or {}}
    result = _compiled.invoke(state)
    return dict(result)


def _handle_pending(message: str, customer_id: str, pending: dict, context: dict | None = None) -> dict:
    """Continuations of a multi-turn action (card number, dispute issue,
    complaint description, picking among multiple transaction matches).

    These are UI navigation steps, not a fresh intent to classify — banking
    state itself still lives in the mock banking API / SQLite, never in
    chat history. However, a message that clearly represents a brand new,
    high-risk intent (e.g. "Transfer ₹50,000 to Rahul" while a complaint
    description was pending) must be allowed to interrupt and route fresh
    instead of being swallowed as the pending workflow's answer.
    """
    ptype = pending.get("type")

    if ptype == "card_last4":
        intent = pending.get("intent", "block_card")
        last4 = extract_last4(message)
        if not last4:
            if classify_intent(message) != "fallback":
                return _run_classified(message, customer_id, context)
            return {
                "response": "I didn't catch the card number. Please share the last 4 digits.",
                "current_step": "Awaiting Card Number",
                "agent": "Card Agent",
                "route": "Card Agent",
                "risk": Risk.REVERSIBLE_ACTION.value,
            }
        result = card_agent.handle(customer_id, intent, last4)
        return {
            "response": result["response"],
            "current_step": result["current_step"],
            "agent": "Card Agent",
            "route": "Card Agent",
            "risk": Risk.REVERSIBLE_ACTION.value,
            "agent_result": result,
        }

    if ptype == "dispute_pick":
        candidates = pending.get("candidates", [])
        tid = extract_transaction_id(message)
        txn = next((t for t in candidates if t["id"] == tid), None)
        if not txn:
            if classify_intent(message) != "fallback":
                return _run_classified(message, customer_id, context)
            return {
                "response": "I couldn't match that to one of the transactions listed. Please reply with the exact transaction ID.",
                "current_step": "Multiple Matches",
                "agent": "Dispute Agent",
                "route": "Dispute Agent",
                "risk": Risk.REVERSIBLE_ACTION.value,
            }
        existing = dispute_agent.by_transaction(customer_id, txn["id")]
        if existing:
            return {
                "response": f"This transaction already has an open dispute: {existing['id']} ({existing['status']}).",
                "current_step": "Already Disputed",
                "agent": "Dispute Agent",
                "route": "Dispute Agent",
                "risk": Risk.READ.value,
            }
        return {
            "response": f"Transaction ID: {txn['id']}\n\nWhat seems to be wrong with this transaction?",
            "current_step": "Awaiting Issue Type",
            "agent": "Dispute Agent",
            "route": "Dispute Agent",
            "risk": Risk.REVERSIBLE_ACTION.value,
            "agent_result": {"transaction": txn},
        }

    if ptype == "dispute_issue":
        if classify_intent(message) in INTERRUPT_INTENTS:
            return _run_classified(message, customer_id, context)
        txn = pending["transaction"]
        response = (
            f"Please confirm: raise a dispute for {txn['merchant']} · ₹{txn['amount']:,} · "
            f"{txn['id']}\nIssue: {message}"
        )
        return {
            "response": response,
            "current_step": "Awaiting Confirmation",
            "agent": "Dispute Agent",
            "route": "Dispute Agent",
            "risk": Risk.REVERSIBLE_ACTION.value,
            "agent_result": {"transaction": txn, "issue": message},
        }

    if ptype == "complaint_description":
        if classify_intent(message) in INTERRUPT_INTENTS:
            return _run_classified(message, customer_id, context)
        response = f"Please confirm: file a complaint with description:\n\n\"{message}\""
        return {
            "response": response,
            "current_step": "Awaiting Confirmation",
            "agent": "Complaint Agent",
            "route": "Complaint Agent",
            "risk": Risk.REVERSIBLE_ACTION.value,
            "agent_result": {"description": message},
        }

    return {"response": "Something went wrong tracking this conversation step. Please start over.", "current_step": "Error"}


def run_graph(message: str, customer_id: str, pending: dict | None = None, context: dict | None = None) -> dict:
    if pending:
        return _handle_pending(message, customer_id, pending, context)
    return _run_classified(message, customer_id, context)
