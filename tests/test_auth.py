from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.governance.auth import Principal, _issue, decode_token, issue_token


def test_principal_accepts_its_permission():
    principal = Principal(2, "analyst", frozenset({"data_analyst"}), frozenset({"analytics.query"}))
    principal.require("analytics.query")


def test_principal_rejects_missing_permission():
    principal = Principal(2, "analyst", frozenset({"data_analyst"}), frozenset())
    with pytest.raises(PermissionError):
        principal.require("governance.table.manage")


def test_admin_bypasses_individual_permission():
    principal = Principal(1, "admin", frozenset({"platform_admin"}))
    principal.require("governance.table.manage")


def test_jwt_round_trip_preserves_scope(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-bytes-long")
    principal = Principal(
        2, "analyst", frozenset({"data_analyst"}), frozenset({"analytics.query"}), "sales", "manager"
    )
    restored = decode_token(issue_token(principal), validate_state=False)
    assert restored == principal


def test_refresh_token_cannot_be_used_as_access_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-bytes-long")
    principal = Principal(2, "analyst", frozenset({"data_analyst"}))
    token = _issue(principal, "refresh", datetime.now(timezone.utc) + timedelta(days=1))
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token)
