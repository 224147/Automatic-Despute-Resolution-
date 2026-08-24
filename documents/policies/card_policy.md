# Card Transaction Dispute Policy

Policy ID: POL-CARD-001
Version: 2.0
Effective Date: 2024-01-01
Category: CARD

## 1. Unauthorized Card Transaction

### 1.1 Customer Liability
- As per RBI circular on limiting liability:
  - Zero liability if reported within 3 days of transaction.
  - Limited liability if reported between 4-7 days.
  - Full liability if reported after 7 days (subject to review).

### 1.2 Resolution
- Unauthorized transactions MUST NOT be auto-resolved.
- All unauthorized card transactions require fraud team review.
- Card must be blocked immediately upon reporting.
- Provisional credit may be issued within 10 business days.
- Amount > INR 50,000: escalate to fraud investigation team.

### 1.3 Required Actions
- Block the card immediately.
- Initiate chargeback process with merchant/acquirer.
- File fraud report if amount > INR 25,000.

## 2. Card Payment Failed/Reversed

### 2.1 Eligibility
- Card payment failed at merchant end but amount was charged.
- Transaction status must show FAILED or REVERSED.

### 2.2 Auto-Resolution
- Amount ≤ INR 10,000: eligible for auto-reversal within T+5 days.
- Amount > INR 10,000: requires merchant confirmation.

## 3. Refund Not Received

### 3.1 Timeline
- Refunds must be processed within 5-7 business days of merchant confirmation.
- If refund not received within 10 business days: escalate.

### 3.2 Auto-Resolution
- Merchant refund confirmed but not credited within 7 days: auto-credit.
- Merchant refund not confirmed: contact merchant through chargeback.

## 4. Credit Card Billing Dispute

### 4.1 Eligibility
- Incorrect charges on credit card statement.
- Duplicate charges.
- Charges for cancelled services.

### 4.2 Resolution
- Amount ≤ INR 5,000 and clear duplicate: auto-reverse.
- All other cases: manual review required.
- Customer must provide supporting documentation for disputed charges.
