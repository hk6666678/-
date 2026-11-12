"""Immutable scoped analysis and evidence API, shared by reporting consumers."""

import hashlib
import json
import sqlite3
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, Literal, NamedTuple, TypedDict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from aqp.authorization import allowed, student_allowed
from aqp.courses import visible
from aqp.exports import excel_report
from aqp.milestones import masked, reconcile_milestones
from aqp.store import audit, connection


class Scope(BaseModel):
    college: str = Field(min_length=1)
    major: str = Field(default="", max_length=100)
    category: Literal["courses", "topic", "midterm"] = "courses"
    grade: str = ""
    level: str = ""
    group_by: Literal["", "grade", "major", "level"] = ""
    course_code: str = ""
    term: str = ""


class PassRule(Scope):
    major: str = Field(min_length=1)
    course_code: str = Field(min_length=1)
    grading: Literal["百分制", "五级制", "二级制"]
    threshold: float | None = Field(default=None, ge=0, le=100)
    passing_values: list[str] = Field(default_factory=list)
    confirmed: bool = False
    reason: str = Field(min_length=1, max_length=2000)


class TrainingRequirement(Scope):
    major: str = Field(min_length=1)
    required_credits: float = Field(gt=0, allow_inf_nan=False)
    repeat_policy: Literal["max_passed_credits"]
    confirmed: bool = False
    reason: str = Field(min_length=1, max_length=2000)


class AnalysisSources(NamedTuple):
    rows: list[dict[str, Any]]
    data_version: str
    rules: list[dict[str, Any]]
    rule_version: str
    trainings: list[dict[str, Any]]


class CreditStudent(TypedDict):
    major: str
    credits: dict[str, float]


def major_options(
    db: sqlite3.Connection, actor: int, scope: Scope, op: str
) -> set[str] | None:
    rows = db.execute(
        "SELECT major FROM grants WHERE user_id=? AND category=? AND operation=? AND college=?",
        (actor, scope.category, op, scope.college),
    ).fetchall()
    return (
        None
        if any(not row["major"] for row in rows)
        else {row["major"] for row in rows if row["major"]}
    )


def effective_majors(
    db: sqlite3.Connection, actor: int, scope: Scope, operations: list[str]
) -> set[str] | None:
    options = [major_options(db, actor, scope, op) for op in operations]
    if all(option is None for option in options):
        return None
    specific = [option for option in options if option is not None]
    if len(specific) == 1:
        return specific[0]
    return set.intersection(*specific)


def require(db: sqlite3.Connection, actor: int, scope: Scope, op: str) -> None:
    denied = bool(scope.major) and not allowed(
        db, actor, scope.category, op, scope.college, scope.major
    )
    if not scope.major:
        denied = effective_majors(db, actor, scope, [op]) == set()
    if denied:
        audit(db, actor, "analysis.access", "restricted", "denied")
        db.commit()
        raise HTTPException(403, "此范围操作未授权")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def sources(
    db: sqlite3.Connection,
    scope: Scope,
    actor: int,
    operations: list[str] | None = None,
) -> AnalysisSources:
    operations = operations or ["view", "analyze"]
    majors = effective_majors(db, actor, scope, operations)
    rows = []
    table = "course_records" if scope.category == "courses" else "milestone_records"
    condition = (
        "c.state='linked'"
        if scope.category == "courses"
        else "c.category=? AND c.student_id IS NOT NULL"
    )
    for r in db.execute(
        f"SELECT c.*,s.version AS student_version,s.payload AS student_payload,s.active AS student_active FROM {table} c JOIN students s ON s.id=c.student_id WHERE {condition} ORDER BY c.id",
        () if scope.category == "courses" else (scope.category,),
    ):
        if not student_allowed(db, actor, r["student_id"]):
            continue
        p = json.loads(r["payload"])
        student = json.loads(r["student_payload"])
        if p.get("所属学院") != scope.college:
            continue
        if scope.major and p.get("专业") != scope.major:
            continue
        if not scope.major and majors is not None and p.get("专业") not in majors:
            continue
        if scope.grade and student.get("入学年份") != scope.grade:
            continue
        if scope.level and student.get("培养层次") != scope.level:
            continue
        if (
            scope.course_code
            and p.get("课程编号", p.get("考核批次")) != scope.course_code
        ):
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
                "dependency_token": f"{scope.category}:{r['id']}:{r['version']}:{r['active']}",
            }
        )

    def major_allowed(item_major: str) -> bool:
        if scope.major:
            return item_major == scope.major
        return majors is None or item_major in majors

    rules = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM pass_rules WHERE college=? AND category=? ORDER BY id",
            (scope.college, scope.category),
        )
        if major_allowed(r["major"])
    ]
    training = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM training_requirements WHERE college=? ORDER BY id",
            (scope.college,),
        )
        if scope.category == "courses" and major_allowed(r["major"])
    ]
    return AnalysisSources(rows, digest(rows), rules, digest([rules, training]), training)

