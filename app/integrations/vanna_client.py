"""Vanna and MySQL adapter used by the application service layer."""

from __future__ import annotations

import os

from openai import OpenAI
from vanna.legacy.chromadb import ChromaDB_VectorStore
from vanna.legacy.openai import OpenAI_Chat

from app.core.config import chroma_path, required_env


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
    vn.connect_to_mysql(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        dbname=os.getenv("MYSQL_DATABASE", "ai_analytics"),
        user=required_env("MYSQL_USER"),
        password=required_env("MYSQL_PASSWORD"),
        ssl_disabled=True,
    )
