import json
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from scipy.stats import t  # type: ignore[import-untyped]

from aqp.agent import OUTPUT_TABLES, agent_scope_students
from aqp.authorization import allowed, student_allowed
from aqp.mentor_groups import relation_allowed
from aqp.research_outputs import current_participant
from aqp.store import audit, connection


def fit_factors(points: list[tuple[float, float, float]]) -> dict[str, Any]:
    if len(points) < 5:
        return {"notice": "完整样本不足 5 人，无法估计两项因素。"}
    observations = np.asarray(points, dtype=float)
    design = np.column_stack((np.ones(len(points)), observations[:, :2]))
    target = observations[:, 2]
    coefficients, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
    if rank < design.shape[1] or np.ptp(target) == 0:
        return {"notice": "分数没有变化，或两项因素无法独立估计。"}
    degrees = len(points) - design.shape[1]
    residuals = target - design @ coefficients
    residual_variance = float(residuals @ residuals) / degrees
    errors = np.sqrt(residual_variance * np.diag(np.linalg.pinv(design.T @ design)))
    critical = float(t.ppf(0.975, degrees))
    rows = []
    for label, coefficient, error in zip(
        ("选题成绩", "中期成绩"), coefficients[1:], errors[1:], strict=True
    ):
        estimate, se = float(coefficient), float(error)
        # A perfect numerical fit does not provide a meaningful sampling error.
        infer = se > 1e-10
        rows.append(
            {
                "factor": label,
                "coefficient": estimate,
                "interval": [estimate - critical * se, estimate + critical * se]
                if infer
                else None,
                "p_value": float(2 * t.sf(abs(estimate / se), degrees))
                if infer
                else None,
            }
        )
    return {"factors": rows}


