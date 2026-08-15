"""FastAPI service for the local AI analytics application."""

from __future__ import annotations

import logging
import time
import uuid
from functools import lru_cache
from typing import Dict, List, Optional, Union

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.services.history import list_query_history
from app.services.text2sql import EXAMPLE_QUESTIONS, AnalyticsQueryService, QueryValidationError
from app.core.logging import configure_logging
from app.governance.auth import (
    Principal, authenticate, change_password, decode_token, issue_token_pair,
    refresh_token, reset_password, revoke_refresh_token,
)
from app.governance.service import GovernanceError, GovernanceService
from app.knowledge.service import KnowledgeError, KnowledgeService
from app.governance.iam_admin import IAMAdminError, IAMAdminService
from app.governance.metrics import MetricError, MetricService


configure_logging()
logger = logging.getLogger("ai_analytics.api")
app = FastAPI(title="AI Analytics API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
bearer = HTTPBearer(auto_error=False)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_complete request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
        request_id, request.method, request.url.path, response.status_code,
        round((time.perf_counter() - started_at) * 1000),
    )
    return response


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    session_id: Optional[str] = Field(default=None, max_length=128)
    context: List[str] = Field(default_factory=list, max_length=3)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


class TableRegistrationRequest(BaseModel):
    table_name: str = Field(min_length=1, max_length=128)
    business_name: str = Field(min_length=1, max_length=255)
    owner_name: str = Field(min_length=1, max_length=100)
    sensitivity_level: str = Field(default="INTERNAL", max_length=20)


class GovernanceActionRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class KnowledgeDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=200000)
    document_type: str = Field(default="business_definition", max_length=64)


class MetricDefinitionRequest(BaseModel):
    metric_code: str = Field(min_length=2, max_length=128)
    metric_name: str = Field(min_length=1, max_length=255)
    definition: str = Field(min_length=1, max_length=10000)
    sql_expression: Optional[str] = Field(default=None, max_length=10000)


class ReferenceRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)
    department_code: Optional[str] = Field(default=None, max_length=64)
    position_code: Optional[str] = Field(default=None, max_length=64)
    roles: List[str] = Field(min_length=1)


class UserStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=16)


@lru_cache(maxsize=1)
def get_service() -> AnalyticsQueryService:
    return AnalyticsQueryService()


def current_principal(credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer)) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=401, detail="请先登录", headers={"WWW-Authenticate": "Bearer"})
    try:
        return decode_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="登录令牌无效或已过期", headers={"WWW-Authenticate": "Bearer"}) from exc


def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    try:
        principal.require("governance.table.manage")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="需要平台管理员权限") from exc
    return principal


def require_query_access(principal: Principal = Depends(current_principal)) -> Principal:
    try:
        principal.require("analytics.query")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="当前角色没有智能问数权限") from exc
    return principal


def require_iam_admin(principal: Principal = Depends(current_principal)) -> Principal:
    try:
        principal.require("iam.user.manage")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="需要用户与组织管理权限") from exc
    return principal


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> Dict[str, Union[str, List[str]]]:
    client_ip = request.client.host if request.client else "unknown"
    principal = authenticate(payload.username, payload.password, client_ip=client_ip)
    if principal is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    tokens = issue_token_pair(principal)
    return {**tokens, "username": principal.username, "roles": sorted(principal.roles)}


@app.post("/api/auth/refresh")
def refresh_access_token(payload: RefreshTokenRequest) -> dict:
    try:
        return refresh_token(payload.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="刷新令牌无效、已过期或已注销") from exc


@app.post("/api/auth/logout", status_code=204)
def logout(payload: RefreshTokenRequest) -> None:
    revoke_refresh_token(payload.refresh_token)


@app.post("/api/auth/change-password", status_code=204)
def change_own_password(payload: PasswordChangeRequest, principal: Principal = Depends(current_principal)) -> None:
    try:
        change_password(principal, payload.current_password, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    try:
        get_service().health_check()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="MySQL 或 Text2SQL 服务不可用") from exc
    return {"status": "healthy", "data_policy": "LLM does not receive query results"}


@app.get("/api/ready")
def readiness() -> dict[str, str]:
    return health()


@app.get("/api/examples")
def examples() -> dict[str, list[str]]:
    return {"questions": EXAMPLE_QUESTIONS}


@app.get("/api/governance/tables")
def governance_tables(_: Principal = Depends(current_principal)) -> dict:
    """Read-only view for the future governance console."""
    try:
        return {"tables": get_service().governance_tables()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="治理元数据暂不可用。") from exc


@app.post("/api/governance/tables", status_code=201)
def register_governance_table(payload: TableRegistrationRequest, principal: Principal = Depends(require_admin)) -> dict:
    try:
        return GovernanceService().register(principal, **payload.model_dump())
    except GovernanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _governance_action(table_name: str, action: str, payload: GovernanceActionRequest, principal: Principal) -> dict:
    try:
        return GovernanceService().transition(principal, table_name, action, payload.reason)
    except GovernanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/governance/tables/{table_name}/submit")
def submit_governance_table(table_name: str, payload: GovernanceActionRequest, principal: Principal = Depends(require_admin)) -> dict:
    return _governance_action(table_name, "submit", payload, principal)


