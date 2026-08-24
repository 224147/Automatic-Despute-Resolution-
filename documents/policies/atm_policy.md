# ATM Transaction Dispute Policy

Policy ID: POL-ATM-001
Version: 1.5
Effective Date: 2024-01-01
Category: ATM

## 1. Cash Not Dispensed – Account Debited

### 1.1 Eligibility
- Customer's account was debited but ATM did not dispense cash (full or partial).
- Transaction must be within the last 30 days.

### 1.2 Resolution Timeline
- As per RBI mandate, ATM transaction disputes must be resolved within 5 business days.
- If not resolved within 5 days, provisional credit of the disputed amount must be provided.

### 1.3 Auto-Resolution Criteria
- Transaction confirmed as failed by the ATM switch.
- Amount ≤ INR 15,000: eligible for auto-reversal.
- Amount > INR 15,000 and ≤ INR 50,000: eligible with system verification.
- Amount > INR 50,000: requires manual review.

### 1.4 Verification Requirements
- Customer identity verification mandatory.
- ATM journal verification (mock: auto-verified in sandbox).
- Camera footage review for amounts > INR 25,000 (mock: flagged for review).

## 2. Partial Cash Dispensed
- If ATM dispensed partial cash, the difference amount is eligible for reversal.
- Customer must specify the amount received vs. amount debited.

## 3. Fraud Indicators
- Multiple ATM disputes at different ATMs in short timeframe: flag for fraud review.
- Disputes for maximum withdrawal amounts: enhanced scrutiny.
- Customer account with recent address/phone change: additional verification needed.
