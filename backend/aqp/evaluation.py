"""Immutable simulation rule drafts; activation is separately authorized."""

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from statistics import quantiles
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from aqp.analysis import outcome
from aqp.authorization import allowed, student_allowed
from aqp.exports import excel_report
from aqp.research_outputs import current_participant
from aqp.store import audit, connection


def simulation_band(total: float | None, dimensions: list[float]) -> str:
    if total is None:
        return "数据不完整"
    if total >= 85:
        return "拔尖潜力（模拟分数段）"
    if total < 70:
        return "常规培养（模拟分数段）"
    if sum(value >= 0.8 for value in dimensions) >= 2:
        return "偏科特长型（模拟分数段）"
    return "待核查维度表现"


def simulation_percentiles(scores: list[float]) -> dict[str, float] | None:
    if len(scores) < 5:
        return None
    cutoffs = quantiles(scores, n=100, method="inclusive")
    return {f"p{p}": round(cutoffs[p - 1], 2) for p in (50, 75, 90)}


SOURCE_CATEGORY = {
    "research_paper_count": "research_papers",
    "patent_count": "patents",
    "award_count": "awards",
    "conference_count": "conferences",
    "latest_citation_count": "research_papers",
    "course_pass_ratio": "courses",
}


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


def builtin_evaluation(college: str, major: str) -> dict[str, Any]:
    dimensions = [
        ("学术基础", [("course_pass_ratio", 1)]),
        ("科研产出", [("research_paper_count", 3), ("patent_count", 2)]),
        ("学术影响", [("award_count", 2), ("conference_count", 2), ("latest_citation_count", 20)]),
    ]
    # Consistent demonstration judgments: foundation and output are equally
    # important and each is twice as important as impact.
    matrix = [[1.0, 1.0, 2.0], [1.0, 1.0, 2.0], [0.5, 0.5, 1.0]]
    size = len(matrix)
    columns = [sum(column) for column in zip(*matrix, strict=True)]
    weights = [sum(value / column for value, column in zip(row, columns, strict=True)) / size for row in matrix]
    eigenvalue = sum(
        sum(value * weight for value, weight in zip(row, weights, strict=True)) / row_weight
        for row, row_weight in zip(matrix, weights, strict=True)
    ) / size
    ratio = max(0.0, (eigenvalue - size) / (size - 1) / 0.58)
    if ratio >= 0.10:
        raise ValueError("内置模拟 AHP 判断矩阵未通过一致性检验")
    return {
        "name": "内置多维模拟评分 v2", "mode": "simulation", "builtin": True,
        "college": college, "major": major,
        "ahp": {"matrix": matrix, "consistency_ratio": ratio, "dimensions": [
            {"name": name, "weight": weight, "features": [feature for feature, _ in metrics]}
            for (name, metrics), weight in zip(dimensions, weights, strict=True)
        ]},
        "metrics": [
            {"feature": feature, "weight": weight / len(metrics), "minimum": 0, "maximum": maximum}
            for (_, metrics), weight in zip(dimensions, weights, strict=True)
            for feature, maximum in metrics
        ],
    }


