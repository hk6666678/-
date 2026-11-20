import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from statistics import StatisticsError, correlation
from typing import Any, Literal

from fastapi import HTTPException

from aqp.authorization import allowed, student_allowed
from aqp.research_outputs import current_participant

OutputCategory = Literal["research_papers", "patents", "awards", "conferences"]


def actual_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def topic_correlation(
    db: sqlite3.Connection,
    actor: int,
    college: str,
    major: str,
    entry_year: int,
    category: OutputCategory,
) -> dict[str, Any]:
    if not all(
        allowed(db, actor, source, operation, college, major)
        for source in ("basic", "topic", category)
        for operation in ("view", "analyze")
    ):
        raise HTTPException(403, "需具有该范围基础档案、选题及所选成果的查看与分析权限")
    students = {
        row["id"]: row["research_id"]
        for row in db.execute(
            "SELECT id,research_id FROM students WHERE active=1 AND college=? AND major=? AND entry_year=?",
            (college, major, entry_year),
        )
        if student_allowed(db, actor, row["id"])
    }
    topics: dict[int, list[tuple[date, int, dict[str, Any]]]] = defaultdict(list)
    for row in db.execute(
        "SELECT id,student_id,payload FROM milestone_records WHERE active=1 AND category='topic'"
    ):
        if row["student_id"] not in students:
            continue
        payload = json.loads(row["payload"])
        if (payload.get("所属学院"), payload.get("专业")) != (college, major):
            continue
        actual = actual_date(payload.get("实际日期") or "")
        if actual is not None:
            topics[row["student_id"]].append((actual, row["id"], payload))

    table, field = {
        "research_papers": ("research", "发表年份"),
        "patents": ("patents", "申请日期"),
        "awards": ("awards", "获奖年份"),
        "conferences": ("conferences", "会议日期"),
    }[category]
    outputs: dict[int, dict[int, str]] = defaultdict(dict)
    for row in db.execute(f"SELECT id,payload FROM {table}_outputs WHERE active=1"):
        payload = json.loads(row["payload"])
        raw = str(payload.get("details", {}).get(field) or "")
        for participant in payload["participants"]:
            viewable, student = current_participant(
                db, actor, category, "view", participant
            )
            if (
                viewable
                and student is not None
                and student["id"] in students
                and current_participant(db, actor, category, "analyze", participant)[0]
            ):
                outputs[student["id"]][row["id"]] = raw

    points = []
    excluded: Counter[str] = Counter()
    uncertain_count = 0
    for sid, research_id in students.items():
        if not topics[sid]:
            excluded["缺少有效选题实际日期"] += 1
            continue
        topic_date, topic_id, topic = min(topics[sid], key=lambda item: item[:2])
        try:
            score = float(topic.get("原始成绩") or "")
        except ValueError:
            score = -1
        if topic.get("评分制度") != "百分制" or not 0 <= score <= 100:
            excluded["首次选题缺有效百分制成绩"] += 1
            continue
        after = []
        for output_id, raw in outputs[sid].items():
            full_date = actual_date(raw)
            if full_date is not None:
                if full_date > topic_date:
                    after.append(output_id)
            elif re.fullmatch(r"[1-9]\d{3}", raw) and int(raw) != topic_date.year:
                if int(raw) > topic_date.year:
                    after.append(output_id)
            else:
                uncertain_count += 1
        points.append(
            {
                "research_id": research_id,
                "score": score,
                "output_count": len(after),
                "topic_record_id": topic_id,
                "output_ids": after,
            }
        )
    coefficient = None
    if len(points) >= 3:
        try:
            coefficient = correlation(
                [p["score"] for p in points], [p["output_count"] for p in points]
            )
        except StatisticsError:
            pass
    return {
        "points": points,
        "cohort_count": len(students),
        "excluded": dict(excluded),
        "uncertain_participations": uncertain_count,
        "pearson_r": coefficient,
    }
