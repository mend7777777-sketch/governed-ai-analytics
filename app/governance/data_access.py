"""Runtime table and column access checks for generated read-only SQL."""

from __future__ import annotations

import os
import re
from typing import Iterable, Set

import pymysql

from app.core.config import required_env
from app.governance.auth import Principal


def _connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", "3306")),
        user=required_env("MYSQL_USER"), password=required_env("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "ai_analytics"), ssl_disabled=True,
    )


def allowed_tables(principal: Principal, published_tables: Set[str]) -> Set[str]:
    """Administrators retain full access; every other role needs an explicit policy row."""
    if "platform_admin" in principal.roles:
        return published_tables
    if not principal.roles:
        return set()
    placeholders = ",".join(["%s"] * len(principal.roles))
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT table_name FROM access_policies "
                "WHERE allow_detail_query=TRUE AND role_name IN (" + placeholders + ")",
                tuple(principal.roles),
            )
            generic = {str(row[0]).lower() for row in cur.fetchall()}
            cur.execute(
                "SELECT DISTINCT table_name FROM access_policy_scopes "
                "WHERE allow_detail_query=TRUE AND role_name IN (" + placeholders + ") "
                "AND (department_code IS NULL OR department_code=%s) "
                "AND (position_code IS NULL OR position_code=%s)",
                tuple(principal.roles) + (principal.department_code, principal.position_code),
            )
            scoped = {str(row[0]).lower() for row in cur.fetchall()}
            return (generic | scoped) & published_tables


def blocked_columns(referenced_tables: Iterable[str]) -> Set[str]:
    tables = list(referenced_tables)
    if not tables:
        return set()
    placeholders = ",".join(["%s"] * len(tables))
    with _connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT column_name FROM metadata_columns "
                "WHERE ai_query_enabled=FALSE AND table_name IN (" + placeholders + ")",
                tuple(tables),
            )
            return {str(row[0]).lower() for row in cur.fetchall()}


def validate_column_access(sql: str, referenced_tables: Iterable[str]) -> None:
    """Reject explicit disabled columns and wildcards that could expose them."""
    disabled = blocked_columns(referenced_tables)
    if not disabled:
        return
    if re.search(r"(?:\b\w+\.)?\*", sql):
        raise PermissionError("该查询涉及受限字段，不允许使用 SELECT *。")
    for column in disabled:
        if re.search(r"(?<![A-Za-z0-9_])`?" + re.escape(column) + r"`?(?![A-Za-z0-9_])", sql, re.IGNORECASE):
            raise PermissionError("SQL 引用了无权访问的敏感字段：" + column)
