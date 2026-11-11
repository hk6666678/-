"""Approved model boundary; callers must filter business data before invocation."""

import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr, model_validator
from starlette.responses import Response

from aqp.accounts import require_admin
from aqp.store import audit, connection


class ModelConfig(BaseModel):
    expected_version: int = Field(default=0, ge=0)
    enabled: bool = False
    approved: bool = False
    approval_reference: str = Field(default="", max_length=500)
    external_authorized: bool = False
    endpoint: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=100)
    key_env: str = Field(
        default="AQP_MODEL_KEY_LOCAL", pattern=r"^AQP_MODEL_KEY_[A-Z0-9_]+$"
    )
    allowed_purposes: list[Literal["papers", "agent"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def approved_target(self) -> "ModelConfig":
        if self.endpoint:
            url = urlsplit(self.endpoint)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("仅允许不含凭证和查询参数的 HTTP(S) 模型地址")
            local = url.hostname in {"localhost", "127.0.0.1", "::1"}
            if not local and not self.external_authorized:
                raise ValueError("非回环服务需要明确外部网络授权")
            if not local and url.scheme != "https":
                raise ValueError("非本机连接须使用 HTTPS")
        if self.enabled and not (
            self.approved
            and self.approval_reference.strip()
            and self.endpoint
            and self.model
            and self.allowed_purposes
        ):
            raise ValueError("启用需审批依据、模型地址、名称及允许用途")
        return self


def config_from(db: sqlite3.Connection) -> tuple[ModelConfig, int]:
    row = db.execute(
        "SELECT * FROM model_configs ORDER BY version DESC LIMIT 1"
    ).fetchone()
    return (
        (ModelConfig.model_validate_json(row["payload"]), row["version"])
        if row
        else (ModelConfig(), 0)
    )


def default_runner(config: ModelConfig, text: str) -> str:
    from langchain_openai import ChatOpenAI
    from langsmith import tracing_context

    key = os.environ.get(config.key_env)
    if not key:
        raise HTTPException(503, "模型凭证未配置")
    with httpx.Client(follow_redirects=False, trust_env=False, timeout=15) as client:  # noqa: SIM117
        with tracing_context(enabled=False):
            model = ChatOpenAI(
                model=config.model,
                base_url=config.endpoint,
                api_key=SecretStr(key),
                http_client=client,
                timeout=15,
                max_retries=0,
            )
            output = model.invoke(text, config={"callbacks": []})
            if not isinstance(output.content, str):
                raise HTTPException(502, "模型返回非文本内容")
            return output.content


def invoke_model(path: Path, purpose: str, text: str) -> str:
    """No fallback and no unapproved network calls. No raw payload in errors."""
    with connection(path) as db:
        config, _ = config_from(db)
    if (
        not config.enabled
        or not config.approved
        or purpose not in config.allowed_purposes
    ):
        raise HTTPException(503, "模型未启用或用途未获准")
    try:
        return default_runner(config, text)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 -- never expose provider exceptions or credentials
        raise HTTPException(502, "模型连接失败或超时，请检查获准服务") from None


def register_model_connection(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, error: RequestValidationError
    ) -> Response:
        if request.url.path.startswith("/api/model/"):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "模型配置格式无效；检查地址、审批依据、用途及环境变量名称"
                },
            )
        return await request_validation_exception_handler(request, error)

    @app.get("/api/model/config")
    def get_config(request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_admin(actor)
            config, version = config_from(db)
            return {
                **config.model_dump(),
                "version": version,
                "credential_configured": bool(os.environ.get(config.key_env)),
                "external_tracing": False,
            }

    @app.get("/api/model/status")
    def status(request: Request) -> dict[str, object]:
        with connection(path) as db:
            current(db, request)
            config, version = config_from(db)
            return {
                "enabled": config.enabled,
                "approved": config.approved,
                "version": version,
                "available": config.enabled and bool(os.environ.get(config.key_env)),
                "message": "已配置，需连接验证" if config.enabled else "Agent 未启用",
            }

    @app.put("/api/model/config")
    def save_config(body: ModelConfig, request: Request) -> dict[str, object]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            require_admin(actor)
            _, version = config_from(db)
            if body.expected_version != version:
                raise HTTPException(409, "模型配置已变化，请重新加载")
            db.execute(
                "INSERT INTO model_configs VALUES (?,?,?,?)",
                (version + 1, body.model_dump_json(), actor["id"], int(time.time())),
            )
            audit(
                db,
                actor["id"],
                "model.configure",
                str(version + 1),
                details={
                    "enabled": body.enabled,
                    "approved": body.approved,
                    "allowed_purposes": body.allowed_purposes,
                },
            )
            return {"version": version + 1, "enabled": body.enabled}

    @app.post("/api/model/check")
    def check(request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_admin(actor)
            config, version = config_from(db)
        purpose = config.allowed_purposes[0] if config.allowed_purposes else "agent"
        try:
            invoke_model(
                path, purpose, "Synthetic connection check. Reply OK. No business data."
            )
        except HTTPException:
            with connection(path) as db:
                audit(db, actor["id"], "model.check", str(version), "failed")
            raise
        with connection(path) as db:
            audit(db, actor["id"], "model.check", str(version))
        return {
            "connected": True,
            "version": version,
            "message": "连接请求成功；不代表业务效果验收",
        }
