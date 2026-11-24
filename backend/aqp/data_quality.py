"""Cross-source consistency checks and the three-level data classification.

The checks compare what different source departments recorded about the same
student. They only report differences: nothing is corrected here, and a record
whose source category the caller cannot see is never treated as missing."""

import json
import sqlite3
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request

from aqp.authorization import allowed, student_allowed
from aqp.mentor_groups import relation_allowed
from aqp.store import audit, connection

Check = dict[str, Any]
Scope = tuple[Any, Any]
Findings = dict[int, list[str]]

CHECK_META: dict[str, tuple[str, str]] = {
    "course_scope": (
        "课程记录的来源学院、专业与学生档案不一致",
        "多为档案更正学院或专业后遗留的旧记录；模拟评分会把这类记录排除在通过比例之外。",
    ),
    "milestone_scope": (
        "选题、中期记录的来源学院、专业与学生档案不一致",
        "核对来源部门的原始表格；确属档案更正的，保留记录并在分析中按范围不一致处理。",
    ),
    "record_name": (
        "来源记录里的姓名与学生档案不一致",
        "可能是同音字、曾用名或填错；对照来源部门确认后更正。",
    ),
    "thesis_scope": (
        "学位论文登记的培养层次或学科专业与学生档案不一致",
        "论文上传时填写的信息有误时，按论文版本替换流程更正。",
    ),
    "thesis_metadata_missing": (
        "学位论文未填写培养层次或学科专业",
        "缺少这两项时论文无法归入对照组，也无法参与同类比较。",
    ),
    "mentor_unlinked": (
        "档案登记了导师，但没有当前有效的指导关系",
        "在导师与课题组数据中补录关系，或更正档案中的导师信息。",
    ),
    "mentor_name_mismatch": (
        "档案登记的导师与当前指导关系中的导师不一致",
        "转导师后两侧未同步；以正式的指导关系为准核对。",
    ),
    "graduation_before_entry": (
        "毕业日期早于入学日期",
        "日期填写有误；入学日期未填写时按入学年份的 9 月 1 日计算。",
    ),
    "blind_review_date": (
        "盲审论文的提交状态与实际提交日期对不上",
        "标记为已提交却没有日期，或有日期却没有状态。",
    ),
    "mobility_incomplete": (
        "学籍异动类型与异动时间缺少其中一项",
        "向学籍管理部门核对后补齐。",
    ),
    "pending_records": (
        "本范围内尚未关联到正式学生档案的记录",
        "这些记录暂不参与任何统计；到对应的导入页面处理。",
    ),
}
KIND_LABELS = {"courses": "课程", "topic": "选题", "midterm": "中期"}


def parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "").split(" ")[0])
    except ValueError:
        return None


def scope_of(payload: dict[str, Any]) -> Scope:
    return payload.get("所属学院", payload.get("学院")), payload.get("专业")


def show_scope(scope: Scope) -> str:
    return f"{scope[0] or '未填'!s}／{scope[1] or '未填'!s}"


def skipped(reason: str) -> Check:
    return {"status": "skipped", "reason": reason, "count": None, "items": [], "truncated": False}


def collected(findings: Findings, research_ids: dict[int, str], limit: int) -> Check:
    ordered = sorted(findings.items())
    return {
        "status": "found" if ordered else "ok",
        "reason": None,
        "count": len(ordered),
        "items": [
            {"research_id": research_ids[sid], "detail": "；".join(details)}
            for sid, details in ordered[:limit]
        ],
        "truncated": len(ordered) > limit,
    }


