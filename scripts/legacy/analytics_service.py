"""Compatibility import. Application code lives in app.services.text2sql."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from vanna_mysql_demo import AnalyticsVanna, connect_mysql


MAX_RESULT_ROWS = 200
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


def validate_read_only_sql(sql: str) -> str:
    """Allow one SELECT/CTE statement only; reject write and admin SQL."""
    normalized = sql.strip()
    if not normalized:
        raise QueryValidationError("模型没有返回 SQL，请换一种问法。")

    # A trailing semicolon is harmless, but multiple statements are not allowed.
    statements = [part.strip() for part in normalized.split(";") if part.strip()]
    if len(statements) != 1:
        raise QueryValidationError("一次只能执行一条只读 SQL。")
    normalized = statements[0]

    if not normalized.upper().startswith(("SELECT", "WITH")):
        raise QueryValidationError("仅允许执行 SELECT 或 WITH 开头的只读 SQL。")
    if FORBIDDEN_SQL.search(normalized):
        raise QueryValidationError("生成的 SQL 包含不允许的写入或管理操作。")
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

    def query(self, question: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        sql = validate_read_only_sql(self.vn.generate_sql(question=question))
        dataframe = self.vn.run_sql(sql)
        truncated = len(dataframe) > MAX_RESULT_ROWS
        dataframe = dataframe.head(MAX_RESULT_ROWS)
        columns = [str(column) for column in dataframe.columns]
        rows = json.loads(dataframe.to_json(orient="records", force_ascii=False, date_format="iso"))
        return {
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
