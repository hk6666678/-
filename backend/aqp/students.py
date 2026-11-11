import hashlib
import json
import sqlite3
import time
import uuid
from collections import Counter
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Annotated
from zipfile import ZipFile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook

from aqp.authorization import allowed, grants_for
from aqp.store import audit, connection

BASIC_REQUIRED = ["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"]
BASIC_OPTIONAL = [
    "前置院校",
    "入学日期",
    "学制",
    "入学方式",
    "学习形式",
    "学位类型",
    "学籍状态",
    "导师标识",
    "导师姓名",
    "研究方向",
    "学籍异动类型",
    "学籍异动时间",
]
SAFE_FIELDS = {
    "所属学院",
    "专业",
    "培养层次",
    "入学年份",
    "学制",
    "入学方式",
    "学习形式",
    "学位类型",
    "学籍状态",
    "研究方向",
    "学籍异动类型",
}


def scope(
    db: sqlite3.Connection, actor: int, op: str, payload: dict[str, object]
) -> bool:
    return allowed(
        db,
        actor,
        "basic",
        op,
        str(payload.get("所属学院", "")),
        str(payload.get("专业", "")),
    )


def masked(
    db: sqlite3.Connection, actor: int, payload: dict[str, object]
) -> dict[str, object]:
    return (
        payload
        if scope(db, actor, "identity", payload)
        else {k: v for k, v in payload.items() if k in SAFE_FIELDS}
    )


def classify_basic(
    db: sqlite3.Connection, payload: dict[str, object]
) -> tuple[str, str]:
    if any(not str(payload.get(k, "")).strip() for k in BASIC_REQUIRED):
        return "invalid", "必要字段为空"
    if not isinstance(payload["学号"], str):
        return "invalid", "学号必须为文本，避免丢失前导零"
    try:
        year = int(str(payload["入学年份"]))
        if not 1900 <= year <= 2100:
            raise ValueError
    except ValueError:
        return "invalid", "入学年份须为1900～2100的整数"
    existing = db.execute(
        "SELECT * FROM students WHERE student_number=?", (payload["学号"],)
    ).fetchone()
    if existing:
        return (
            ("duplicate", "")
            if json.loads(existing["payload"]) == payload
            else ("conflict", "身份或内容变化，需人工确认")
        )
    return "ready", ""


