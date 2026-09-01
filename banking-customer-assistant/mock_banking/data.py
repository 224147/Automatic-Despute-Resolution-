from copy import deepcopy

CUSTOMERS = {
    "CUST001": {"name": "Rahul Sharma", "pin": "1234", "email": "demo@test.com"},
    "CUST002": {"name": "Priya Singh", "pin": "2345", "email": "demo@test.com"},
    "CUST003": {"name": "Amit Kumar", "pin": "3456", "email": "demo@test.com"},
}

ACCOUNTS = {"CUST001": {"balance": 75420.50, "type": "Savings"}, "CUST002": {"balance": 48100.00, "type": "Savings"}, "CUST003": {"balance": 12999.25, "type": "Current"}}

TRANSACTIONS = {"CUST001": [{"id": "TXN982341", "merchant": "ABC Store", "amount": 4999, "date": "27 Aug 2026", "status": "Completed"}, {"id": "TXN982342", "merchant": "Metro Mart", "amount": 850, "date": "25 Aug 2026", "status": "Completed"}], "CUST002": [], "CUST003": []}

CARDS = {"CARD4321": {"customer_id": "CUST001", "last4": "4321", "status": "ACTIVE", "expired": False}, "CARD7788": {"customer_id": "CUST001", "last4": "7788", "status": "ACTIVE", "expired": False}, "CARD9999": {"customer_id": "CUST002", "last4": "9999", "status": "ACTIVE", "expired": True}}

LOANS = {"CUST001": {"loan_type": "Personal Loan", "emi": 4250, "next_due": "05 Sep 2026", "remaining": 18}, "CUST002": {"loan_type": "Home Loan", "emi": 18400, "next_due": "10 Sep 2026", "remaining": 96}, "CUST003": {"loan_type": "No active loan", "emi": 0, "next_due": "N/A", "remaining": 0}}

_ORIGINAL_STATE = deepcopy({"customers": CUSTOMERS, "accounts": ACCOUNTS, "transactions": TRANSACTIONS, "cards": CARDS, "loans": LOANS})


def snapshot():
    return deepcopy({"customers": CUSTOMERS, "accounts": ACCOUNTS, "transactions": TRANSACTIONS, "cards": CARDS, "loans": LOANS})


def reset_state():
    """Test-support only: restores the in-memory mock banking data to its
    original values. Real persistence for a POC is out of scope — this just
    keeps tests independent of each other's mutations."""
    CUSTOMERS.clear(); CUSTOMERS.update(deepcopy(_ORIGINAL_STATE["customers"]))
    ACCOUNTS.clear(); ACCOUNTS.update(deepcopy(_ORIGINAL_STATE["accounts"]))
    TRANSACTIONS.clear(); TRANSACTIONS.update(deepcopy(_ORIGINAL_STATE["transactions"]))
    CARDS.clear(); CARDS.update(deepcopy(_ORIGINAL_STATE["cards"]))
    LOANS.clear(); LOANS.update(deepcopy(_ORIGINAL_STATE["loans"]))


def find_card(last4: str):
    return next((card_id, card) for card_id, card in CARDS.items() if card["last4"] == last4), None


def card_for_customer(customer_id: str, last4: str):
    for card_id, card in CARDS.items():
        if card["customer_id"] == customer_id and card["last4"] == last4:
            return card_id, card
    return None, None


def block_card(card_id: str):
    card = CARDS[card_id]
    if card["expired"]:
        raise ValueError("expired card")
    if card["status"] == "BLOCKED":
        return False
    card["status"] = "BLOCKED"
    return True


def unblock_card(card_id: str):
    card = CARDS[card_id]
    if card["status"] == "ACTIVE":
        return False
    card["status"] = "ACTIVE"
    return True


def get_customer(customer_id: str):
    return CUSTOMERS.get(customer_id)


def get_transactions(customer_id: str):
    return deepcopy(TRANSACTIONS.get(customer_id, []))


def get_cards(customer_id: str):
    return deepcopy([dict(card, card_id=card_id) for card_id, card in CARDS.items() if card["customer_id"] == customer_id])


def get_account(customer_id: str):
    return deepcopy(ACCOUNTS.get(customer_id))


def get_loan(customer_id: str):
    return deepcopy(LOANS.get(customer_id))


def get_transaction(customer_id: str, transaction_id: str):
    return next((deepcopy(t) for t in TRANSACTIONS.get(customer_id, []) if t["id"] == transaction_id), None)


def match_transactions(customer_id: str, amount: float):
    return [t for t in get_transactions(customer_id) if float(t["amount"]) == float(amount)]


if __name__ == "__main__":
    print(snapshot())

