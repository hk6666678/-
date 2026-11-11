import hashlib
import json
import sqlite3
import time
from collections import Counter
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Annotated
from zipfile import ZipFile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook

from aqp.authorization import allowed, compatible_scope, grants_for
from aqp.store import audit, connection

BASIC_REQUIRED = ["学号", "姓名", "考核批次", "评分制度", "原始成绩"]
BASIC_OPTIONAL = [
    "选题标题",
    "实际日期",
    "计划日期",
    "评语",
    "成果说明",
    "正文版本说明",
    "业务通过结果",
    "所属学院",
    "专业",
]
SAFE_FIELDS = {
    "考核批次",
    "评分制度",
    "原始成绩",
    "实际日期",
    "计划日期",
    "业务通过结果",
    "所属学院",
    "专业",
}


def scope(
    db: sqlite3.Connection,
    actor: int,
    op: str,
    payload: dict[str, object],
    category: str,
) -> bool:
    if op == "maintain" and (not payload.get("所属学院") or not payload.get("专业")):
        return compatible_scope(db, actor, category, payload)
    return allowed(
        db,
        actor,
        category,
        op,
        str(payload.get("所属学院", "")),
        str(payload.get("专业", "")),
    )


def masked(
    db: sqlite3.Connection, actor: int, payload: dict[str, object], category: str
) -> dict[str, object]:
    return (
        payload
        if scope(db, actor, "identity", payload, category)
        else {k: v for k, v in payload.items() if k in SAFE_FIELDS}
    )


def classify_milestone(
    db: sqlite3.Connection,
    payload: dict[str, object],
    category: str,
    source_row_id: int = -1,
) -> tuple[str, str]:
    required = ["学号", "姓名", "考核批次", "评分制度", "所属学院", "专业"] + (
        ["选题标题"] if category == "topic" else []
    )
    if any(not str(payload.get(k, "")).strip() for k in required):
        return "invalid", "必要字段为空（缺基础档案须填写来源学院和专业）"
    system = payload["评分制度"]
    score = str(payload.get("原始成绩", ""))
    if system not in ["百分制", "五级制", "二级制"]:
        return "invalid", "评分制度须为百分制、五级制或二级制"
    if score:
        if system == "百分制":
            try:
                if not 0 <= float(score) <= 100:
                    raise ValueError
            except ValueError:
                return "invalid", "百分制成绩须在0～100之间"
        elif score not in (
            {"优秀", "良好", "中等", "及格", "不及格"}
            if system == "五级制"
            else {"通过", "不通过", "合格", "不合格"}
        ):
            return "invalid", "成绩与评分制度不一致"
    if payload.get("业务通过结果", "") not in ["", "通过", "不通过"]:
        return "invalid", "通过结果须为空、通过或不通过"
    student = db.execute(
        "SELECT * FROM students WHERE student_number=? AND active=1", (payload["学号"],)
    ).fetchone()
    if student and (
        student["name"] != payload["姓名"]
        or student["college"] != payload["所属学院"]
        or student["major"] != payload["专业"]
    ):
        return "conflict", "身份或来源范围不一致，需人工确认"
    record = db.execute(
        "SELECT * FROM milestone_records WHERE student_number=? AND category=? AND assessment_batch=? AND source_row_id!=?",
        (payload["学号"], category, payload["考核批次"], source_row_id),
    ).fetchone()
    if record:
        return (
            ("duplicate", "")
            if json.loads(record["payload"]) == payload
            else ("conflict", "同环节同批次内容变化，需人工确认")
        )
    return ("ready", "") if student else ("pending", "缺基础档案，待关联")


def reconcile_milestones(db: sqlite3.Connection, actor: int | None = None) -> None:
    for row in db.execute(
        "SELECT * FROM milestone_records WHERE student_id IS NULL"
    ).fetchall():
        payload = json.loads(row["payload"])
        student = db.execute(
            "SELECT * FROM students WHERE student_number=? AND active=1",
            (row["student_number"],),
        ).fetchone()
        if not student:
            continue
        matched = (
            student["name"] == payload["姓名"]
            and student["college"] == payload["所属学院"]
            and student["major"] == payload["专业"]
        )
        if matched:
            db.execute(
                "UPDATE milestone_records SET student_id=? WHERE id=?",
                (student["id"], row["id"]),
            )
        db.execute(
            "UPDATE import_rows SET state=?,error=?,student_id=? WHERE id=?",
            (
                "imported" if matched else "conflict",
                "" if matched else "身份或来源范围不一致，需人工确认",
                student["id"] if matched else None,
                row["source_row_id"],
            ),
        )
        if actor is not None:
            audit(
                db,
                actor,
                "milestone.associate" if matched else "milestone.identity_conflict",
                str(row["id"]),
            )


