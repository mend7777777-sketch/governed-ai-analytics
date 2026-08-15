"""User query history and governance audit persistence."""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from app.core.db import db_connection
from app.governance.auth import Principal


def record_query(
    principal: Principal,
    question: str,
    generated_sql: Optional[str],
    status: str,
    row_count: int,
    elapsed_ms: int,
    session_id: Optional[str] = None,
) -> Optional[int]:
    """Persist metadata only; query result rows are deliberately not stored."""
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO query_history (user_id, session_id, question, generated_sql, status, row_count, elapsed_ms) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (principal.user_id, session_id, question, generated_sql, status, row_count, elapsed_ms),
                )
                history_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO query_audit_logs (actor_user_id, actor_role, question_hash, generated_sql, status, elapsed_ms) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        principal.user_id,
                        ",".join(sorted(principal.roles)) or "unknown",
                        hashlib.sha256(question.encode("utf-8")).hexdigest(),
                        generated_sql,
                        status,
                        elapsed_ms,
                    ),
                )
            conn.commit()
        return int(history_id)
    except Exception:
        # Query execution must not fail because audit storage is temporarily unavailable.
        return None


def list_query_history(principal: Principal, limit: int = 50) -> list[dict[str, Any]]:
    limit = min(max(1, int(limit)), 200)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, session_id, question, generated_sql, status, row_count, elapsed_ms, created_at "
                "FROM query_history WHERE user_id=%s ORDER BY id DESC LIMIT %s",
                (principal.user_id, limit),
            )
            rows, columns = cur.fetchall(), [item[0] for item in cur.description]
    return [dict(zip(columns, row)) for row in rows]
