"""Three-level reports (student, mentor group, college) with current
authority only: unauthorized sections are labelled, missing data is never
filled with zeros, and every number keeps its record/version evidence."""

import json
import re
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from aqp.analysis import outcome
from aqp.authorization import allowed, student_allowed
from aqp.exports import excel_report
from aqp.mentor_groups import group_facts
from aqp.research_outputs import current_participant
from aqp.store import audit, connection

OUTPUT_CATEGORY_TABLE = [
    ("research_papers", "research"),
    ("patents", "patents"),
    ("awards", "awards"),
    ("conferences", "conferences"),
]
YEAR_KEY = {
    "patents": "申请日期",
    "awards": "获奖年份",
    "conferences": "会议日期",
    "research_papers": "发表年份",
}


def register_reports(app: FastAPI, path: Path, current: Callable[..., Any]) -> None:
    def deny(db: Any, actor: int, target: str, message: str) -> None:
        audit(db, actor, "reports.access", target, "denied")
        db.commit()
        raise HTTPException(403, message)

    def section_allowed(
        db: Any, actor: int, category: str, college: str, major: str
    ) -> bool:
        return all(
            allowed(db, actor, category, op, college, major)
            for op in ("view", "analyze")
        )

    def unauthorized() -> dict[str, Any]:
        return {"status": "unauthorized", "reason": "当前授权不足，该段未纳入"}

    def missing(reason: str) -> dict[str, Any]:
        return {"status": "missing", "reason": reason}

    def student_outputs(
        db: Any, actor: int, student: Any
    ) -> dict[str, Any]:
        sections: dict[str, Any] = {}
        for category, table in OUTPUT_CATEGORY_TABLE:
            if not section_allowed(
                db, actor, category, student["college"], student["major"]
            ):
                sections[category] = unauthorized()
                continue
            items: list[dict[str, Any]] = []
            hidden = False
            for output in db.execute(
                f"SELECT * FROM {table}_outputs WHERE active=1 ORDER BY id"
            ):
                payload = json.loads(output["payload"])
                matches = [
                    p
                    for p in payload["participants"]
                    if p["student_number"] == student["student_number"]
                ]
                if not matches:
                    continue
                if not all(
                    current_participant(db, actor, category, op, participant)[0]
                    for participant in matches
                    for op in ("view", "analyze")
                ):
                    # Strict section semantics: one out-of-scope record hides
                    # the whole category count instead of leaking a partial one.
                    hidden = True
                    break
                raw = payload.get("details", {}).get(YEAR_KEY[category]) or payload.get(
                    YEAR_KEY[category], ""
                )
                items.append(
                    {
                        "record_id": output["id"],
                        "business_key": output["business_key"],
                        "title": payload.get("title"),
                        "version": output["version"],
                        "year": (
                            str(raw)[:4]
                            if re.fullmatch(r"\d{4}(?:-\d{2}-\d{2})?", str(raw))
                            else None
                        ),
                    }
                )
            if hidden:
                sections[category] = unauthorized()
            elif items:
                sections[category] = {
                    "status": "ok",
                    "count": len(items),
                    "items": items,
                }
            else:
                sections[category] = missing("尚无可查证成果记录")
        return sections

    def student_course_section(db: Any, actor: int, student: Any) -> dict[str, Any]:
        if not section_allowed(
            db, actor, "courses", student["college"], student["major"]
        ):
            return unauthorized()
        rules = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM pass_rules WHERE college=? AND major=? AND category='courses' ORDER BY id",
                (student["college"], student["major"]),
            )
        ]
        evidence = []
        statuses = []
        for row in db.execute(
            "SELECT * FROM course_records WHERE student_id=? AND state='linked' AND active=1 ORDER BY id",
            (student["id"],),
        ):
            payload = json.loads(row["payload"])
            if (
                payload.get("学院") != student["college"]
                or payload.get("专业") != student["major"]
            ):
                return unauthorized()
            status, pass_rule = outcome(payload, rules)
            statuses.append(status)
            evidence.append(
                {
                    "record_id": row["id"],
                    "course_code": row["course_code"],
                    "term": row["term"],
                    "attempt": row["attempt"],
                    "version": row["version"],
                    "status": status,
                    "pass_rule_id": pass_rule,
                }
            )
        if not evidence:
            return missing("尚无已关联课程记录")
        unknown = statuses.count("未知")
        return {
            "status": "ok",
            "total": len(statuses),
            "passed": statuses.count("通过"),
            "failed": statuses.count("不通过"),
            "unknown": unknown,
            "pass_ratio": None if unknown else statuses.count("通过") / len(statuses),
            "pass_rule_version": max((r["version"] for r in rules), default=None),
            "evidence": evidence,
        }

    def student_milestone_sections(
        db: Any, actor: int, student: Any
    ) -> dict[str, Any]:
        sections: dict[str, Any] = {}
        for category in ("topic", "midterm"):
            if not section_allowed(
                db, actor, category, student["college"], student["major"]
            ):
                sections[category] = unauthorized()
                continue
            items: list[dict[str, Any]] = []
            hidden = False
            for row in db.execute(
                "SELECT * FROM milestone_records WHERE student_id=? AND active=1 ORDER BY assessment_batch",
                (student["id"],),
            ):
                if row["category"] != category:
                    continue
                payload = json.loads(row["payload"])
                if (
                    payload.get("学院") != student["college"]
                    or payload.get("专业") != student["major"]
                ):
                    hidden = True
                    break
                items.append(
                    {
                        "record_id": row["id"],
                        "batch": row["assessment_batch"],
                        "version": row["version"],
                        "result": payload.get("业务通过结果", "未知"),
                    }
                )
            if hidden:
                sections[category] = unauthorized()
            elif items:
                sections[category] = {
                    "status": "ok",
                    "count": len(items),
                    "items": items,
                }
            else:
                sections[category] = missing("尚无该类别里程碑记录")
        return sections

    def student_evaluation_section(
        db: Any, actor: int, student: Any
    ) -> dict[str, Any]:
        if not section_allowed(
            db, actor, "talent_evaluation", student["college"], student["major"]
        ):
            return unauthorized()
        latest = db.execute(
            "SELECT * FROM evaluation_snapshots WHERE student_id=? ORDER BY id DESC LIMIT 1",
            (student["id"],),
        ).fetchone()
        if latest is None:
            return missing("尚无评分快照")
        result = json.loads(latest["result"])
        return {
            "status": "ok",
            "snapshot_id": latest["id"],
            "rule_id": result["rule_id"],
            "rule_version": result["rule_version"],
            "mode": result["mode"],
            "total": result["total"],
            "as_of": result["as_of"],
            "notice": "评分明细与证据见人才指标模拟评价；模拟演示，不构成正式人才识别",
        }

    def student_report(db: Any, actor: int, student_id: int) -> dict[str, Any]:
        student = db.execute(
            "SELECT * FROM students WHERE id=? AND active=1", (student_id,)
        ).fetchone()
        if student is None or not student_allowed(db, actor, student_id):
            deny(db, actor, str(student_id), "学生当前范围不可访问")
        if not allowed(
            db, actor, "basic", "view", student["college"], student["major"]
        ):
            deny(db, actor, str(student_id), "基础档案查看授权不足")
        identity = allowed(
            db, actor, "basic", "identity", student["college"], student["major"]
        )
        return {
            "level": "student",
            "generated_at": int(time.time()),
            "student": {
                "id": student["id"],
                "research_id": student["research_id"],
                "student_number": student["student_number"] if identity else None,
                "name": student["name"] if identity else None,
                "college": student["college"],
                "major": student["major"],
                "level": student["level"],
                "entry_year": student["entry_year"],
                "identity_masked": not identity,
            },
            "sections": {
                "courses": student_course_section(db, actor, student),
                "milestones": student_milestone_sections(db, actor, student),
                **student_outputs(db, actor, student),
                "evaluation": student_evaluation_section(db, actor, student),
            },
            "basis": "全部段落按读取时当前权限现算；无授权段落仅标注不计数，缺数据标注缺失不填零；每项数值保留记录与版本依据。",
        }

    def group_report(
        db: Any,
        actor: int,
        as_of: date,
        mentor_id: int | None,
        group_id: int | None,
    ) -> dict[str, Any]:
        return {
            "level": "mentor_group",
            "generated_at": int(time.time()),
            "mentor_id": mentor_id,
            "group_id": group_id,
            **group_facts(db, actor, as_of.isoformat(), mentor_id, group_id),
        }

    def college_report(
        db: Any, actor: int, college: str, major: str
    ) -> dict[str, Any]:
        if not allowed(db, actor, "basic", "view", college, major):
            deny(db, actor, f"{college}/{major}", "基础档案查看授权不足")
        sections: dict[str, Any] = {}
        students = [
            row
            for row in db.execute(
                "SELECT * FROM students WHERE active=1 AND college=? AND major=? ORDER BY id",
                (college, major),
            )
            if student_allowed(db, actor, row["id"])
        ]
        if students:
            sections["students"] = {
                "status": "ok",
                "count": len(students),
                "note": "仅统计当前授权可见的在册学生",
            }
        else:
            sections["students"] = missing("当前授权范围内无在册学生")
        for category, table in OUTPUT_CATEGORY_TABLE:
            if not section_allowed(db, actor, category, college, major):
                sections[category] = unauthorized()
                continue
            distinct: set[int] = set()
            participation = 0
            hidden = False
            for output in db.execute(
                f"SELECT * FROM {table}_outputs WHERE active=1 ORDER BY id"
            ):
                payload = json.loads(output["payload"])
                matched = [
                    p
                    for p in payload["participants"]
                    if p["student_number"]
                    in {s["student_number"] for s in students}
                ]
                if not matched:
                    continue
                if not all(
                    current_participant(db, actor, category, op, participant)[0]
                    for participant in matched
                    for op in ("view", "analyze")
                ):
                    hidden = True
                    break
                distinct.add(output["id"])
                participation += len(matched)
            if hidden:
                sections[category] = unauthorized()
            elif distinct:
                sections[category] = {
                    "status": "ok",
                    "distinct_outputs": len(distinct),
                    "personal_participations": participation,
                }
            else:
                sections[category] = missing("尚无可查证成果记录")
        if section_allowed(db, actor, "courses", college, major):
            rules = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM pass_rules WHERE college=? AND major=? AND category='courses' ORDER BY id",
                    (college, major),
                )
            ]
            statuses = []
            stopped = False
            for student in students:
                for row in db.execute(
                    "SELECT * FROM course_records WHERE student_id=? AND state='linked' AND active=1",
                    (student["id"],),
                ):
                    payload = json.loads(row["payload"])
                    if (
                        payload.get("学院") != college
                        or payload.get("专业") != major
                    ):
                        stopped = True
                        break
                    status, _ = outcome(payload, rules)
                    statuses.append(status)
                if stopped:
                    break
            if stopped:
                sections["courses"] = unauthorized()
            elif statuses:
                unknown = statuses.count("未知")
                sections["courses"] = {
                    "status": "ok",
                    "records": len(statuses),
                    "passed": statuses.count("通过"),
                    "unknown": unknown,
                    "pass_ratio": (
                        None if unknown else statuses.count("通过") / len(statuses)
                    ),
                    "pass_rule_version": max(
                        (r["version"] for r in rules), default=None
                    ),
                }
            else:
                sections["courses"] = missing("尚无已关联课程记录")
        else:
            sections["courses"] = unauthorized()
        if all(
            allowed(db, actor, "mentor_groups", op, college, major)
            for op in ("view", "analyze")
        ):
            active_relations = []
            today = time.strftime("%Y-%m-%d")
            for row in db.execute(
                "SELECT * FROM mentor_group_relations ORDER BY id"
            ):
                student = db.execute(
                    "SELECT * FROM students WHERE id=? AND active=1",
                    (row["student_id"],),
                ).fetchone()
                if (
                    student is None
                    or student["college"] != college
                    or student["major"] != major
                    or not student_allowed(db, actor, student["id"])
                    or not (
                        row["start_date"]
                        <= today
                        <= (row["end_date"] or "9999-12-31")
                    )
                ):
                    continue
                mentor = db.execute(
                    "SELECT * FROM mentor_directory WHERE id=?", (row["mentor_id"],)
                ).fetchone()
                group = db.execute(
                    "SELECT * FROM research_groups WHERE id=?", (row["group_id"],)
                ).fetchone()
                if mentor is None or group is None:
                    continue
                if not all(
                    allowed(db, actor, "mentor_groups", op, scope["college"], scope["major"])
                    for op in ("view", "analyze")
                    for scope in (student, mentor, group)
                ):
                    continue
                active_relations.append(row["id"])
            sections["mentor_groups"] = {
                "status": "ok",
                "active_relations": len(active_relations),
                "relation_ids": active_relations,
                "note": "仅统计当前授权与导师显式绑定范围内、指定学院专业的当前有效关系",
            }
        else:
            sections["mentor_groups"] = unauthorized()
        return {
            "level": "college",
            "generated_at": int(time.time()),
            "scope": {"college": college, "major": major},
            "sections": sections,
            "basis": "学院学科聚合按读取时当前权限现算；成果去重数与个人参与人次分别口径；缺数据标注缺失不填零；无授权段落仅标注。",
        }

    def require_section_exports(
        db: Any,
        actor: int,
        sections: dict[str, Any],
        college: str,
        major: str,
    ) -> None:
        """Downloading a report needs the export grant for every category that
        actually contributed an ok section; unauthorized/missing sections stay
        labelled and never widen access."""
        if not allowed(db, actor, "basic", "export", college, major):
            deny(db, actor, "export", "报告导出授权不足")
        required = {
            "courses": "courses",
            "research_papers": "research_papers",
            "patents": "patents",
            "awards": "awards",
            "conferences": "conferences",
            "evaluation": "talent_evaluation",
            "mentor_groups": "mentor_groups",
        }
        for key, section in sections.items():
            target = required.get(key)
            if (
                target is not None
                and isinstance(section, dict)
                and section.get("status") == "ok"
                and not allowed(db, actor, target, "export", college, major)
            ):
                deny(db, actor, "export", "报告导出授权不足")
        milestones = sections.get("milestones")
        if isinstance(milestones, dict):
            for category, section in milestones.items():
                if (
                    isinstance(section, dict)
                    and section.get("status") == "ok"
                    and not allowed(db, actor, category, "export", college, major)
                ):
                    deny(db, actor, "export", "报告导出授权不足")

    def group_export_scopes(
        db: Any, report: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        """Export requires the export grant wherever the report actually drew
        data: the relation scopes behind relation_ids plus every category with
        a nonzero distinct count."""
        scopes: set[tuple[str, str, str]] = set()
        categories = {
            category
            for category, values in report["categories"].items()
            if values["distinct_outputs"]
        }
        for relation_id in report["relation_ids"]:
            row = db.execute(
                "SELECT * FROM mentor_group_relations WHERE id=?", (relation_id,)
            ).fetchone()
            if row is None:
                continue
            for table, key in (
                ("students", "student_id"),
                ("mentor_directory", "mentor_id"),
                ("research_groups", "group_id"),
            ):
                scope = db.execute(
                    f"SELECT * FROM {table} WHERE id=?", (row[key],)
                ).fetchone()
                if scope is not None:
                    scopes.add(("mentor_groups", scope["college"], scope["major"]))
                    scopes.add(("basic", scope["college"], scope["major"]))
                    for category in categories:
                        scopes.add((category, scope["college"], scope["major"]))
        return sorted(scopes)

    def any_basic_export(db: Any, actor: int) -> bool:
        return (
            db.execute(
                "SELECT 1 FROM grants WHERE user_id=? AND category='basic' AND operation='export' LIMIT 1",
                (actor,),
            ).fetchone()
            is not None
        )

    @app.get("/api/reports/students/{student_id}")
    def student(student_id: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            report = student_report(db, actor["id"], student_id)
            audit(db, actor["id"], "reports.read", f"student:{student_id}")
            db.commit()
            return report

    @app.get("/api/reports/mentor-groups")
    def group(
        request: Request, as_of: date, mentor_id: int | None = None, group_id: int | None = None
    ) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            report = group_report(db, actor["id"], as_of, mentor_id, group_id)
            audit(
                db,
                actor["id"],
                "reports.read",
                f"group:{mentor_id or '*'}/{group_id or '*'}@{as_of}",
            )
            db.commit()
            return report

    @app.get("/api/reports/colleges")
    def college(request: Request, college: str, major: str) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            report = college_report(db, actor["id"], college, major)
            audit(db, actor["id"], "reports.read", f"college:{college}/{major}")
            db.commit()
            return report

    @app.get("/api/reports/students/{student_id}/export")
    def student_export(student_id: int, request: Request) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            report = student_report(db, actor["id"], student_id)
            require_section_exports(
                db,
                actor["id"],
                report["sections"],
                report["student"]["college"],
                report["student"]["major"],
            )
            audit(db, actor["id"], "reports.export", f"student:{student_id}")
            db.commit()
            return excel_report(report, f"report-student-{student_id}")

    @app.get("/api/reports/mentor-groups/export")
    def group_export(
        request: Request, as_of: date, mentor_id: int | None = None, group_id: int | None = None
    ) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            report = group_report(db, actor["id"], as_of, mentor_id, group_id)
            # The same basic-export floor as the other two report exports,
            # even when the report drew no relations at all.
            if not any_basic_export(db, actor["id"]):
                deny(db, actor["id"], "export", "报告导出授权不足")
            for category, college, major in group_export_scopes(db, report):
                if not allowed(db, actor["id"], category, "export", college, major):
                    deny(db, actor["id"], "export", "报告导出授权不足")
            audit(
                db,
                actor["id"],
                "reports.export",
                f"group:{mentor_id or '*'}/{group_id or '*'}@{as_of}",
            )
            db.commit()
            return excel_report(report, f"report-group-{mentor_id or group_id or 'all'}")

    @app.get("/api/reports/colleges/export")
    def college_export(request: Request, college: str, major: str) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            report = college_report(db, actor["id"], college, major)
            require_section_exports(
                db, actor["id"], report["sections"], college, major
            )
            audit(db, actor["id"], "reports.export", f"college:{college}/{major}")
            db.commit()
            # Attachment names stay ASCII; the scope itself is inside the
            # workbook, and non-latin-1 header values would break the download.
            return excel_report(report, "report-college")
