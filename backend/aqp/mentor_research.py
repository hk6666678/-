"""Descriptive research views over mentor groups: how group size relates to
output, and the growth paths of students whose theses carry expert labels.

Every figure is computed from currently authorized evidence only. Nothing here
ranks mentors or predicts outcomes: sample sizes and gaps are reported so the
reader can judge how much weight a number deserves."""

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from math import sqrt
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request

from aqp.analysis import outcome
from aqp.attachments import authorize_students
from aqp.authorization import allowed, has_category_grant
from aqp.mentor_groups import group_facts, relation_allowed
from aqp.research_outputs import current_participant
from aqp.store import audit, connection

OUTPUTS = (
    ("research_papers", "research"),
    ("patents", "patents"),
    ("awards", "awards"),
    ("conferences", "conferences"),
)
METRICS = (
    "course_pass_ratio",
    "topic_score",
    "midterm_score",
    "outputs_per_student",
    "oral_reports",
)
LABEL_GROUP = {"优秀": "excellent", "普通": "ordinary"}
MIN_CORRELATION_UNITS = 3
MIN_GROUP_SIZE = 2
GROWTH_BASIS = (
    "优秀与普通取自论文样本标签（专家标注），待评或未标注的学生不纳入比较；"
    "各组均值只对有数据的学生计算，缺失不填零。差值为优秀组减对照组，"
    "仅描述当前授权范围内的样本，不作因果或预测解读。"
)


