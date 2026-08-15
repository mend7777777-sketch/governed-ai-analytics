"""HTTP contract tests that isolate FastAPI from MySQL, Vanna, and external LLMs."""

from fastapi.testclient import TestClient
import pytest

import app.api.main as api
from app.governance.auth import Principal


ADMIN = Principal(1, "admin", frozenset({"platform_admin"}))
ANALYST = Principal(2, "analyst", frozenset({"data_analyst"}), frozenset({"analytics.query"}))


@pytest.fixture
def client():
    api.app.dependency_overrides.clear()
    with TestClient(api.app) as test_client:
        yield test_client
    api.app.dependency_overrides.clear()


def test_query_requires_login(client):
    response = client.post("/api/query", json={"question": "2025年GMV是多少"})
    assert response.status_code == 401


def test_analyst_can_query_with_permission(client, monkeypatch):
    class QueryService:
        def query(self, question, principal, session_id=None, context=None):
            assert principal == ANALYST
            return {"question": question, "rows": [], "columns": [], "sql": "SELECT 1"}

    api.app.dependency_overrides[api.require_query_access] = lambda: ANALYST
    monkeypatch.setattr(api, "get_service", lambda: QueryService())
    response = client.post("/api/query", json={"question": "2025年GMV是多少"})
    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT 1"


def test_analyst_cannot_approve_governance_table(client):
    api.app.dependency_overrides[api.require_admin] = _forbidden
    response = client.post("/api/governance/tables/dim_date/approve", json={"reason": "test"})
    assert response.status_code == 403


def test_admin_can_approve_governance_table(client, monkeypatch):
    api.app.dependency_overrides[api.require_admin] = lambda: ADMIN

    class Governance:
        def transition(self, principal, table_name, action, reason):
            assert principal == ADMIN
            assert (table_name, action, reason) == ("dim_date", "approve", "approved")
            return {"table_name": table_name, "approval_status": "APPROVED"}

    monkeypatch.setattr(api, "GovernanceService", Governance)
    response = client.post("/api/governance/tables/dim_date/approve", json={"reason": "approved"})
    assert response.status_code == 200
    assert response.json()["approval_status"] == "APPROVED"


def test_login_returns_token_pair(client, monkeypatch):
    monkeypatch.setattr(api, "authenticate", lambda username, password, client_ip="unknown": ADMIN if (username, password) == ("admin", "admin") else None)
    monkeypatch.setattr(api, "issue_token_pair", lambda principal: {"access_token": "access", "refresh_token": "refresh", "token_type": "bearer"})
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert response.status_code == 200
    assert response.json()["refresh_token"] == "refresh"


def test_password_change_requires_login(client):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "old-password", "new_password": "new-password"},
    )
    assert response.status_code == 401


def test_admin_password_reset_contract(client, monkeypatch):
    api.app.dependency_overrides[api.require_iam_admin] = lambda: ADMIN
    called = {}
    monkeypatch.setattr(api, "reset_password", lambda actor, username, new_password: called.update({"username": username, "password": new_password}))
    response = client.post(
        "/api/iam/users/analyst/reset-password",
        json={"new_password": "new-password"},
    )
    assert response.status_code == 204
    assert called == {"username": "analyst", "password": "new-password"}


def test_refresh_and_logout_contracts(client, monkeypatch):
    revoked = []
    monkeypatch.setattr(api, "refresh_token", lambda token: {"access_token": "new-access", "refresh_token": "new-refresh", "token_type": "bearer"})
    monkeypatch.setattr(api, "revoke_refresh_token", lambda token: revoked.append(token))
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": "old-refresh"})
    logged_out = client.post("/api/auth/logout", json={"refresh_token": "new-refresh"})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] == "new-access"
    assert logged_out.status_code == 204
    assert revoked == ["new-refresh"]


def _forbidden():
    from fastapi import HTTPException

    raise HTTPException(status_code=403, detail="需要平台管理员权限")