def register_evaluation(app: FastAPI, path: Path, current: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    def deny(db: Any, actor: int, target: str, message: str) -> None:
        # Matches the analysis module: refusals stay auditable.
        audit(db, actor, "evaluation.access", target, "denied")
        db.commit()
        raise HTTPException(403, message)

    def authorize(db: Any, actor: int, config: dict[str, Any], operation: str) -> None:
        if not allowed(
            db,
            actor,
            "talent_evaluation",
            operation,
            config["college"],
            config["major"],
        ):
            deny(db, actor, "restricted", "人才评价授权不足")

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
            audit(db, actor["id"], "evaluation.list", "rules")
            db.commit()
            return {"items": items}

    def inputs(
        db: Any, actor: int, student_id: int, config: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str]:
        student = db.execute(
            "SELECT * FROM students WHERE id=? AND active=1", (student_id,)
        ).fetchone()
        if student is None or not student_allowed(db, actor, student_id):
            deny(db, actor, str(student_id), "学生当前范围不可访问")
        if (
            student["college"] != config["college"]
            or student["major"] != config["major"]
        ):
            deny(db, actor, str(student_id), "学生不在规则范围")
        for category in ["basic", "talent_evaluation"]:
            for operation in ["view", "identity", "analyze"]:
                if not allowed(
                    db, actor, category, operation, student["college"], student["major"]
                ):
                    deny(db, actor, str(student_id), "评价当前授权不足")
        result = []
        for metric in config["metrics"]:
            feature = metric["feature"]
            category = SOURCE_CATEGORY[feature]
            for operation in ["view", "identity", "analyze"]:
                if not allowed(
                    db, actor, category, operation, student["college"], student["major"]
                ):
                    deny(db, actor, str(student_id), "指标来源授权不足")
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
                                deny(db, actor, str(row["id"]), "来源记录当前范围不可访问")
                    item = {
                        "category": category,
                        "record_id": row["id"],
                        "business_key": row["business_key"],
                        "title": payload.get("title"),
                        "source_department": (
                            source[0]
                            if (
                                source := db.execute(
                                    f"SELECT source_department FROM {table}_output_versions WHERE output_id=? ORDER BY version DESC LIMIT 1",
                                    (row["id"],),
                                ).fetchone()
                            )
                            else None
                        ),
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
                        payload.get("所属学院", payload.get("学院")) != student["college"]
                        or payload.get("专业") != student["major"]
                    ):
                        deny(db, actor, str(row["id"]), "课程来源范围已变化")
                    status, pass_rule = outcome(payload, rules)
                    statuses.append(status)
                    evidence.append(
                        {
                            "category": "courses",
                            "record_id": row["id"],
                            "course_code": row["course_code"],
                            "term": row["term"],
                            "attempt": row["attempt"],
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
        # The digest covers only semantic data identity (which records and
        # versions produced which values). Presentation-only evidence fields
        # may evolve without marking every stored snapshot stale.
        stable = [
            {
                "feature": v["feature"],
                "value": v["value"],
                "normalized": v["normalized"],
                "weight": v["weight"],
                "records": [
                    {
                        "category": e["category"],
                        "record_id": e["record_id"],
                        "version": e["version"],
                    }
                    for e in v["evidence"]
                ],
                **(
                    {"citations": [e.get("citation") for e in v["evidence"]]}
                    if v["feature"] == "latest_citation_count"
                    else {}
                ),
            }
            for v in result
        ]
        digest = hashlib.sha256(
            json.dumps(stable, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        return result, digest

    def load_snapshot(db: Any, actor: int, ident: int, export: bool = False) -> dict[str, Any]:
        saved = db.execute(
            "SELECT * FROM evaluation_snapshots WHERE id=?", (ident,)
        ).fetchone()
        if saved is None:
            raise HTTPException(404, "评分快照不存在")
        rule = db.execute(
            "SELECT * FROM evaluation_rules WHERE id=?", (saved["rule_id"],)
        ).fetchone()
        config = json.loads(rule["config"])
        if export:
            for category in {"basic", "talent_evaluation"} | {
                SOURCE_CATEGORY[m["feature"]] for m in config["metrics"]
            }:
                if not allowed(db, actor, category, "export", config["college"], config["major"]):
                    deny(db, actor, str(ident), "评价或指标来源导出授权不足")
        _, digest = inputs(
            db, actor, saved["student_id"], config
        )
        result = json.loads(saved["result"])
        return {
            "id": ident,
            **result,
            "band": simulation_band(result["total"], [
                dimension["normalized"]
                for dimension in result.get("ahp", {}).get("dimensions", [])
                if dimension["normalized"] is not None
            ]),
            "family_id": rule["family_id"],
            "stale": digest != saved["data_digest"],
            "rule_currently_enabled": bool(rule["enabled"]),
        }

    @app.post("/api/evaluation-snapshots")
    def score(body: ScoreInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            if body.rule_id is None:
                student = db.execute("SELECT college,major FROM students WHERE id=? AND active=1", (body.student_id,)).fetchone()
                if student is None or not student_allowed(db, actor["id"], body.student_id):
                    deny(db, actor["id"], str(body.student_id), "学生当前范围不可访问")
                rule = db.execute(
                    """SELECT * FROM evaluation_rules WHERE enabled=1
                    AND json_extract(config,'$.college')=? AND json_extract(config,'$.major')=?
                    AND (COALESCE(json_extract(config,'$.builtin'),0)=0 OR json_type(config,'$.ahp')='object')
                    ORDER BY COALESCE(json_extract(config,'$.builtin'),0), id DESC LIMIT 1""",
                    (student["college"], student["major"]),
                ).fetchone()
                config = json.loads(rule["config"]) if rule else builtin_evaluation(student["college"], student["major"])
            else:
                rule = db.execute("SELECT * FROM evaluation_rules WHERE id=?", (body.rule_id,)).fetchone()
                if rule is None:
                    raise HTTPException(404, "规则不存在")
                config = json.loads(rule["config"])
            authorize(db, actor["id"], config, "analyze")
            if rule is not None and not rule["enabled"]:
                raise HTTPException(409, "规则尚未启用")
            values, digest = inputs(db, actor["id"], body.student_id, config)
            if rule is None:
                family = db.execute("SELECT COALESCE(MAX(family_id),0)+1 FROM evaluation_rules").fetchone()[0]
                cursor = db.execute(
                    """INSERT INTO evaluation_rules(family_id,version,config,enabled,confirmed_by,basis,created_by,created_at,enabled_at)
                    VALUES(?,1,?,1,'系统内置','仅供模拟研究',?,?,?)""",
                    (family, json.dumps(config), actor["id"], int(time.time()), int(time.time())),
                )
                rule = db.execute("SELECT * FROM evaluation_rules WHERE id=?", (cursor.lastrowid,)).fetchone()
            max_weight = max(v["weight"] for v in values)
            total = (
                None
                if any(v["missing"] for v in values)
                else sum(v["normalized"] * (v["weight"] / max_weight) for v in values)
                / sum(v["weight"] / max_weight for v in values)
                * 100
            )
            now = int(time.time())
            result = {
                "mode": config["mode"],
                "notice": "模拟演示，不构成正式人才识别",
                "student_id": body.student_id,
                "rule_id": rule["id"],
                "rule_name": config["name"],
                "family_id": rule["family_id"],
                "rule_version": rule["version"],
                "scope": {"college": config["college"], "major": config["major"]},
                "as_of": now,
                "inputs": values,
                "total": total,
                "data_digest": digest,
            }
            if ahp := config.get("ahp"):
                by_feature = {value["feature"]: value for value in values}
                dimensions = []
                for dimension in ahp["dimensions"]:
                    members = [by_feature[feature] for feature in dimension["features"]]
                    normalized = (
                        None if any(member["missing"] for member in members)
                        else sum(member["normalized"] for member in members) / len(members)
                    )
                    dimensions.append({**dimension, "normalized": normalized})
                result["ahp"] = {**ahp, "dimensions": dimensions}
            result["band"] = simulation_band(total, [
                dimension["normalized"] for dimension in result.get("ahp", {}).get("dimensions", [])
                if dimension["normalized"] is not None
            ])
            cursor = db.execute(
                "INSERT INTO evaluation_snapshots(student_id,rule_id,result,data_digest,created_by,created_at) VALUES(?,?,?,?,?,?)",
                (
                    body.student_id,
                    rule["id"],
                    json.dumps(result, allow_nan=False),
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

    @app.get("/api/evaluation-snapshots/dashboard")
    def dashboard(request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            items = []
            for row in db.execute(
                "SELECT e.id,e.rule_id,st.research_id,st.college,st.major "
                "FROM evaluation_snapshots e JOIN students st ON st.id=e.student_id "
                "WHERE st.active=1 AND e.id=(SELECT MAX(id) FROM evaluation_snapshots WHERE student_id=e.student_id)"
            ):
                try:
                    result = load_snapshot(db, actor["id"], row["id"])
                except HTTPException as exc:
                    if exc.status_code == 403:
                        continue
                    raise
                if result["mode"] != "simulation":
                    continue
                current_score = not result["stale"] and result["rule_currently_enabled"]
                items.append({
                    **dict(row), "rule_version": result["rule_version"], "as_of": result["as_of"],
                    "total": result["total"] if current_score else None,
                    "current": current_score,
                    "band": result["band"] if current_score else None,
                })
            audit(db, actor["id"], "evaluation.dashboard", "simulation")
            db.commit()
            benchmarks = {}
            for rule_id in {row["rule_id"] for row in items}:
                scores = [row["total"] for row in items if row["rule_id"] == rule_id and row["total"] is not None]
                benchmarks[rule_id] = {"count": len(scores), "percentiles": simulation_percentiles(scores)}
            return {"items": items, **({"benchmarks": benchmarks} if benchmarks else {})}

    @app.get("/api/evaluation-snapshots/{ident}")
    def snapshot(ident: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            result = load_snapshot(db, actor["id"], ident)
            audit(db, actor["id"], "evaluation.read", str(ident))
            db.commit()
            return result

    @app.get("/api/evaluation-snapshots")
    def snapshot_listing(request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            items = []
            # Re-check the student and rule scope now: history never bypasses
            # deactivation or grant changes since the snapshot was saved.
            for row in db.execute(
                "SELECT s.id, s.student_id, st.research_id, s.result, r.family_id "
                "FROM evaluation_snapshots s "
                "JOIN students st ON st.id=s.student_id AND st.active=1 "
                "JOIN evaluation_rules r ON r.id=s.rule_id "
                "ORDER BY s.id DESC"
            ):
                result = json.loads(row["result"])
                scope = result.get("scope") or {}
                if not student_allowed(db, actor["id"], row["student_id"]):
                    continue
                if not allowed(
                    db,
                    actor["id"],
                    "talent_evaluation",
                    "view",
                    scope.get("college", ""),
                    scope.get("major", ""),
                ):
                    continue
                items.append(
                    {
                        "id": row["id"],
                        "student_id": row["student_id"],
                        "research_id": row["research_id"],
                        "rule_id": result["rule_id"],
                        "family_id": row["family_id"],
                        "rule_version": result["rule_version"],
                        "mode": result["mode"],
                        "total": result["total"],
                        "as_of": result["as_of"],
                    }
                )
            audit(db, actor["id"], "evaluation.list", "snapshots")
            db.commit()
            return {"items": items}

    @app.get("/api/evaluation-snapshots/{ident}/export")
    def snapshot_export(ident: int, request: Request) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            report = load_snapshot(db, actor["id"], ident, export=True)
            audit(db, actor["id"], "evaluation.export", str(ident))
            db.commit()
            return excel_report(report, f"evaluation-snapshot-{ident}")

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
                previous_config = json.loads(previous["config"])
                authorize(db, actor["id"], previous_config, "maintain")
                if (
                    previous_config["college"],
                    previous_config["major"],
                ) != (config["college"], config["major"]):
                    # Activating a family version disables the whole family;
                    # a scope change would silently retire another scope's
                    # enabled rule.
                    raise HTTPException(409, "修订不得改变规则范围")
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

    return load_snapshot


class ScoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: int = Field(ge=1)
    rule_id: int | None = Field(default=None, ge=1)
