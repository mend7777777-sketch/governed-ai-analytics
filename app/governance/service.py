"""Administrative metadata-governance operations with an immutable audit trail."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

from app.core.config import required_env
from app.core.db import db_connection
from app.governance.auth import Principal


TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
SENSITIVITY_LEVELS = {"PUBLIC", "INTERNAL", "SENSITIVE"}


class GovernanceError(ValueError):
    """Raised for invalid governance commands or metadata state."""


def _connection():
    return db_connection()


def _valid_table_name(table_name: str) -> str:
    value = table_name.strip().lower()
    if not TABLE_NAME.fullmatch(value):
        raise GovernanceError("表名只能包含字母、数字和下划线，且必须以字母或下划线开头。")
    return value


class GovernanceService:
    def _audit(self, cursor: Any, principal: Principal, action: str, table_name: str, detail: Dict[str, Any]) -> None:
        cursor.execute(
            "INSERT INTO iam_audit_logs (actor_user_id, action_code, target_type, target_id, detail_json) "
            "VALUES (%s, %s, 'metadata_table', %s, %s)",
            (principal.user_id, action, table_name, json.dumps(detail, ensure_ascii=False)),
        )

    def register(self, principal: Principal, table_name: str, business_name: str, owner_name: str, sensitivity_level: str) -> Dict[str, str]:
        table_name = _valid_table_name(table_name)
        sensitivity_level = sensitivity_level.upper()
        if sensitivity_level not in SENSITIVITY_LEVELS:
            raise GovernanceError("sensitivity_level 必须是 PUBLIC、INTERNAL 或 SENSITIVE。")
        if not business_name.strip() or not owner_name.strip():
            raise GovernanceError("business_name 和 owner_name 不能为空。")
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table_name,))
                if not cur.fetchone():
                    raise GovernanceError("目标表不存在，不能登记发布。")
                cur.execute("SELECT approval_status FROM metadata_tables WHERE table_name=%s", (table_name,))
                if cur.fetchone():
                    raise GovernanceError("该表已登记；请使用提交审批或更新接口。")
                cur.execute(
                    "INSERT INTO metadata_tables (table_name, business_name, owner_name, sensitivity_level, ai_query_enabled, approval_status) "
                    "VALUES (%s, %s, %s, %s, FALSE, 'PENDING')",
                    (table_name, business_name.strip(), owner_name.strip(), sensitivity_level),
                )
                self._audit(cur, principal, "GOVERNANCE_TABLE_REGISTER", table_name, {"status": "PENDING"})
            conn.commit()
        return {"table_name": table_name, "approval_status": "PENDING"}

    def transition(self, principal: Principal, table_name: str, action: str, reason: str = "") -> Dict[str, str]:
        table_name = _valid_table_name(table_name)
        changes = {
            "submit": ("PENDING", False, "GOVERNANCE_TABLE_SUBMIT"),
            "approve": ("APPROVED", True, "GOVERNANCE_TABLE_APPROVE"),
            "reject": ("REJECTED", False, "GOVERNANCE_TABLE_REJECT"),
            "revoke": ("PENDING", False, "GOVERNANCE_TABLE_REVOKE"),
        }
        if action not in changes:
            raise GovernanceError("不支持的治理操作。")
        status, enabled, audit_action = changes[action]
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM metadata_tables WHERE table_name=%s", (table_name,))
                if not cur.fetchone():
                    raise GovernanceError("该表尚未登记。")
                cur.execute(
                    "UPDATE metadata_tables SET approval_status=%s, ai_query_enabled=%s WHERE table_name=%s",
                    (status, enabled, table_name),
                )
                self._audit(cur, principal, audit_action, table_name, {"status": status, "reason": reason.strip()})
            conn.commit()
        return {"table_name": table_name, "approval_status": status, "ai_query_enabled": str(enabled).lower()}
