"""Tests for security module."""
from __future__ import annotations

import pytest

from app.security.auth import create_access_token, decode_token, hash_password, verify_password


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("TestPass123")
        assert verify_password("TestPass123", hashed)

    def test_wrong_password(self):
        hashed = hash_password("TestPass123")
        assert not verify_password("WrongPass", hashed)


class TestJWT:
    def test_create_and_decode_token(self):
        token = create_access_token({"sub": "test-user-id", "role": "CUSTOMER"})
        payload = decode_token(token)
        assert payload["sub"] == "test-user-id"
        assert payload["role"] == "CUSTOMER"

    def test_invalid_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            decode_token("invalid.token.here")
