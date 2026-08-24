"""Seed script: generates synthetic banking data. Run with `python -m scripts.seed`."""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AccountStatus,
    CardStatus,
    DisputeCategory,
    DisputeStatus,
    TransactionStatus,
    TransactionType,
)
from app.database.session import get_session_factory, init_db
from app.models.models import Account, Card, Customer, Dispute, Transaction

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Ananya", "Diya", "Saanvi", "Aadhya", "Isha", "Priya", "Meera", "Kavya", "Riya", "Neha",
    "Rohan", "Kunal", "Amit", "Vikram", "Suresh", "Rajesh", "Deepak", "Manish", "Rahul", "Nikhil",
    "Pooja", "Swati", "Anjali", "Shruti", "Divya", "Sneha", "Tanvi", "Nisha", "Pallavi", "Rashmi",
    "Akash", "Yash", "Harsh", "Karan", "Gaurav", "Siddharth", "Pranav", "Dev", "Aryan", "Sahil",
]
LAST_NAMES = [
    "Sharma", "Patel", "Gupta", "Singh", "Kumar", "Verma", "Jain", "Reddy", "Nair", "Iyer",
    "Chatterjee", "Mukherjee", "Das", "Bose", "Sen", "Rao", "Pillai", "Menon", "Banerjee", "Ghosh",
    "Agarwal", "Mishra", "Tiwari", "Pandey", "Mehta", "Shah", "Desai", "Joshi", "Kulkarni", "Patil",
]
MERCHANTS = [
    "Amazon India", "Flipkart", "Swiggy", "Zomato", "BigBasket", "PhonePe Merchant",
    "Google Pay Merchant", "Paytm Mall", "Myntra", "Jio Mart", "DMart", "Reliance Digital",
    "BookMyShow", "MakeMyTrip", "IRCTC", "Uber India", "Ola Cabs", "Airtel Recharge",
    "Vodafone Recharge", "Electricity Board",
]
BANKS = ["SBI", "HDFC", "ICICI", "Axis", "Kotak", "PNB", "BOB", "Canara", "Union", "IndusInd"]


def _random_phone() -> str:
    return f"+91{random.randint(7000000000, 9999999999)}"


def _random_account_number() -> str:
    return f"{random.randint(1000, 9999)}{random.randint(10000000, 99999999)}"


def _random_card_number() -> str:
    return f"4{random.randint(100, 999)}{random.randint(1000, 9999)}{random.randint(1000, 9999)}{random.randint(1000, 9999)}"


def _random_txn_ref(txn_type: str) -> str:
    return f"{txn_type[:3].upper()}{random.randint(100000000, 999999999)}"


