"""Immutable scoped analysis and evidence API, shared by reporting consumers."""

import hashlib
import json
import sqlite3
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.authorization import allowed
from aqp.courses import visible
from aqp.store import audit, connection


class Scope(BaseModel):
    college: str = Field(min_length=1)
    major: str = Field(min_length=1)
    course_code: str = ""
    term: str = ""


class PassRule(Scope):
    course_code: str = Field(min_length=1)
    grading: Literal["百分制", "五级制", "二级制"]
    threshold: float | None = Field(default=None, ge=0, le=100)
    passing_values: list[str] = Field(default_factory=list)
    confirmed: bool = False
    reason: str = Field(min_length=1, max_length=2000)


def require(db: sqlite3.Connection, actor: int, scope: Scope, op: str) -> None:
    if not allowed(db, actor, "courses", op, scope.college, scope.major):
        raise HTTPException(403, "此范围操作未授权")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def sources(
    db: sqlite3.Connection, scope: Scope
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]], str]:
    rows = []
    for r in db.execute(
        "SELECT c.*,s.version AS student_version,s.payload AS student_payload,s.active AS student_active FROM course_records c JOIN students s ON s.id=c.student_id WHERE c.state='linked' ORDER BY c.id"
    ):
        p = json.loads(r["payload"])
        student = json.loads(r["student_payload"])
        if p.get("所属学院") != scope.college or p.get("专业") != scope.major:
            continue
        if scope.course_code and p.get("课程编号") != scope.course_code:
            continue
        if scope.term and p.get("修读学期") != scope.term:
            continue
        rows.append(
            {
                "id": r["id"],
                "version": r["version"],
                "active": r["active"],
                "student_id": r["student_id"],
                "student_version": r["student_version"],
                "student_dependency_token": f"basic:{r['student_id']}:{r['student_version']}:{r['student_active']}",
                "student_active": r["student_active"],
                "student": student,
                "payload": p,
                "source_row_id": r["source_row_id"],
                "source": dict(
                    db.execute(
                        "SELECT i.batch_id,i.sheet,i.row_number,b.source_department,b.created_at FROM import_rows i JOIN import_batches b ON b.id=i.batch_id WHERE i.id=?",
                        (r["source_row_id"],),
                    ).fetchone()
                ),
                "dependency_token": f"courses:{r['id']}:{r['version']}:{r['active']}",
            }
        )
    rules = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM pass_rules WHERE college=? AND major=? ORDER BY id",
            (scope.college, scope.major),
        )
    ]
    return rows, digest(rows), rules, digest(rules)


