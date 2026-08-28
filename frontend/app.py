"""Streamlit frontend for the Dispute Resolution System."""
from __future__ import annotations

import os

import httpx
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

st.set_page_config(page_title="Bank Dispute Resolution", layout="wide")


def get_headers():
    token = st.session_state.get("token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def login_page():
    st.title("🏦 Bank Dispute Resolution System")
    st.subheader("Login")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted and email and password:
        try:
            resp = httpx.post(
                f"{API_BASE}/auth/login",
                json={"email": email, "password": password},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                st.session_state["token"] = data["access_token"]
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error(f"Login failed: {resp.json().get('detail', 'Unknown error')}")
        except httpx.ConnectError:
            st.error("Cannot connect to backend. Is the server running?")


def customer_chat():
    st.subheader("📝 Submit a Dispute")

    with st.form("dispute_form"):
        message = st.text_area(
            "Describe your issue",
            placeholder="e.g., My UPI transaction failed but Rs. 500 was deducted from my account.",
            height=120,
        )
        txn_ref = st.text_input("Transaction Reference (optional)")
        submitted = st.form_submit_button("Submit Dispute")

    if submitted and message:
        with st.spinner("Processing your dispute..."):
            try:
                resp = httpx.post(
                    f"{API_BASE}/disputes",
                    json={"customer_message": message, "transaction_ref": txn_ref or None},
                    headers=get_headers(),
                    timeout=60,
                )
                if resp.status_code == 201:
                    result = resp.json()
                    if result.get("status") == "AUTO_RESOLVED":
                        st.success(f"✅ {result.get('final_response', 'Dispute resolved!')}")
                    else:
                        st.warning(f"⏳ {result.get('final_response', 'Dispute escalated for review.')}")

                    with st.expander("Dispute Details"):
                        st.json(result)
                else:
                    st.error(f"Error: {resp.json().get('detail', resp.text)}")
            except httpx.ConnectError:
                st.error("Cannot connect to backend.")

    # Classify only
    st.divider()
    st.subheader("🔍 Classify a Complaint (Preview)")
    with st.form("classify_form"):
        cls_message = st.text_area("Enter complaint to classify", height=80)
        cls_submitted = st.form_submit_button("Classify")

    if cls_submitted and cls_message:
        try:
            resp = httpx.post(
                f"{API_BASE}/disputes/classify",
                json={"customer_message": cls_message},
                headers=get_headers(),
                timeout=30,
            )
            if resp.status_code == 200:
                st.json(resp.json())
        except httpx.ConnectError:
            st.error("Cannot connect to backend.")


def dispute_history():
    st.subheader("📋 Dispute History")
    st.info("Enter a Dispute ID to check status.")

    dispute_id = st.text_input("Dispute ID", value=st.query_params.get("dispute_id", ""))
    if st.button("Check Status") and dispute_id:
        try:
            resp = httpx.get(
                f"{API_BASE}/disputes/{dispute_id}/status",
                headers=get_headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                cols = st.columns(3)
                cols[0].metric("Status", data["status"])
                cols[1].metric("Category", data["category"])
                cols[2].metric("Priority", data["priority"])
                if data.get("risk_level"):
                    st.metric("Risk Level", data["risk_level"])
                if data.get("resolution_summary"):
                    st.success(f"Resolution: {data['resolution_summary']}")
            else:
                st.error("Dispute not found or not authorized.")
        except httpx.ConnectError:
            st.error("Cannot connect to backend.")


def agent_dashboard():
    st.subheader("🛡️ Agent Dashboard - Escalation Queue")

    status_filter = st.selectbox("Filter by status", ["", "OPEN", "ASSIGNED", "IN_PROGRESS", "RESOLVED"])
    if st.button("Refresh"):
        pass  # triggers rerun

    try:
        params = {"status_filter": status_filter} if status_filter else {}
        resp = httpx.get(
            f"{API_BASE}/escalations",
            params=params,
            headers=get_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            escalations = resp.json()
            if not escalations:
                st.info("No escalations found.")
            for esc in escalations:
                with st.expander(
                    f"#{str(esc['id'])[:8]} | {esc['reason']} | Priority: {esc['priority']} | Status: {esc['status']}"
                ):
                    st.write(f"**Dispute ID:** {esc['dispute_id']}")
                    st.write(f"**Team:** {esc.get('assigned_team', 'Unassigned')}")
                    st.write(f"**SLA:** {esc['sla_hours']} hours")
                    st.write(f"**Created:** {esc['created_at']}")
                    if esc.get("agent_notes"):
                        st.write(f"**Notes:** {esc['agent_notes']}")

                    # Resolve form
                    with st.form(f"resolve_{esc['id']}"):
                        notes = st.text_area("Resolution notes", key=f"notes_{esc['id']}")
                        refund = st.number_input("Refund amount (optional)", min_value=0.0, key=f"refund_{esc['id']}")
                        if st.form_submit_button("Resolve"):
                            resolve_resp = httpx.post(
                                f"{API_BASE}/escalations/{esc['id']}/resolve",
                                json={
                                    "resolution_notes": notes,
                                    "refund_amount": refund if refund > 0 else None,
                                },
                                headers=get_headers(),
                                timeout=10,
                            )
                            if resolve_resp.status_code == 200:
                                st.success("Escalation resolved!")
                                st.rerun()
                            else:
                                st.error(f"Error: {resolve_resp.text}")
        elif resp.status_code == 403:
            st.error("Access denied. Agent role required.")
        else:
            st.error("Failed to load escalations.")
    except httpx.ConnectError:
        st.error("Cannot connect to backend.")


def main():
    if not st.session_state.get("logged_in"):
        login_page()
        return

    st.sidebar.title("🏦 Navigation")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    page = st.sidebar.radio("Go to", ["Submit Dispute", "Dispute History", "Agent Dashboard"])

    st.title("🏦 Bank Dispute Resolution System")

    if page == "Submit Dispute":
        customer_chat()
    elif page == "Dispute History":
        dispute_history()
    elif page == "Agent Dashboard":
        agent_dashboard()


if __name__ == "__main__":
    main()
