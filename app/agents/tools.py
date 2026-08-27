"""LangChain tool wrappers — expose banking services as tools agents can call."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from langchain_core.tools import tool


# ── Classification Tools ──

@tool
async def classify_dispute_tool(customer_message: str) -> str:
    """Classify a banking dispute from the customer's message. Returns category, confidence, fraud indicator."""
    from app.services.classification import classify_dispute
    result = await classify_dispute(customer_message)
    return result.model_dump_json()


@tool
async def retrieve_policies_tool(query: str) -> str:
    """Retrieve relevant banking policy documents for a dispute query using RAG."""
    from app.rag.pipeline import retrieve_policies
    result = await retrieve_policies(query)
    import json
    return json.dumps({
        "found": result.found,
        "chunk_count": len(result.chunks),
        "chunks": [c.model_dump() for c in result.chunks[:3]],
    })


# ── Verification Tools ──

@tool
async def lookup_customer_tool(customer_id: str, db_ref: str = "") -> str:
    """Look up a customer by ID to verify they exist and are active."""
    # db is injected at runtime via closure; this is a placeholder signature
    raise NotImplementedError("Must be bound with db session")


@tool
async def lookup_transaction_by_ref_tool(transaction_ref: str, db_ref: str = "") -> str:
    """Look up a transaction by its reference number."""
    raise NotImplementedError("Must be bound with db session")


@tool
async def search_customer_transactions_tool(
    customer_id: str, amount: str = "", transaction_type: str = ""
) -> str:
    """Search a customer's recent transactions to find one matching the dispute."""
    raise NotImplementedError("Must be bound with db session")


# ── Rules & Risk Tools ──

@tool
def evaluate_rules_tool(
    category: str,
    amount: str,
    transaction_status: str,
    customer_verified: str,
    previous_dispute_count: str,
    fraud_indicator: str,
    policy_found: str,
    transaction_age_days: str = "",
) -> str:
    """Run the deterministic banking rules engine to check auto-resolution eligibility."""
    from app.rules.engine import evaluate_rules
    result = evaluate_rules(
        category=category,
        amount=float(amount) if amount else None,
        transaction_status=transaction_status or None,
        customer_verified=customer_verified.lower() == "true",
        previous_dispute_count=int(previous_dispute_count) if previous_dispute_count else 0,
        fraud_indicator=fraud_indicator.lower() == "true",
        policy_found=policy_found.lower() == "true",
        transaction_age_days=int(transaction_age_days) if transaction_age_days else None,
    )
    return result.model_dump_json()


@tool
def assess_risk_tool(
    amount: str,
    transaction_type: str,
    transaction_status: str,
    dispute_category: str,
    customer_dispute_frequency: str,
    fraud_indicator: str,
    customer_verified: str,
    transaction_age_days: str = "",
) -> str:
    """Assess the risk/fraud level of a dispute. Returns risk score and level."""
    import json

    from app.services.risk import assess_risk
    result = assess_risk(
        amount=float(amount) if amount else 0,
        transaction_type=transaction_type or None,
        transaction_status=transaction_status or None,
        dispute_category=dispute_category,
        customer_dispute_frequency=int(customer_dispute_frequency) if customer_dispute_frequency else 0,
        fraud_indicator=fraud_indicator.lower() == "true",
        customer_verified=customer_verified.lower() == "true",
        transaction_age_days=int(transaction_age_days) if transaction_age_days else None,
    )
    return json.dumps(result)


