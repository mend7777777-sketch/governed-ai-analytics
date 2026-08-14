"""Persist and train approved business knowledge in the existing Vanna store."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from app.core.config import required_env
from app.core.db import db_connection
from app.governance.auth import Principal


def _connection():
    return db_connection()


class KnowledgeError(ValueError):
    pass


class KnowledgeService:
    def register_and_train(self, vn: Any, principal: Principal, title: str, content: str, document_type: str) -> Dict[str, Any]:
        title = title.strip()
        content = content.strip()
        document_type = document_type.strip().lower()
        if not title or not content:
            raise KnowledgeError("文档标题和内容不能为空。")
        if len(content) > 200000:
            raise KnowledgeError("单个文档不能超过 200000 个字符。")
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO knowledge_documents (title, document_type, content, status, created_by) "
                    "VALUES (%s, %s, %s, 'TRAINING', %s)",
                    (title, document_type, content, principal.user_id),
                )
                document_id = cur.lastrowid
            conn.commit()
        try:
            training_id = vn.train(documentation=content)
            status = "TRAINED"
            error_message = None
        except Exception as exc:
            training_id = None
            status = "FAILED"
            error_message = str(exc)[:1000]
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE knowledge_documents SET status=%s, training_id=%s, error_message=%s WHERE id=%s",
                    (status, str(training_id) if training_id is not None else None, error_message, document_id),
                )
            conn.commit()
        if status == "FAILED":
            raise KnowledgeError("知识训练失败，请检查向量库或模型配置。")
        return {"id": document_id, "title": title, "status": status, "training_id": str(training_id) if training_id is not None else None}

    def list_documents(self) -> list[dict[str, Any]]:
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, title, document_type, status, training_id, created_by, created_at FROM knowledge_documents ORDER BY id DESC")
                rows = cur.fetchall()
                columns = [description[0] for description in cur.description]
        return [dict(zip(columns, row)) for row in rows]
