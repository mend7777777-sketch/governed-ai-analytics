"""Vanna and MySQL adapter used by the application service layer."""

from __future__ import annotations

import os

import pandas as pd
from openai import OpenAI
import pymysql.cursors
from vanna.legacy.chromadb import ChromaDB_VectorStore
from vanna.legacy.openai import OpenAI_Chat

from app.core.config import chroma_path, required_env
from app.core.db import pool, query_timeout_ms


class AnalyticsVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self) -> None:
        config = {
            "api_key": required_env("OPENAI_API_KEY"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "path": str(chroma_path()),
        }
        ChromaDB_VectorStore.__init__(self, config=config)
        base_url = os.getenv("OPENAI_BASE_URL")
        client = OpenAI(api_key=config["api_key"], base_url=base_url) if base_url else OpenAI(api_key=config["api_key"])
        OpenAI_Chat.__init__(self, client=client, config=config)

    def submit_prompt(self, prompt, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=kwargs.get("model") or self.config["model"],
            messages=prompt,
            stop=None,
            temperature=self.temperature,
        )
        if isinstance(response, str):
            return response
        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError(f"Unexpected model response type: {type(response).__name__}")
        return choices[0].message.content or ""


def connect_mysql(vn: AnalyticsVanna) -> None:
    """Attach Vanna's read path to the shared bounded pool."""

    def run_sql_mysql(sql: str) -> pd.DataFrame:
        with pool.connection() as connection:
            cursor = connection.cursor(pymysql.cursors.DictCursor)
            try:
                # MySQL enforces this limit server-side for SELECT statements.
                cursor.execute("SET SESSION max_execution_time=%s", (query_timeout_ms(),))
                cursor.execute(sql)
                rows = cursor.fetchall()
                return pd.DataFrame(rows, columns=[description[0] for description in cursor.description or []])
            finally:
                cursor.close()

    vn.run_sql_is_set = True
    vn.run_sql = run_sql_mysql
