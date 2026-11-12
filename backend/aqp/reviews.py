"""Append-only human opinions bound to authorized candidate evidence."""

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aqp.store import audit, connection


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["建议推荐", "不建议推荐", "待补充材料"]
    comment: str = Field(min_length=1, max_length=10000, pattern=r".*\S.*")
    mode: Literal["self", "proxy"] = "self"
    confirmed_by: str = Field(default="", max_length=200)
    basis: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=0)
    request_id: str = Field(min_length=16, max_length=64)

    @model_validator(mode="after")
    def confirmation(self) -> "ReviewInput":
        if self.mode == "proxy" and (
            not self.confirmed_by.strip() or not self.basis.strip()
        ):
            raise ValueError("代录必须提供专家确认人及书面确认来源")
        if self.mode == "self" and (self.confirmed_by or self.basis):
            raise ValueError("本人复核使用实际登录账号")
        return self


def register_reviews(
    app: FastAPI,
    path: Path,
    current: Callable[..., Any],
    paper: Callable[..., Any],
    candidate: Callable[..., Any],
) -> None:
    def view(row: sqlite3.Row, evidence: dict[str, Any]) -> dict[str, Any]:
        return {
            k: row[k]
            for k in (
                "id",
                "candidate_id",
                "version",
                "decision",
                "comment",
                "mode",
                "confirmed_by",
                "basis",
                "recorded_by",
                "created_at",
            )
        } | {
            "evidence": json.loads(row["evidence"]),
            "stale": evidence["stale"],
            "current_confirmation": not evidence["stale"],
        }

    @app.get("/api/candidate-results/{ident}/reviews")
    def history(ident: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            evidence = candidate(db, actor["id"], ident)
            rows = db.execute(
                "SELECT * FROM paper_reviews WHERE candidate_id=? ORDER BY version",
                (ident,),
            ).fetchall()
            audit(db, actor["id"], "review.read", str(ident))
            items = [view(row, evidence) for row in rows]
            for item in items[:-1]:
                item["current_confirmation"] = False
            return {
                "candidate_id": ident,
                "version": len(items),
                "stale": evidence["stale"],
                "items": items,
            }

    @app.post("/api/candidate-results/{ident}/reviews")
    def submit(ident: int, body: ReviewInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            evidence = candidate(db, actor["id"], ident)
            paper(
                db,
                actor["id"],
                evidence["paper_version_id"],
                ("view", "analyze", "identity", "review"),
            )
            serialized = body.model_dump_json()
            previous = db.execute(
                "SELECT * FROM paper_reviews WHERE recorded_by=? AND request_id=?",
                (actor["id"], body.request_id),
            ).fetchone()
            if previous:
                if (
                    previous["candidate_id"] != ident
                    or previous["request_body"] != serialized
                ):
                    raise HTTPException(409, "重试标识已用于其他内容")
                return view(previous, evidence)
            if evidence["stale"]:
                raise HTTPException(409, "候选已过时，请重新分析后复核")
            version = db.execute(
                "SELECT COALESCE(MAX(version),0) FROM paper_reviews WHERE candidate_id=?",
                (ident,),
            ).fetchone()[0]
            if version != body.expected_version:
                raise HTTPException(409, "复核已更新，请读取历史后重试")
            cur = db.execute(
                "INSERT INTO paper_reviews(candidate_id,version,decision,comment,mode,confirmed_by,basis,recorded_by,created_at,request_id,request_body,evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    version + 1,
                    body.decision,
                    body.comment,
                    body.mode,
                    body.confirmed_by if body.mode == "proxy" else actor["username"],
                    body.basis,
                    actor["id"],
                    int(time.time()),
                    body.request_id,
                    serialized,
                    json.dumps(evidence),
                ),
            )
            audit(db, actor["id"], "review.create", str(cur.lastrowid))
            return view(
                db.execute(
                    "SELECT * FROM paper_reviews WHERE id=?", (cur.lastrowid,)
                ).fetchone(),
                evidence,
            )
