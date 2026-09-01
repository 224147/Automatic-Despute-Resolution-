import pytest

import database.database as db_module
import mock_banking.data as mock_data


@pytest.fixture(autouse=True)
def isolated_mock_banking():
    mock_data.reset_state()
    yield
    mock_data.reset_state()


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Every test gets a fresh, throwaway SQLite file instead of writing
    into the real demo database/banking.db."""
    db_path = tmp_path / "test_banking.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    yield


@pytest.fixture(autouse=True)
def reset_sessions():
    from backend.session import PENDING, SESSIONS
    SESSIONS.clear()
    PENDING.clear()
    yield
    SESSIONS.clear()
    PENDING.clear()
