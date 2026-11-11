"""Management audit metadata. Business contents never become management access."""

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request

from aqp.accounts import require_admin
from aqp.store import audit, connection


def safe_details(value: object, depth: int = 0, context: str = "") -> object:
    """Allow only structured audit metadata, never arbitrary text or credentials."""
    if depth > 4:
        return None
    if isinstance(value, dict):
        allowed = {
            "before",
            "after",
            "active",
            "roles",
            "version",
            "count",
            "total",
            "rule_version",
            "data_version",
            "reason_code",
            "category",
            "operation",
            "college",
            "major",
        }
        return {
            key: safe_details(item, depth + 1, key)
            for key, item in value.items()
            if key in allowed
        }
    if isinstance(value, list):
        return [safe_details(item, depth + 1) for item in value[:50]]
    if isinstance(value, (bool, int)) or value is None:
        return value
    if isinstance(value, str) and value in {
        "platform_admin",
        "college_data_admin",
        "college_analyst",
    }:
        return value
    if isinstance(value, str) and context in {
        "category",
        "operation",
        "college",
        "major",
        "reason_code",
    }:
        return value[:100]
    return "[内容受限]"


def public_target(action: str, target: str) -> str:
    if action in {
        "login",
        "logout",
        "bootstrap",
        "user.create",
        "user.update",
        "grants.replace",
        "audit.query",
    }:
        return target
    return "ref-" + hashlib.sha256(target.encode()).hexdigest()[:16]


def register_audit_viewer(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    @app.get("/api/audit")
    def audit_list(
        request: Request,
        actor_id: int | None = None,
        action: str = Query(default="", max_length=100),
        target: str = Query(default="", max_length=100),
        started_at: int | None = Query(default=None, ge=0),
        ended_at: int | None = Query(default=None, ge=0),
        page: int = Query(default=1, ge=1, le=1000000),
        page_size: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, object]:
        if started_at is not None and ended_at is not None and started_at > ended_at:
            raise HTTPException(422, "开始时间不能晚于结束时间")
        with connection(path) as db:
            actor, _ = current(db, request)
            require_admin(actor)
            db.create_function("public_target", 2, public_target, deterministic=True)
            clauses: list[str] = []
            values: list[object] = []
            for column, value in [
                ("actor_id", actor_id),
                ("action", action or None),
                ("public_target(action,target)", target or None),
            ]:
                if value is not None:
                    clauses.append(f"{column}=?")
                    values.append(value)
            if started_at is not None:
                clauses.append("created_at>=?")
                values.append(started_at)
            if ended_at is not None:
                clauses.append("created_at<=?")
                values.append(ended_at)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            total = db.execute("SELECT COUNT(*) FROM audit" + where, values).fetchone()[
                0
            ]
            result: list[dict[str, object]] = []
            for row in db.execute(
                "SELECT * FROM audit" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                [*values, page_size, (page - 1) * page_size],
            ):
                item = dict(row)
                item["target"] = public_target(row["action"], row["target"])
                item["action"] = (
                    row["action"]
                    if re.fullmatch(r"[a-z0-9_.-]{1,100}", row["action"])
                    else "restricted-event"
                )
                try:
                    item["details"] = safe_details(json.loads(row["details"]))
                except (ValueError, TypeError):
                    item["details"] = {}
                result.append(item)
            audit(
                db,
                actor["id"],
                "audit.query",
                "audit-metadata",
                details={"count": len(result)},
            )
            return {
                "items": result,
                "total": total,
                "page": page,
                "page_size": page_size,
                "notice": "仅展示管理元信息；业务内容与敏感信息受限。",
            }
