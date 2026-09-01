import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).with_name("banking.db")))


def connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS disputes (id TEXT PRIMARY KEY, customer_id TEXT, transaction_id TEXT, amount REAL, merchant TEXT, status TEXT, issue TEXT, idempotency_key TEXT UNIQUE, created_at TEXT);
        CREATE TABLE IF NOT EXISTS complaints (id TEXT PRIMARY KEY, customer_id TEXT, description TEXT, status TEXT, idempotency_key TEXT UNIQUE, created_at TEXT);
        CREATE TABLE IF NOT EXISTS audit (event_id TEXT PRIMARY KEY, event_type TEXT, customer_id TEXT, session_id TEXT, timestamp TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, record_id TEXT, record_type TEXT);
        """)


def add_audit(event_id, event_type, customer_id, session_id, payload):
    with connection() as conn:
        conn.execute("INSERT OR IGNORE INTO audit VALUES (?, ?, ?, ?, ?, ?)", (event_id, event_type, customer_id, session_id, datetime.now(timezone.utc).isoformat(), json.dumps(payload)))


def find_idempotent(key):
    with connection() as conn:
        row = conn.execute("SELECT * FROM idempotency WHERE key = ?", (key,)).fetchone()
        return dict(row) if row else None


def save_idempotency(key, record_id, record_type):
    with connection() as conn:
        conn.execute("INSERT OR IGNORE INTO idempotency VALUES (?, ?, ?)", (key, record_id, record_type))


def create_dispute(dispute):
    with connection() as conn:
        conn.execute("INSERT INTO disputes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(dispute.values()))


def get_dispute(dispute_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM disputes WHERE id = ?", (dispute_id,)).fetchone()
        return dict(row) if row else None


def list_disputes(customer_id):
    with connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM disputes WHERE customer_id = ?", (customer_id,))]


def create_complaint(complaint):
    with connection() as conn:
        conn.execute("INSERT INTO complaints VALUES (?, ?, ?, ?, ?, ?)", tuple(complaint.values()))


def get_complaint(complaint_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        return dict(row) if row else None


def next_dispute_id():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"DSP-{today}-"
    with connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM disputes WHERE id LIKE ?", (prefix + "%",)).fetchone()[0]
    return f"{prefix}{count + 1:03d}"


def find_dispute_by_transaction(customer_id, transaction_id):
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM disputes WHERE customer_id = ? AND transaction_id = ?",
            (customer_id, transaction_id),
        ).fetchone()
        return dict(row) if row else None


init_db()
