"""Reusable, read-only Text2SQL service for the AI analytics demo."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

try:
    from sqlglot import exp, parse, parse_one
    from sqlglot.errors import ParseError
except ImportError:  # pragma: no cover - compatibility for an un-updated local environment
    exp = None
    parse = parse_one = None
    ParseError = Exception

from app.integrations.vanna_client import AnalyticsVanna, connect_mysql
from app.governance.auth import Principal
from app.governance.data_access import allowed_tables, validate_column_access
from app.governance.row_filter import apply_row_filters
from app.services.history import record_query


MAX_RESULT_ROWS = 200
logger = logging.getLogger("ai_analytics.audit")
FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE|"
    r"CALL|EXEC|SET|USE|INTO\s+(?:OUTFILE|DUMPFILE)|LOAD\s+DATA|"
    r"FOR\s+UPDATE|LOCK\s+IN\s+SHARE\s+MODE|LOAD_FILE|GET_LOCK|RELEASE_LOCK|"
    r"SLEEP|BENCHMARK)\b",
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

    # A trailing semicolon is harmless, but multiple statements are not allowed
    # even when the optional AST dependency is not installed yet.
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    if len(statements) != 1:
        raise QueryValidationError("一次只能执行一条只读 SQL。")
    normalized = statements[0]
    if "--" in normalized or "/*" in normalized:
        raise QueryValidationError("SQL 不允许包含注释。")
    if FORBIDDEN_SQL.search(normalized):
        raise QueryValidationError("生成的 SQL 包含不允许的写入或管理操作。")
    if parse is not None:
        try:
            statements = [statement for statement in parse(normalized, read="mysql") if statement is not None]
        except ParseError as exc:
            raise QueryValidationError("生成的 SQL 无法解析，请换一种问法。") from exc
        if len(statements) != 1:
            raise QueryValidationError("一次只能执行一条只读 SQL。")
        root = statements[0]
        if root.__class__.__name__ not in {"Select", "Union", "Except", "Intersect"}:
            raise QueryValidationError("仅允许执行 SELECT 或 WITH 开头的只读 SQL。")
    elif not normalized.upper().startswith(("SELECT", "WITH")):
        raise QueryValidationError("仅允许执行 SELECT 或 WITH 开头的只读 SQL。")

    referenced_tables = extract_sql_references(normalized)
    unknown_tables = {table.lower() for table in referenced_tables} - {table.lower() for table in allowed_tables}
    if unknown_tables:
        raise QueryValidationError(f"SQL 引用了未授权表：{', '.join(sorted(unknown_tables))}。")
    return normalized


def extract_sql_references(sql: str) -> set[str]:
    """Return physical table references, excluding CTE aliases."""
    if parse_one is None:
        return {
            table.lower()
            for table in re.findall(r"\b(?:FROM|JOIN)\s+`?([a-zA-Z_][\w]*)`?", sql, re.IGNORECASE)
        }
    try:
        expression = parse_one(sql, read="mysql")
    except ParseError as exc:
        raise QueryValidationError("生成的 SQL 无法解析，请换一种问法。") from exc
    cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
    database_name = os.getenv("MYSQL_DATABASE", "ai_analytics").lower()
    references: set[str] = set()
    for table in expression.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            continue
        if table.db and table.db.lower() != database_name:
            raise QueryValidationError("SQL 不允许访问当前数据仓库之外的数据库。")
        references.add(name)
    return references


def bound_read_only_sql(sql: str, max_rows: int) -> str:
    """Add a server-side safety limit, preserving an explicit smaller LIMIT."""
    limit = max_rows + 1
    if parse_one is not None:
        expression = parse_one(sql, read="mysql")
        existing = expression.args.get("limit")
        if existing is None:
            expression = expression.limit(limit)
        elif existing.expression is not None and existing.expression.is_number:
            existing_value = int(existing.expression.this)
            if existing_value > limit:
                existing.set("expression", exp.Literal.number(limit))
        return expression.sql(dialect="mysql")
    if re.search(r"\bLIMIT\s+\d+", sql, re.IGNORECASE):
        return sql
    return sql.rstrip(";") + f" LIMIT {limit}"


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

    def query(self, question: str, principal: Principal, session_id: str | None = None, context: list[str] | None = None) -> dict[str, Any]:
        started_at = time.perf_counter()
        sql = None
        try:
            published_tables = self.published_tables()
            permitted_tables = allowed_tables(principal, published_tables)
            if not permitted_tables:
                raise QueryValidationError("当前没有已发布的 AI 可查询表。")
            context = [item.strip() for item in (context or []) if item and item.strip()][-3:]
            model_question = question if not context else (
                "参考此前对话问题：\n" + "\n".join(f"- {item}" for item in context) + "\n当前问题：\n" + question
            )
            sql = validate_read_only_sql(self.vn.generate_sql(question=model_question), permitted_tables)
            referenced_tables = extract_sql_references(sql)
            try:
                validate_column_access(sql, {table.lower() for table in referenced_tables})
            except PermissionError as exc:
                raise QueryValidationError(str(exc)) from exc
            try:
                sql = apply_row_filters(sql, principal, {table.lower() for table in referenced_tables})
            except PermissionError as exc:
                raise QueryValidationError(str(exc)) from exc
            sql = bound_read_only_sql(sql, MAX_RESULT_ROWS)
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
            response["query_id"] = record_query(
                principal, question, sql, "SUCCESS", response["row_count"], response["elapsed_ms"], session_id
            )
            logger.info("query_success elapsed_ms=%s rows=%s sql=%r", response["elapsed_ms"], response["row_count"], sql)
            return response
        except Exception:
            record_query(
                principal, question, sql, "FAILED", 0,
                round((time.perf_counter() - started_at) * 1000), session_id
            )
            logger.exception("query_failed question=%r", question)
            raise