async def seed(session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    customers: list[Customer] = []
    accounts: list[Account] = []
    cards: list[Card] = []
    transactions: list[Transaction] = []

    hashed = pwd_ctx.hash("Test@1234")

    # ── Customers (100+) ──
    used_emails: set[str] = set()
    for i in range(110):
        fn = random.choice(FIRST_NAMES)
        ln = random.choice(LAST_NAMES)
        email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
        if email in used_emails:
            email = f"{fn.lower()}{i}.{ln.lower()}@example.com"
        used_emails.add(email)
        c = Customer(
            id=uuid.uuid4(),
            first_name=fn,
            last_name=ln,
            email=email,
            phone=_random_phone(),
            hashed_password=hashed,
            is_active=True,
            role="CUSTOMER",
            verification_code="1234",
        )
        customers.append(c)

    # Add agent and admin users
    agent = Customer(
        id=uuid.uuid4(), first_name="Agent", last_name="Smith",
        email="agent@bank.com", phone="+919000000001",
        hashed_password=hashed, is_active=True, role="SUPPORT_AGENT",
        verification_code="0000",
    )
    admin = Customer(
        id=uuid.uuid4(), first_name="Admin", last_name="User",
        email="admin@bank.com", phone="+919000000002",
        hashed_password=hashed, is_active=True, role="ADMIN",
        verification_code="0000",
    )
    manager = Customer(
        id=uuid.uuid4(), first_name="Dispute", last_name="Manager",
        email="manager@bank.com", phone="+919000000003",
        hashed_password=hashed, is_active=True, role="DISPUTE_MANAGER",
        verification_code="0000",
    )
    customers.extend([agent, admin, manager])
    session.add_all(customers)
    await session.flush()

    # ── Accounts ──
    used_acc: set[str] = set()
    for c in customers:
        if c.role != "CUSTOMER":
            continue
        for _ in range(random.randint(1, 2)):
            acc_num = _random_account_number()
            while acc_num in used_acc:
                acc_num = _random_account_number()
            used_acc.add(acc_num)
            a = Account(
                id=uuid.uuid4(), customer_id=c.id, account_number=acc_num,
                account_type=random.choice(["SAVINGS", "CURRENT"]),
                balance=round(random.uniform(5000, 500000), 2),
                status=AccountStatus.ACTIVE.value,
            )
            accounts.append(a)
    session.add_all(accounts)
    await session.flush()

    # ── Cards ──
    used_card: set[str] = set()
    for c in customers:
        if c.role != "CUSTOMER":
            continue
        for _ in range(random.randint(0, 2)):
            cn = _random_card_number()
            while cn in used_card:
                cn = _random_card_number()
            used_card.add(cn)
            card = Card(
                id=uuid.uuid4(), customer_id=c.id, card_number=cn,
                card_type=random.choice(["DEBIT", "CREDIT"]),
                expiry_date=f"{random.randint(1,12):02d}/{random.randint(2026,2030)}",
                status=CardStatus.ACTIVE.value,
                credit_limit=round(random.uniform(50000, 500000), 2) if random.random() > 0.5 else None,
            )
            cards.append(card)
    session.add_all(cards)
    await session.flush()

    # ── Transactions (500+) ──
    used_ref: set[str] = set()
    statuses_weighted = [
        (TransactionStatus.SUCCESS.value, 60),
        (TransactionStatus.FAILED.value, 15),
        (TransactionStatus.PENDING.value, 10),
        (TransactionStatus.REVERSED.value, 10),
        (TransactionStatus.REFUNDED.value, 5),
    ]
    status_pool = [s for s, w in statuses_weighted for _ in range(w)]
    txn_types = [t.value for t in TransactionType if t != TransactionType.OTHER]

    for _ in range(550):
        acc = random.choice(accounts)
        txn_type = random.choice(txn_types)
        ref = _random_txn_ref(txn_type)
        while ref in used_ref:
            ref = _random_txn_ref(txn_type)
        used_ref.add(ref)
        card_id = None
        if txn_type in ("CARD", "CREDIT_CARD") and cards:
            cust_cards = [cd for cd in cards if cd.customer_id == acc.customer_id]
            if cust_cards:
                card_id = random.choice(cust_cards).id
        txn = Transaction(
            id=uuid.uuid4(), account_id=acc.id, transaction_ref=ref,
            transaction_type=txn_type,
            amount=round(random.uniform(10, 100000), 2),
            status=random.choice(status_pool),
            description=f"Payment to {random.choice(MERCHANTS)}",
            merchant=random.choice(MERCHANTS),
            counterparty=f"{random.choice(BANKS)} - {random.choice(LAST_NAMES)}",
            card_id=card_id,
            transaction_date=now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23)),
        )
        transactions.append(txn)
    session.add_all(transactions)
    await session.flush()

    # ── Sample Disputes ──
    dispute_messages = {
        DisputeCategory.UPI_FAILED: "My UPI transaction failed but Rs. {amt} was deducted from my account.",
        DisputeCategory.UPI_PENDING: "My UPI payment of Rs. {amt} is still showing as pending since yesterday.",
        DisputeCategory.ATM_CASH_NOT_RECEIVED: "ATM did not dispense cash but Rs. {amt} was debited from my account.",
        DisputeCategory.UNAUTHORIZED_CARD_TRANSACTION: "I see an unauthorized card transaction of Rs. {amt} that I did not make.",
        DisputeCategory.CARD_PAYMENT_FAILED: "My card payment of Rs. {amt} failed but the amount was charged.",
        DisputeCategory.REFUND_NOT_RECEIVED: "I returned my order but the refund of Rs. {amt} has not been credited.",
        DisputeCategory.NEFT_RTGS_IMPS_ISSUE: "My NEFT transfer of Rs. {amt} failed but money was debited.",
        DisputeCategory.WRONG_BANK_CHARGE: "I was wrongly charged Rs. {amt} as bank fees.",
        DisputeCategory.LOAN_EMI_DISPUTE: "My loan EMI of Rs. {amt} was debited twice this month.",
        DisputeCategory.CREDIT_CARD_BILLING_DISPUTE: "My credit card bill shows an incorrect charge of Rs. {amt}.",
    }
    failed_txns = [t for t in transactions if t.status in ("FAILED", "PENDING", "REVERSED")]
    for i, (cat, msg_tpl) in enumerate(dispute_messages.items()):
        if i >= len(failed_txns):
            break
        txn = failed_txns[i]
        acc = next(a for a in accounts if a.id == txn.account_id)
        d = Dispute(
            id=uuid.uuid4(), customer_id=acc.customer_id, transaction_id=txn.id,
            category=cat.value, status=DisputeStatus.SUBMITTED.value, priority="MEDIUM",
            customer_message=msg_tpl.format(amt=int(txn.amount)), amount=txn.amount,
        )
        session.add(d)

    await session.commit()
    print(f"Seeded: {len(customers)} customers, {len(accounts)} accounts, "
          f"{len(cards)} cards, {len(transactions)} transactions, {min(len(failed_txns), len(dispute_messages))} disputes")


async def main() -> None:
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
