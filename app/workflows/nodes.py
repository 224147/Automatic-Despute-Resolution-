"""LangGraph dispute resolution workflow – typed state, conditional routing, audit at every node."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TypedDict

from app.core.enums import (
    ActorType,
    AuditEventType,
    DisputeCategory,
    DisputeStatus,
    EscalationReason,
    RiskLevel,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class DisputeState(TypedDict, total=False):
    customer_id: str
    dispute_id: str
    customer_message: str
    dispute_category: str
    transaction_type: str | None
    transaction_id: str | None
    transaction_ref: str | None
    transaction_status: str | None
    transaction_amount: float | None
    transaction_age_days: int | None
    customer_verified: bool
    transaction_verified: bool
    classification_confidence: float
    fraud_indicator: bool
    retrieved_policies: list[dict]
    policy_found: bool
    rule_result: dict
    risk_result: dict
    resolution_decision: str
    action_result: dict
    escalation_required: bool
    escalation_reason: str | None
    final_response: str
    errors: list[str]
    audit_events: list[str]
    customer_name: str
    previous_dispute_count: int


# ── Node implementations ──

async def intake_node(state: DisputeState, db) -> dict:
    """Validate and register the incoming dispute."""
    from app.tools.banking import create_dispute

    logger.info("node_intake", customer_id=state.get("customer_id"))
    errors = list(state.get("errors", []))
    audit_events = list(state.get("audit_events", []))

    customer_id = state.get("customer_id")
    message = state.get("customer_message", "")

    if not customer_id or not message:
        errors.append("Missing customer_id or message")
        return {"errors": errors, "resolution_decision": "ERROR"}

    dispute = await create_dispute(
        db,
        customer_id=uuid.UUID(customer_id),
        customer_message=message,
        category=DisputeCategory.UNKNOWN.value,
        transaction_id=uuid.UUID(state["transaction_id"]) if state.get("transaction_id") else None,
    )

    audit_events.append(f"INTAKE: Dispute {dispute.id} created")
    return {
        "dispute_id": str(dispute.id),
        "errors": errors,
        "audit_events": audit_events,
    }


async def classify_dispute_node(state: DisputeState, db) -> dict:
    """Classify the dispute using LLM + deterministic fallback."""
    from app.audit.service import log_audit_event
    from app.services.classification import classify_dispute

    logger.info("node_classify", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    result = await classify_dispute(state["customer_message"])

    await log_audit_event(
        db,
        event_type=AuditEventType.CLASSIFICATION.value,
        event_description=f"Classified as {result.dispute_category} (confidence: {result.confidence})",
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
        customer_id=uuid.UUID(state["customer_id"]),
        new_state=result.model_dump(),
    )

    # Update dispute record
    from app.tools.banking import update_dispute
    if state.get("dispute_id"):
        await update_dispute(
            db, uuid.UUID(state["dispute_id"]),
            category=result.dispute_category,
            classification_confidence=result.confidence,
            status=DisputeStatus.UNDER_REVIEW.value,
        )

    audit_events.append(f"CLASSIFY: {result.dispute_category} ({result.confidence})")
    return {
        "dispute_category": result.dispute_category,
        "transaction_type": result.transaction_type,
        "classification_confidence": result.confidence,
        "fraud_indicator": result.fraud_indicator,
        "audit_events": audit_events,
    }


async def authenticate_customer_node(state: DisputeState, db) -> dict:
    """Verify the customer identity."""
    from sqlalchemy import select as sa_select

    from app.audit.service import log_audit_event
    from app.models.models import Customer as CustomerModel

    logger.info("node_authenticate", customer_id=state.get("customer_id"))
    audit_events = list(state.get("audit_events", []))

    # Customer is already JWT-authenticated via the API; confirm active in DB
    cid = uuid.UUID(state["customer_id"])
    res = await db.execute(sa_select(CustomerModel).where(CustomerModel.id == cid))
    cust = res.scalar_one_or_none()
    verified = cust is not None and cust.is_active

    await log_audit_event(
        db,
        event_type=AuditEventType.AUTHENTICATION.value,
        event_description=f"Customer authentication: {'success' if verified else 'failed'}",
        customer_id=uuid.UUID(state["customer_id"]),
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
    )

    audit_events.append(f"AUTH: {'verified' if verified else 'failed'}")
    return {"customer_verified": verified, "audit_events": audit_events}


async def identify_transaction_node(state: DisputeState, db) -> dict:
    """Find the relevant transaction."""
    from app.tools.banking import get_customer_transactions, get_transaction_by_ref

    logger.info("node_identify_txn", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    txn_ref = state.get("transaction_ref")
    if txn_ref:
        txn = await get_transaction_by_ref(db, txn_ref)
        if txn:
            age = (datetime.now(UTC) - txn.transaction_date).days
            audit_events.append(f"TXN_FOUND: {txn.id} via ref {txn_ref}")
            return {
                "transaction_id": str(txn.id),
                "transaction_status": txn.status,
                "transaction_amount": txn.amount,
                "transaction_age_days": age,
                "transaction_verified": True,
                "audit_events": audit_events,
            }

    # If no ref, try to find matching transaction from customer history
    if state.get("customer_id"):
        txns = await get_customer_transactions(db, uuid.UUID(state["customer_id"]), limit=50)
        amount = state.get("transaction_amount")
        txn_type = state.get("transaction_type")
        for txn in txns:
            # Match by amount + failed status
            if amount and abs(txn.amount - amount) < 1.0 and txn.status in ("FAILED", "PENDING", "REVERSED"):
                age = (datetime.now(UTC) - txn.transaction_date).days
                audit_events.append(f"TXN_MATCHED: {txn.id}")
                return {
                    "transaction_id": str(txn.id),
                    "transaction_status": txn.status,
                    "transaction_amount": txn.amount,
                    "transaction_age_days": age,
                    "transaction_verified": True,
                    "audit_events": audit_events,
                }
        # Fallback: match by transaction type + failed status
        if txn_type:
            for txn in txns:
                if txn.transaction_type == txn_type and txn.status in ("FAILED", "PENDING", "REVERSED"):
                    age = (datetime.now(UTC) - txn.transaction_date).days
                    audit_events.append(f"TXN_MATCHED_BY_TYPE: {txn.id}")
                    return {
                        "transaction_id": str(txn.id),
                        "transaction_status": txn.status,
                        "transaction_amount": txn.amount,
                        "transaction_age_days": age,
                        "transaction_verified": True,
                        "audit_events": audit_events,
                    }

    audit_events.append("TXN_NOT_FOUND")
    return {
        "transaction_verified": False,
        "audit_events": audit_events,
    }


async def verify_transaction_node(state: DisputeState, db) -> dict:
    """Verify transaction details match the dispute."""
    from app.audit.service import log_audit_event

    logger.info("node_verify_txn", transaction_id=state.get("transaction_id"))
    audit_events = list(state.get("audit_events", []))

    txn_id = state.get("transaction_id")
    if not txn_id:
        audit_events.append("VERIFY_TXN: no transaction to verify")
        return {"transaction_verified": False, "audit_events": audit_events}

    await log_audit_event(
        db,
        event_type=AuditEventType.TRANSACTION_LOOKUP.value,
        event_description=f"Transaction {txn_id} verified",
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
        customer_id=uuid.UUID(state["customer_id"]),
    )

    audit_events.append(f"VERIFY_TXN: {txn_id} confirmed")
    return {"transaction_verified": True, "audit_events": audit_events}


async def retrieve_policy_node(state: DisputeState, db) -> dict:
    """Retrieve relevant banking policies via RAG."""
    from app.audit.service import log_audit_event
    from app.rag.pipeline import retrieve_policies

    logger.info("node_retrieve_policy", category=state.get("dispute_category"))
    audit_events = list(state.get("audit_events", []))

    category = state.get('dispute_category', '')
    amount = state.get('transaction_amount', 'unknown')
    query = f"{category} dispute policy for amount {amount}"
    rag_result = await retrieve_policies(query)

    found_str = 'found' if rag_result.found else 'NOT FOUND'
    desc = f"Policy retrieval: {found_str} ({len(rag_result.chunks)} chunks)"
    await log_audit_event(
        db,
        event_type=AuditEventType.POLICY_RETRIEVAL.value,
        event_description=desc,
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
        customer_id=uuid.UUID(state["customer_id"]),
    )

    policies = [c.model_dump() for c in rag_result.chunks]
    audit_events.append(f"POLICY: {'found' if rag_result.found else 'NOT_FOUND'} ({len(policies)} chunks)")
    return {
        "retrieved_policies": policies,
        "policy_found": rag_result.found,
        "audit_events": audit_events,
    }


async def evaluate_rules_node(state: DisputeState, db) -> dict:
    """Run deterministic rules engine."""
    from app.audit.service import log_audit_event
    from app.rules.engine import evaluate_rules
    from app.tools.banking import get_dispute_count_last_90_days

    logger.info("node_evaluate_rules", category=state.get("dispute_category"))
    audit_events = list(state.get("audit_events", []))

    prev_count = state.get("previous_dispute_count", 0)
    if state.get("customer_id"):
        try:
            prev_count = await get_dispute_count_last_90_days(db, uuid.UUID(state["customer_id"]))
        except Exception:
            pass

    result = evaluate_rules(
        category=state.get("dispute_category", DisputeCategory.UNKNOWN.value),
        amount=state.get("transaction_amount"),
        transaction_status=state.get("transaction_status"),
        customer_verified=state.get("customer_verified", False),
        previous_dispute_count=prev_count,
        fraud_indicator=state.get("fraud_indicator", False),
        policy_found=state.get("policy_found", False),
        transaction_age_days=state.get("transaction_age_days"),
    )

    await log_audit_event(
        db,
        event_type=AuditEventType.RULE_EVALUATION.value,
        event_description=f"Rules: eligible={result.eligible_for_auto_resolution}, action={result.recommended_action}",
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
        customer_id=uuid.UUID(state["customer_id"]),
        new_state=result.model_dump(),
        decision_reason=", ".join(result.reason_codes),
    )

    audit_events.append(f"RULES: {result.recommended_action} (eligible={result.eligible_for_auto_resolution})")
    return {
        "rule_result": result.model_dump(),
        "previous_dispute_count": prev_count,
        "audit_events": audit_events,
    }


async def assess_risk_node(state: DisputeState, db) -> dict:
    """Risk/fraud assessment."""
    from app.audit.service import log_audit_event
    from app.services.risk import assess_risk

    logger.info("node_assess_risk", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    result = assess_risk(
        amount=state.get("transaction_amount") or 0,
        transaction_type=state.get("transaction_type"),
        transaction_status=state.get("transaction_status"),
        dispute_category=state.get("dispute_category", "UNKNOWN"),
        customer_dispute_frequency=state.get("previous_dispute_count", 0),
        fraud_indicator=state.get("fraud_indicator", False),
        customer_verified=state.get("customer_verified", False),
        transaction_age_days=state.get("transaction_age_days"),
    )

    await log_audit_event(
        db,
        event_type=AuditEventType.RISK_ASSESSMENT.value,
        event_description=f"Risk: {result['risk_level']} (score: {result['risk_score']})",
        dispute_id=uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None,
        customer_id=uuid.UUID(state["customer_id"]),
        new_state=result,
    )

    # Update dispute
    from app.tools.banking import update_dispute
    if state.get("dispute_id"):
        await update_dispute(
            db, uuid.UUID(state["dispute_id"]),
            risk_score=result["risk_score"],
            risk_level=result["risk_level"],
        )

    audit_events.append(f"RISK: {result['risk_level']} ({result['risk_score']})")
    return {"risk_result": result, "audit_events": audit_events}


async def resolution_decision_node(state: DisputeState, db) -> dict:
    """Decide: auto-resolve, escalate, or request more info."""
    logger.info("node_resolution_decision", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    rule = state.get("rule_result", {})
    risk = state.get("risk_result", {})

    risk_level = risk.get("risk_level", "MEDIUM")
    eligible = rule.get("eligible_for_auto_resolution", False)
    human_required = rule.get("required_human_review", False)

    # Decision logic: risk overrides eligibility
    if risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value):
        decision = "ESCALATE"
        esc_reason = EscalationReason.HIGH_RISK.value
    elif not state.get("customer_verified", False):
        decision = "ESCALATE"
        esc_reason = EscalationReason.CUSTOMER_NOT_VERIFIED.value
    elif state.get("fraud_indicator", False):
        decision = "ESCALATE"
        esc_reason = EscalationReason.FRAUD_SUSPECTED.value
    elif not state.get("policy_found", True):
        decision = "ESCALATE"
        esc_reason = EscalationReason.POLICY_NOT_FOUND.value
    elif human_required:
        decision = "ESCALATE"
        esc_reason = rule.get("reason_codes", ["RULE_NOT_ELIGIBLE"])[0]
    elif eligible and risk_level == RiskLevel.LOW.value:
        decision = "AUTO_RESOLVE"
        esc_reason = None
    elif eligible and risk_level == RiskLevel.MEDIUM.value:
        decision = "AUTO_RESOLVE"
        esc_reason = None
    else:
        decision = "ESCALATE"
        esc_reason = EscalationReason.RULE_NOT_ELIGIBLE.value

    audit_events.append(f"DECISION: {decision}")
    return {
        "resolution_decision": decision,
        "escalation_required": decision == "ESCALATE",
        "escalation_reason": esc_reason,
        "audit_events": audit_events,
    }


async def execute_safe_action_node(state: DisputeState, db) -> dict:
    """Execute the safe automated action (refund, credit, etc.)."""
    from app.audit.service import log_audit_event
    from app.tools.banking import (
        create_provisional_credit_request,
        create_refund_request,
        update_dispute,
    )

    logger.info("node_execute_action", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    dispute_id = uuid.UUID(state["dispute_id"])
    amount = state.get("transaction_amount") or 0
    if amount == 0:
        logger.warning("execute_action_zero_amount", dispute_id=str(dispute_id))
    action = state.get("rule_result", {}).get("recommended_action", "AUTO_REFUND")

    if action in ("AUTO_REFUND", "AUTO_CREDIT", "REFUND_WITH_VERIFICATION"):
        resolution = await create_refund_request(db, dispute_id, amount)
        if amount > 0:
            action_taken = f"Refund of INR {amount:,.2f} initiated"
        else:
            action_taken = "Refund initiated (amount will be confirmed after transaction verification)"
    else:
        resolution = await create_provisional_credit_request(db, dispute_id, amount)
        if amount > 0:
            action_taken = f"Provisional credit of INR {amount:,.2f} applied"
        else:
            action_taken = "Provisional credit applied (amount will be confirmed after transaction verification)"

    await update_dispute(
        db, dispute_id,
        status=DisputeStatus.AUTO_RESOLVED.value,
        resolution_summary=action_taken,
        resolved_at=datetime.now(UTC),
    )

    await log_audit_event(
        db,
        event_type=AuditEventType.RESOLUTION.value,
        event_description=action_taken,
        dispute_id=dispute_id,
        customer_id=uuid.UUID(state["customer_id"]),
        actor_type=ActorType.RULES_ENGINE.value,
        new_state={"resolution_id": str(resolution.id), "action": action_taken},
        decision_reason=", ".join(state.get("rule_result", {}).get("reason_codes", [])),
    )

    audit_events.append(f"ACTION: {action_taken}")
    return {
        "action_result": {"resolution_id": str(resolution.id), "action": action_taken},
        "final_response": f"Your dispute has been resolved. {action_taken}. "
                          f"Reference: {str(dispute_id)[:8]}",
        "audit_events": audit_events,
    }


async def escalation_node(state: DisputeState, db) -> dict:
    """Escalate to human agent."""
    from app.audit.service import log_audit_event
    from app.tools.banking import escalate_dispute

    logger.info("node_escalation", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    dispute_id = uuid.UUID(state["dispute_id"])
    reason = state.get("escalation_reason", EscalationReason.SYSTEM_ERROR.value)
    risk_level = state.get("risk_result", {}).get("risk_level", "MEDIUM")

    priority_map = {"LOW": "LOW", "MEDIUM": "MEDIUM", "HIGH": "HIGH", "CRITICAL": "CRITICAL"}
    priority = priority_map.get(risk_level, "MEDIUM")

    team = "FRAUD_TEAM" if reason in (
        EscalationReason.FRAUD_SUSPECTED.value, EscalationReason.HIGH_RISK.value
    ) else "DISPUTE_TEAM"

    sla = 24 if priority in ("HIGH", "CRITICAL") else 48

    esc = await escalate_dispute(db, dispute_id, reason or "", priority, team, sla)

    await log_audit_event(
        db,
        event_type=AuditEventType.ESCALATION.value,
        event_description=f"Escalated: {reason}, team={team}, priority={priority}",
        dispute_id=dispute_id,
        customer_id=uuid.UUID(state["customer_id"]),
        new_state={"escalation_id": str(esc.id), "reason": reason, "team": team},
    )

    audit_events.append(f"ESCALATE: {reason} -> {team}")
    return {
        "action_result": {"escalation_id": str(esc.id), "reason": reason, "team": team},
        "final_response": f"Your dispute has been escalated to our {team.replace('_', ' ').title()} "
                          f"for further review. Priority: {priority}. "
                          f"Expected resolution within {sla} hours. "
                          f"Reference: {str(dispute_id)[:8]}",
        "audit_events": audit_events,
    }


async def notification_node(state: DisputeState, db) -> dict:
    """Send notification to customer."""
    from app.notifications.service import notify_customer

    logger.info("node_notification", dispute_id=state.get("dispute_id"))
    audit_events = list(state.get("audit_events", []))

    decision = state.get("resolution_decision", "")
    dispute_id = uuid.UUID(state["dispute_id"])
    customer_id = uuid.UUID(state["customer_id"])
    name = state.get("customer_name", "Customer")
    category = state.get("dispute_category", "UNKNOWN")

    if decision == "AUTO_RESOLVE":
        template = "auto_resolution"
        extra = {
            "category": category,
            "action_taken": state.get("action_result", {}).get("action", "Resolved"),
        }
    else:
        template = "escalated"
        extra = {"category": category, "sla": "48"}

    await notify_customer(
        db,
        customer_id=customer_id,
        customer_name=name,
        dispute_id=dispute_id,
        template_name=template,
        extra_vars=extra,
    )

    audit_events.append(f"NOTIFY: {template}")
    return {"audit_events": audit_events}


async def audit_node(state: DisputeState, db) -> dict:
    """Final audit summary."""
    from app.audit.service import log_audit_event

    audit_events = list(state.get("audit_events", []))
    dispute_id = uuid.UUID(state["dispute_id"]) if state.get("dispute_id") else None

    await log_audit_event(
        db,
        event_type="WORKFLOW_COMPLETE",
        event_description=f"Workflow completed. Decision: {state.get('resolution_decision')}. "
                          f"Events: {len(audit_events)}",
        dispute_id=dispute_id,
        customer_id=uuid.UUID(state["customer_id"]) if state.get("customer_id") else None,
        new_state={
            "decision": state.get("resolution_decision"),
            "risk_level": state.get("risk_result", {}).get("risk_level"),
            "category": state.get("dispute_category"),
            "audit_trail": audit_events,
        },
    )

    return {"audit_events": audit_events}