def create_db_bound_tools(db):
    """Create tool instances with db session bound via closure."""
    import json

    @tool
    async def lookup_customer(customer_id: str) -> str:
        """Look up a customer by ID to verify they exist and are active."""
        from sqlalchemy import select as sa_select

        from app.models.models import Customer as CustomerModel
        cid = uuid.UUID(customer_id)
        res = await db.execute(sa_select(CustomerModel).where(CustomerModel.id == cid))
        cust = res.scalar_one_or_none()
        if not cust:
            return json.dumps({"found": False, "active": False})
        return json.dumps({"found": True, "active": cust.is_active, "name": f"{cust.first_name} {cust.last_name}"})

    @tool
    async def lookup_transaction_by_ref(transaction_ref: str) -> str:
        """Look up a transaction by its reference number."""
        from app.tools.banking import get_transaction_by_ref
        txn = await get_transaction_by_ref(db, transaction_ref)
        if not txn:
            return json.dumps({"found": False})
        age = (datetime.now(UTC) - txn.transaction_date).days
        return json.dumps({
            "found": True,
            "transaction_id": str(txn.id),
            "status": txn.status,
            "amount": txn.amount,
            "age_days": age,
        })

    @tool
    async def search_customer_transactions(
        customer_id: str, amount: str = "", transaction_type: str = ""
    ) -> str:
        """Search a customer's recent transactions to find one matching the dispute."""
        from app.tools.banking import get_customer_transactions
        txns = await get_customer_transactions(db, uuid.UUID(customer_id), limit=50)
        target_amount = float(amount) if amount else None
        matches = []
        for txn in txns:
            if txn.status not in ("FAILED", "PENDING", "REVERSED"):
                continue
            if target_amount and abs(txn.amount - target_amount) >= 1.0:
                continue
            if transaction_type and txn.transaction_type != transaction_type:
                continue
            age = (datetime.now(UTC) - txn.transaction_date).days
            matches.append({
                "transaction_id": str(txn.id),
                "status": txn.status,
                "amount": txn.amount,
                "type": txn.transaction_type,
                "age_days": age,
            })
            if len(matches) >= 5:
                break
        return json.dumps({"matches": matches, "count": len(matches)})

    @tool
    async def get_dispute_history(customer_id: str) -> str:
        """Get count of disputes filed by this customer in the last 90 days."""
        from app.tools.banking import get_dispute_count_last_90_days
        try:
            count = await get_dispute_count_last_90_days(db, uuid.UUID(customer_id))
        except Exception:
            count = 0
        return json.dumps({"dispute_count_90_days": count})

    @tool
    async def create_dispute(customer_id: str, customer_message: str, category: str, transaction_id: str = "") -> str:
        """Create a new dispute record in the system."""
        from app.tools.banking import create_dispute as _create
        dispute = await _create(
            db,
            customer_id=uuid.UUID(customer_id),
            customer_message=customer_message,
            category=category,
            transaction_id=uuid.UUID(transaction_id) if transaction_id else None,
        )
        return json.dumps({"dispute_id": str(dispute.id)})

    @tool
    async def create_refund(dispute_id: str, amount: str) -> str:
        """Create a refund request for a dispute."""
        from app.tools.banking import create_refund_request
        res = await create_refund_request(db, uuid.UUID(dispute_id), float(amount) if amount else 0)
        return json.dumps({"resolution_id": str(res.id), "type": "REFUND"})

    @tool
    async def create_provisional_credit(dispute_id: str, amount: str) -> str:
        """Create a provisional credit for a dispute."""
        from app.tools.banking import create_provisional_credit_request
        res = await create_provisional_credit_request(db, uuid.UUID(dispute_id), float(amount) if amount else 0)
        return json.dumps({"resolution_id": str(res.id), "type": "PROVISIONAL_CREDIT"})

    @tool
    async def update_dispute_status(dispute_id: str, status: str, resolution_summary: str = "") -> str:
        """Update a dispute's status and optional resolution summary."""
        from app.tools.banking import update_dispute
        kwargs = {"status": status}
        if resolution_summary:
            kwargs["resolution_summary"] = resolution_summary
        if status in ("AUTO_RESOLVED", "RESOLVED"):
            kwargs["resolved_at"] = datetime.now(UTC)
        await update_dispute(db, uuid.UUID(dispute_id), **kwargs)
        return json.dumps({"updated": True})

    @tool
    async def escalate_dispute(dispute_id: str, reason: str, priority: str, team: str, sla_hours: str) -> str:
        """Escalate a dispute to a human agent team."""
        from app.tools.banking import escalate_dispute as _escalate
        esc = await _escalate(
            db, uuid.UUID(dispute_id), reason, priority, team, int(sla_hours),
        )
        return json.dumps({"escalation_id": str(esc.id), "team": team, "priority": priority})

    @tool
    async def log_audit(event_type: str, description: str, dispute_id: str = "", customer_id: str = "") -> str:
        """Log an audit event for compliance tracking."""
        from app.audit.service import log_audit_event
        await log_audit_event(
            db,
            event_type=event_type,
            event_description=description,
            dispute_id=uuid.UUID(dispute_id) if dispute_id else None,
            customer_id=uuid.UUID(customer_id) if customer_id else None,
        )
        return json.dumps({"logged": True})

    @tool
    async def send_notification(
        customer_id: str, customer_name: str, dispute_id: str, template_name: str, extra_vars: str = "{}"
    ) -> str:
        """Send a notification to the customer using a template."""
        import json as _json

        from app.notifications.service import notify_customer
        await notify_customer(
            db,
            customer_id=uuid.UUID(customer_id),
            customer_name=customer_name,
            dispute_id=uuid.UUID(dispute_id),
            template_name=template_name,
            extra_vars=_json.loads(extra_vars) if extra_vars else {},
        )
        return _json.dumps({"notified": True})

    return {
        "lookup_customer": lookup_customer,
        "lookup_transaction_by_ref": lookup_transaction_by_ref,
        "search_customer_transactions": search_customer_transactions,
        "get_dispute_history": get_dispute_history,
        "create_dispute": create_dispute,
        "create_refund": create_refund,
        "create_provisional_credit": create_provisional_credit,
        "update_dispute_status": update_dispute_status,
        "escalate_dispute": escalate_dispute,
        "log_audit": log_audit,
        "send_notification": send_notification,
    }