def consistency_checks(
    db: sqlite3.Connection, actor: int, college: str, major: str, limit: int
) -> dict[str, Any]:
    students = {
        row["id"]: row
        for row in db.execute(
            "SELECT * FROM students WHERE active=1 AND college=? AND major=? ORDER BY id",
            (college, major),
        )
        if student_allowed(db, actor, row["id"])
    }
    research_ids = {sid: row["research_id"] for sid, row in students.items()}
    archives = {sid: json.loads(row["payload"]) for sid, row in students.items()}

    def granted(category: str, operation: str) -> bool:
        return allowed(db, actor, category, operation, college, major)

    def labelled(code: str, check: Check) -> Check:
        return {"code": code, "title": CHECK_META[code][0], "hint": CHECK_META[code][1], **check}

    results: dict[str, Check] = {}

    # --- records whose source scope no longer matches the archive ---
    course_rows = db.execute(
        "SELECT student_id,payload FROM course_records "
        "WHERE state='linked' AND active=1 AND student_id IS NOT NULL ORDER BY id"
    ).fetchall()
    milestone_rows = db.execute(
        "SELECT student_id,category,payload FROM milestone_records "
        "WHERE active=1 AND student_id IS NOT NULL ORDER BY id"
    ).fetchall()

    def source_rows(kind: str) -> list[tuple[int, str, dict[str, Any]]]:
        if kind == "courses":
            return [
                (row["student_id"], "courses", json.loads(row["payload"])) for row in course_rows
            ]
        return [
            (row["student_id"], row["category"], json.loads(row["payload"]))
            for row in milestone_rows
        ]

    def scope_mismatch(code: str, kinds: list[str], missing: str) -> Check:
        visible = [kind for kind in kinds if granted(kind, "view")]
        if not visible:
            return skipped(missing)
        # student -> kind -> scopes recorded by the source department
        seen: dict[int, dict[str, list[Scope]]] = {}
        for sid, kind, payload in [row for item in visible for row in source_rows(item)]:
            if sid not in students:
                continue
            scope = scope_of(payload)
            if scope != (college, major):
                seen.setdefault(sid, {}).setdefault(kind, []).append(scope)
        findings: Findings = {}
        for sid, per_kind in seen.items():
            parts = [
                f"{KIND_LABELS[kind]}记录 {len(scopes)} 条，登记为"
                + "、".join(sorted({show_scope(scope) for scope in scopes}))
                for kind, scopes in per_kind.items()
            ]
            findings[sid] = [f"{'；'.join(parts)}，档案为 {college}／{major}"]
        return collected(findings, research_ids, limit)

    results["course_scope"] = labelled(
        "course_scope", scope_mismatch("course_scope", ["courses"], "需要课程的查看权限")
    )
    results["milestone_scope"] = labelled(
        "milestone_scope",
        scope_mismatch("milestone_scope", ["topic", "midterm"], "需要选题或中期的查看权限"),
    )

    # --- names recorded by source departments ---
    visible = [kind for kind in KIND_LABELS if granted(kind, "view")]
    if not granted("basic", "identity"):
        check: Check = skipped("需要基础档案的身份授权才能比对姓名")
    elif not visible:
        check = skipped("需要课程、选题或中期的查看权限")
    else:
        counts: dict[int, dict[str, int]] = {}
        for sid, kind, payload in [row for item in visible for row in source_rows(item)]:
            recorded = payload.get("姓名")
            if sid not in students or not recorded or recorded == students[sid]["name"]:
                continue
            per_kind = counts.setdefault(sid, {})
            per_kind[kind] = per_kind.get(kind, 0) + 1
        findings = {
            sid: [
                f"{sum(per_kind.values())} 条来源记录的姓名与档案不一致（"
                + "、".join(f"{KIND_LABELS[kind]} {number} 条" for kind, number in per_kind.items())
                + "）"
            ]
            for sid, per_kind in counts.items()
        }
        check = collected(findings, research_ids, limit)
    results["record_name"] = labelled("record_name", check)

    # --- thesis metadata against the archive ---
    if not granted("papers", "view"):
        for code in ("thesis_scope", "thesis_metadata_missing"):
            results[code] = labelled(code, skipped("需要学位论文的查看权限"))
    else:
        wrong: Findings = {}
        incomplete: Findings = {}
        latest = db.execute(
            "SELECT student_id,level,discipline FROM paper_versions "
            "WHERE id IN (SELECT MAX(id) FROM paper_versions GROUP BY student_id) ORDER BY id"
        )
        for row in latest:
            student = students.get(row["student_id"])
            if student is None:
                continue
            level, discipline = row["level"] or "", row["discipline"] or ""
            if not level or not discipline:
                missing = "培养层次和学科专业" if not level and not discipline else (
                    "培养层次" if not level else "学科专业"
                )
                incomplete[row["student_id"]] = [
                    f"学位论文未填写{missing}，无法归入论文对照组"
                ]
            elif level != student["level"] or discipline != student["major"]:
                wrong[row["student_id"]] = [
                    (
                        f"学位论文登记为 {level}／{discipline}，"
                        f"档案为 {student['level']}／{student['major']}"
                    )
                ]
        results["thesis_scope"] = labelled(
            "thesis_scope", collected(wrong, research_ids, limit)
        )
        results["thesis_metadata_missing"] = labelled(
            "thesis_metadata_missing", collected(incomplete, research_ids, limit)
        )

    # --- mentor recorded in the archive against current relations ---
    if not granted("mentor_groups", "view"):
        for code in ("mentor_unlinked", "mentor_name_mismatch"):
            results[code] = labelled(code, skipped("需要导师课题组的查看权限"))
    else:
        today = date.today().isoformat()
        # Relations the caller cannot see are not evidence of "no relation".
        current: dict[int, set[int]] = {}
        for relation in db.execute("SELECT * FROM mentor_group_relations ORDER BY id"):
            active = relation["start_date"] <= today <= (relation["end_date"] or "9999-12-31")
            if active and relation_allowed(db, actor, "view", relation):
                current.setdefault(relation["student_id"], set()).add(relation["mentor_id"])
        unlinked: Findings = {}
        mismatch: Findings = {}
        if granted("mentor_groups", "identity"):
            mentor_names = {
                row["id"]: row["name"]
                for row in db.execute("SELECT id,name FROM mentor_directory")
            }
        else:
            mentor_names = {}
        for sid, data in archives.items():
            recorded = str(data.get("导师姓名") or "").strip()
            identified = recorded or str(data.get("导师标识") or "").strip()
            related = {mentor_names.get(mid, "") for mid in current.get(sid, set())}
            related.discard("")
            if identified and sid not in current:
                unlinked[sid] = ["档案登记了导师，但截至今天没有有效的指导关系"]
            elif recorded and related and recorded not in related:
                mismatch[sid] = [
                    (
                        f"档案登记的导师为 {recorded}，"
                        f"当前指导关系的导师为 {'、'.join(sorted(related))}"
                    )
                ]
        results["mentor_unlinked"] = labelled(
            "mentor_unlinked", collected(unlinked, research_ids, limit)
        )
        if not granted("mentor_groups", "identity"):
            check = skipped("需要导师课题组的身份授权才能比对导师姓名")
        else:
            check = collected(mismatch, research_ids, limit)
        results["mentor_name_mismatch"] = labelled("mentor_name_mismatch", check)

    # --- dates and status fields inside the archive itself ---
    dated: dict[str, Findings] = {name: {} for name in (
        "graduation_before_entry", "blind_review_date", "mobility_incomplete"
    )}
    for sid, data in archives.items():
        entry = parse_date(data.get("入学日期"))
        if entry is None:
            try:
                entry = date(int(str(data.get("入学年份"))), 9, 1)
            except ValueError:
                entry = None
        for field in ("实际毕业日期", "预计毕业日期"):
            value = parse_date(data.get(field))
            if entry is not None and value is not None and value < entry:
                dated["graduation_before_entry"].setdefault(sid, []).append(
                    f"{field} {value.isoformat()} 早于入学日期 {entry.isoformat()}"
                )
        status = str(data.get("盲审论文提交状态") or "").strip()
        submitted = parse_date(data.get("盲审论文实际提交日期"))
        if "提交" in status and "未" not in status and submitted is None:
            dated["blind_review_date"].setdefault(sid, []).append(
                f"盲审论文标记为{status}，但没有登记实际提交日期"
            )
        elif submitted is not None and not status:
            dated["blind_review_date"].setdefault(sid, []).append(
                "登记了盲审论文实际提交日期，但没有填写提交状态"
            )
        kind = str(data.get("学籍异动类型") or "").strip()
        when = str(data.get("学籍异动时间") or "").strip()
        if bool(kind) != bool(when):
            dated["mobility_incomplete"].setdefault(sid, []).append(
                f"学籍异动类型与异动时间缺少其中一项（已填{'类型' if kind else '时间'}）"
            )
    for name, findings in dated.items():
        results[name] = labelled(name, collected(findings, research_ids, limit))

    # --- records still waiting for an archive ---
    pending_counts: dict[str, int | None] = {}
    skipped_categories: list[str] = []
    for kind in KIND_LABELS:
        if not granted(kind, "view"):
            pending_counts[kind] = None
            skipped_categories.append(kind)
            continue
        if kind == "courses":
            rows = db.execute(
                "SELECT payload FROM course_records WHERE active=1 AND state<>'linked'"
            )
        else:
            rows = db.execute(
                "SELECT payload FROM milestone_records WHERE active=1 AND student_id IS NULL AND category=?",
                (kind,),
            )
        pending_counts[kind] = sum(
            1 for row in rows if scope_of(json.loads(row["payload"])) == (college, major)
        )
    known = [value for value in pending_counts.values() if value is not None]
    results["pending_records"] = labelled(
        "pending_records",
        {
            "status": (
                "skipped" if not known
                else "partial" if len(known) < len(KIND_LABELS)
                else "found" if sum(known)
                else "ok"
            ),
            "reason": "需要课程、选题或中期的查看权限" if not known else None,
            "count": sum(known) if known else None,
            "items": [],
            "truncated": False,
            "courses": pending_counts["courses"],
            "topic": pending_counts["topic"],
            "midterm": pending_counts["midterm"],
            "skipped_categories": skipped_categories,
        },
    )
    return {
        "college": college,
        "major": major,
        "students": len(students),
        "generated_at": int(time.time()),
        "items": list(results.values()),
        "basis": (
            "交叉比对同一学生在不同来源部门登记的数据是否一致，只报告差异，不自动修改；"
            "需要更正时在数据纠错与维护中处理并留下依据。数量为涉及的学生数；"
            "无查看权限的来源标注为未核对，不按缺失处理。"
        ),
    }


