from fastapi import Header, HTTPException

from backend.session import SESSIONS, validate_session


def get_current_customer(x_session_id: str = Header(...)) -> str:
    """Resolve the authenticated customer_id from the session header.

    This is the only source of customer identity for sensitive endpoints —
    a client-supplied customer_id is never trusted for actions.
    """
    if not validate_session(x_session_id):
        raise HTTPException(401, "Session invalid or expired. Please log in again.")
    return SESSIONS[x_session_id]["customer_id"]