def outcome(p: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[str, int | None]:
    if p.get("业务通过结果") in ("通过", "不通过"):
        return p["业务通过结果"], None
    matching = [
        r
        for r in rules
        if r["course_code"] == p["课程编号"]
        and r["grading"] == p["评分制度"]
        and (not r["term"] or r["term"] == p["修读学期"])
    ]
    if not matching or p.get("原始成绩", "") == "":
        return "未知", None
    r = matching[-1]
    config = json.loads(r["config"])
    passed = (
        float(p["原始成绩"]) >= config["threshold"]
        if p["评分制度"] == "百分制"
        else p["原始成绩"] in config["passing_values"]
    )
    return ("通过" if passed else "不通过"), r["id"]


def calculate(
    rows: list[dict[str, Any]], rules: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    evidence = []
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row["active"] or not row["student_active"]:
            continue
        p = row["payload"]
        status, rule_id = outcome(p, rules)
        e = {**row, "status": status, "rule_id": rule_id}
        evidence.append(e)
        groups[(p["课程编号"], p["评分制度"], p["修读学期"])].append(e)

    def summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(e["status"] for e in items)
        known = counts["通过"] + counts["不通过"]
        return {
            "assessment_count": len(items),
            "student_count": len({e["student_id"] for e in items}),
            "passed": counts["通过"],
            "failed": counts["不通过"],
            "unknown": counts["未知"],
            "known_count": known,
            "missing_scores": sum(e["payload"]["原始成绩"] == "" for e in items),
            "pass_rate": round(counts["通过"] / known * 100, 2) if known else None,
        }

    distribution = []
    for (course, grading, term), items in groups.items():
        scores = (
            [
                float(e["payload"]["原始成绩"])
                for e in items
                if e["payload"]["原始成绩"] != ""
            ]
            if grading == "百分制"
            else []
        )
        distribution.append(
            {
                "course_code": course,
                "grading": grading,
                "term": term,
                **summary(items),
                "mean": round(sum(scores) / len(scores), 2) if scores else None,
                "values": dict(
                    Counter(e["payload"]["原始成绩"] or "缺失" for e in items)
                ),
            }
        )
    return {
        **summary(evidence),
        "groups": distribution,
        "calculation_version": "courses-v1",
        "methodology": "考核记录为单位；学生内部标识去重；通过率=通过/(通过+不通过)；未知不入分母；空成绩不计零；同课程学期评分制度内计算分布与均值；业务结果优先；否则采用最新确认的匹配规则",
    }, evidence


def register_analysis(app: FastAPI, path: Path, current: Callable[..., Any]) -> None:
    @app.post("/api/pass-rules")
    def save_rule(body: PassRule, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            require(db, actor["id"], body, "pass_rules")
            choices = (
                ["优秀", "良好", "中等", "及格", "不及格"]
                if body.grading == "五级制"
                else ["通过", "不通过", "合格", "不合格"]
            )
            if (
                not body.confirmed
                or not body.reason.strip()
                or (
                    body.grading == "百分制"
                    and (body.threshold is None or body.passing_values)
                )
                or (
                    body.grading != "百分制"
                    and (
                        body.threshold is not None
                        or not body.passing_values
                        or set(body.passing_values) - set(choices)
                    )
                )
            ):
                raise HTTPException(422, "须业务确认并填写此评分制度的完整通过条件")
            version = (
                db.execute(
                    "SELECT COUNT(*) FROM pass_rules WHERE college=? AND major=? AND course_code=? AND grading=? AND term=?",
                    (
                        body.college,
                        body.major,
                        body.course_code,
                        body.grading,
                        body.term,
                    ),
                ).fetchone()[0]
                + 1
            )
            rid = db.execute(
                "INSERT INTO pass_rules(college,major,course_code,grading,term,version,config,actor_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    body.college,
                    body.major,
                    body.course_code,
                    body.grading,
                    body.term,
                    version,
                    body.model_dump_json(),
                    actor["id"],
                    int(time.time()),
                ),
            ).lastrowid
            audit(db, actor["id"], "pass_rule.confirm", str(rid))
            return {"id": rid, "version": version}

    @app.get("/api/pass-rules")
    def list_rules(request: Request, college: str, major: str) -> dict[str, Any]:
        scope = Scope(college=college, major=major)
        with connection(path) as db:
            actor, _ = current(db, request)
            require(db, actor["id"], scope, "view")
            _, _, rules, version = sources(db, scope)
            audit(db, actor["id"], "pass_rule.list", scope.model_dump_json())
            return {"items": rules, "rule_version": version}

    def load(
        db: sqlite3.Connection, actor: int, sid: int, export: bool = False
    ) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM analysis_snapshots WHERE id=?", (sid,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "分析不存在")
        scope = Scope(**json.loads(row["scope"]))
        require(db, actor, scope, "view")
        require(db, actor, scope, "analyze")
        if export:
            require(db, actor, scope, "export")
        _, dv, _, rv = sources(db, scope)
        evidence = json.loads(row["evidence"])
        for e in evidence:
            current_row = db.execute(
                "SELECT payload FROM course_records WHERE id=?", (e["id"],)
            ).fetchone()
            for p in [
                e["payload"],
                json.loads(current_row["payload"]) if current_row else e["payload"],
            ]:
                for op in ["view", "analyze"] + (["export"] if export else []):
                    if not allowed(
                        db,
                        actor,
                        "courses",
                        op,
                        p.get("所属学院", ""),
                        p.get("专业", ""),
                    ):
                        raise HTTPException(403, "历史证据当前范围未授权")
            e["payload"] = visible(db, actor, e["payload"])
            e.pop("student", None)
        return {
            "id": sid,
            "category": row["category"],
            "scope": scope.model_dump(),
            "created_at": row["created_at"],
            "data_version": row["data_version"],
            "rule_version": row["rule_version"],
            "stale": dv != row["data_version"] or rv != row["rule_version"],
            "result": json.loads(row["result"]),
            "evidence": evidence,
        }

    @app.post("/api/analyses/courses")
    def analyze(body: Scope, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            require(db, actor["id"], body, "view")
            require(db, actor["id"], body, "analyze")
            rows, dv, rules, rv = sources(db, body)
            result, evidence = calculate(rows, rules)
            sid = db.execute(
                "INSERT INTO analysis_snapshots(category,scope,result,evidence,data_version,rule_version,actor_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    "courses",
                    body.model_dump_json(),
                    json.dumps(result),
                    json.dumps(evidence),
                    dv,
                    rv,
                    actor["id"],
                    int(time.time()),
                ),
            ).lastrowid
            assert sid is not None
            audit(db, actor["id"], "analysis.create", str(sid))
            return load(db, actor["id"], sid)

    @app.get("/api/analyses")
    def listing(request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            items = []
            for row in db.execute("SELECT id FROM analysis_snapshots ORDER BY id DESC"):
                try:
                    item = load(db, actor["id"], row["id"])
                    item.pop("evidence")
                    items.append(item)
                except HTTPException as exc:
                    if exc.status_code != 403:
                        raise
            audit(db, actor["id"], "analysis.list", "courses")
            return {"items": items}

    @app.get("/api/analyses/{sid}")
    @app.get("/api/analyses/{sid}/evidence")
    def get(sid: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            result = load(db, actor["id"], sid)
            audit(db, actor["id"], "analysis.read", str(sid))
            return result

    @app.get("/api/analyses/{sid}/export")
    def export(sid: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            result = load(db, actor["id"], sid, True)
            audit(db, actor["id"], "analysis.export", str(sid))
            return result
