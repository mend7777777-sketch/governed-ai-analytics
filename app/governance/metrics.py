"""Versioned business metric definitions backed by the governance database."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.db import db_connection
from app.governance.auth import Principal


METRIC_CODE = re.compile(r"^[a-z][a-z0-9_]{1,127}$")


class MetricError(ValueError):
    pass


class MetricService:
    def list(self) -> list[dict[str, Any]]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, metric_code, metric_name, definition, sql_expression, status, version_no, created_by, created_at "
                    "FROM metric_definitions WHERE is_current=TRUE ORDER BY metric_code"
                )
                rows, columns = cur.fetchall(), [item[0] for item in cur.description]
        return [dict(zip(columns, row)) for row in rows]

    def create(
        self,
        vn: Any,
        principal: Principal,
        metric_code: str,
        metric_name: str,
        definition: str,
        sql_expression: str | None,
    ) -> dict[str, Any]:
        metric_code = metric_code.strip().lower()
        metric_name, definition = metric_name.strip(), definition.strip()
        if not METRIC_CODE.fullmatch(metric_code):
            raise MetricError("指标编码只能使用小写字母、数字和下划线。")
        if not metric_name or not definition:
            raise MetricError("指标名称和口径定义不能为空。")
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(version_no),0) FROM metric_definitions WHERE metric_code=%s", (metric_code,))
                version = int(cur.fetchone()[0]) + 1
                cur.execute("UPDATE metric_definitions SET is_current=FALSE WHERE metric_code=%s", (metric_code,))
                cur.execute(
                    "INSERT INTO metric_definitions (metric_code, metric_name, definition, sql_expression, status, version_no, is_current, created_by) "
                    "VALUES (%s,%s,%s,%s,'PUBLISHED',%s,TRUE,%s)",
                    (metric_code, metric_name, definition, sql_expression.strip() if sql_expression else None, version, principal.user_id),
                )
                metric_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO iam_audit_logs (actor_user_id, action_code, target_type, target_id, detail_json) VALUES (%s,'METRIC_PUBLISH','metric_definition',%s,%s)",
                    (principal.user_id, metric_code, json.dumps({"version_no": version}, ensure_ascii=False)),
                )
            conn.commit()
        try:
            training_id = vn.train(documentation=f"指标 {metric_name}（{metric_code}）：{definition}\nSQL表达式：{sql_expression or '未提供'}")
        except Exception as exc:
            raise MetricError("指标已保存，但知识训练失败，请稍后重训。") from exc
        return {"id": metric_id, "metric_code": metric_code, "version_no": version, "training_id": str(training_id)}
