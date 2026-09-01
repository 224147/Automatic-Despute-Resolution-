from dotenv import load_dotenv

load_dotenv()  # must run before api_client reads API_BASE_URL from os.environ

import streamlit as st

import api_client

st.set_page_config(page_title="Navyline Banking Assistant", page_icon="◈", layout="wide")

RAG_THRESHOLD = 0.70  # mirrors rag/retrieval.py THRESHOLD

DEFAULTS = {
    "authenticated": False,
    "messages": [],
    "pending_otp": None,
    "customer_id": None,
    "session_id": None,
    "debug": {},
    "chat_pending": None,
    "chat_context": {},
    "pending_card_action": None,
    "pending_dispute_confirm": None,
    "pending_complaint_confirm": None,
    "notifications": [],
    "profile": None,
    "account": None,
    "cards": None,
    "disputes": None,
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)

st.markdown("""<style>
:root { --navy:#10243e; --teal:#197d78; --ink:#172234; --surface:#f7f9fb; --line:#dfe6ed; }
.block-container {max-width:1180px;padding-top:2rem;} .bank-title {color:var(--navy);font-size:2rem;font-weight:700;margin-bottom:.2rem}.muted{color:#687789}.pill{padding:.25rem .55rem;border-radius:999px;background:#e6f3f1;color:#12625e;font-size:.8rem;font-weight:600}.event{color:#197d78}.warning{color:#9a6500}
</style>""", unsafe_allow_html=True)


def add_message(role, content):
    st.session_state.messages.append((role, content))


def format_notification(events):
    if not events:
        return None
    if events.get("published"):
        return "Event published to RabbitMQ — audit & notification will be processed by the consumer."
    notification = events.get("notification", {})
    email = notification.get("email", {})
    sms = notification.get("sms", {})
    return f"Email {email.get('status', '?')} · SMS {sms.get('status', '?')}"


def update_debug(result: dict):
    debug = st.session_state.debug
    debug["session"] = "VALID"
    debug["customer"] = st.session_state.customer_id
    for field in ("intent", "risk", "route", "agent", "current_step", "rag_confidence", "guardrail", "idempotency_result", "events"):
        if field in result:
            debug[field] = result[field]
    debug["risk_source"] = "Backend Risk Policy Engine"
    debug["rag_threshold"] = RAG_THRESHOLD
    step = result.get("current_step", "")
    if step in ("Card Not Found", "Card Expired"):
        debug["ownership"] = "FAILED"
        debug["authorization"] = "FAILED"
    elif result.get("agent") in ("Card Agent", "Dispute Agent", "Complaint Agent"):
        debug["ownership"] = "PASSED"
        debug["authorization"] = "PASSED"
    else:
        debug["ownership"] = "N/A"
        debug["authorization"] = "N/A"
    st.session_state.debug = debug


def refresh_profile_and_account():
    """Sidebar/account data is fetched once (at login) and cached in
    session_state, then refreshed only after an action that can actually
    change it — not on every Streamlit rerun. Streamlit reruns this whole
    script on every click/message, so re-fetching on every rerun turned
    every interaction into 4-5 sequential network round-trips."""
    sid = st.session_state.session_id
    st.session_state.profile = api_client.profile(sid)
    st.session_state.account = api_client.balance(sid)
    refresh_cards()
    refresh_disputes()


def refresh_cards():
    st.session_state.cards = api_client.cards(st.session_state.session_id)


def refresh_disputes():
    st.session_state.disputes = api_client.list_disputes(st.session_state.session_id)


def login_view():
    st.markdown('<div class="bank-title">Navyline Banking Assistant</div>', unsafe_allow_html=True)
    st.caption("Secure customer support for everyday banking needs")
    st.info("Demo Environment — no real banking credentials or notifications are used.")
    if not st.session_state.pending_otp:
        with st.form("login"):
            cid = st.text_input("Customer ID", placeholder="CUST001")
            pin = st.text_input("PIN", type="password", placeholder="1234")
            if st.form_submit_button("Continue", type="primary"):
                try:
                    otp = api_client.login(cid.strip().upper(), pin)
                    st.session_state.pending_otp = (cid.strip().upper(), otp)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    else:
        cid, otp = st.session_state.pending_otp
        st.success("Demo OTP generated. It expires in 5 minutes and allows 3 attempts.")
        st.code(f"Demo OTP: {otp}")
        with st.form("otp"):
            entered = st.text_input("Enter demo OTP", max_chars=6)
            if st.form_submit_button("Verify OTP", type="primary"):
                try:
                    session = api_client.verify_otp(cid, entered)
                    st.session_state.update(
                        authenticated=True,
                        customer_id=session["customer_id"],
                        session_id=session["session_id"],
                        pending_otp=None,
                    )
                    refresh_profile_and_account()
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        if st.button("Start over"):
            st.session_state.pending_otp = None
            st.rerun()


