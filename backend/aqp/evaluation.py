"""Immutable simulation rule drafts; activation is separately authorized."""

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from aqp.analysis import outcome
from aqp.authorization import allowed, student_allowed
from aqp.research_outputs import current_participant
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

    @app.get("/api/evaluation-rules")
    def listing(request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            items = []
            for row in db.execute("SELECT * FROM evaluation_rules ORDER BY id DESC"):
                config = json.loads(row["config"])
                if allowed(
                    db,
                    actor["id"],
                    "talent_evaluation",
                    "view",
                    config["college"],
                    config["major"],
                ):
                    items.append({**dict(row), "config": config})
            return {"items": items}

    def inputs(
        db: Any, actor: int, student_id: int, config: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        student = db.execute(
            "SELECT * FROM students WHERE id=? AND active=1", (student_id,)
        ).fetchone()
        if student is None or not student_allowed(db, actor, student_id):
            raise HTTPException(403, "学生当前范围不可访问")
        if (
            student["college"] != config["college"]
            or student["major"] != config["major"]
        ):
            raise HTTPException(403, "学生不在规则范围")
        for category in ["basic", "talent_evaluation"]:
            for operation in ["view", "identity", "analyze"]:
                if not allowed(
                    db, actor, category, operation, student["college"], student["major"]
                ):
                    raise HTTPException(403, "评价当前授权不足")
        result = []
        for metric in config["metrics"]:
            feature = metric["feature"]
            category = {
                "research_paper_count": "research_papers",
                "patent_count": "patents",
                "award_count": "awards",
                "conference_count": "conferences",
                "latest_citation_count": "research_papers",
                "course_pass_ratio": "courses",
            }[feature]
            for operation in ["view", "identity", "analyze"]:
                if not allowed(
                    db, actor, category, operation, student["college"], student["major"]
                ):
                    raise HTTPException(403, "指标来源授权不足")
            evidence = []
            value = None
            missing = "尚无可查证来源记录"
            if category != "courses":
                table = "research" if category == "research_papers" else category
                for row in db.execute(
                    f"SELECT * FROM {table}_outputs WHERE active=1 ORDER BY id"
                ):
                    payload = json.loads(row["payload"])
                    matches = [
                        p
                        for p in payload["participants"]
                        if p["student_number"] == student["student_number"]
                    ]
                    if not matches:
                        continue
                    for participant in matches:
                        for operation in ["view", "identity", "analyze"]:
                            if not current_participant(
                                db, actor, category, operation, participant
                            )[0]:
                                raise HTTPException(403, "来源记录当前范围不可访问")
                    item = {
                        "category": category,
                        "record_id": row["id"],
                        "version": row["version"],
                    }
                    if feature == "latest_citation_count":
                        citation = db.execute(
                            "SELECT snapshot_date,version,count FROM research_citations WHERE output_id=? ORDER BY snapshot_date DESC,version DESC LIMIT 1",
                            (row["id"],),
                        ).fetchone()
                        item["citation"] = dict(citation) if citation else None
                    evidence.append(item)
                if evidence:
                    if feature == "latest_citation_count":
                        if all(e["citation"] is not None for e in evidence):
                            value = sum(e["citation"]["count"] for e in evidence)
                        else:
                            missing = "部分成果缺少引用快照"
                    else:
                        value = len(evidence)
            else:
                rules = [
                    dict(r)
                    for r in db.execute(
                        "SELECT * FROM pass_rules WHERE college=? AND category='courses' ORDER BY id",
                        (student["college"],),
                    )
                ]
                statuses = []
                for row in db.execute(
                    "SELECT * FROM course_records WHERE student_id=? AND state='linked' AND active=1 ORDER BY id",
                    (student_id,),
                ):
                    payload = json.loads(row["payload"])
                    if (
                        payload.get("学院") != student["college"]
                        or payload.get("专业") != student["major"]
                    ):
                        raise HTTPException(403, "课程来源范围已变化")
                    status, pass_rule = outcome(payload, rules)
                    statuses.append(status)
                    evidence.append(
                        {
                            "category": "courses",
                            "record_id": row["id"],
                            "version": row["version"],
                            "source_row_id": row["source_row_id"],
                            "status": status,
                            "pass_rule_id": pass_rule,
                        }
                    )
                if statuses and "未知" not in statuses:
                    value = statuses.count("通过") / len(statuses)
                else:
                    missing = "课程记录缺失或存在通过状态未知"

            normalized = (
                None
                if value is None
                else min(
                    1.0,
                    max(
                        0.0,
                        (value - metric["minimum"])
                        / (metric["maximum"] - metric["minimum"]),
                    ),
                )
            )
            result.append(
                {
                    "feature": feature,
                    "value": value,
                    "normalized": normalized,
                    "weight": metric["weight"],
                    "evidence": evidence,
                    "missing": missing if value is None else None,
                }
            )
        digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        return result, digest

    @app.post("/api/evaluation-snapshots")
    def score(body: ScoreInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            rule = db.execute(
                "SELECT * FROM evaluation_rules WHERE id=?", (body.rule_id,)
            ).fetchone()
            if rule is None:
                raise HTTPException(404, "规则不存在")
            config = json.loads(rule["config"])
            authorize(db, actor["id"], config, "analyze")
            if not rule["enabled"]:
                raise HTTPException(409, "规则尚未启用")
            values, digest = inputs(db, actor["id"], body.student_id, config)
            total = (
                None
                if any(v["missing"] for v in values)
                else sum(v["normalized"] * v["weight"] for v in values)
                / sum(v["weight"] for v in values)
                * 100
            )
            now = int(time.time())
            result = {
                "mode": config["mode"],
                "notice": "模拟演示，不构成正式人才识别",
                "student_id": body.student_id,
                "rule_id": body.rule_id,
                "rule_version": rule["version"],
                "scope": {"college": config["college"], "major": config["major"]},
                "as_of": now,
                "inputs": values,
                "total": total,
                "data_digest": digest,
            }
            cursor = db.execute(
                "INSERT INTO evaluation_snapshots(student_id,rule_id,result,data_digest,created_by,created_at) VALUES(?,?,?,?,?,?)",
                (
                    body.student_id,
                    body.rule_id,
                    json.dumps(result),
                    digest,
                    actor["id"],
                    now,
                ),
            )
            audit(
                db, actor["id"], "evaluation.score", str(cursor.lastrowid), "simulation"
            )
            db.commit()
            return {"id": cursor.lastrowid, **result, "stale": False}

    @app.get("/api/evaluation-snapshots/{ident}")
    def snapshot(ident: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            saved = db.execute(
                "SELECT * FROM evaluation_snapshots WHERE id=?", (ident,)
            ).fetchone()
            if saved is None:
                raise HTTPException(404, "评分快照不存在")
            rule = db.execute(
                "SELECT * FROM evaluation_rules WHERE id=?", (saved["rule_id"],)
            ).fetchone()
            _, digest = inputs(
                db, actor["id"], saved["student_id"], json.loads(rule["config"])
            )
            return {
                "id": ident,
                **json.loads(saved["result"]),
                "stale": digest != saved["data_digest"],
                "rule_currently_enabled": bool(rule["enabled"]),
            }

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


class ScoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: int = Field(ge=1)
    rule_id: int = Field(ge=1)