def milestone_details(
    db: sqlite3.Connection, actor: int, student_id: int
) -> list[dict[str, object]]:
    result = []
    for row in db.execute(
        "SELECT m.*,i.batch_id,i.row_number,b.source_department FROM milestone_records m JOIN import_rows i ON i.id=m.source_row_id JOIN import_batches b ON b.id=i.batch_id WHERE m.student_id=? AND m.active=1 ORDER BY m.category,m.assessment_batch",
        (student_id,),
    ):
        payload = json.loads(row["payload"])
        if scope(db, actor, "view", payload, row["category"]):
            result.append(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "version": row["version"],
                    "source_row_id": row["source_row_id"],
                    "batch_id": row["batch_id"],
                    "row_number": row["row_number"],
                    "source_department": row["source_department"],
                    "data": masked(db, actor, payload, row["category"]),
                }
            )
    return result


def register_milestones(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    def require_any(
        db: sqlite3.Connection, actor: int, operation: str, category: str
    ) -> None:
        if category not in ("topic", "midterm"):
            raise HTTPException(404, "环节不存在")
        if not any(
            g["category"] == category and g["operation"] == operation
            for g in grants_for(db, actor)
        ):
            raise HTTPException(403, "没有基础信息操作权限")

    def batch_view(
        db: sqlite3.Connection, actor: int, batch_id: int
    ) -> dict[str, object]:
        batch = db.execute(
            "SELECT * FROM import_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not batch or batch["uploaded_by"] != actor:
            raise HTTPException(404, "批次不存在或无权查看")
        category = batch["category"]
        if category not in ("topic", "midterm"):
            raise HTTPException(404, "环节批次不存在")
        require_any(db, actor, "maintain", category)
        rows = []
        for record in db.execute(
            "SELECT * FROM import_rows WHERE batch_id=? ORDER BY row_number",
            (batch_id,),
        ):
            payload = json.loads(record["normalized_json"])
            if not scope(db, actor, "maintain", payload, category):
                raise HTTPException(403, "批次中存在当前无权维护的范围")
            rows.append(
                {
                    "id": record["id"],
                    "row_number": record["row_number"],
                    "sheet": record["sheet"],
                    "state": record["state"],
                    "error": record["error"],
                    "data": masked(db, actor, payload, category),
                    "student_id": record["student_id"],
                }
            )
        return {
            "id": batch_id,
            "source_department": batch["source_department"],
            "filename": batch["filename"]
            if all(
                scope(db, actor, "identity", json.loads(r["normalized_json"]), category)
                for r in db.execute(
                    "SELECT normalized_json FROM import_rows WHERE batch_id=?",
                    (batch_id,),
                )
            )
            else "名称已脱敏",
            "created_at": batch["created_at"],
            "confirmed": bool(batch["confirmed"]),
            "total": len(rows),
            "counts": dict(Counter(str(r["state"]) for r in rows)),
            "rows": rows,
        }

    @app.get("/api/templates/milestones/{category}")
    def template(category: str, request: Request, sample: bool = False) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_any(db, actor["id"], "maintain", category)
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.append(["AQP-PGS", category, "1"])
        ws.append(
            BASIC_REQUIRED
            + (["选题标题"] if category == "topic" else [])
            + [k for k in BASIC_OPTIONAL if k != "选题标题"]
        )
        if sample:
            headers = (
                BASIC_REQUIRED
                + (["选题标题"] if category == "topic" else [])
                + [k for k in BASIC_OPTIONAL if k != "选题标题"]
            )
            sample_data = {
                "学号": "SYN0001",
                "姓名": "合成学生甲",
                "考核批次": "2025第一批",
                "评分制度": "百分制",
                "选题标题": "合成选题",
                "所属学院": "合成学院",
                "专业": "合成专业",
            }
            ws.append([sample_data.get(k, "") for k in headers])
            sample_data.update({"学号": "SYN0002", "姓名": ""})
            ws.append([sample_data.get(k, "") for k in headers])
        ws.column_dimensions["A"].width = 22
        for row in range(3, 1003):
            ws.cell(row, 1).number_format = "@"
        stream = BytesIO()
        wb.save(stream)
        return Response(
            stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="milestone-v1.xlsx"'},
        )

    @app.post("/api/milestones/{category}/preview")
    async def preview(
        category: str,
        request: Request,
        file: Annotated[UploadFile, File()],
        source_college: Annotated[str, Form()] = "",
        source_major: Annotated[str, Form()] = "",
        source_department: Annotated[str, Form()] = "",
    ) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_any(db, actor["id"], "maintain", category)
            if (
                not source_department.strip()
                or len(source_department) > 100
                or not (file.filename or "").lower().endswith(".xlsx")
            ):
                raise HTTPException(422, "请填写来源部门并上传标准xlsx")
            content = await file.read(8 * 1024 * 1024 + 1)
            if len(content) > 8 * 1024 * 1024:
                raise HTTPException(413, "文件超过8MB")
            try:
                with ZipFile(BytesIO(content)) as archive:
                    if (
                        sum(info.file_size for info in archive.infolist())
                        > 40 * 1024 * 1024
                    ):
                        raise ValueError("解压大小超限")
                wb = load_workbook(BytesIO(content), read_only=True, data_only=False)
                ws = wb.active
                assert ws is not None
                cells = ws.iter_rows(values_only=True)
                marker = next(cells)
                headers = next(cells)
                if list(marker[:3]) != ["AQP-PGS", category, "1"]:
                    raise ValueError("模板类型或版本不符")
                if any(
                    k not in headers
                    for k in BASIC_REQUIRED
                    + (["选题标题"] if category == "topic" else [])
                ) or len(set(headers)) != len(headers):
                    raise ValueError("必要列缺失或重复")
                parsed: list[
                    tuple[int, dict[str, str], dict[str, object], str, str]
                ] = []
                for number, values in enumerate(cells, 3):
                    if not any(v is not None for v in values):
                        continue
                    if len(parsed) >= 10000:
                        raise ValueError("超过10000行")
                    raw = {
                        str(k): str(v) if v is not None else ""
                        for k, v in zip(headers, values)
                        if k
                    }
                    payload: dict[str, object] = {
                        k: raw.get(k, "").strip()
                        for k in BASIC_REQUIRED + BASIC_OPTIONAL
                    }
                    student = db.execute(
                        "SELECT * FROM students WHERE student_number=?",
                        (payload["学号"],),
                    ).fetchone()
                    payload["所属学院"] = (
                        payload.get("所属学院")
                        or source_college.strip()
                        or (student["college"] if student else "")
                    )
                    payload["专业"] = (
                        payload.get("专业")
                        or source_major.strip()
                        or (student["major"] if student else "")
                    )
                    if not scope(db, actor["id"], "maintain", payload, category):
                        raise HTTPException(403, "文件包含无维护权限的学院或专业")
                    state, error = classify_milestone(db, payload, category)
                    if not isinstance(values[headers.index("学号")], str):
                        state, error = "invalid", "学号必须为文本"
                    parsed.append((number, raw, payload, state, error))
                wb.close()
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    422, "无法解析标准模板，请检查版本、必要列或文件内容"
                ) from exc
            cursor = db.execute(
                "INSERT INTO import_batches(category,template_version,source_department,filename,file_hash,original_file,uploaded_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    category,
                    "1",
                    source_department.strip(),
                    Path(file.filename or "upload.xlsx").name,
                    hashlib.sha256(content).hexdigest(),
                    content,
                    actor["id"],
                    int(time.time()),
                ),
            )
            batch_id = cursor.lastrowid
            assert batch_id is not None
            seen: dict[str, dict[str, object]] = {}
            for number, raw, payload, state, error in parsed:
                key = str(payload["学号"]) + "|" + str(payload["考核批次"])
                if state in ("ready", "pending") and key in seen:
                    state, error = (
                        ("duplicate", "")
                        if seen[key] == payload
                        else ("conflict", "同一文件中同号内容冲突")
                    )
                    if state == "conflict":
                        db.execute(
                            "UPDATE import_rows SET state='conflict',error=? WHERE batch_id=? AND json_extract(normalized_json,'$.学号')=? AND json_extract(normalized_json,'$.考核批次')=?",
                            (error, batch_id, payload["学号"], payload["考核批次"]),
                        )
                seen[key] = payload
                db.execute(
                    "INSERT INTO import_rows(batch_id,sheet,row_number,raw_json,normalized_json,state,error) VALUES (?,?,?,?,?,?,?)",
                    (
                        batch_id,
                        ws.title,
                        number,
                        json.dumps(raw, ensure_ascii=False),
                        json.dumps(payload, ensure_ascii=False),
                        state,
                        error,
                    ),
                )
            audit(db, actor["id"], "import.preview", str(batch_id))
            return batch_view(db, actor["id"], batch_id)

    @app.get("/api/milestone-imports/{batch_id}")
    def get_batch(batch_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return batch_view(db, actor["id"], batch_id)

    @app.post("/api/milestone-imports/{batch_id}/confirm")
    def confirm(batch_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            batch_view(db, actor["id"], batch_id)
            category = db.execute(
                "SELECT category FROM import_batches WHERE id=?", (batch_id,)
            ).fetchone()["category"]
            for row in db.execute(
                "SELECT * FROM import_rows WHERE batch_id=? AND state IN ('ready','pending') AND id NOT IN (SELECT source_row_id FROM milestone_records)",
                (batch_id,),
            ).fetchall():
                payload = json.loads(row["normalized_json"])
                state, error = classify_milestone(db, payload, category)
                student = db.execute(
                    "SELECT id FROM students WHERE student_number=?", (payload["学号"],)
                ).fetchone()
                student_id = student["id"] if student and state == "ready" else None
                if state in ("ready", "pending"):
                    db.execute(
                        "INSERT INTO milestone_records(category,student_number,assessment_batch,student_id,payload,source_row_id) VALUES (?,?,?,?,?,?)",
                        (
                            category,
                            payload["学号"],
                            payload["考核批次"],
                            student_id,
                            row["normalized_json"],
                            row["id"],
                        ),
                    )
                    state = "imported" if student_id else "pending"
                db.execute(
                    "UPDATE import_rows SET state=?,error=?,student_id=? WHERE id=?",
                    (state, error, student_id, row["id"]),
                )
            db.execute("UPDATE import_batches SET confirmed=1 WHERE id=?", (batch_id,))
            audit(db, actor["id"], "import.confirm", str(batch_id))
            return batch_view(db, actor["id"], batch_id)

    @app.get("/api/milestones")
    def records(
        request: Request,
        student_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, object]:
        if offset < 0 or not 1 <= limit <= 200:
            raise HTTPException(422, "分页范围无效")
        with connection(path) as db:
            actor, _ = current(db, request)
            reconcile_milestones(db, actor["id"])
            items = []
            for row in db.execute(
                "SELECT m.*,i.batch_id,i.row_number,i.sheet,b.source_department FROM milestone_records m JOIN import_rows i ON i.id=m.source_row_id JOIN import_batches b ON b.id=i.batch_id WHERE m.active=1 ORDER BY m.id"
            ):
                payload = json.loads(row["payload"])
                if student_id is not None and row["student_id"] != student_id:
                    continue
                if scope(db, actor["id"], "view", payload, row["category"]):
                    items.append(
                        {
                            "id": row["id"],
                            "category": row["category"],
                            "student_id": row["student_id"],
                            "version": row["version"],
                            "source_row_id": row["source_row_id"],
                            "batch_id": row["batch_id"],
                            "row_number": row["row_number"],
                            "sheet": row["sheet"],
                            "source_department": row["source_department"],
                            "data": masked(db, actor["id"], payload, row["category"]),
                        }
                    )
            audit(db, actor["id"], "milestone.list", "milestones")
            return {"total": len(items), "items": items[offset : offset + limit]}
