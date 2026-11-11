"""Course import boundary. Business keys retain every term and assessment attempt."""

import hashlib
import json
import sqlite3
import time
from collections import Counter
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any
from zipfile import ZipFile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook

from aqp.authorization import allowed, compatible_scope
from aqp.store import audit, connection

REQUIRED = [
    "学号",
    "姓名",
    "课程编号",
    "课程名称",
    "修读学期",
    "考核次数",
    "评分制度",
    "原始成绩",
]
OPTIONAL = ["学分", "业务通过结果", "课程类别", "考核日期", "所属学院", "专业"]
IDENTITY = {"学号", "姓名"}


def permitted(db: sqlite3.Connection, actor: int, op: str, p: dict[str, Any]) -> bool:
    if op == "maintain" and (not p.get("所属学院") or not p.get("专业")):
        return compatible_scope(db, actor, "courses", p)
    return allowed(db, actor, "courses", op, p.get("所属学院", ""), p.get("专业", ""))


def visible(db: sqlite3.Connection, actor: int, p: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in p.items()
        if k not in IDENTITY or permitted(db, actor, "identity", p)
    }


def classify(
    db: sqlite3.Connection, p: dict[str, Any], source_row_id: int = -1
) -> tuple[str, str]:
    if not p.get("所属学院") or not p.get("专业"):
        return "invalid", "缺少来源学院或专业，待补齐范围"
    if any(not p.get(k) for k in REQUIRED if k != "原始成绩"):
        return "invalid", "必要字段为空"
    try:
        if int(p["考核次数"]) < 1:
            raise ValueError
        if p.get("学分") and float(p["学分"]) < 0:
            raise ValueError
        if p["评分制度"] not in ["百分制", "五级制", "二级制"]:
            raise ValueError
        score = p["原始成绩"]
        if score:
            if p["评分制度"] == "百分制" and not 0 <= float(score) <= 100:
                raise ValueError
            if p["评分制度"] == "五级制" and score not in [
                "优秀",
                "良好",
                "中等",
                "及格",
                "不及格",
            ]:
                raise ValueError
            if p["评分制度"] == "二级制" and score not in [
                "通过",
                "不通过",
                "合格",
                "不合格",
            ]:
                raise ValueError
        if p.get("业务通过结果") not in ["", "通过", "不通过"]:
            raise ValueError
    except (ValueError, OverflowError):
        return "invalid", "次数、学分、评分制度或成绩格式无效"
    old = db.execute(
        "SELECT * FROM course_records WHERE student_number=? AND course_code=? AND term=? AND attempt=? AND source_row_id!=?",
        (*key(p), source_row_id),
    ).fetchone()
    if old:
        return (
            ("duplicate", "")
            if json.loads(old["payload"]) == p
            else ("conflict", "同键内容变化，需人工确认")
        )
    student = db.execute(
        "SELECT * FROM students WHERE student_number=? AND active=1", (p["学号"],)
    ).fetchone()
    if not student:
        return "pending", "基础档案缺失"
    if (
        student["college"] != p["所属学院"]
        or student["major"] != p["专业"]
        or (p.get("姓名") and student["name"] != p["姓名"])
    ):
        return "conflict", "身份或所属范围冲突，需人工确认"
    return "ready", ""


def key(p: dict[str, Any]) -> tuple[str, str, str, int]:
    return p["学号"], p["课程编号"], p["修读学期"], int(p["考核次数"])


def reconcile_courses(db: sqlite3.Connection, actor: int) -> None:
    for row in db.execute(
        "SELECT * FROM course_records WHERE state='pending'"
    ).fetchall():
        p = json.loads(row["payload"])
        student = db.execute(
            "SELECT * FROM students WHERE student_number=? AND active=1", (p["学号"],)
        ).fetchone()
        if not student:
            continue
        conflict = (
            student["college"] != p["所属学院"]
            or student["major"] != p["专业"]
            or (p.get("姓名") and student["name"] != p["姓名"])
        )
        state = "conflict" if conflict else "linked"
        db.execute(
            "UPDATE course_records SET student_id=?,state=? WHERE id=?",
            (None if conflict else student["id"], state, row["id"]),
        )
        db.execute(
            "UPDATE import_rows SET student_id=?,state=?,error=? WHERE id=?",
            (
                None if conflict else student["id"],
                state,
                "身份或范围冲突，需人工确认" if conflict else "",
                row["source_row_id"],
            ),
        )
        audit(db, actor, "course.reconcile", str(row["id"]))


