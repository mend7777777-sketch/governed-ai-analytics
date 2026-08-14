"""Database-driven row filters for scoped analytics queries."""

from __future__ import annotations

import json
import os
import re
from typing import Any, List

import pymysql

from app.core.config import required_env
from app.governance.auth import Principal


def _connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", "3306")),
        user=required_env("MYSQL_USER"), password=required_env("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "ai_analytics"), ssl_disabled=True,
    )


def apply_row_filters(sql: str, principal: Principal, referenced_tables: set[str]) -> str:
    if "platform_admin" in principal.roles or not referenced_tables:
        return sql
    roles = tuple(principal.roles)
    placeholders = ",".join(["%s"] * len(roles))
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name, allowed_values_json "
                "FROM access_row_filters WHERE role_name IN (" + placeholders + ") "
                "AND (department_code IS NULL OR department_code=%s) "
                "AND (position_code IS NULL OR position_code=%s) "
                "AND table_name IN (" + ",".join(["%s"] * len(referenced_tables)) + ")",
                roles + (principal.department_code, principal.position_code) + tuple(referenced_tables),
            )
            filters = cur.fetchall()
    if not filters:
        return sql
    wrapped = sql
    for table_name, column_name, values_json in filters:
        values = json.loads(values_json)
        if not isinstance(values, list) or not values:
            raise PermissionError("行级策略没有配置有效的允许值。")
        if not re.search(r"(?<![A-Za-z0-9_])`?" + re.escape(column_name) + r"`?(?![A-Za-z0-9_])", wrapped, re.IGNORECASE):
            raise PermissionError("查询未返回行级策略字段，无法安全应用数据范围限制。")
        literals: List[str] = []
        for value in values:
            if isinstance(value, bool) or isinstance(value, (int, float)):
                literals.append(str(value))
            elif isinstance(value, str) and len(value) <= 128:
                literals.append("'" + value.replace("'", "''") + "'")
            else:
                raise PermissionError("行级策略值格式不受支持。")
        wrapped = "SELECT * FROM (" + wrapped + ") AS _secured WHERE _secured.`" + column_name + "` IN (" + ",".join(literals) + ")"
    return wrapped
