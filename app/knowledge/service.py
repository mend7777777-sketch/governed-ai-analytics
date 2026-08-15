"""Persist and train approved business knowledge in the existing Vanna store."""

from __future__ import annotations

import json
import os
import re
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
        document_key = f"{document_type}:{title}"[:320]
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(MAX(version_no), 0) FROM knowledge_documents WHERE document_key=%s",
                    (document_key,),
                )
                version_no = int(cur.fetchone()[0]) + 1
                cur.execute("UPDATE knowledge_documents SET is_current=FALSE WHERE document_key=%s", (document_key,))
                cur.execute(
                    "INSERT INTO knowledge_documents "
                    "(title, document_type, content, document_key, version_no, is_current, status, created_by) "
                    "VALUES (%s, %s, %s, %s, %s, TRUE, 'TRAINING', %s)",
                    (title, document_type, content, document_key, version_no, principal.user_id),
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
                    "UPDATE knowledge_documents SET status=%s, training_id=%s, error_message=%s, trained_at=IF(%s='TRAINED', NOW(), trained_at) WHERE id=%s",
                    (status, str(training_id) if training_id is not None else None, error_message, status, document_id),
                )
            conn.commit()
        if status == "FAILED":
            raise KnowledgeError("知识训练失败，请检查向量库或模型配置。")
        return {"id": document_id, "title": title, "status": status, "version_no": version_no, "training_id": str(training_id) if training_id is not None else None}

    def list_documents(self) -> list[dict[str, Any]]:
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, document_type, version_no, is_current, status, training_id, "
                    "created_by, created_at, trained_at FROM knowledge_documents "
                    "WHERE deleted_at IS NULL ORDER BY id DESC"
                )
                rows = cur.fetchall()
                columns = [description[0] for description in cur.description]
        return [dict(zip(columns, row)) for row in rows]

    def retrain(self, vn: Any, document_id: int) -> Dict[str, Any]:
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, content FROM knowledge_documents WHERE id=%s AND deleted_at IS NULL",
                    (document_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise KnowledgeError("知识文档不存在或已删除。")
                cur.execute("UPDATE knowledge_documents SET status='TRAINING', error_message=NULL WHERE id=%s", (document_id,))
            conn.commit()
        try:
            training_id = vn.train(documentation=row[2])
            status, error_message = "TRAINED", None
        except Exception as exc:
            training_id, status, error_message = None, "FAILED", str(exc)[:1000]
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE knowledge_documents SET status=%s, training_id=%s, error_message=%s, trained_at=IF(%s='TRAINED', NOW(), trained_at) WHERE id=%s",
                    (status, str(training_id) if training_id is not None else None, error_message, status, document_id),
                )
            conn.commit()
        if status == "FAILED":
            raise KnowledgeError("知识重训失败，请检查向量库或模型配置。")
        return {"id": document_id, "title": row[1], "status": status, "training_id": str(training_id) if training_id is not None else None}

    def delete(self, principal: Principal, document_id: int) -> None:
        with _connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE knowledge_documents SET deleted_at=NOW(), is_current=FALSE WHERE id=%s AND deleted_at IS NULL",
                    (document_id,),
                )
                if not cur.rowcount:
                    raise KnowledgeError("知识文档不存在或已删除。")
                cur.execute(
                    "INSERT INTO iam_audit_logs (actor_user_id, action_code, target_type, target_id, detail_json) VALUES (%s,'KNOWLEDGE_DELETE','knowledge_document',%s,%s)",
                    (principal.user_id, str(document_id), json.dumps({"document_id": document_id}, ensure_ascii=False)),
                )
            conn.commit()
