"""Streamlit frontend for the Dispute Resolution POC.

Adapted from the original full-system frontend: this POC backend exposes a single
POST /disputes endpoint and has no authentication, so login and the agent/escalation
dashboard pages (which depended on removed endpoints) are dropped.
"""
from __future__ import annotations

import os

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8001")

st.set_page_config(page_title="Dispute Resolution POC", layout="centered")


def submit_dispute():
    st.title("🏦 Automated Dispute Resolution — POC")
    st.caption(
        "Only `exact_duplicate` disputes under the configured threshold auto-resolve. Everything else escalates."
    )

    with st.form("dispute_form"):
        customer_id = st.text_input("Customer ID", value="CUST-1")
        transaction_id = st.text_input("Transaction ID", value="TXN-1")
        st.caption("Seeded transactions: TXN-1 ($25.00), TXN-2 ($500.00)")
        amount_usd = st.text_input("Amount (USD)", value="25.00")
        description = st.text_area(
            "Describe the issue",
            value="I was charged twice for the same purchase.",
            height=100,
        )
        submitted = st.form_submit_button("Submit Dispute")

    if submitted and customer_id and transaction_id and description:
        with st.spinner("Processing your dispute..."):
            try:
                resp = httpx.post(
                    f"{API_BASE}/disputes",
                    json={
                        "customer_id": customer_id,
                        "transaction_id": transaction_id,
                        "amount_usd": amount_usd,
                        "description": description,
                    },
                    timeout=60,
                )
                if resp.status_code == 200:
                    result = resp.json()

                    if not result["is_new_case"]:
                        st.info(
                            f"ℹ️ You already have an open case for this customer/transaction "
                            f"(**{result['case_id']}**, amount **${result['amount_usd']}**). "
                            f"That existing case was reused instead of creating a new one — the amount and "
                            f"description you just entered were **not** applied. Use a different Customer ID "
                            f"or Transaction ID to start a fresh case."
                        )

                    if result["decision"] == "auto_resolve":
                        st.success(
                            f"✅ Good news — we've reviewed your dispute and confirmed it as a duplicate charge. "
                            f"A provisional credit of **${result['amount_usd']}** has been issued to your account.\n\n"
                            f"**Reference number:** {result['case_id']}"
                        )
                        if result.get("rationale"):
                            st.caption(f"Why: {result['rationale']}")
                    else:
                        st.warning(
                            f"⏳ We've received your dispute and it's been passed to our review team for a closer "
                            f"look. You'll hear back from us shortly.\n\n"
                            f"**Reference number:** {result['case_id']}"
                        )
                        st.write("**Why it needs manual review:**")
                        for reason in result["reasons"]:
                            st.write(f"- {reason}")
                        if result.get("rationale"):
                            st.caption(f"Assistant's read on the case: {result['rationale']}")

                    with st.expander("Full response (raw)"):
                        st.json(result)
                else:
                    st.error(f"Error: {resp.json().get('detail', resp.text)}")
            except httpx.ConnectError:
                st.error(f"Cannot connect to backend at {API_BASE}. Is `uvicorn api:app` running?")


if __name__ == "__main__":
    submit_dispute()