def register_courses(app: FastAPI, path: Path, current: Callable[..., Any]) -> None:
    def batch_view(db: sqlite3.Connection, actor: int, batch_id: int) -> dict[str, Any]:
        batch = db.execute(
            "SELECT * FROM import_batches WHERE id=? AND category='courses' AND uploaded_by=?",
            (batch_id, actor),
        ).fetchone()
        if not batch:
            raise HTTPException(404, "课程批次不存在或无权查看")
        rows = []
        for r in db.execute(
            "SELECT * FROM import_rows WHERE batch_id=? ORDER BY row_number",
            (batch_id,),
        ):
            p = json.loads(r["normalized_json"])
            if not permitted(db, actor, "maintain", p):
                raise HTTPException(403, "没有此范围课程维护权限")
            rows.append(
                {
                    "id": r["id"],
                    "row_number": r["row_number"],
                    "state": r["state"],
                    "error": r["error"],
                    "data": visible(db, actor, p),
                }
            )
        for item in rows:
            if item["state"] == "conflict":
                source = db.execute(
                    "SELECT normalized_json FROM import_rows WHERE id=?", (item["id"],)
                ).fetchone()
                p = json.loads(source["normalized_json"])
                try:
                    previous = db.execute(
                        "SELECT payload,version FROM course_records WHERE student_number=? AND course_code=? AND term=? AND attempt=?",
                        key(p),
                    ).fetchone()
                except (ValueError, KeyError):
                    previous = None
                if previous:
                    old = json.loads(previous["payload"])
                    if permitted(db, actor, "maintain", old):
                        item["existing"] = {
                            "version": previous["version"],
                            "data": visible(db, actor, old),
                        }
        return {
            "id": batch_id,
            "confirmed": bool(batch["confirmed"]),
            "total": len(rows),
            "counts": dict(Counter(r["state"] for r in rows)),
            "rows": rows,
        }

    @app.get("/api/templates/courses")
    def template(request: Request, sample: bool = False) -> Response:
        with connection(path) as db:
            current(db, request)
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.append(["AQP-PGS", "courses", "1"])
        ws.append(REQUIRED + OPTIONAL)
        if sample:
            ws.append(
                [
                    "SYN0001",
                    "合成学生甲",
                    "SYN-C1",
                    "合成课程",
                    "2025秋",
                    "1",
                    "百分制",
                    "",
                    "2",
                    "",
                    "",
                    "",
                    "合成学院",
                    "合成专业",
                ]
            )
        ws.cell(3, 1).number_format = "@"
        stream = BytesIO()
        wb.save(stream)
        return Response(
            stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="courses-v1.xlsx"'},
        )

    @app.post("/api/imports/courses/preview")
    async def preview(
        request: Request,
        source_department: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        college: Annotated[str, Form()] = "",
        major: Annotated[str, Form()] = "",
    ) -> dict[str, Any]:
        content = await file.read(16 * 1024 * 1024 + 1)
        if len(content) > 16 * 1024 * 1024:
            raise HTTPException(413, "文件超过16MB")
        if (
            not source_department.strip()
            or len(source_department) > 100
            or not (file.filename or "").lower().endswith(".xlsx")
        ):
            raise HTTPException(422, "请填写来源部门并上传标准xlsx")
        with connection(path) as db:
            actor, _ = current(db, request)
            parsed: list[tuple[int, dict[str, str], dict[str, Any], str, str]] = []
            try:
                with ZipFile(BytesIO(content)) as archive:
                    if sum(i.file_size for i in archive.infolist()) > 128 * 1024 * 1024:
                        raise ValueError
                wb = load_workbook(BytesIO(content), read_only=True, data_only=False)
                ws = wb.active
                assert ws is not None
                cells = ws.iter_rows(values_only=True)
                if list(next(cells)[:3]) != ["AQP-PGS", "courses", "1"]:
                    raise ValueError
                headers = next(cells)
                if any(k not in headers for k in REQUIRED) or len(set(headers)) != len(
                    headers
                ):
                    raise ValueError
                seen: dict[tuple[str, str, str, int], int] = {}
                for n, values in enumerate(cells, 3):
                    if not any(v is not None for v in values):
                        continue
                    if len(parsed) >= 60000:
                        raise ValueError
                    raw = {
                        str(k): str(v) if v is not None else ""
                        for k, v in zip(headers, values)
                        if k
                    }
                    p = {k: raw.get(k, "").strip() for k in REQUIRED + OPTIONAL}
                    student = db.execute(
                        "SELECT * FROM students WHERE student_number=?", (p["学号"],)
                    ).fetchone()
                    p["所属学院"] = (
                        p["所属学院"]
                        or college
                        or (student["college"] if student else "")
                    )
                    p["专业"] = (
                        p["专业"] or major or (student["major"] if student else "")
                    )
                    if not permitted(db, actor["id"], "maintain", p):
                        raise HTTPException(403, "须明确来源学院专业且具备课程维护权限")
                    state, error = classify(db, p)
                    if not isinstance(values[headers.index("学号")], str):
                        state, error = "invalid", "学号必须为文本"
                    if state in ["ready", "pending"]:
                        k = key(p)
                        if k in seen:
                            prior = parsed[seen[k]]
                            if prior[2] == p:
                                state, error = "duplicate", ""
                            else:
                                state, error = "conflict", "同文件同键内容冲突"
                                parsed[seen[k]] = (*prior[:3], state, error)
                        else:
                            seen[k] = len(parsed)
                    parsed.append((n, raw, p, state, error))
                title = ws.title
                wb.close()
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    422, "无法解析课程v1模板（最多60000行），请检查版本及必要列"
                ) from exc
            batch_id = db.execute(
                "INSERT INTO import_batches(category,template_version,source_department,filename,file_hash,original_file,uploaded_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    "courses",
                    "1",
                    source_department.strip(),
                    Path(file.filename or "upload.xlsx").name,
                    hashlib.sha256(content).hexdigest(),
                    content,
                    actor["id"],
                    int(time.time()),
                ),
            ).lastrowid
            assert batch_id is not None
            for n, raw, p, state, error in parsed:
                db.execute(
                    "INSERT INTO import_rows(batch_id,sheet,row_number,raw_json,normalized_json,state,error) VALUES (?,?,?,?,?,?,?)",
                    (
                        batch_id,
                        title,
                        n,
                        json.dumps(raw, ensure_ascii=False),
                        json.dumps(p, ensure_ascii=False),
                        state,
                        error,
                    ),
                )
            audit(db, actor["id"], "course.preview", str(batch_id))
            return batch_view(db, actor["id"], batch_id)

    @app.get("/api/imports/courses/{batch_id}")
    def get_batch(batch_id: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return batch_view(db, actor["id"], batch_id)

    @app.post("/api/imports/courses/{batch_id}/confirm")
    def confirm(batch_id: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            if batch_view(db, actor["id"], batch_id)["confirmed"]:
                return batch_view(db, actor["id"], batch_id)
            for r in db.execute(
                "SELECT * FROM import_rows WHERE batch_id=? AND state IN ('ready','pending')",
                (batch_id,),
            ).fetchall():
                p = json.loads(r["normalized_json"])
                state, error = classify(db, p)
                if state in ["ready", "pending"]:
                    student = db.execute(
                        "SELECT id FROM students WHERE student_number=?", (p["学号"],)
                    ).fetchone()
                    sid = student["id"] if student else None
                    state = "linked" if sid else "pending"
                    db.execute(
                        "INSERT INTO course_records(student_number,course_code,term,attempt,student_id,payload,state,source_row_id) VALUES (?,?,?,?,?,?,?,?)",
                        (*key(p), sid, r["normalized_json"], state, r["id"]),
                    )
                    db.execute(
                        "UPDATE import_rows SET student_id=? WHERE id=?", (sid, r["id"])
                    )
                db.execute(
                    "UPDATE import_rows SET state=?,error=? WHERE id=?",
                    (state, error, r["id"]),
                )
            db.execute("UPDATE import_batches SET confirmed=1 WHERE id=?", (batch_id,))
            audit(db, actor["id"], "course.confirm", str(batch_id))
            return batch_view(db, actor["id"], batch_id)

    @app.get("/api/students/{student_id}/courses")
    def records(
        student_id: int, request: Request, offset: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        if offset < 0 or not 1 <= limit <= 200:
            raise HTTPException(422, "分页范围无效")
        with connection(path) as db:
            actor, _ = current(db, request)
            items = []
            for r in db.execute(
                "SELECT c.*,i.batch_id,i.row_number,i.sheet,b.source_department,b.created_at FROM course_records c JOIN import_rows i ON i.id=c.source_row_id JOIN import_batches b ON b.id=i.batch_id WHERE c.student_id=? AND c.state='linked' ORDER BY c.id",
                (student_id,),
            ):
                p = json.loads(r["payload"])
                if permitted(db, actor["id"], "view", p):
                    items.append(
                        {
                            "id": r["id"],
                            "version": r["version"],
                            "data": visible(db, actor["id"], p),
                            "source": {
                                "batch_id": r["batch_id"],
                                "row_id": r["source_row_id"],
                                "row_number": r["row_number"],
                                "sheet": r["sheet"],
                                "source_department": r["source_department"],
                                "created_at": r["created_at"],
                            },
                        }
                    )
            audit(db, actor["id"], "course.list", str(student_id))
            return {"total": len(items), "items": items[offset : offset + limit]}
