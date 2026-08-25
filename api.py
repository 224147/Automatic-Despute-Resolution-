"""Thin FastAPI wrapper around the POC dispute flow. No business logic here —
it only translates HTTP requests into calls to main.process_dispute.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from adapters import AnalystQueue, CaseManagement, MerchantAPI, NotificationService, PaymentsAPI, TransactionAPI
from config import load_config
from main import Adapters, process_dispute

app = FastAPI(title="Automated Dispute Resolution POC")

_config = load_config()

# Seed data: two transactions demonstrating an auto-resolvable duplicate charge
# and a higher-value transaction that will escalate on amount.
_adapters = Adapters(
    transaction_api=TransactionAPI(
        {
            "TXN-1": {"merchant_id": "M-1", "amount_usd": Decimal("25.00")},
            "TXN-2": {"merchant_id": "M-1", "amount_usd": Decimal("500.00")},
        }
    ),
    merchant_api=MerchantAPI({"M-1": {"name": "Example Merchant"}}),
    case_mgmt=CaseManagement(),
    payments=PaymentsAPI(),
    analyst_queue=AnalystQueue(),
    notifications=NotificationService(),
)


class DisputeRequest(BaseModel):
    customer_id: str
    transaction_id: str
    description: str
    amount_usd: Decimal


@app.post("/disputes")
def submit_dispute(req: DisputeRequest) -> dict:
    if not _adapters.transaction_api.has_transaction(req.transaction_id):
        raise HTTPException(status_code=404, detail=f"unknown transaction_id '{req.transaction_id}'")

    result = process_dispute(
        customer_id=req.customer_id,
        transaction_id=req.transaction_id,
        description=req.description,
        amount_usd=req.amount_usd,
        adapters=_adapters,
        config=_config,
    )
    case = result["case"]
    decision = result["decision"]
    agent_result = result["agent_result"]
    return {
        "case_id": case.case_id,
        "status": case.status,
        "decision": decision.decision,
        "reasons": decision.reasons,
        "action_taken": result["action_taken"],
        "amount_usd": str(case.amount_usd),
        "rationale": agent_result.rationale if agent_result else None,
        "is_new_case": result["is_new_case"],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
