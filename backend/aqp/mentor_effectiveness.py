"""Descriptive effectiveness measures over currently authorized evidence."""

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from datetime import date
from statistics import mean, pvariance
from typing import Any

from fastapi import HTTPException

from aqp.mentor_groups import relation_allowed
from aqp.research_outputs import current_participant


def effectiveness(
    db: sqlite3.Connection,
    actor: int,
    as_of: date,
    key: str,
    selected: int,
    load_snapshot: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    table = "mentor_directory" if key == "mentor_id" else "research_groups"
    unit = db.execute(f"SELECT college FROM {table} WHERE id=?", (selected,)).fetchone()
    if unit is None:
        return {}
    ids = {
        row["id"]
        for row in db.execute(
            f"SELECT id FROM {table} WHERE college=?", (unit["college"],)
        )
    }
    current_students: dict[int, set[int]] = defaultdict(set)
    periods: dict[int, list[tuple[int, str, str]]] = defaultdict(list)
    for row in db.execute("SELECT * FROM mentor_group_relations"):
        if row[key] not in ids or row["start_date"] > as_of.isoformat():
            continue
        if not all(relation_allowed(db, actor, op, row) for op in ("view", "analyze")):
            continue
        end = row["end_date"] or "9999-12-31"
        periods[row["student_id"]].append((row[key], row["start_date"], end))
        if as_of.isoformat() <= end:
            current_students[row[key]].add(row["student_id"])
    if not current_students.get(selected):
        return {}

    scores: dict[int, tuple[int, int, float]] = {}
    for student_id in set().union(*current_students.values()):
        latest = db.execute(
            "SELECT id,rule_id FROM evaluation_snapshots WHERE student_id=? AND date(created_at,'unixepoch','+8 hours')<=? ORDER BY created_at DESC,id DESC LIMIT 1",
            (student_id, as_of.isoformat()),
        ).fetchone()
        if latest is None:
            continue
        try:
            snapshot = load_snapshot(db, actor, latest["id"])
        except HTTPException as exc:
            if exc.status_code == 403:
                continue
            raise
        if (
            snapshot["mode"] == "simulation"
            and not snapshot["stale"]
            and snapshot["rule_currently_enabled"]
            and snapshot["total"] is not None
        ):
            year = db.execute(
                "SELECT entry_year FROM students WHERE id=?", (student_id,)
            ).fetchone()["entry_year"]
            scores[student_id] = (latest["rule_id"], year, snapshot["total"])

    years = [as_of.year - 3, as_of.year - 2, as_of.year - 1]
    annual: dict[tuple[int, int], set[tuple[str, int]]] = defaultdict(set)
    coverage = {
        (unit_id, year)
        for relations in periods.values()
        for unit_id, start, end in relations
        for year in years
        if start <= f"{year}-12-31" and end >= f"{year}-01-01"
    }
    for category, output_table, field in (
        ("research_papers", "research", "发表年份"),
        ("patents", "patents", "申请日期"),
        ("awards", "awards", "获奖年份"),
        ("conferences", "conferences", "会议日期"),
    ):
        for row in db.execute(
            f"SELECT id,payload FROM {output_table}_outputs WHERE active=1"
        ):
            payload = json.loads(row["payload"])
            raw = str(payload.get("details", {}).get(field, ""))
            if raw[:4] not in {str(year) for year in years}:
                continue
            year = int(raw[:4])
            earliest, latest_date = (
                (raw, raw) if len(raw) == 10 else (f"{year}-01-01", f"{year}-12-31")
            )
            for participant in payload["participants"]:
                permitted, student = current_participant(
                    db, actor, category, "view", participant
                )
                if not permitted or student is None or student["id"] not in periods:
                    continue
                if not current_participant(db, actor, category, "analyze", participant)[
                    0
                ]:
                    continue
                for unit_id, start, end in periods[student["id"]]:
                    if start <= earliest and latest_date <= end:
                        annual[unit_id, year].add((category, row["id"]))

    metrics: dict[int, dict[str, Any]] = {}
    for unit_id, students in current_students.items():
        usable = [scores[sid] for sid in students if sid in scores]
        same_rule = len({rule for rule, _, _ in usable}) == 1
        by_cohort: dict[int, list[float]] = defaultdict(list)
        for _, cohort, score in usable:
            by_cohort[cohort].append(score)
        counts = [len(annual[unit_id, year]) for year in years]
        metrics[unit_id] = {
            "scored": len(usable),
            "students": len(students),
            "rule_id": usable[0][0] if same_rule else None,
            "rate": 100 * sum(score >= 85 for _, _, score in usable) / len(usable)
            if same_rule
            else None,
            "acceleration": counts[2] - 2 * counts[1] + counts[0]
            if all((unit_id, year) in coverage for year in years)
            else None,
            "stability": pvariance(mean(values) for values in by_cohort.values())
            if same_rule and len(by_cohort) >= 2
            else None,
            "annual_counts": dict(zip(years, counts, strict=True)),
            "cohorts": len(by_cohort),
        }
    result = metrics[selected]
    benchmark = {}
    for metric in ("rate", "acceleration", "stability"):
        peers = [
            row[metric]
            for unit_id, row in metrics.items()
            if unit_id != selected
            and row[metric] is not None
            and (metric == "acceleration" or row["rule_id"] == result["rule_id"])
        ]
        benchmark[metric] = {
            "mean": mean(peers) if peers else None,
            "count": len(peers),
        }
        value = result[metric]
        if peers and value is not None:
            benchmark[metric]["rank"] = 1 + sum(
                peer < value if metric == "stability" else peer > value for peer in peers
            )
    return {**result, "benchmark": benchmark}