def register_students(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    def require_any(db: sqlite3.Connection, actor: int, operation: str) -> None:
        if not any(
            g["category"] == "basic" and g["operation"] == operation
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
        rows = []
        for record in db.execute(
            "SELECT * FROM import_rows WHERE batch_id=? ORDER BY row_number",
            (batch_id,),
        ):
            payload = json.loads(record["normalized_json"])
            if not scope(db, actor, "maintain", payload):
                raise HTTPException(403, "批次中存在当前无权维护的范围")
            rows.append(
                {
                    "id": record["id"],
                    "row_number": record["row_number"],
                    "sheet": record["sheet"],
                    "state": record["state"],
                    "error": record["error"],
                    "data": masked(db, actor, payload),
                    "student_id": record["student_id"],
                }
            )
        return {
            "id": batch_id,
            "source_department": batch["source_department"],
            "filename": batch["filename"]
            if all(
                scope(db, actor, "identity", json.loads(r["normalized_json"]))
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

    @app.get("/api/templates/basic")
    def template(request: Request, sample: bool = False) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_any(db, actor["id"], "maintain")
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.append(["AQP-PGS", "basic", "1"])
        ws.append(BASIC_REQUIRED + BASIC_OPTIONAL)
        if sample:
            ws.append(["SYN0001", "合成学生甲", "合成学院", "合成专业", "硕士", "2025"])
            ws.append(["SYN0002", "", "合成学院", "合成专业", "硕士", "2025"])
        ws.column_dimensions["A"].width = 22
        for row in range(3, 1003):
            ws.cell(row, 1).number_format = "@"
        stream = BytesIO()
        wb.save(stream)
        return Response(
            stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="basic-v1.xlsx"'},
        )

    @app.post("/api/imports/basic/preview")
    async def preview(
        request: Request,
        source_department: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_any(db, actor["id"], "maintain")
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
                if list(marker[:3]) != ["AQP-PGS", "basic", "1"]:
                    raise ValueError("模板类型或版本不符")
                if any(k not in headers for k in BASIC_REQUIRED) or len(
                    set(headers)
                ) != len(headers):
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
                    if not scope(db, actor["id"], "maintain", payload):
                        raise HTTPException(403, "文件包含无维护权限的学院或专业")
                    state, error = classify_basic(db, payload)
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
                    "basic",
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
                key = str(payload["学号"])
                if state == "ready" and key in seen:
                    state, error = (
                        ("duplicate", "")
                        if seen[key] == payload
                        else ("conflict", "同一文件中同号内容冲突")
                    )
                    if state == "conflict":
                        db.execute(
                            "UPDATE import_rows SET state='conflict',error=? WHERE batch_id=? AND json_extract(normalized_json,'$.学号')=?",
                            (error, batch_id, key),
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

    @app.get("/api/imports/{batch_id}")
    def get_batch(batch_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return batch_view(db, actor["id"], batch_id)

    @app.post("/api/imports/{batch_id}/confirm")
    def confirm(batch_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            batch_view(db, actor["id"], batch_id)
            for row in db.execute(
                "SELECT * FROM import_rows WHERE batch_id=? AND state='ready'",
                (batch_id,),
            ).fetchall():
                payload = json.loads(row["normalized_json"])
                state, error = classify_basic(db, payload)
                if state == "ready":
                    cursor = db.execute(
                        "INSERT INTO students(research_id,student_number,name,college,major,level,entry_year,payload) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            "R-" + uuid.uuid4().hex,
                            payload["学号"],
                            payload["姓名"],
                            payload["所属学院"],
                            payload["专业"],
                            payload["培养层次"],
                            int(payload["入学年份"]),
                            row["normalized_json"],
                        ),
                    )
                    student_id = cursor.lastrowid
                    db.execute(
                        "INSERT INTO student_revisions(student_id,version,payload,source_row_id,created_at,actor_id) VALUES (?,?,?,?,?,?)",
                        (
                            student_id,
                            1,
                            row["normalized_json"],
                            row["id"],
                            int(time.time()),
                            actor["id"],
                        ),
                    )
                    db.execute(
                        "UPDATE import_rows SET state='imported',student_id=? WHERE id=?",
                        (student_id, row["id"]),
                    )
                else:
                    db.execute(
                        "UPDATE import_rows SET state=?,error=? WHERE id=?",
                        (state, error, row["id"]),
                    )
            from aqp.courses import reconcile_courses

            reconcile_courses(db, actor["id"])
            db.execute("UPDATE import_batches SET confirmed=1 WHERE id=?", (batch_id,))
            audit(db, actor["id"], "import.confirm", str(batch_id))
            return batch_view(db, actor["id"], batch_id)

    def student_view(
        db: sqlite3.Connection, actor: int, row: sqlite3.Row
    ) -> dict[str, object]:
        payload = json.loads(row["payload"])
        if not scope(db, actor, "view", payload):
            raise HTTPException(404, "档案不存在或无权查看")
        result: dict[str, object] = {
            "id": row["id"],
            "research_id": row["research_id"],
            "version": row["version"],
            "data": masked(db, actor, payload),
        }
        if scope(db, actor, "identity", payload):
            result.update(student_number=row["student_number"], name=row["name"])
        return result

    @app.get("/api/students")
    def students(
        request: Request,
        major: str = "",
        level: str = "",
        entry_year: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, object]:
        if offset < 0 or not 1 <= limit <= 200:
            raise HTTPException(422, "分页范围无效")
        with connection(path) as db:
            actor, _ = current(db, request)
            require_any(db, actor["id"], "view")
            items = []
            for row in db.execute("SELECT * FROM students WHERE active=1 ORDER BY id"):
                if (
                    (major and row["major"] != major)
                    or (level and row["level"] != level)
                    or (entry_year is not None and row["entry_year"] != entry_year)
                ):
                    continue
                if scope(db, actor["id"], "view", json.loads(row["payload"])):
                    items.append(student_view(db, actor["id"], row))
            audit(db, actor["id"], "student.list", "students")
            return {"total": len(items), "items": items[offset : offset + limit]}

    @app.get("/api/students/{student_id}")
    def student(student_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            row = db.execute(
                "SELECT * FROM students WHERE id=? AND active=1", (student_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "档案不存在或无权查看")
            result = student_view(db, actor["id"], row)
            history = []
            for revision in db.execute(
                "SELECT r.*,i.batch_id,i.row_number,i.sheet,i.raw_json FROM student_revisions r JOIN import_rows i ON i.id=r.source_row_id WHERE r.student_id=?",
                (student_id,),
            ):
                history.append(
                    {
                        "version": revision["version"],
                        "batch_id": revision["batch_id"],
                        "row_number": revision["row_number"],
                        "sheet": revision["sheet"],
                        "original_row": masked(
                            db, actor["id"], json.loads(revision["raw_json"])
                        ),
                        "created_at": revision["created_at"],
                        "data": masked(
                            db, actor["id"], json.loads(revision["payload"])
                        ),
                    }
                )
            result["history"] = history
            audit(db, actor["id"], "student.detail", str(student_id))
            return result