@app.post("/api/governance/tables/{table_name}/approve")
def approve_governance_table(table_name: str, payload: GovernanceActionRequest, principal: Principal = Depends(require_admin)) -> dict:
    return _governance_action(table_name, "approve", payload, principal)


@app.post("/api/governance/tables/{table_name}/reject")
def reject_governance_table(table_name: str, payload: GovernanceActionRequest, principal: Principal = Depends(require_admin)) -> dict:
    return _governance_action(table_name, "reject", payload, principal)


@app.post("/api/governance/tables/{table_name}/revoke")
def revoke_governance_table(table_name: str, payload: GovernanceActionRequest, principal: Principal = Depends(require_admin)) -> dict:
    return _governance_action(table_name, "revoke", payload, principal)


@app.get("/api/knowledge/documents")
def knowledge_documents(_: Principal = Depends(require_admin)) -> dict:
    try:
        return {"documents": KnowledgeService().list_documents()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="知识库元数据暂不可用。") from exc


@app.post("/api/knowledge/documents", status_code=201)
def train_knowledge_document(payload: KnowledgeDocumentRequest, principal: Principal = Depends(require_admin)) -> dict:
    try:
        return KnowledgeService().register_and_train(get_service().vn, principal, **payload.model_dump())
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/knowledge/documents/{document_id}/retrain")
def retrain_knowledge_document(document_id: int, principal: Principal = Depends(require_admin)) -> dict:
    try:
        return KnowledgeService().retrain(get_service().vn, document_id)
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/knowledge/documents/{document_id}", status_code=204)
def delete_knowledge_document(document_id: int, principal: Principal = Depends(require_admin)) -> None:
    try:
        KnowledgeService().delete(principal, document_id)
    except KnowledgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/governance/tables/{table_name}/columns")
def governance_columns(table_name: str, _: Principal = Depends(current_principal)) -> dict:
    try:
        return {"columns": GovernanceService().list_columns(table_name)}
    except GovernanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/governance/tables/{table_name}/sync-columns")
def sync_governance_columns(table_name: str, principal: Principal = Depends(require_admin)) -> dict:
    try:
        return GovernanceService().sync_columns(principal, table_name)
    except GovernanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/governance/metrics")
def governance_metrics(_: Principal = Depends(current_principal)) -> dict:
    return {"metrics": MetricService().list()}


@app.post("/api/governance/metrics", status_code=201)
def create_governance_metric(payload: MetricDefinitionRequest, principal: Principal = Depends(require_admin)) -> dict:
    try:
        return MetricService().create(get_service().vn, principal, **payload.model_dump())
    except MetricError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/iam/departments")
def iam_departments(_: Principal = Depends(require_iam_admin)) -> dict:
    return {"departments": IAMAdminService().list_departments()}


@app.post("/api/iam/departments", status_code=201)
def create_iam_department(payload: ReferenceRequest, principal: Principal = Depends(require_iam_admin)) -> dict:
    try:
        return IAMAdminService().create_department(principal, payload.code, payload.name)
    except IAMAdminError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/iam/positions")
def iam_positions(_: Principal = Depends(require_iam_admin)) -> dict:
    return {"positions": IAMAdminService().list_positions()}


@app.post("/api/iam/positions", status_code=201)
def create_iam_position(payload: ReferenceRequest, principal: Principal = Depends(require_iam_admin)) -> dict:
    try:
        return IAMAdminService().create_position(principal, payload.code, payload.name)
    except IAMAdminError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/iam/roles")
def iam_roles(_: Principal = Depends(require_iam_admin)) -> dict:
    return {"roles": IAMAdminService().list_roles()}


@app.get("/api/iam/users")
def iam_users(_: Principal = Depends(require_iam_admin)) -> dict:
    return {"users": IAMAdminService().list_users()}


@app.post("/api/iam/users", status_code=201)
def create_iam_user(payload: UserCreateRequest, principal: Principal = Depends(require_iam_admin)) -> dict:
    try:
        return IAMAdminService().create_user(principal, **payload.model_dump())
    except IAMAdminError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/iam/users/{username}/status")
def update_iam_user_status(username: str, payload: UserStatusRequest, principal: Principal = Depends(require_iam_admin)) -> dict:
    try:
        return IAMAdminService().set_user_status(principal, username, payload.status)
    except IAMAdminError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/iam/users/{username}/reset-password", status_code=204)
def reset_iam_user_password(username: str, payload: PasswordResetRequest, principal: Principal = Depends(require_iam_admin)) -> None:
    try:
        reset_password(principal, username, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/query")
def query(payload: QueryRequest, principal: Principal = Depends(require_query_access)) -> dict:
    try:
        return get_service().query(payload.question.strip(), principal, payload.session_id, payload.context)
    except QueryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # The raw upstream/provider exception may include sensitive connection details.
        logger.exception("Text2SQL query failed for question: %s", payload.question)
        raise HTTPException(status_code=502, detail="查询未完成，请检查问题或稍后重试。") from exc


@app.get("/api/query/history")
def query_history(limit: int = 50, principal: Principal = Depends(require_query_access)) -> dict:
    return {"history": list_query_history(principal, limit)}
