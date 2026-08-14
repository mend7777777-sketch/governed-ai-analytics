"""FastAPI service for the local AI analytics application."""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analytics_service import EXAMPLE_QUESTIONS, AnalyticsQueryService, QueryValidationError


logger = logging.getLogger("ai_analytics.api")
app = FastAPI(title="AI Analytics API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@lru_cache(maxsize=1)
def get_service() -> AnalyticsQueryService:
    return AnalyticsQueryService()


@app.get("/api/health")
def health() -> dict[str, str]:
    try:
        get_service().health_check()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MySQL 或 Text2SQL 服务不可用") from exc
    return {"status": "healthy", "data_policy": "LLM does not receive query results"}


@app.get("/api/examples")
def examples() -> dict[str, list[str]]:
    return {"questions": EXAMPLE_QUESTIONS}


@app.post("/api/query")
def query(payload: QueryRequest) -> dict:
    try:
        return get_service().query(payload.question.strip())
    except QueryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # The raw upstream/provider exception may include sensitive connection details.
        logger.exception("Text2SQL query failed for question: %s", payload.question)
        raise HTTPException(status_code=502, detail="查询未完成，请检查问题或稍后重试。") from exc