def data_classification() -> dict[str, Any]:
    def item(category: str, name: str, note: str) -> dict[str, str]:
        return {"category": category, "name": name, "note": note}

    return {
        "status": "建议映射，待业务确认",
        "principle": (
            "分级按字段而不是按表：含姓名、学号、工号的字段，以及论文原件、附件和评语原文，"
            "一律按敏感处理，需要身份或下载授权；其余业务字段为内部，需要对应类别的查看授权；"
            "外网抓取的公开数据为公开。"
        ),
        "levels": [
            {
                "level": "公开",
                "protection": "来自公开渠道，可自由引用；接入时仍需记录来源与抓取日期。",
                "items": [
                    item(
                        "external", "外网抓取数据",
                        "引用次数、公开论文与专利信息。当前系统尚未接入外网抓取。",
                    )
                ],
            },
            {
                "level": "内部",
                "protection": (
                    "按数据类别授予查看与分析权限；分析结果以研究编号呈现，"
                    "导出另行授权，访问留痕。"
                ),
                "items": [
                    item("basic", "基础档案（不含身份）", "学院、专业、培养层次、入学年份、学籍状态与异动、毕业信息。"),
                    item("courses", "课程成绩记录", "课程、学期、成绩、学分与通过结果。"),
                    item("topic", "选题记录", "考核批次、成绩、选题标题与日期。"),
                    item("midterm", "中期记录", "考核批次、成绩与日期。"),
                    item("research_papers", "科研论文成果", "标题、发表年份、分区与引用快照。"),
                    item("patents", "专利成果", "专利名称、类型、申请日期。"),
                    item("awards", "获奖项目", "项目名称、等级、年份、资源类型。"),
                    item("conferences", "会议成果", "会议名称、报告类型、会议范围与日期。"),
                    item("papers", "学位论文解析特征", "页数、字数、章节数、参考文献数等本地特征。"),
                    item("blind_reviews", "盲审与答辩评分", "批次与分项评分；评语原文另按敏感处理。"),
                    item("mentor_groups", "导师课题组目录与指导关系", "不含姓名与工号的目录条目、关系起止日期。"),
                    item("talent_evaluation", "模拟评价快照", "各维度得分、总分与指标证据；仅供模拟研究。"),
                ],
            },
            {
                "level": "敏感",
                "protection": (
                    "在查看之外还需要身份或下载授权；身份信息以研究编号替代呈现，"
                    "访问与导出全部留痕。"
                ),
                "items": [
                    item("basic", "学生姓名与学号", "未获身份授权时一律显示为研究编号。"),
                    item("research_papers", "成果参与者的姓名与学号", "四类成果记录中的参与者身份字段相同处理。"),
                    item("mentor_groups", "导师姓名与工号", "未获身份授权时目录仅显示编号。"),
                    item("imports", "原始导入文件", "原始 Excel 含姓名与学号，下载需要下载与身份授权。"),
                    item("papers", "学位论文原件与正文附件", "未发表的学位论文、选题与中期正文。"),
                    item("blind_reviews", "盲审与答辩评语原文", "评语全文仅在具备下载授权时可见。"),
                ],
            },
        ],
    }


def register_data_quality(
    app: FastAPI, path: Path, current: Callable[..., Any]
) -> None:
    @app.get("/api/consistency/checks")
    def checks(
        request: Request,
        college: str = Query(min_length=1, max_length=100),
        major: str = Query(min_length=1, max_length=100),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            if not all(
                allowed(db, actor["id"], "basic", op, college, major)
                for op in ("view", "analyze")
            ):
                audit(db, actor["id"], "consistency.access", f"{college}/{major}", "denied")
                db.commit()
                raise HTTPException(403, "基础档案查看授权不足")
            result = consistency_checks(db, actor["id"], college, major, limit)
            audit(db, actor["id"], "consistency.checks", f"{college}/{major}")
            db.commit()
            return result

    @app.get("/api/data-classification")
    def classification(request: Request) -> dict[str, Any]:
        with connection(path) as db:
            current(db, request)
        return data_classification()
