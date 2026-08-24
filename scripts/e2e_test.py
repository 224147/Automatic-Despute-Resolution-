"""End-to-end test script that exercises the full system via API calls."""
import json
import sys

import httpx

BASE = "http://localhost:8000"
client = httpx.Client(timeout=60.0)


def heading(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def check(label: str, response, expected_status: int = 200) -> dict:
    ok = response.status_code == expected_status
    symbol = "PASS" if ok else "FAIL"
    print(f"  [{symbol}] {label} - HTTP {response.status_code}")
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:200]}
    if not ok:
        print(f"    Response: {json.dumps(data, indent=2)[:300]}")
    return data


def main():
    failures = 0

    # ── Health ──
    heading("1. Health Check")
    r = client.get(f"{BASE}/health")
    d = check("GET /health", r)
    if d.get("status") != "healthy":
        failures += 1

    # ── Register customer ──
    heading("2. Register Customer")
    r = client.post(f"{BASE}/api/v1/auth/register", json={
        "first_name": "E2E", "last_name": "Tester",
        "email": "e2e@example.com", "phone": "+919876543210",
        "password": "Test@1234"
    })
    d = check("POST /auth/register", r, 201)
    customer_id = d.get("id")

    # ── Login ──
    heading("3. Login")
    r = client.post(f"{BASE}/api/v1/auth/login", json={
        "email": "e2e@example.com", "password": "Test@1234"
    })
    d = check("POST /auth/login", r)
    token = d.get("access_token", "")
    headers = {"Authorization": f"Bearer {token}"}

    # ── Get customer profile ──
    heading("4. Customer Profile")
    r = client.get(f"{BASE}/api/v1/customers/me", headers=headers)
    d = check("GET /customers/me", r)

    # ── Classify disputes ──
    heading("5. Classification Tests")

    test_cases = [
        ("My UPI transaction failed but Rs. 500 was deducted from my account.", "UPI_FAILED"),
        ("ATM did not give me cash but Rs. 10000 was deducted.", "ATM_CASH_NOT_RECEIVED"),
        ("I don't recognize this Rs. 75000 card transaction.", "UNAUTHORIZED_CARD_TRANSACTION"),
        ("My refund has not been credited yet.", "REFUND_NOT_RECEIVED"),
        ("My NEFT transfer of Rs. 30000 failed.", "NEFT_RTGS_IMPS_ISSUE"),
        ("I was wrongly charged Rs. 500 as bank fees.", "WRONG_BANK_CHARGE"),
        ("My loan EMI was debited twice this month.", "LOAN_EMI_DISPUTE"),
        ("My credit card bill shows an incorrect charge of Rs. 2000.", "CREDIT_CARD_BILLING_DISPUTE"),
    ]

    for msg, expected_cat in test_cases:
        r = client.post(f"{BASE}/api/v1/disputes/classify", headers=headers,
                        json={"customer_message": msg})
        d = check(f"Classify: {expected_cat}", r)
        actual = d.get("dispute_category", "")
        if actual != expected_cat:
            print(f"    MISMATCH: expected={expected_cat}, got={actual}")
            failures += 1
        else:
            print(f"    Category: {actual}, Confidence: {d.get('confidence')}")

    # ── Scenario 1: UPI Failed - Auto Resolution ──
    heading("6. Scenario: UPI Failed (Auto-resolve)")
    r = client.post(f"{BASE}/api/v1/disputes", headers=headers, json={
        "customer_message": "My UPI transaction failed but Rs. 500 was deducted from my account."
    })
    d = check("POST /disputes (UPI failed)", r, 201)
    dispute_id_1 = d.get("dispute_id")
    print(f"    Dispute ID: {dispute_id_1}")
    print(f"    Category: {d.get('category')}")
    print(f"    Status: {d.get('status')}")
    print(f"    Risk Level: {d.get('risk_level')}")
    print(f"    Response: {d.get('final_response', '')[:200]}")

    if dispute_id_1:
        r = client.get(f"{BASE}/api/v1/disputes/{dispute_id_1}", headers=headers)
        d = check("GET /disputes/{id}", r)
        print(f"    DB Status: {d.get('status')}")

        r = client.get(f"{BASE}/api/v1/disputes/{dispute_id_1}/status", headers=headers)
        d = check("GET /disputes/{id}/status", r)

    # ── Scenario 2: ATM Dispute ──
    heading("7. Scenario: ATM Cash Not Received")
    r = client.post(f"{BASE}/api/v1/disputes", headers=headers, json={
        "customer_message": "ATM did not give me cash but Rs. 10000 was deducted from my account."
    })
    d = check("POST /disputes (ATM)", r, 201)
    print(f"    Category: {d.get('category')}, Status: {d.get('status')}")
    print(f"    Response: {d.get('final_response', '')[:200]}")

    # ── Scenario 3: Unauthorized Card - High Risk - Escalation ──
    heading("8. Scenario: Unauthorized Card Transaction (should escalate)")
    r = client.post(f"{BASE}/api/v1/disputes", headers=headers, json={
        "customer_message": "I don't recognize this Rs. 75000 card transaction on my account."
    })
    d = check("POST /disputes (unauthorized card)", r, 201)
    _dispute_id_3 = d.get("dispute_id")
    print(f"    Category: {d.get('category')}, Status: {d.get('status')}")
    print(f"    Risk Level: {d.get('risk_level')}")
    print(f"    Response: {d.get('final_response', '')[:200]}")

    # ── Agent login and escalation management ──
    heading("9. Agent Escalation Management")
    r = client.post(f"{BASE}/api/v1/auth/login", json={
        "email": "agent@bank.com", "password": "Test@1234"
    })
    d = check("Agent login", r)
    agent_token = d.get("access_token", "")
    agent_headers = {"Authorization": f"Bearer {agent_token}"}

    r = client.get(f"{BASE}/api/v1/escalations", headers=agent_headers)
    d = check("GET /escalations", r)
    print(f"    Open escalations: {len(d)}")
    if d:
        esc_id = d[0]["id"]
        print(f"    First escalation: {esc_id}, reason: {d[0].get('reason')}")

        # Assign to agent
        r2 = client.post(f"{BASE}/api/v1/escalations/{esc_id}/assign",
                         headers=agent_headers,
                         json={"agent_id": customer_id, "team": "FRAUD_TEAM"})
        check("POST /escalations/{id}/assign", r2)

        # Resolve
        r3 = client.post(f"{BASE}/api/v1/escalations/{esc_id}/resolve",
                         headers=agent_headers,
                         json={"resolution_notes": "Investigated and resolved. Refund initiated.",
                               "resolution_type": "MANUAL_RESOLUTION", "refund_amount": 75000})
        check("POST /escalations/{id}/resolve", r3)

    # ── Customer transactions ──
    heading("10. Customer Transactions")
    r = client.get(f"{BASE}/api/v1/customers/me/transactions", headers=headers)
    d = check("GET /customers/me/transactions", r)
    print(f"    Transaction count: {len(d)}")

    # ── OpenAPI docs ──
    heading("11. API Documentation")
    r = client.get(f"{BASE}/docs")
    print(f"  [{'PASS' if r.status_code == 200 else 'FAIL'}] GET /docs - HTTP {r.status_code}")

    # ── Summary ──
    heading("SUMMARY")
    if failures == 0:
        print("  All tests PASSED!")
    else:
        print(f"  {failures} test(s) FAILED")

    return failures


if __name__ == "__main__":
    sys.exit(main())
