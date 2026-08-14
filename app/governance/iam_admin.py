"""Administrative CRUD operations for local IAM master data."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from app.core.config import required_env
from app.core.db import db_connection
from app.governance.auth import Principal
from app.governance.iam import hash_password


def _connection():
    return db_connection()


class IAMAdminError(ValueError):
    pass


class IAMAdminService:
    def _audit(self, cur: Any, actor: Principal, action: str, target_type: str, target_id: str, detail: Dict[str, Any]) -> None:
        cur.execute(
            "INSERT INTO iam_audit_logs (actor_user_id, action_code, target_type, target_id, detail_json) VALUES (%s,%s,%s,%s,%s)",
            (actor.user_id, action, target_type, target_id, json.dumps(detail, ensure_ascii=False)),
        )

    def list_departments(self) -> List[Dict[str, Any]]:
        return self._list("SELECT department_code, department_name, status FROM iam_departments ORDER BY department_code")

    def list_positions(self) -> List[Dict[str, Any]]:
        return self._list("SELECT position_code, position_name FROM iam_positions ORDER BY position_code")

    def list_roles(self) -> List[Dict[str, Any]]:
        return self._list("SELECT role_code, role_name FROM iam_roles ORDER BY role_code")

    def list_users(self) -> List[Dict[str, Any]]:
        return self._list(
            "SELECT u.username, u.display_name, u.status, d.department_code, p.position_code, "
            "GROUP_CONCAT(r.role_code ORDER BY r.role_code SEPARATOR ',') AS roles "
            "FROM iam_users u LEFT JOIN iam_departments d ON d.id=u.department_id "
            "LEFT JOIN iam_positions p ON p.id=u.position_id "
            "LEFT JOIN iam_user_roles ur ON ur.user_id=u.id LEFT JOIN iam_roles r ON r.id=ur.role_id "
            "GROUP BY u.id, u.username, u.display_name, u.status, d.department_code, p.position_code ORDER BY u.username"
        )

    def _list(self, sql: str) -> List[Dict[str, Any]]:
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                columns = [item[0] for item in cur.description]
        return [dict(zip(columns, row)) for row in rows]

    def create_department(self, actor: Principal, code: str, name: str) -> Dict[str, str]:
        return self._create_reference(actor, "iam_departments", "department_code", "department_name", code, name, "IAM_DEPARTMENT_CREATE")

    def create_position(self, actor: Principal, code: str, name: str) -> Dict[str, str]:
        return self._create_reference(actor, "iam_positions", "position_code", "position_name", code, name, "IAM_POSITION_CREATE")

    def _create_reference(self, actor: Principal, table: str, code_col: str, name_col: str, code: str, name: str, action: str) -> Dict[str, str]:
        code, name = code.strip().lower(), name.strip()
        if not code or not name:
            raise IAMAdminError("编码和名称不能为空。")
        with _connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute("INSERT INTO " + table + " (" + code_col + ", " + name_col + ") VALUES (%s,%s)", (code, name))
                except pymysql.err.IntegrityError as exc:
                    raise IAMAdminError("该编码已存在。") from exc
                self._audit(cur, actor, action, table, code, {"name": name})
            conn.commit()
        return {"code": code, "name": name}

    def create_user(self, actor: Principal, username: str, display_name: str, password: str, department_code: Optional[str], position_code: Optional[str], roles: List[str]) -> Dict[str, Any]:
        username, display_name = username.strip(), display_name.strip()
        role_codes = sorted({item.strip() for item in roles if item.strip()})
        if not username or not display_name or len(password) < 8 or not role_codes:
            raise IAMAdminError("用户名、显示名称、至少 8 位密码和至少一个角色不能为空。")
        with _connection() as conn:
            with conn.cursor() as cur:
                department_id = self._reference_id(cur, "iam_departments", "department_code", department_code)
                position_id = self._reference_id(cur, "iam_positions", "position_code", position_code)
                role_ids = self._role_ids(cur, role_codes)
                if len(role_ids) != len(role_codes):
                    raise IAMAdminError("包含不存在的角色。")
                try:
                    cur.execute("INSERT INTO iam_users (username, display_name, password_hash, department_id, position_id) VALUES (%s,%s,%s,%s,%s)", (username, display_name, hash_password(password), department_id, position_id))
                except pymysql.err.IntegrityError as exc:
                    raise IAMAdminError("用户名已存在。") from exc
                user_id = cur.lastrowid
                cur.executemany("INSERT INTO iam_user_roles (user_id, role_id) VALUES (%s,%s)", [(user_id, role_id) for role_id in role_ids])
                self._audit(cur, actor, "IAM_USER_CREATE", "iam_user", username, {"roles": role_codes})
            conn.commit()
        return {"username": username, "roles": role_codes, "status": "ACTIVE"}

    def set_user_status(self, actor: Principal, username: str, status: str) -> Dict[str, str]:
        status = status.upper()
        if status not in {"ACTIVE", "LOCKED", "DISABLED"}:
            raise IAMAdminError("状态必须是 ACTIVE、LOCKED 或 DISABLED。")
        with _connection() as conn:
            with conn.cursor() as cur:
                if status == "ACTIVE":
                    cur.execute(
                        "UPDATE iam_users SET status=%s, failed_login_attempts=0, locked_until=NULL WHERE username=%s",
                        (status, username),
                    )
                else:
                    cur.execute("UPDATE iam_users SET status=%s WHERE username=%s", (status, username))
                if not cur.rowcount:
                    raise IAMAdminError("用户不存在。")
                self._audit(cur, actor, "IAM_USER_STATUS_CHANGE", "iam_user", username, {"status": status})
            conn.commit()
        return {"username": username, "status": status}

    @staticmethod
    def _reference_id(cur: Any, table: str, column: str, code: Optional[str]) -> Optional[int]:
        if not code:
            return None
        cur.execute("SELECT id FROM " + table + " WHERE " + column + "=%s", (code,))
        row = cur.fetchone()
        if not row:
            raise IAMAdminError("关联的部门或岗位不存在。")
        return row[0]

    @staticmethod
    def _role_ids(cur: Any, role_codes: List[str]) -> List[int]:
        cur.execute("SELECT id FROM iam_roles WHERE role_code IN (" + ",".join(["%s"] * len(role_codes)) + ")", tuple(role_codes))
        return [row[0] for row in cur.fetchall()]