def sidebar():
    profile = st.session_state.profile
    with st.sidebar:
        st.markdown("### Customer")
        st.write(f"**{profile['name']}**")
        st.caption(st.session_state.customer_id)

        st.markdown("### Account")
        account = st.session_state.account
        st.metric("Available balance", f"₹{account['balance']:,.2f}")

        st.markdown("### Cards")
        for card in st.session_state.cards:
            st.write(f"****{card['last4']} — {card['status']}")

        st.markdown("### Open disputes")
        if st.session_state.disputes:
            for dispute in st.session_state.disputes:
                st.write(f"{dispute['id']} — {dispute['status']}")
        else:
            st.caption("No open disputes")

        st.markdown("### Notifications")
        for note in st.session_state.notifications:
            st.caption(note)

        if st.button("Logout"):
            api_client.logout(st.session_state.session_id)
            for key, value in DEFAULTS.items():
                st.session_state[key] = value
            st.rerun()


def send_to_backend(message, pending=None):
    try:
        result = api_client.chat(st.session_state.session_id, message, pending, st.session_state.chat_context)
    except ValueError as exc:
        add_message("assistant", f"Something went wrong reaching the assistant: {exc}")
        return

    update_debug(result)
    add_message("assistant", result.get("response"))

    # Structured conversation context (e.g. transactions already shown) is
    # always carried forward, independent of any pending slot-filling flow.
    st.session_state.chat_context = result.get("context") or {}

    agent = result.get("agent")
    step = result.get("current_step")
    agent_result = result.get("agent_result") or {}

    st.session_state.chat_pending = None

    if agent == "Card Agent" and step == "Awaiting Confirmation":
        if "pending_card" in agent_result:
            st.session_state.pending_card_action = {"action": "block", "last4": agent_result["pending_card"]}
        elif "pending_unblock_card" in agent_result:
            st.session_state.pending_card_action = {"action": "unblock", "last4": agent_result["pending_unblock_card"]}

    elif agent == "Card Agent" and step == "Awaiting Card Number":
        st.session_state.chat_pending = {"type": "card_last4", "intent": result.get("intent")}

    elif agent == "Dispute Agent" and step == "Awaiting Issue Type":
        st.session_state.chat_pending = {"type": "dispute_issue", "transaction": agent_result["transaction"]}

    elif agent == "Dispute Agent" and step == "Multiple Matches":
        st.session_state.chat_pending = {"type": "dispute_pick", "candidates": agent_result["candidates"]}

    elif agent == "Dispute Agent" and step == "Awaiting Confirmation":
        st.session_state.pending_dispute_confirm = {"transaction": agent_result["transaction"], "issue": agent_result["issue"]}

    elif agent == "Complaint Agent" and step == "Awaiting Description":
        st.session_state.chat_pending = {"type": "complaint_description"}

    elif agent == "Complaint Agent" and step == "Awaiting Confirmation":
        st.session_state.pending_complaint_confirm = agent_result["description"]


