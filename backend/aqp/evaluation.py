"""Immutable simulation rule drafts; activation is separately authorized."""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aqp.authorization import allowed
from aqp.store import audit, connection


class Metric(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    feature: Literal[
        "course_pass_ratio",
        "research_paper_count",
        "patent_count",
        "award_count",
        "conference_count",
        "latest_citation_count",
    ]
    weight: float = Field(gt=0)
    minimum: float = Field(ge=0)
    maximum: float = Field(gt=0)


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, pattern=r".*\S.*")
    college: str = Field(min_length=1)
    major: str = Field(min_length=1)
    mode: Literal["simulation"]
    metrics: list[Metric] = Field(min_length=1, max_length=6)
    previous_id: int | None = Field(default=None, ge=1)
    expected_version: int = Field(ge=0)


class Activation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    confirmed_by: str = Field(min_length=1, pattern=r".*\S.*")
    basis: str = Field(min_length=1, pattern=r".*\S.*")
    acknowledge_simulation: Literal[True]


def register_evaluation(app: FastAPI, path: Path, current: Callable[..., Any]) -> None:
    def authorize(db: Any, actor: int, config: dict[str, Any], operation: str) -> None:
        if not allowed(
            db,
            actor,
            "talent_evaluation",
            operation,
            config["college"],
            config["major"],
        ):
            raise HTTPException(403, "人才评价授权不足")

    @app.post("/api/evaluation-rules")
    def draft(body: Draft, request: Request) -> dict[str, Any]:
        config = body.model_dump(exclude={"previous_id", "expected_version"})
        if len({m.feature for m in body.metrics}) != len(body.metrics) or any(
            m.maximum <= m.minimum for m in body.metrics
        ):
            raise HTTPException(422, "指标须唯一且归一化上限须大于下限")
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            authorize(db, actor["id"], config, "maintain")
            family = db.execute(
                "SELECT COALESCE(MAX(family_id),0)+1 FROM evaluation_rules"
            ).fetchone()[0]
            version = 1
            if body.previous_id is not None:
                previous = db.execute(
                    "SELECT * FROM evaluation_rules WHERE id=?", (body.previous_id,)
                ).fetchone()
                if previous is None:
                    raise HTTPException(404, "规则不存在")
                authorize(db, actor["id"], json.loads(previous["config"]), "maintain")
                family = previous["family_id"]
                latest = db.execute(
                    "SELECT MAX(version) FROM evaluation_rules WHERE family_id=?",
                    (family,),
                ).fetchone()[0]
                if latest != body.expected_version or previous["version"] != latest:
                    raise HTTPException(409, "规则版本冲突")
                version = latest + 1
            elif body.expected_version != 0:
                raise HTTPException(409, "新规则版本须为0")
            cursor = db.execute(
                "INSERT INTO evaluation_rules(family_id,version,config,created_by,created_at) VALUES(?,?,?,?,?)",
                (family, version, json.dumps(config), actor["id"], int(time.time())),
            )
            audit(
                db, actor["id"], "evaluation.draft", str(cursor.lastrowid), "simulation"
            )
            db.commit()
            return {
                "id": cursor.lastrowid,
                "version": version,
                "enabled": False,
                "config": config,
            }

    @app.post("/api/evaluation-rules/{ident}/activate")
    def activate(ident: int, body: Activation, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            row = db.execute(
                "SELECT * FROM evaluation_rules WHERE id=?", (ident,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "规则不存在")
            authorize(db, actor["id"], json.loads(row["config"]), "activate_evaluation")
            latest = db.execute(
                "SELECT MAX(version) FROM evaluation_rules WHERE family_id=?",
                (row["family_id"],),
            ).fetchone()[0]
            if (
                row["enabled_at"] is not None
                or row["version"] != latest
                or latest != body.expected_version
            ):
                raise HTTPException(409, "规则版本冲突或已确认")
            db.execute(
                "UPDATE evaluation_rules SET enabled=0 WHERE family_id=?",
                (row["family_id"],),
            )
            db.execute(
                "UPDATE evaluation_rules SET enabled=1,confirmed_by=?,basis=?,enabled_by=?,enabled_at=? WHERE id=?",
                (body.confirmed_by, body.basis, actor["id"], int(time.time()), ident),
            )
            audit(
                db,
                actor["id"],
                "evaluation.activate",
                str(ident),
                json.dumps(body.model_dump(), ensure_ascii=False),
            )
            db.commit()
            return {
                "id": ident,
                "version": latest,
                "mode": "simulation",
                "enabled": True,
                "notice": "模拟演示，不构成正式人才识别",
            }