def correlation(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r, or None when there is too little or no variation to learn from."""
    if len(xs) < MIN_CORRELATION_UNITS:
        return None
    dx = [x - mean(xs) for x in xs]
    dy = [y - mean(ys) for y in ys]
    spread = sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    if spread == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy, strict=True)) / spread


def can_analyze(db: sqlite3.Connection, actor: int, college: str, major: str, category: str) -> bool:
    return all(
        allowed(db, actor, category, op, college, major) for op in ("view", "analyze")
    )


def scale_output(db: sqlite3.Connection, actor: int, as_of: date, kind: str) -> dict[str, Any]:
    table, key = (
        ("mentor_directory", "mentor_id")
        if kind == "mentor"
        else ("research_groups", "group_id")
    )
    units = []
    excluded = 0
    for row in db.execute(f"SELECT id,name,college,major FROM {table} ORDER BY id"):
        facts = group_facts(db, actor, as_of.isoformat(), **{key: row["id"]})
        if not facts["student_count"]:
            continue
        rates = [
            facts["categories"][category]["participations_per_student"]
            for category, _ in OUTPUTS
        ]
        if any(rate is None for rate in rates):
            # One output category is not fully analyzable, so a per-student
            # total would silently undercount. Leave the unit out and say so.
            excluded += 1
            continue
        units.append(
            {
                "id": row["id"],
                "name": row["name"]
                if allowed(db, actor, "mentor_groups", "identity", row["college"], row["major"])
                else None,
                "students": facts["student_count"],
                "outputs_per_student": sum(float(rate) for rate in rates if rate is not None),
            }
        )
    sizes = [float(unit["students"]) for unit in units]
    outputs = [float(unit["outputs_per_student"]) for unit in units]
    return {
        "as_of": as_of.isoformat(),
        "kind": key,
        "units": units,
        "excluded_units": excluded,
        "correlation": {"r": correlation(sizes, outputs), "count": len(units)},
        "note": (
            "规模取统计日期当前有效关系的去重学生数，产出取四类成果的人均参与人次"
            "（同一成果可计多次个人参与）。仅纳入当前有学生且四类成果均可分析的同类单位。"
            "相关系数为描述性统计，单位不足三个或规模、产出没有变化时不计算；"
            "相关不代表规模导致产出差异。"
        ),
    }


def historical_students(
    db: sqlite3.Connection, actor: int, as_of: date, key: str, selected: int
) -> dict[int, sqlite3.Row]:
    """Students whose relation to this unit had started by the as-of date,
    including relations that have since ended."""
    students: dict[int, sqlite3.Row] = {}
    for relation in db.execute("SELECT * FROM mentor_group_relations ORDER BY id"):
        if relation[key] != selected or relation["start_date"] > as_of.isoformat():
            continue
        if not all(
            relation_allowed(db, actor, op, relation) for op in ("view", "analyze")
        ):
            continue
        student = db.execute(
            "SELECT * FROM students WHERE id=? AND active=1", (relation["student_id"],)
        ).fetchone()
        if student is not None:
            students[student["id"]] = student
    return students


def participant_index(
    db: sqlite3.Connection, numbers: set[str]
) -> dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]]:
    """Output participants keyed by student number: one pass over all outputs."""
    index: dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for category, table in OUTPUTS:
        for row in db.execute(f"SELECT payload FROM {table}_outputs WHERE active=1"):
            payload = json.loads(row["payload"])
            for participant in payload["participants"]:
                if participant["student_number"] in numbers:
                    index[participant["student_number"]].append(
                        (category, participant, payload.get("details") or {})
                    )
    return index


def sample_label(
    db: sqlite3.Connection, actor: int, student_id: int
) -> tuple[str, str | None]:
    """Latest expert label of the student's newest thesis version.

    Reading a label needs view and identity on every student the thesis
    covers, the same boundary as the label history endpoint."""
    latest = db.execute(
        "SELECT id,covered_student_ids FROM paper_versions WHERE student_id=? ORDER BY id DESC LIMIT 1",
        (student_id,),
    ).fetchone()
    if latest is None:
        return "unlabeled", None
    try:
        authorize_students(
            db, actor, "papers", json.loads(latest["covered_student_ids"]), ("view", "identity")
        )
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        return "denied", None
    label = db.execute(
        "SELECT label FROM paper_labels WHERE paper_id=? ORDER BY version DESC LIMIT 1",
        (latest["id"],),
    ).fetchone()
    return ("labeled", label["label"]) if label else ("unlabeled", None)


def student_metrics(
    db: sqlite3.Connection,
    actor: int,
    student: sqlite3.Row,
    outputs: list[tuple[str, dict[str, Any], dict[str, Any]]],
) -> dict[str, float | None]:
    college, major = student["college"], student["major"]

    def analyzable(category: str) -> bool:
        return can_analyze(db, actor, college, major, category)

    def in_scope(payload: dict[str, Any]) -> bool:
        return (payload.get("所属学院", payload.get("学院")), payload.get("专业")) == (
            college,
            major,
        )

    metrics: dict[str, float | None] = {}
    statuses: list[str] = []
    if analyzable("courses"):
        rules = [
            dict(rule)
            for rule in db.execute(
                "SELECT * FROM pass_rules WHERE college=? AND category='courses' ORDER BY id",
                (college,),
            )
        ]
        for row in db.execute(
            "SELECT payload FROM course_records WHERE student_id=? AND state='linked' AND active=1 ORDER BY id",
            (student["id"],),
        ):
            payload = json.loads(row["payload"])
            if in_scope(payload):
                statuses.append(outcome(payload, rules)[0])
    # Records whose scope no longer matches the archive are left out, the
    # same rule simulation scoring applies.
    metrics["course_pass_ratio"] = (
        statuses.count("通过") / len(statuses)
        if statuses and "未知" not in statuses
        else None
    )
    for category in ("topic", "midterm"):
        value = None
        row = (
            db.execute(
                "SELECT payload FROM milestone_records WHERE student_id=? AND category=? AND active=1 ORDER BY id DESC LIMIT 1",
                (student["id"], category),
            ).fetchone()
            if analyzable(category)
            else None
        )
        if row is not None:
            payload = json.loads(row["payload"])
            if in_scope(payload) and payload.get("评分制度") == "百分制":
                try:
                    score = float(payload.get("原始成绩") or "")
                except ValueError:
                    score = None
                if score is not None and 0 <= score <= 100:
                    value = score
        metrics[f"{category}_score"] = value
    if all(analyzable(category) for category, _ in OUTPUTS):
        visible_outputs = 0
        talks = 0
        for category, participant, details in outputs:
            permitted, linked = current_participant(db, actor, category, "view", participant)
            if (
                not permitted
                or linked is None
                or linked["id"] != student["id"]
                or not current_participant(db, actor, category, "analyze", participant)[0]
            ):
                continue
            visible_outputs += 1
            if details.get("报告类型") == "口头报告" and details.get("会议范围") == "国际":
                talks += 1
        metrics["outputs_per_student"] = float(visible_outputs)
        metrics["oral_reports"] = float(talks)
    else:
        metrics["outputs_per_student"] = None
        metrics["oral_reports"] = None
    return metrics


def summarize(rows: list[dict[str, float | None]]) -> dict[str, Any]:
    metrics = {}
    for name in METRICS:
        values: list[float] = []
        for row in rows:
            value = row[name]
            if value is not None:
                values.append(value)
        metrics[name] = {"count": len(values), "mean": mean(values) if values else None}
    return {"count": len(rows), "metrics": metrics}


def growth_path(
    db: sqlite3.Connection, actor: int, as_of: date, key: str, selected: int
) -> dict[str, Any]:
    table = "mentor_directory" if key == "mentor_id" else "research_groups"
    unit = db.execute(
        f"SELECT id,name,college,major FROM {table} WHERE id=?", (selected,)
    ).fetchone()
    if unit is None:
        raise HTTPException(404, "导师或课题组不存在")
    students = historical_students(db, actor, as_of, key, selected)
    index = participant_index(db, {row["student_number"] for row in students.values()})
    groups: dict[str, list[dict[str, float | None]]] = {"excellent": [], "ordinary": []}
    excluded = {"unlabeled": 0, "unauthorized": 0}
    for student_id, student in students.items():
        status, label = sample_label(db, actor, student_id)
        if status == "denied":
            excluded["unauthorized"] += 1
        elif status == "labeled" and label in LABEL_GROUP:
            groups[LABEL_GROUP[label]].append(
                student_metrics(db, actor, student, index.get(student["student_number"], []))
            )
        else:
            excluded["unlabeled"] += 1
    excellent, ordinary = summarize(groups["excellent"]), summarize(groups["ordinary"])
    labeled = excellent["count"] + ordinary["count"]
    if labeled == 0 and excluded["unauthorized"]:
        notice = (
            f"有 {excluded['unauthorized']} 名学生的论文标签因当前论文查看或身份权限不足未能读取，"
            "无法比较成长路径。"
        )
    elif labeled == 0:
        notice = (
            "该导师或课题组的学生尚无专家样本标签，无法比较成长路径；"
            "请先在学位论文质量页标注优秀或普通。"
        )
    elif min(excellent["count"], ordinary["count"]) < MIN_GROUP_SIZE:
        notice = (
            f"优秀组 {excellent['count']} 人、对照组 {ordinary['count']} 人，"
            "任一组不足 2 人，样本太小，不给出均值差。"
        )
    else:
        notice = None
    differences = (
        {
            name: (
                excellent["metrics"][name]["mean"] - ordinary["metrics"][name]["mean"]
                if excellent["metrics"][name]["mean"] is not None
                and ordinary["metrics"][name]["mean"] is not None
                else None
            )
            for name in METRICS
        }
        if notice is None
        else None
    )
    return {
        "as_of": as_of.isoformat(),
        "kind": key,
        "unit_id": selected,
        "unit_name": unit["name"]
        if allowed(db, actor, "mentor_groups", "identity", unit["college"], unit["major"])
        else None,
        "students": len(students),
        "excellent": excellent,
        "ordinary": ordinary,
        "excluded": excluded,
        "differences": differences,
        "notice": notice,
        "basis": GROWTH_BASIS,
    }


def register_mentor_research(
    app: FastAPI, path: Path, current: Callable[..., Any]
) -> None:
    def require_analysis(db: sqlite3.Connection, actor: int) -> None:
        if not all(
            has_category_grant(db, actor, "mentor_groups", op) for op in ("view", "analyze")
        ):
            raise HTTPException(403, "指导关系统计需要查看和分析权限")

    @app.get("/api/mentor-groups/scale-output")
    def scale_output_route(
        request: Request, as_of: date, kind: Literal["mentor", "group"] = "mentor"
    ) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_analysis(db, actor["id"])
            result = scale_output(db, actor["id"], as_of, kind)
            audit(db, actor["id"], "mentor_groups.scale_output", kind)
            db.commit()
            return result

    @app.get("/api/mentor-groups/growth-path")
    def growth_path_route(
        request: Request,
        as_of: date,
        mentor_id: int | None = None,
        group_id: int | None = None,
    ) -> dict[str, Any]:
        if (mentor_id is None) == (group_id is None):
            raise HTTPException(422, "请指定一位导师或一个课题组")
        with connection(path) as db:
            actor, _ = current(db, request)
            require_analysis(db, actor["id"])
            key, selected = (
                ("mentor_id", mentor_id) if mentor_id is not None else ("group_id", group_id)
            )
            assert selected is not None
            result = growth_path(db, actor["id"], as_of, key, selected)
            audit(db, actor["id"], "mentor_groups.growth_path", str(selected))
            db.commit()
            return result
