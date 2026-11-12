"""Structured, versioned auxiliary recommendations, never formal reviews."""

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from aqp.authorization import allowed
from aqp.exports import excel_report
from aqp.store import audit, connection


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    feature: Literal[
        "page_count", "character_count", "section_count", "reference_count"
    ]
    operator: Literal["gte", "lte", "eq"]
    value: float = Field(ge=0)


class RuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200, pattern=r".*\S.*")
    college: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    major: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    level: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    conditions: list[Condition] = Field(min_length=1, max_length=20)
    required_evidence: list[Literal["pages"]] = Field(min_length=1, max_length=1)
    minimum_samples: int = Field(ge=1, le=10000)
    missing_policy: Literal["insufficient"]
    synthetic: bool = False
    previous_id: int | None = Field(default=None, ge=1)


class Confirmation(BaseModel):
    confirmed_by: str = Field(min_length=1, max_length=200, pattern=r".*\S.*")
    basis: str = Field(min_length=1, max_length=2000, pattern=r".*\S.*")


class CandidateInput(BaseModel):
    comparison_id: int = Field(ge=1)


def register_candidates(
    app: FastAPI,
    path: Path,
    current: Callable[..., Any],
    paper: Callable[..., Any],
    snapshot: Callable[..., Any],
) -> Callable[..., Any]:
    def scope(
        db: sqlite3.Connection, actor: int, config: dict[str, Any], op: str
    ) -> None:
        if not allowed(db, actor, "papers", op, config["college"], config["major"]):
            audit(db, actor, "candidate.access", "restricted", "denied")
            db.commit()
            raise HTTPException(403, "候选规则范围授权不足")

    def rule_view(row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "config": json.loads(row["config"])}

    def comparison(
        db: sqlite3.Connection, actor: int, ident: int
    ) -> tuple[Any, Any, bool]:
        row = db.execute(
            "SELECT * FROM paper_comparisons WHERE id=?", (ident,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "比较不存在")
        target = paper(db, actor, row["target_id"], ("view", "analyze", "identity"))
        saved = json.loads(row["result"])
        for member in saved["evidence_versions"]:
            paper(db, actor, member["version_id"], ("view", "analyze", "identity"))
        members, _ = snapshot(db, actor, target, row["year"])
        newest = db.execute(
            "SELECT MAX(id) FROM paper_versions WHERE student_id=?",
            (target["student_id"],),
        ).fetchone()[0]
        return (
            target,
            saved,
            newest != target["id"]
            or json.dumps(members, sort_keys=True) != row["snapshot"],
        )

    def active(db: sqlite3.Connection, target: Any) -> list[dict[str, Any]]:
        student = db.execute(
            "SELECT * FROM students WHERE id=?", (target["student_id"],)
        ).fetchone()
        result = []
        for row in db.execute(
            "SELECT * FROM candidate_rules WHERE enabled=1 ORDER BY id"
        ):
            config = json.loads(row["config"])
            if (
                config["college"] == student["college"]
                and config["major"] == student["major"]
                and config["level"] == target["level"]
                and config["major"] == target["discipline"]
            ):
                result.append(rule_view(row))
        return result

    @app.post("/api/candidate-rules")
    def draft(body: RuleInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            config = body.model_dump(exclude={"previous_id"})
            scope(db, actor["id"], config, "candidate_rules")
            family, version = (
                db.execute(
                    "SELECT COALESCE(MAX(family_id),0)+1 FROM candidate_rules"
                ).fetchone()[0],
                1,
            )
            if body.previous_id:
                prev = db.execute(
                    "SELECT * FROM candidate_rules WHERE id=?", (body.previous_id,)
                ).fetchone()
                if prev is None:
                    raise HTTPException(404, "规则不存在")
                scope(db, actor["id"], json.loads(prev["config"]), "candidate_rules")
                family = prev["family_id"]
                version = db.execute(
                    "SELECT MAX(version)+1 FROM candidate_rules WHERE family_id=?",
                    (family,),
                ).fetchone()[0]
            cur = db.execute(
                "INSERT INTO candidate_rules(family_id,version,config,created_by,created_at) VALUES (?,?,?,?,?)",
                (family, version, json.dumps(config), actor["id"], int(time.time())),
            )
            audit(db, actor["id"], "candidate.rule.draft", str(cur.lastrowid))
            return rule_view(
                db.execute(
                    "SELECT * FROM candidate_rules WHERE id=?", (cur.lastrowid,)
                ).fetchone()
            )

    @app.get("/api/candidate-rules")
    def rules(request: Request) -> list[dict[str, Any]]:
        with connection(path) as db:
            actor, _ = current(db, request)
            items = [
                rule_view(r)
                for r in db.execute("SELECT * FROM candidate_rules ORDER BY id DESC")
                if allowed(
                    db,
                    actor["id"],
                    "papers",
                    "candidate_rules",
                    json.loads(r["config"])["college"],
                    json.loads(r["config"])["major"],
                )
            ]
            audit(db, actor["id"], "candidate.rules.read", "scoped")
            return items

    @app.post("/api/candidate-rules/{ident}/enable")
    def enable(ident: int, body: Confirmation, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            row = db.execute(
                "SELECT * FROM candidate_rules WHERE id=?", (ident,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "规则不存在")
            scope(db, actor["id"], json.loads(row["config"]), "candidate_rules")
            if row["confirmed_by"]:
                raise HTTPException(409, "已确认版本不可重复启用；请建立新版本")
            if db.execute(
                "SELECT 1 FROM candidate_rules WHERE family_id=? AND version>? AND confirmed_by!=''",
                (row["family_id"], row["version"]),
            ).fetchone():
                raise HTTPException(409, "已有更新确认版本")
            db.execute(
                "UPDATE candidate_rules SET enabled=0 WHERE family_id=?",
                (row["family_id"],),
            )
            db.execute(
                "UPDATE candidate_rules SET enabled=1,confirmed_by=?,basis=?,enabled_by=?,enabled_at=? WHERE id=?",
                (body.confirmed_by, body.basis, actor["id"], int(time.time()), ident),
            )
            audit(db, actor["id"], "candidate.rule.enable", str(ident))
            return rule_view(
                db.execute(
                    "SELECT * FROM candidate_rules WHERE id=?", (ident,)
                ).fetchone()
            )

    @app.post("/api/candidate-results")
    def evaluate(body: CandidateInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            target, compared, stale = comparison(db, actor["id"], body.comparison_id)
            if stale:
                raise HTTPException(409, "比较已过时，请重算")
            selected = active(db, target)
            results = []
            for rule in selected:
                config = rule["config"]
                raw = json.loads(target["result"] or "{}")
                missing = [] if raw.get("pages") else ["pages"]
                checks = []
                for cond in config["conditions"]:
                    value = compared["target_features"].get(cond["feature"])
                    groups = compared["groups"]
                    sufficient = compared["sufficient"] and all(
                        groups.get(k, {})
                        .get("features", {})
                        .get(cond["feature"], {})
                        .get("denominator", 0)
                        >= config["minimum_samples"]
                        for k in ("优秀", "普通")
                    )
                    if value is None:
                        missing.append(cond["feature"])
                    if not sufficient:
                        missing.append(
                            "同类优秀／普通组有效样本不足：" + cond["feature"]
                        )
                    status = "证据不足"
                    if value is not None and sufficient and not missing:
                        hit = {
                            "gte": value >= cond["value"],
                            "lte": value <= cond["value"],
                            "eq": value == cond["value"],
                        }[cond["operator"]]
                        status = "命中" if hit else "未命中"
                    checks.append({**cond, "value_observed": value, "status": status})
                results.append(
                    {
                        "rule_id": rule["id"],
                        "rule_version": rule["version"],
                        "rule": rule,
                        "checks": checks,
                        "missing": missing,
                        "recommended": all(c["status"] == "命中" for c in checks),
                    }
                )
            result = {
                "paper_version_id": target["id"],
                "file_sha256": target["sha256"],
                "comparison_id": body.comparison_id,
                "rules": results,
                "recommended": bool(results) and any(r["recommended"] for r in results),
                "notice": "辅助候选推荐，供专家人工复核；不是正式优秀评审或概率。合成规则仅用于软件验证。"
                if selected
                else "无适用启用规则，证据不足。",
                "groups": compared["groups"],
                "evidence_versions": compared["evidence_versions"],
                "evidence_url": f"/api/papers/{target['id']}/evidence",
            }
            ids = [r["id"] for r in selected]
            cur = db.execute(
                "INSERT INTO candidate_results(comparison_id,rules_snapshot,result,created_by,created_at) VALUES (?,?,?,?,?)",
                (
                    body.comparison_id,
                    json.dumps(ids),
                    json.dumps(result),
                    actor["id"],
                    int(time.time()),
                ),
            )
            audit(db, actor["id"], "candidate.evaluate", str(cur.lastrowid))
            return {"id": cur.lastrowid, "stale": False, **result}

    @app.get("/api/candidate-results/{ident}")
    def result_history(ident: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return load_result(db, actor["id"], ident)

    def load_result(db: sqlite3.Connection, actor: int, ident: int) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM candidate_results WHERE id=?", (ident,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "候选结果不存在")
        target, _, stale = comparison(db, actor, row["comparison_id"])
        stale = (
            stale
            or json.dumps([r["id"] for r in active(db, target)])
            != row["rules_snapshot"]
        )
        audit(db, actor, "candidate.result.read", str(ident))
        return {"id": ident, "stale": stale, **json.loads(row["result"])}

    @app.get("/api/candidate-results/{ident}/export")
    def export(ident: int, request: Request) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            data = load_result(db, actor["id"], ident)
            target = paper(
                db, actor["id"], data["paper_version_id"], ("view", "analyze", "export")
            )
            for member in data["evidence_versions"]:
                paper(
                    db, actor["id"], member["version_id"], ("view", "analyze", "export")
                )
            row = db.execute(
                "SELECT * FROM candidate_results WHERE id=?", (ident,)
            ).fetchone()
            data["created_at"] = row["created_at"]
            data["scope"] = {
                "level": target["level"],
                "discipline": target["discipline"],
                "year": data.get("year", ""),
            }
            data["data_version"] = data["evidence_versions"]
            data["rule_version"] = data.get("rules", "paper-comparison-v1")
            data["methodology"] = (
                "同层次同学科，排除自身；缺失不计零，待评不计普通；仅辅助人工复核。"
            )
            audit(db, actor["id"], "candidates.export", str(ident))
            return excel_report(data, f"candidate-results-{ident}")

    return load_result