def outcome(p: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[str, int | None]:
    if p.get("业务通过结果") in ("通过", "不通过"):
        return p["业务通过结果"], None
    matching = [
        r
        for r in rules
        if r["major"] == p.get("专业", "")
        and r["course_code"] == p.get("课程编号", p.get("考核批次", ""))
        and r["grading"] == p["评分制度"]
        and (not r["term"] or r["term"] == p.get("修读学期", ""))
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
    rows: list[dict[str, Any]], rules: list[dict[str, Any]], scope: Scope
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    evidence = []
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row["active"] or not row["student_active"]:
            continue
        p = row["payload"]
        status, rule_id = outcome(p, rules)
        e = {**row, "status": status, "rule_id": rule_id}
        evidence.append(e)
        groups[
            (
                p.get("课程编号", p.get("考核批次", "")),
                p["评分制度"],
                p.get("修读学期", ""),
                str(
                    row["student"].get(
                        {"grade": "入学年份", "major": "专业", "level": "培养层次"}.get(
                            scope.group_by, ""
                        ),
                        "",
                    )
                ),
            )
        ].append(e)

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
    for (course, grading, term, group_value), items in groups.items():
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
                "group_value": group_value,
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
        "calculation_version": "courses-v1"
        if scope.category == "courses"
        else "milestones-v1",
        "credit_progress": {
            "value": None,
            "missing_conditions": ["学分", "培养要求", "重复修读计入规则"],
        },
        "reminders": [reminder(e) for e in evidence],
        "methodology": "考核记录为单位；学生内部标识去重；通过率=通过/(通过+不通过)；未知不入分母；空成绩不计零；同课程学期评分制度内计算分布与均值；业务结果优先；否则采用最新确认的匹配规则",
    }, evidence


def credit_progress(
    evidence: list[dict[str, Any]], trainings: list[dict[str, Any]], scope: Scope
) -> dict[str, Any]:
    missing = []
    if scope.course_code or scope.term:
        missing.append("完整课程范围")
    latest = {item["major"]: item for item in trainings}
    represented = {e["payload"].get("专业", "") for e in evidence}
    if any(major not in latest for major in represented):
        missing.extend(["培养要求", "重复修读计入规则"])
    if not evidence or any(e["payload"].get("学分", "") == "" for e in evidence):
        missing.append("学分")
    if any(e["status"] == "未知" for e in evidence):
        missing.append("通过状态")
    if missing:
        return {"value": None, "missing_conditions": missing, "students": []}

    requirements = [latest[major] for major in sorted(represented)]
    students: dict[int, CreditStudent] = {}
    for e in evidence:
        major = e["payload"]["专业"]
        student = students.setdefault(
            e["student_id"], CreditStudent(major=major, credits={})
        )
        if e["status"] == "通过":
            credits = student["credits"]
            course = e["payload"]["课程编号"]
            credits[course] = max(
                credits.get(course, 0), float(e["payload"]["学分"])
            )
    student_rows = []
    for sid, item in students.items():
        credits = item["credits"]
        requirement = latest[item["major"]]
        config = json.loads(requirement["config"])
        earned = sum(credits.values())
        student_rows.append(
            {
                "student_id": sid,
                "earned_credits": earned,
                "progress_percent": round(
                    earned / config["required_credits"] * 100, 2
                ),
            }
        )
    single = len(requirements) == 1
    return {
        "value": "available",
        "missing_conditions": [],
        "requirement_id": requirements[0]["id"]
        if single
        else [item["id"] for item in requirements],
        "requirement": dict(requirements[0])
        if single
        else [dict(item) for item in requirements],
        "required_credits": json.loads(requirements[0]["config"])["required_credits"]
        if single
        else [
            json.loads(item["config"])["required_credits"] for item in requirements
        ],
        "repeat_policy": "max_passed_credits",
        "students": student_rows,
    }

def reminder(e: dict[str, Any]) -> dict[str, Any]:
    p = e["payload"]
    missing = []

    def parsed(field: str) -> date | None:
        try:
            return date.fromisoformat(str(p.get(field, "")))
        except ValueError:
            missing.append(field)
            return None

    planned = parsed("计划日期")
    actual = parsed("实际日期") if p.get("实际日期") else None
    if actual is None and p.get("完成状态") != "未完成":
        missing.append("实际日期或明确未完成状态")
    overdue = None if missing or planned is None else (actual or date.today()) > planned
    return {
        "record_id": e["id"],
        "overdue": overdue,
        "missing_conditions": missing,
        "as_of": date.today().isoformat(),
        "dependency_token": e["dependency_token"],
    }


def register_analysis(
    app: FastAPI, path: Path, current: Callable[..., Any]
) -> Callable[..., Any]:
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
                    "SELECT COUNT(*) FROM pass_rules WHERE college=? AND major=? AND course_code=? AND grading=? AND term=? AND category=?",
                    (
                        body.college,
                        body.major,
                        body.course_code,
                        body.grading,
                        body.term,
                        body.category,
                    ),
                ).fetchone()[0]
                + 1
            )
            rid = db.execute(
                "INSERT INTO pass_rules(college,major,course_code,grading,term,version,config,actor_id,created_at,category) VALUES (?,?,?,?,?,?,?,?,?,?)",
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
                    body.category,
                ),
            ).lastrowid
            audit(db, actor["id"], "pass_rule.confirm", str(rid))
            return {"id": rid, "version": version}

    @app.get("/api/pass-rules")
    def list_rules(
        request: Request,
        college: str,
        major: str,
        category: Literal["courses", "topic", "midterm"] = "courses",
    ) -> dict[str, Any]:
        scope = Scope(college=college, major=major, category=category)
        with connection(path) as db:
            actor, _ = current(db, request)
            require(db, actor["id"], scope, "view")
            _, _, rules, version, _ = sources(db, scope, actor["id"], ["view"])
            audit(db, actor["id"], "pass_rule.list", scope.model_dump_json())
            return {"items": rules, "rule_version": version}

    @app.post("/api/training-requirements")
    def training(body: TrainingRequirement, request: Request) -> dict[str, Any]:
        body.category = "courses"
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            require(db, actor["id"], body, "pass_rules")
            if not body.confirmed or not body.reason.strip():
                raise HTTPException(422, "须业务确认培养要求及重复修读计入规则")
            rid = db.execute(
                "INSERT INTO training_requirements(college,major,config,actor_id,created_at) VALUES (?,?,?,?,?)",
                (
                    body.college,
                    body.major,
                    body.model_dump_json(),
                    actor["id"],
                    int(time.time()),
                ),
            ).lastrowid
            audit(db, actor["id"], "training_requirement.confirm", str(rid))
            return {"id": rid}

    def load(
        db: sqlite3.Connection, actor: int, sid: int, export: bool = False
    ) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM analysis_snapshots WHERE id=?", (sid,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "分析不存在")
        scope = Scope(**{**json.loads(row["scope"]), "category": row["category"]})
        require(db, actor, scope, "view")
        require(db, actor, scope, "analyze")
        if export:
            require(db, actor, scope, "export")
        _, dv, _, rv, _ = sources(db, scope, actor)
        evidence = json.loads(row["evidence"])
        for e in evidence:
            if not student_allowed(db, actor, e["student_id"]):
                raise HTTPException(403, "历史证据当前学生范围未授权")
            current_row = db.execute(
                f"SELECT payload FROM {'course_records' if scope.category == 'courses' else 'milestone_records'} WHERE id=?",
                (e["id"],),
            ).fetchone()
            for p in [
                e["payload"],
                json.loads(current_row["payload"]) if current_row else e["payload"],
            ]:
                for op in ["view", "analyze"] + (["export"] if export else []):
                    if not allowed(
                        db,
                        actor,
                        scope.category,
                        op,
                        p.get("所属学院", ""),
                        p.get("专业", ""),
                    ):
                        raise HTTPException(403, "历史证据当前范围未授权")
            student = db.execute(
                "SELECT college,major FROM students WHERE id=?", (e["student_id"],)
            ).fetchone()
            if student is None or not all(
                allowed(db, actor, scope.category, op, student["college"], student["major"])
                for op in ["view", "analyze"] + (["export"] if export else [])
            ):
                audit(db, actor, "analysis.access", "restricted", "denied")
                db.commit()
                raise HTTPException(403, "历史证据当前学生范围未授权")
            e["payload"] = (
                visible(db, actor, e["payload"])
                if scope.category == "courses"
                else masked(db, actor, e["payload"], scope.category)
            )
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

    @app.post("/api/analyses/{category}")
    def analyze(
        body: Scope, request: Request, category: Literal["courses", "topic", "midterm"]
    ) -> dict[str, Any]:
        with connection(path) as db:
            # Five local analyses can queue behind a full baseline calculation.
            # Keep the transaction snapshot intact with a bounded wait.
            db.execute("PRAGMA busy_timeout=60000")
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            body.category = category
            require(db, actor["id"], body, "view")
            require(db, actor["id"], body, "analyze")
            if category != "courses":
                reconcile_milestones(db, actor["id"])
            rows, dv, rules, rv, trainings = sources(db, body, actor["id"])
            result, evidence = calculate(rows, rules, body)
            if category == "courses":
                result["credit_progress"] = credit_progress(evidence, trainings, body)
            sid = db.execute(
                "INSERT INTO analysis_snapshots(category,scope,result,evidence,data_version,rule_version,actor_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    body.category,
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
    def export(sid: int, request: Request) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            result = load(db, actor["id"], sid, True)
            audit(db, actor["id"], "analysis.export", str(sid))
            return excel_report(result, f"analysis-{sid}")
    return load
