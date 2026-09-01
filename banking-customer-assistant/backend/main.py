import logging

from dotenv import load_dotenv

load_dotenv()  # must run before any module below reads GROQ_API_KEY etc. from os.environ

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("banking_assistant")

from agents import dispute_agent, complaint_agent
from backend.deps import get_current_customer
from backend.orchestrator import run_graph
from backend.session import start_login, verify_otp, logout
from database.database import find_idempotent, save_idempotency
from events.dispatch import dispatch
from mock_banking.data import (
    get_account,
    get_transactions,
    get_cards,
    get_customer,
    get_loan,
    get_transaction,
    card_for_customer,
    block_card,
    unblock_card,
)

app = FastAPI(title="Banking Assistant POC")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Defense in depth: individual agents (e.g. rag_agent) already catch
    their own known failure modes, but nothing should ever leak a raw
    traceback or generic "Internal Server Error" to a customer. Log the
    real exception server-side and return a safe, generic message."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our end. Please try again."})


class LoginRequest(BaseModel):
    customer_id: str
    pin: str


class OTPRequest(BaseModel):
    customer_id: str
    otp: str


class CardActionRequest(BaseModel):
    last4: str


class ChatRequest(BaseModel):
    message: str
    pending: dict | None = None
    context: dict | None = None


class DisputeCreateRequest(BaseModel):
    transaction_id: str
    issue: str


class ComplaintCreateRequest(BaseModel):
    description: str


@app.get("/health")
def health():
    return {"status": "ok"}


# ---- Authentication (public — this is where identity is established) ----

@app.post("/auth/login")
def login(body: LoginRequest):
    try:
        return {"demo_otp": start_login(body.customer_id, body.pin)}
    except ValueError as exc:
        raise HTTPException(401, str(exc))


@app.post("/auth/verify")
def verify(body: OTPRequest):
    try:
        return verify_otp(body.customer_id, body.otp)
    except ValueError as exc:
        raise HTTPException(401, str(exc))


@app.post("/auth/logout")
def logout_endpoint(x_session_id: str = Header(...)):
    logout(x_session_id)
    return {"status": "logged_out"}


# ---- Session-protected endpoints — identity always comes from the session ----

@app.get("/me/profile")
def profile(customer_id: str = Depends(get_current_customer)):
    customer = get_customer(customer_id)
    return {"customer_id": customer_id, "name": customer["name"]}


@app.get("/me/balance")
def balance(customer_id: str = Depends(get_current_customer)):
    account = get_account(customer_id)
    if not account:
        raise HTTPException(404, "Account not found")
    return account


@app.get("/me/transactions")
def transactions(customer_id: str = Depends(get_current_customer)):
    return get_transactions(customer_id)


@app.get("/me/cards")
def cards(customer_id: str = Depends(get_current_customer)):
    return get_cards(customer_id)


@app.get("/me/loan")
def loan(customer_id: str = Depends(get_current_customer)):
    result = get_loan(customer_id)
    if not result:
        raise HTTPException(404, "Loan not found")
    return result


@app.post("/cards/block")
def block(body: CardActionRequest, customer_id: str = Depends(get_current_customer)):
    card_id, card = card_for_customer(customer_id, body.last4)
    if not card:
        raise HTTPException(404, "Card not found or not owned by this customer")

    idempotency_key = f"{customer_id}-CARD{body.last4}-BLOCK"
    # The idempotency ledger (SQLite, durable) and the card's actual status
    # (in-memory mock data) can drift apart — e.g. a backend restart resets
    # mock data but not the ledger. Only trust a replay when the real
    # current state actually matches what the record claims; otherwise the
    # mock banking data is the source of truth and the mutation must run.
    if find_idempotent(idempotency_key) and card["status"] == "BLOCKED":
        return {"status": "BLOCKED", "idempotency_result": "REPLAYED"}

    try:
        changed = block_card(card_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    save_idempotency(idempotency_key, card_id, "card_block")
    events = dispatch("action.performed", {"action": "card_block", "card_last4": body.last4, "status": "BLOCKED"}, customer_id)
    return {"status": "BLOCKED", "already_blocked": not changed, "idempotency_result": "CREATED", "events": events}


@app.post("/cards/unblock")
def unblock(body: CardActionRequest, customer_id: str = Depends(get_current_customer)):
    card_id, card = card_for_customer(customer_id, body.last4)
    if not card:
        raise HTTPException(404, "Card not found or not owned by this customer")

    idempotency_key = f"{customer_id}-CARD{body.last4}-UNBLOCK"
    if find_idempotent(idempotency_key) and card["status"] == "ACTIVE":
        return {"status": "ACTIVE", "idempotency_result": "REPLAYED"}

    changed = unblock_card(card_id)
    save_idempotency(idempotency_key, card_id, "card_unblock")
    events = dispatch("action.performed", {"action": "card_unblock", "card_last4": body.last4, "status": "ACTIVE"}, customer_id)
    return {"status": "ACTIVE", "already_active": not changed, "idempotency_result": "CREATED", "events": events}


@app.get("/disputes")
def list_disputes_endpoint(customer_id: str = Depends(get_current_customer)):
    return dispute_agent.status(customer_id)


@app.post("/disputes")
def create_dispute_endpoint(body: DisputeCreateRequest, customer_id: str = Depends(get_current_customer)):
    txn = get_transaction(customer_id, body.transaction_id)
    if not txn:
        raise HTTPException(404, "Transaction not found on this account")
    return dispute_agent.create(customer_id, txn, body.issue)


@app.post("/complaints")
def create_complaint_endpoint(body: ComplaintCreateRequest, customer_id: str = Depends(get_current_customer)):
    return complaint_agent.create(customer_id, body.description)


@app.post("/chat")
def chat(body: ChatRequest, customer_id: str = Depends(get_current_customer)):
    return run_graph(body.message, customer_id, body.pending, body.context)
