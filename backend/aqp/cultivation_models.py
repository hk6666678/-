import json
import sqlite3
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from scipy.stats import t  # type: ignore[import-untyped]

from aqp.agent import OUTPUT_TABLES, agent_scope_students
from aqp.authorization import allowed, student_allowed
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
    payload = json.loads(student["payload"])
    mobility = payload.get("学籍异动类型")
    result: dict[str, Any] = {
        "mobility": {"type": mobility, "date": payload.get("学籍异动时间")}
        if mobility
        else None,
        "peer_outputs": None,
    }
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
    audit(db, aid, "cultivation.signals", str(student_id))
    return result


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
