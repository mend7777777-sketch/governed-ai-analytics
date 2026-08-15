"""Local authentication, JWT issuance, account lockout, and refresh sessions."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from dotenv import load_dotenv

from app.core.config import PROJECT_ROOT, required_env
from app.core.db import db_connection


load_dotenv(PROJECT_ROOT / ".env")
password_hasher = PasswordHasher()
MAX_LOGIN_FAILURES = 5
LOCKOUT_MINUTES = 15
ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 7
RATE_LIMIT_ATTEMPTS = 10
RATE_LIMIT_WINDOW_MINUTES = 1
RATE_LIMIT_BLOCK_MINUTES = 5


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    roles: frozenset[str]
    permissions: frozenset[str] = frozenset()
    department_code: Optional[str] = None
    position_code: Optional[str] = None
    token_version: int = 0

    def require(self, permission: str) -> None:
        if permission not in self.permissions and "platform_admin" not in self.roles:
            raise PermissionError("insufficient role")


def _connection():
    return db_connection()


def _principal_for_user(cur, user_id: int) -> Optional[Principal]:
    cur.execute(
        "SELECT u.id, u.username, d.department_code, p.position_code, u.token_version FROM iam_users u "
        "LEFT JOIN iam_departments d ON d.id=u.department_id "
        "LEFT JOIN iam_positions p ON p.id=u.position_id WHERE u.id=%s AND u.status='ACTIVE'",
        (user_id,),
    )
    user = cur.fetchone()
    if not user:
        return None
    cur.execute("SELECT r.role_code FROM iam_user_roles ur JOIN iam_roles r ON r.id=ur.role_id WHERE ur.user_id=%s", (user_id,))
    roles = frozenset(row[0] for row in cur.fetchall())
    cur.execute("SELECT DISTINCT rp.permission_code FROM iam_user_roles ur JOIN iam_role_permissions rp ON rp.role_id=ur.role_id WHERE ur.user_id=%s", (user_id,))
    permissions = frozenset(row[0] for row in cur.fetchall())
    return Principal(user[0], user[1], roles, permissions, user[2], user[3], int(user[4] or 0))


def _audit(cur, action: str, username: str, detail: str) -> None:
    cur.execute(
        "INSERT INTO iam_audit_logs (actor_user_id, action_code, target_type, target_id, detail_json) VALUES (NULL,%s,'iam_user',%s,%s)",
        (action, username, json.dumps({"detail": detail}, ensure_ascii=False)),
    )


def _rate_key(kind: str, value: str) -> str:
    return f"{kind}:{value.strip().lower()[:180]}"


def _rate_limited(cur, key: str) -> bool:
    cur.execute(
        "SELECT attempt_count, window_started_at, blocked_until FROM auth_rate_limits "
        "WHERE rate_key=%s FOR UPDATE",
        (key,),
    )
    row = cur.fetchone()
    if not row:
        return False
    if row[2] is not None and row[2].replace(tzinfo=None) > datetime.utcnow():
        return True
    if row[1].replace(tzinfo=None) < datetime.utcnow() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES):
        cur.execute(
            "UPDATE auth_rate_limits SET attempt_count=0, window_started_at=NOW(), blocked_until=NULL WHERE rate_key=%s",
            (key,),
        )
    return False


def _record_rate_failure(cur, key: str) -> None:
    cur.execute(
        "SELECT attempt_count, window_started_at FROM auth_rate_limits WHERE rate_key=%s FOR UPDATE",
        (key,),
    )
    row = cur.fetchone()
    now = datetime.utcnow()
    if not row or row[1].replace(tzinfo=None) < now - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES):
        cur.execute(
            "INSERT INTO auth_rate_limits (rate_key, attempt_count, window_started_at, blocked_until) "
            "VALUES (%s,1,NOW(),NULL) ON DUPLICATE KEY UPDATE attempt_count=1, window_started_at=NOW(), blocked_until=NULL",
            (key,),
        )
        return
    attempts = int(row[0]) + 1
    blocked_until = RATE_LIMIT_BLOCK_MINUTES if attempts >= RATE_LIMIT_ATTEMPTS else None
    cur.execute(
        "UPDATE auth_rate_limits SET attempt_count=%s, blocked_until="
        + ("DATE_ADD(NOW(), INTERVAL %s MINUTE)" if blocked_until else "NULL")
        + " WHERE rate_key=%s",
        (attempts, blocked_until, key) if blocked_until else (attempts, key),
    )


def authenticate(username: str, password: str, client_ip: str = "unknown") -> Optional[Principal]:
    with _connection() as conn:
        with conn.cursor() as cur:
            rate_keys = (_rate_key("ip", client_ip), _rate_key("user", username))
            if any(_rate_limited(cur, key) for key in rate_keys):
                _audit(cur, "AUTH_LOGIN_REJECTED", username, "rate_limited")
                conn.commit()
                return None
            cur.execute("SELECT id, password_hash, locked_until FROM iam_users WHERE username=%s AND status='ACTIVE'", (username,))
            user = cur.fetchone()
            if not user:
                for key in rate_keys:
                    _record_rate_failure(cur, key)
                _audit(cur, "AUTH_LOGIN_FAILED", username, "unknown_user")
                conn.commit()
                return None
            if user[2] is not None and user[2].replace(tzinfo=None) > datetime.utcnow():
                _audit(cur, "AUTH_LOGIN_REJECTED", username, "account_locked")
                conn.commit()
                return None
            try:
                password_hasher.verify(user[1], password)
            except Exception:
                for key in rate_keys:
                    _record_rate_failure(cur, key)
                cur.execute(
                    "UPDATE iam_users SET failed_login_attempts=failed_login_attempts+1, "
                    "locked_until=CASE WHEN failed_login_attempts+1 >= %s THEN DATE_ADD(NOW(), INTERVAL %s MINUTE) ELSE NULL END "
                    "WHERE id=%s",
                    (MAX_LOGIN_FAILURES, LOCKOUT_MINUTES, user[0]),
                )
                _audit(cur, "AUTH_LOGIN_FAILED", username, "invalid_password")
                conn.commit()
                return None
            cur.execute("UPDATE iam_users SET failed_login_attempts=0, locked_until=NULL, last_login_at=NOW() WHERE id=%s", (user[0],))
            _audit(cur, "AUTH_LOGIN_SUCCESS", username, "password")
            principal = _principal_for_user(cur, user[0])
            conn.commit()
            return principal


def _issue(principal: Principal, token_type: str, expires_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(principal.user_id), "username": principal.username, "roles": list(principal.roles),
         "permissions": list(principal.permissions), "department_code": principal.department_code,
         "position_code": principal.position_code, "typ": token_type, "jti": str(uuid.uuid4()),
         "iat": now, "exp": expires_at, "ver": principal.token_version},
        required_env("JWT_SECRET"), algorithm="HS256",
    )


def issue_token(principal: Principal) -> str:
    return _issue(principal, "access", datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token_pair(principal: Principal) -> dict[str, str]:
    access_token = issue_token(principal)
    refresh_token = _issue(principal, "refresh", datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS))
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO auth_refresh_tokens (token_hash, user_id, expires_at) VALUES (%s,%s,DATE_ADD(NOW(), INTERVAL %s DAY))",
                (_token_hash(refresh_token), principal.user_id, REFRESH_TOKEN_DAYS),
            )
        conn.commit()
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


def _load_active_principal(user_id: int) -> Optional[Principal]:
    with _connection() as conn:
        with conn.cursor() as cur:
            return _principal_for_user(cur, user_id)


def decode_token(token: str, *, validate_state: bool = True) -> Principal:
    payload = jwt.decode(token, required_env("JWT_SECRET"), algorithms=["HS256"])
    if payload.get("typ", "access") != "access":
        raise jwt.InvalidTokenError("not an access token")
    principal = Principal(
        int(payload["sub"]), payload["username"], frozenset(payload.get("roles", [])),
        frozenset(payload.get("permissions", [])), payload.get("department_code"),
        payload.get("position_code"), int(payload.get("ver", 0)),
    )
    if not validate_state:
        return principal
    current = _load_active_principal(principal.user_id)
    if current is None or current.token_version != principal.token_version:
        raise jwt.InvalidTokenError("user session is no longer valid")
    return current


def refresh_token(token: str) -> dict[str, str]:
    payload = jwt.decode(token, required_env("JWT_SECRET"), algorithms=["HS256"])
    if payload.get("typ") != "refresh":
        raise jwt.InvalidTokenError("not a refresh token")
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM auth_refresh_tokens WHERE token_hash=%s AND revoked_at IS NULL AND expires_at > NOW()", (_token_hash(token),))
            row = cur.fetchone()
            if not row or int(payload["sub"]) != row[0]:
                raise jwt.InvalidTokenError("refresh token revoked")
            cur.execute("UPDATE auth_refresh_tokens SET revoked_at=NOW() WHERE token_hash=%s", (_token_hash(token),))
            principal = _principal_for_user(cur, row[0])
            if principal is None:
                raise jwt.InvalidTokenError("user unavailable")
            conn.commit()
    return issue_token_pair(principal)


def revoke_refresh_token(token: str) -> None:
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE auth_refresh_tokens SET revoked_at=NOW() WHERE token_hash=%s AND revoked_at IS NULL", (_token_hash(token),))
        conn.commit()


def revoke_user_sessions(cur, user_id: int) -> None:
    cur.execute("UPDATE iam_users SET token_version=token_version+1 WHERE id=%s", (user_id,))
    cur.execute("UPDATE auth_refresh_tokens SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL", (user_id,))


def change_password(principal: Principal, current_password: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise ValueError("新密码至少需要 8 位。")
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM iam_users WHERE id=%s AND status='ACTIVE' FOR UPDATE", (principal.user_id,))
            row = cur.fetchone()
            try:
                password_matches = bool(row and password_hasher.verify(row[0], current_password))
            except Exception:
                password_matches = False
            if not password_matches:
                raise ValueError("当前密码错误。")
            cur.execute(
                "UPDATE iam_users SET password_hash=%s, password_changed_at=NOW() WHERE id=%s",
                (password_hasher.hash(new_password), principal.user_id),
            )
            revoke_user_sessions(cur, principal.user_id)
            _audit(cur, "AUTH_PASSWORD_CHANGE", principal.username, "self")
        conn.commit()


def reset_password(actor: Principal, username: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise ValueError("新密码至少需要 8 位。")
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM iam_users WHERE username=%s FOR UPDATE", (username,))
            row = cur.fetchone()
            if not row:
                raise ValueError("用户不存在。")
            cur.execute(
                "UPDATE iam_users SET password_hash=%s, password_changed_at=NOW(), status='ACTIVE', "
                "failed_login_attempts=0, locked_until=NULL WHERE id=%s",
                (password_hasher.hash(new_password), row[0]),
            )
            revoke_user_sessions(cur, row[0])
            _audit(cur, "IAM_PASSWORD_RESET", actor.username, username)
        conn.commit()
