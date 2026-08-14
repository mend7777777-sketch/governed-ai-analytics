"""Reusable, read-only Text2SQL service for the AI analytics demo."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.integrations.vanna_client import AnalyticsVanna, connect_mysql
from app.governance.auth import Principal
from app.governance.data_access import allowed_tables, validate_column_access
from app.governance.row_filter import apply_row_filters


MAX_RESULT_ROWS = 200
logger = logging.getLogger("ai_analytics.audit")
FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE|"
    r"CALL|EXEC|SET|USE|INTO\s+OUTFILE|LOAD\s+DATA)\b",
    re.IGNORECASE,
)

EXAMPLE_QUESTIONS = [
    "2025年12月哪个品类退款率最高？",
    "2025年3月有多少个黑卡用户下单？",
    "2025年每月GMV环比增长率",
    "2025年连续3个月下单的用户数",
    "2025年11月华东各省GMV是多少？",
]


class QueryValidationError(ValueError):
    """Raised when generated SQL is not safe for this read-only demo."""


def validate_read_only_sql(sql: str, allowed_tables: set[str]) -> str:
    """Allow one SELECT/CTE statement only; reject write and admin SQL."""
    normalized = sql.strip()
    if not normalized:
        raise QueryValidationError("模型没有返回 SQL，请换一种问法。")

    # A trailing semicolon is harmless, but multiple statements are not allowed.
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    if len(statements) != 1:
        raise QueryValidationError("一次只能执行一条只读 SQL。")
    normalized = statements[0]

    if "--" in normalized or "/*" in normalized:
        raise QueryValidationError("SQL 不允许包含注释。")
    if not normalized.upper().startswith(("SELECT", "WITH")):
        raise QueryValidationError("仅允许执行 SELECT 或 WITH 开头的只读 SQL。")
    if FORBIDDEN_SQL.search(normalized):
        raise QueryValidationError("生成的 SQL 包含不允许的写入或管理操作。")
    referenced_tables = set(re.findall(r"\b(?:FROM|JOIN)\s+`?([a-zA-Z_][\w]*)`?", normalized, re.IGNORECASE))
    unknown_tables = {table.lower() for table in referenced_tables} - allowed_tables
    if unknown_tables:
        raise QueryValidationError(f"SQL 引用了未授权表：{', '.join(sorted(unknown_tables))}。")
    return normalized


def suggest_chart(columns: list[str], rows: list[dict[str, Any]]) -> str:
    if len(rows) == 1 and len(columns) == 1:
        return "metric"
    lowered = {column.lower() for column in columns}
    if {"year_num", "month_num"}.issubset(lowered) or "full_date" in lowered:
        return "line"
    if len(columns) >= 2 and rows:
        return "bar"
    return "table"


class AnalyticsQueryService:
    """Owns the Vanna instance used by a single API process."""

    def __init__(self) -> None:
        self.vn = AnalyticsVanna()
        connect_mysql(self.vn)

    def health_check(self) -> None:
        self.vn.run_sql("SELECT 1 AS ok")

    def published_tables(self) -> set[str]:
        dataframe = self.vn.run_sql(
            "SELECT table_name FROM metadata_tables "
            "WHERE ai_query_enabled = TRUE AND approval_status = 'APPROVED'"
        )
        return {str(value).lower() for value in dataframe["table_name"].tolist()}

    def governance_tables(self) -> list[dict[str, Any]]:
        dataframe = self.vn.run_sql(
            "SELECT table_name, business_name, owner_name, sensitivity_level, "
            "ai_query_enabled, approval_status, updated_at "
            "FROM metadata_tables ORDER BY table_name"
        )
        return json.loads(dataframe.to_json(orient="records", force_ascii=False, date_format="iso"))

    def query(self, question: str, principal: Principal) -> dict[str, Any]:
        started_at = time.perf_counter()
        try:
            published_tables = self.published_tables()
            permitted_tables = allowed_tables(principal, published_tables)
            if not permitted_tables:
                raise QueryValidationError("当前没有已发布的 AI 可查询表。")
            sql = validate_read_only_sql(self.vn.generate_sql(question=question), permitted_tables)
            referenced_tables = set(re.findall(r"\b(?:FROM|JOIN)\s+`?([a-zA-Z_][\w]*)`?", sql, re.IGNORECASE))
            try:
                validate_column_access(sql, {table.lower() for table in referenced_tables})
            except PermissionError as exc:
                raise QueryValidationError(str(exc)) from exc
            try:
                sql = apply_row_filters(sql, principal, {table.lower() for table in referenced_tables})
            except PermissionError as exc:
                raise QueryValidationError(str(exc)) from exc
            dataframe = self.vn.run_sql(sql)
            truncated = len(dataframe) > MAX_RESULT_ROWS
            dataframe = dataframe.head(MAX_RESULT_ROWS)
            columns = [str(column) for column in dataframe.columns]
            rows = json.loads(dataframe.to_json(orient="records", force_ascii=False, date_format="iso"))
            response = {
            "question": question,
            "sql": sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "chart_type": suggest_chart(columns, rows),
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            "data_shared_with_llm": False,
            }
            logger.info("query_success elapsed_ms=%s rows=%s sql=%r", response["elapsed_ms"], response["row_count"], sql)
            return response
        except Exception:
            logger.exception("query_failed question=%r", question)
            raise