def confirmation_panels():
    action = st.session_state.pending_card_action
    if action:
        st.warning(f"Confirm card {action['action']}")
        c1, c2 = st.columns(2)
        if c1.button(f"Confirm {action['action'].title()}", type="primary", key="confirm-card"):
            try:
                if action["action"] == "block":
                    result = api_client.block_card(st.session_state.session_id, action["last4"])
                else:
                    result = api_client.unblock_card(st.session_state.session_id, action["last4"])
                note = format_notification(result.get("events"))
                if note:
                    st.session_state.notifications.append(note)
                st.session_state.debug.update(idempotency_result=result.get("idempotency_result"), events=result.get("events"))
                add_message("assistant", f"Your card ending {action['last4']} has been {result['status'].lower()} successfully.")
                refresh_cards()
            except ValueError as exc:
                add_message("assistant", f"Couldn't complete that: {exc}")
            st.session_state.pending_card_action = None
            st.rerun()
        if c2.button("Cancel", key="cancel-card"):
            st.session_state.pending_card_action = None
            add_message("assistant", "Card action cancelled.")
            st.rerun()

    dispute = st.session_state.pending_dispute_confirm
    if dispute:
        st.warning("Confirm dispute submission")
        c1, c2 = st.columns(2)
        if c1.button("Confirm Dispute", type="primary", key="confirm-dispute"):
            try:
                result = api_client.create_dispute(st.session_state.session_id, dispute["transaction"]["id"], dispute["issue"])
                note = format_notification(result.get("events"))
                if note:
                    st.session_state.notifications.append(note)
                st.session_state.debug.update(idempotency_result=result.get("idempotency_result"), events=result.get("events"))
                add_message("assistant", f"Dispute {result['id']} has been submitted.\n\nStatus: {result['status']}\nEstimated resolution: {result.get('estimated_resolution', '3-7 business days')}")
                refresh_disputes()
            except ValueError as exc:
                add_message("assistant", f"Couldn't submit that dispute: {exc}")
            st.session_state.pending_dispute_confirm = None
            st.rerun()
        if c2.button("Cancel", key="cancel-dispute"):
            st.session_state.pending_dispute_confirm = None
            add_message("assistant", "Dispute cancelled.")
            st.rerun()

    complaint = st.session_state.pending_complaint_confirm
    if complaint:
        st.warning("Confirm complaint submission")
        c1, c2 = st.columns(2)
        if c1.button("Confirm Complaint", type="primary", key="confirm-complaint"):
            try:
                result = api_client.create_complaint(st.session_state.session_id, complaint)
                note = format_notification(result.get("events"))
                if note:
                    st.session_state.notifications.append(note)
                st.session_state.debug.update(idempotency_result=result.get("idempotency_result"), events=result.get("events"))
                add_message("assistant", f"Complaint {result['id']} has been filed. Status: {result['status']}")
            except ValueError as exc:
                add_message("assistant", f"Couldn't file that complaint: {exc}")
            st.session_state.pending_complaint_confirm = None
            st.rerun()
        if c2.button("Cancel", key="cancel-complaint"):
            st.session_state.pending_complaint_confirm = None
            add_message("assistant", "Complaint cancelled.")
            st.rerun()


def main_view():
    if not st.session_state.profile:
        # First render after a hot-reload, or state lost some other way —
        # fetch once and cache, same as right after login.
        try:
            refresh_profile_and_account()
        except ValueError as exc:
            st.error(f"Session error: {exc}")
            st.session_state.authenticated = False
            st.rerun()
            return

    sidebar()
    name = st.session_state.profile["name"]
    st.markdown(f'<div class="bank-title">Good morning, {name.split()[0]}</div>', unsafe_allow_html=True)
    st.caption("Authenticated session · Customer support assistant")

    for role, content in st.session_state.messages:
        with st.chat_message(role):
            if isinstance(content, list):
                st.dataframe(content, hide_index=True, use_container_width=True)
            elif isinstance(content, dict):
                st.json(content)
            else:
                st.markdown(content)

    st.markdown("#### Quick actions")
    cols = st.columns(4)
    for col, label in zip(cols, ["Check balance", "View transactions", "Show cards", "View EMI"]):
        if col.button(label, use_container_width=True):
            add_message("user", label)
            send_to_backend(label)
            st.rerun()

    confirmation_panels()

    prompt = st.chat_input("Ask about your account, cards, transactions, or policies")
    if prompt:
        add_message("user", prompt)
        send_to_backend(prompt, st.session_state.chat_pending)
        st.rerun()

    with st.expander("Developer / Debug Information — Not customer-facing"):
        st.caption("Backend workflow state only")
        st.json(st.session_state.debug)


if st.session_state.authenticated:
    main_view()
else:
    login_view()