def cultivation_factors(
    db: sqlite3.Connection, aid: int, college: str, major: str, entry_year: int,
    load_snapshot: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    if not all(
        allowed(db, aid, category, op, college, major)
        for category in ("basic", "topic", "midterm", "talent_evaluation")
        for op in ("view", "analyze")
    ):
        raise HTTPException(
            403, "需具有该范围的档案、选题、中期和模拟评价查看及分析权限"
        )
    students = {
        row["id"]
        for row in agent_scope_students(db, aid, college, major)
        if row["entry_year"] == entry_year
    }
    grades: dict[tuple[int, str], float] = {}
    for row in db.execute(
        "SELECT student_id,category,payload FROM milestone_records WHERE active=1 ORDER BY id DESC"
    ):
        key = (row["student_id"], row["category"])
        if key[0] not in students or key in grades:
            continue
        payload = json.loads(row["payload"])
        if (payload.get("所属学院"), payload.get("专业")) != (
            college,
            major,
        ) or payload.get("评分制度") != "百分制":
            continue
        try:
            value = float(payload.get("原始成绩") or "")
        except ValueError:
            continue
        if 0 <= value <= 100:
            grades[key] = value
    points = []
    rules = set()
    for student_id in students:
        topic = grades.get((student_id, "topic"))
        midterm = grades.get((student_id, "midterm"))
        if topic is None or midterm is None:
            continue
        latest = db.execute(
            "SELECT id FROM evaluation_snapshots WHERE student_id=? ORDER BY id DESC LIMIT 1",
            (student_id,),
        ).fetchone()
        if latest is None:
            continue
        try:
            score = load_snapshot(db, aid, latest["id"])
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        if (
            score["stale"]
            or not score["rule_currently_enabled"]
            or score["total"] is None
        ):
            continue
        rules.add(score["rule_id"])
        points.append((topic, midterm, score["total"]))
    outcome = (
        {"notice": "样本含不同评分规则版本，无法合并比较。"}
        if len(rules) > 1
        else fit_factors(points)
    )
    audit(db, aid, "cultivation.factors", "simulation")
    return {
        **outcome,
        "sample_size": len(points),
        "excluded": len(students) - len(points),
    }


def student_signals(db: sqlite3.Connection, aid: int, student_id: int) -> dict[str, Any]:
    student = db.execute(
        "SELECT * FROM students WHERE id=? AND active=1", (student_id,)
    ).fetchone()
    if (
        student is None
        or not student_allowed(db, aid, student_id)
        or not allowed(
            db,
            aid,
            "basic",
            "view",
            student["college"],
            student["major"],
        )
    ):
        raise HTTPException(403, "当前无权查看该学生")
    audit(db, aid, "cultivation.signals", str(student_id))
    payload = json.loads(student["payload"])
    mobility = payload.get("学籍异动类型")
    result: dict[str, Any] = {
        "mobility": {"type": mobility, "date": payload.get("学籍异动时间")}
        if mobility
        else None,
        "peer_outputs": None,
    }
    if all(
        allowed(db, aid, "papers", op, student["college"], student["major"])
        for op in ("view", "analyze")
    ) and (batch := payload.get("盲审送审批次")):
        due_text = payload.get("盲审论文应交日期") or ""
        actual_text = payload.get("盲审论文实际提交日期") or ""
        submission = payload.get("盲审论文提交状态")
        status = "待核查"
        try:
            due = date.fromisoformat(due_text[:10])
            if actual_text and submission != "未提交":
                actual = date.fromisoformat(actual_text[:10])
                status = "超期提交" if actual > due else "按期提交"
            elif not actual_text and submission == "未提交":
                status = "未提交且已逾期" if date.today() > due else "未提交，尚未逾期"
        except ValueError:
            pass
        result["blind_review"] = {"batch": batch, "due": due_text[:10], "status": status}
    if not all(
        allowed(db, aid, category, op, student["college"], student["major"])
        for category in OUTPUT_TABLES
        for op in ("view", "analyze")
    ):
        result["notice"] = "成果对比需要查看和分析四类成果的权限。"
        return result
    cohort = {
        row["id"]
        for row in agent_scope_students(
            db, aid, student["college"], student["major"]
        )
        if row["entry_year"] == student["entry_year"]
    }
    peers = cohort - {student_id}
    if len(peers) < 3:
        result["notice"] = "可比的同届同专业学生不足 3 人。"
        return result
    counts: Counter[int] = Counter()
    sources = []
    any_outputs = False
    for category, table in OUTPUT_TABLES.items():
        for row in db.execute(
            f"SELECT id,payload FROM {table}_outputs WHERE active=1"
        ):
            matched = set()
            for participant in json.loads(row["payload"])["participants"]:
                visible, linked = current_participant(
                    db, aid, category, "view", participant
                )
                if (
                    visible
                    and linked is not None
                    and linked["id"] in cohort
                    and current_participant(
                        db,
                        aid,
                        category,
                        "analyze",
                        participant,
                    )[0]
                ):
                    matched.add(linked["id"])
            any_outputs = any_outputs or bool(matched)
            counts.update(matched)
            if student_id in matched:
                endpoint = (
                    "research-outputs"
                    if category == "research_papers"
                    else category
                )
                sources.append(f"/api/{endpoint}/{row['id']}/history")
    if not any_outputs:
        result["notice"] = "当前同届同专业范围暂无可用于比较的有效成果。"
        return result
    benchmark = median(counts[peer] for peer in peers)
    result["peer_outputs"] = {
        "count": counts[student_id],
        "peer_median": benchmark,
        "peer_count": len(peers),
        "below": counts[student_id] < benchmark,
        "sources": sources,
    }
    return result


def course_control_chart(
    db: sqlite3.Connection, aid: int, college: str, major: str
) -> dict[str, Any]:
    """课程学期均分控制图：按学生均分计算 x̄±3σ，越限仅作统计信号。"""
    if not all(
        allowed(db, aid, "courses", op, college, major) for op in ("view", "analyze")
    ):
        raise HTTPException(403, "需具有该范围的课程查看及分析权限")
    students = {
        row["id"]: row["research_id"]
        for row in agent_scope_students(db, aid, college, major)
    }
    scores: dict[tuple[int, str, str], list[float]] = defaultdict(list)
    skipped = 0
    for row in db.execute(
        "SELECT student_id,payload FROM course_records WHERE state='linked' AND active=1"
    ):
        if row["student_id"] not in students:
            continue
        payload = json.loads(row["payload"])
        if payload.get("评分制度") != "百分制":
            continue
        try:
            value = float(payload.get("原始成绩") or "")
        except ValueError:
            skipped += 1
            continue
        if not 0 <= value <= 100:
            continue
        scores[
            (row["student_id"], payload.get("课程编号", ""), payload.get("修读学期", ""))
        ].append(value)
    per_course: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for (student_id, code, term), values in scores.items():
        per_course[(code, term)].append((student_id, mean(values)))
    items = []
    insufficient = 0
    for (code, term), entries in sorted(per_course.items()):
        if len(entries) < 5:
            insufficient += 1
            continue
        values = [value for _, value in entries]
        center = mean(values)
        deviation = pstdev(values)
        lower, upper = center - 3 * deviation, center + 3 * deviation
        below = sorted(students[sid] for sid, value in entries if value < lower)
        above = sorted(students[sid] for sid, value in entries if value > upper)
        if below or above:
            items.append(
                {
                    "course_code": code,
                    "term": term,
                    "students": len(entries),
                    "mean": round(center, 2),
                    "limits": [round(lower, 2), round(upper, 2)],
                    "below": below,
                    "above": above,
                }
            )
    audit(db, aid, "cultivation.control_chart", "scoped")
    return {
        "items": items,
        "courses_evaluated": len(per_course),
        "insufficient_baseline": insufficient,
        "skipped_non_numeric": skipped,
        "note": "控制限为均值±3倍标准差的统计信号，不作优劣判定；不足5人的课程不计算。",
    }


def milestone_alerts(
    db: sqlite3.Connection, aid: int, college: str, major: str
) -> dict[str, Any]:
    """选题与中期的明确超期、未完成逾期和业务未通过清单，口径与分析快照一致。"""
    if not all(
        allowed(db, aid, category, op, college, major)
        for category in ("topic", "midterm")
        for op in ("view", "analyze")
    ):
        raise HTTPException(403, "需具有该范围的选题与中期查看及分析权限")
    students = {
        row["id"]: row["research_id"]
        for row in agent_scope_students(db, aid, college, major)
    }
    today = date.today()
    latest: set[tuple[int, str]] = set()
    summary = {
        category: {
            "explicit_overdue": 0,
            "pending_overdue": 0,
            "failed": 0,
            "unknown_status": 0,
            "records": 0,
        }
        for category in ("topic", "midterm")
    }
    alerts: list[dict[str, Any]] = []
    for row in db.execute(
        "SELECT id,student_id,category,payload FROM milestone_records WHERE active=1 ORDER BY id DESC"
    ):
        if row["student_id"] not in students or row["category"] not in summary:
            continue
        payload = json.loads(row["payload"])
        if (payload.get("所属学院"), payload.get("专业")) != (college, major):
            continue
        key = (row["student_id"], row["category"])
        if key in latest:
            continue
        latest.add(key)
        counts = summary[row["category"]]
        counts["records"] += 1
        try:
            planned = (
                date.fromisoformat(str(payload.get("计划日期") or ""))
                if payload.get("计划日期")
                else None
            )
        except ValueError:
            planned = None
        actual = None
        if payload.get("实际日期"):
            try:
                actual = date.fromisoformat(str(payload.get("实际日期")))
            except ValueError:
                actual = None
        failed = payload.get("业务通过结果") == "不通过"
        if failed:
            counts["failed"] += 1
            alerts.append(
                {
                    "research_id": students[row["student_id"]],
                    "student_id": row["student_id"],
                    "category": row["category"],
                    "kind": "业务未通过",
                }
            )
        if actual is not None and planned is not None and actual > planned:
            counts["explicit_overdue"] += 1
            alerts.append(
                {
                    "research_id": students[row["student_id"]],
                    "student_id": row["student_id"],
                    "category": row["category"],
                    "kind": "明确超期",
                    "plan": planned.isoformat(),
                    "actual": actual.isoformat(),
                }
            )
        elif (
            actual is None
            and payload.get("完成状态") == "未完成"
            and planned is not None
            and today > planned
        ):
            counts["pending_overdue"] += 1
            alerts.append(
                {
                    "research_id": students[row["student_id"]],
                    "student_id": row["student_id"],
                    "category": row["category"],
                    "kind": "未完成且已逾期",
                    "plan": planned.isoformat(),
                }
            )
        elif actual is None and payload.get("完成状态") != "未完成":
            counts["unknown_status"] += 1
    audit(db, aid, "cultivation.milestone_alerts", "scoped")
    return {
        "summary": summary,
        "alerts": alerts[:20],
        "alerts_truncated": len(alerts) > 20,
        "note": "超期口径与分析快照一致：双日期明确超期或未完成且已过计划日期；无日期依据的只计入未知，不推断。",
    }


def mentor_course_comparison(
    db: sqlite3.Connection, actor: int, student_id: int,
) -> dict[str, Any]:
    student = db.execute("SELECT college,major FROM students WHERE id=? AND active=1", (student_id,)).fetchone()
    if student is None or not student_allowed(db, actor, student_id) or not all(
        allowed(db, actor, category, operation, student["college"], student["major"])
        for category, operation in (("basic", "view"), ("courses", "view"), ("courses", "analyze"))
    ):
        raise HTTPException(403, "当前无权查看该学生的课程对比")
    today = date.today().isoformat()
    relations = db.execute(
        "SELECT * FROM mentor_group_relations WHERE start_date<=? AND (end_date IS NULL OR end_date>=?)",
        (today, today),
    ).fetchall()
    keys = {
        (row["mentor_id"], row["group_id"]) for row in relations
        if row["student_id"] == student_id and all(
            relation_allowed(db, actor, op, row) for op in ("view", "analyze")
        )
    }
    peers = {
        row["student_id"] for row in relations
        if row["student_id"] != student_id and (row["mentor_id"], row["group_id"]) in keys
        and all(relation_allowed(db, actor, op, row) for op in ("view", "analyze"))
    }
    rows: dict[tuple[str, str, str], dict[int, list[tuple[int, float]]]] = defaultdict(lambda: defaultdict(list))
    for record in db.execute(
        """SELECT c.*, s.college, s.major FROM course_records c JOIN students s ON s.id=c.student_id
        WHERE c.active=1 AND c.state='linked' AND s.active=1 AND json_extract(c.payload,'$.评分制度')='百分制'"""
    ):
        sid = record["student_id"]
        if sid != student_id and sid not in peers:
            continue
        payload = json.loads(record["payload"])
        source = (payload.get("所属学院", payload.get("学院")), payload.get("专业"))
        if not all(isinstance(part, str) and part for part in source) or not all(
            allowed(db, actor, "courses", op, college, major)
            for college, major in (source, (record["college"], record["major"]))
            for op in ("view", "analyze")
        ):
            continue
        try:
            score = float(payload.get("原始成绩") or "")
        except ValueError:
            continue
        if 0 <= score <= 100:
            rows[(source[0], record["course_code"], record["term"])][sid].append((record["id"], score))
    items = []
    for (college, code, term), grades in sorted(rows.items()):
        own = grades.get(student_id)
        if not own:
            continue
        peer_scores = [mean(score for _, score in values) for sid, values in grades.items() if sid != student_id]
        items.append({
            "college": college, "course_code": code, "term": term,
            "score": mean(score for _, score in own), "peer_count": len(peer_scores),
            "peer_mean": mean(peer_scores) if len(peer_scores) >= 3 else None,
            "record_ids": [record_id for record_id, _ in own],
        })
    audit(db, actor, "cultivation.mentor_course_comparison", str(student_id))
    return {"items": items, "as_of": today, "has_group": bool(keys)}


def register_cultivation_models(
    app: FastAPI,
    path: Path,
    current: Callable[..., Any],
    load_snapshot: Callable[..., dict[str, Any]],
) -> None:
    @app.get("/api/cultivation/factors")
    def factors(
        request: Request,
        college: str = Query(min_length=1),
        major: str = Query(min_length=1),
        entry_year: int = Query(ge=1900, le=2100),
    ) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return cultivation_factors(db, actor["id"], college, major, entry_year, load_snapshot)

    @app.get("/api/cultivation/students/{student_id}/signals")
    def signals(request: Request, student_id: int) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return student_signals(db, actor["id"], student_id)

    @app.get("/api/cultivation/students/{student_id}/mentor-course-comparison")
    def mentor_courses(request: Request, student_id: int) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return mentor_course_comparison(db, actor["id"], student_id)

    @app.get("/api/cultivation/course-control-chart")
    def control_chart(
        request: Request,
        college: str = Query(min_length=1),
        major: str = Query(min_length=1),
    ) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return course_control_chart(db, actor["id"], college, major)

    @app.get("/api/cultivation/milestone-alerts")
    def alerts(
        request: Request,
        college: str = Query(min_length=1),
        major: str = Query(min_length=1),
    ) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return milestone_alerts(db, actor["id"], college, major)
