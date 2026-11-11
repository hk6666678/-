"""Pending import correction; immutable originals and explicit revision confirmation."""

import json
import time
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import BaseModel, Field

from aqp.authorization import allowed, compatible_scope
from aqp.courses import OPTIONAL, REQUIRED, classify, key, visible
from aqp.milestones import classify_milestone
from aqp.milestones import masked as milestone_masked
from aqp.store import audit, connection
from aqp.students import classify_basic, masked


class Correction(BaseModel):
    data: dict[str, str]
    evidence: str = Field(min_length=1, max_length=2000)
    version: int = 0


class Confirmation(BaseModel):
    version: int


def register_resolutions(app, path: Path, current):
    def permitted(db, actor, category, payload, op="maintain"):
        return allowed(
            db,
            actor,
            category,
            op,
            payload.get("所属学院", ""),
            payload.get("专业", ""),
        )

    def access(db, actor, row_id):
        r = db.execute(
            "SELECT i.*,b.category,b.uploaded_by FROM import_rows i JOIN import_batches b ON b.id=i.batch_id WHERE i.id=?",
            (row_id,),
        ).fetchone()
        if (
            r
            and r["uploaded_by"] == actor
            and compatible_scope(
                db, actor, r["category"], json.loads(r["normalized_json"])
            )
            and (
                not json.loads(r["normalized_json"]).get("所属学院")
                or not json.loads(r["normalized_json"]).get("专业")
            )
        ):
            return r
        if not r or not permitted(
            db, actor, r["category"], json.loads(r["normalized_json"])
        ):
            raise HTTPException(404, "记录不存在或无权处理")
        return r

    def mask(db, actor, category, p):
        if category == "basic":
            return masked(db, actor, p)
        if category == "courses":
            return visible(
                db, actor, {k: v for k, v in p.items() if k in REQUIRED + OPTIONAL}
            )
        return milestone_masked(db, actor, p, category)

    def classify_row(db, category, p, row_id):
        if category == "basic":
            return classify_basic(db, p)
        if category == "courses":
            return classify(db, p, row_id)
        return classify_milestone(db, p, category, row_id)

    def view(db, actor, batch_id):
        batch = db.execute(
            "SELECT * FROM import_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if not batch:
            raise HTTPException(404, "批次不存在")
        result = []
        for r in db.execute(
            "SELECT * FROM import_rows WHERE batch_id=? ORDER BY row_number",
            (batch_id,),
        ):
            p = json.loads(r["normalized_json"])
            if not permitted(db, actor, batch["category"], p) and not (
                batch["uploaded_by"] == actor
                and compatible_scope(db, actor, batch["category"], p)
                and (not p.get("所属学院") or not p.get("专业"))
            ):
                continue
            revisions = []
            for v in db.execute(
                "SELECT * FROM import_resolutions WHERE row_id=? ORDER BY version",
                (r["id"],),
            ):
                revisions.append(
                    {
                        "version": v["version"],
                        "data": mask(
                            db, actor, batch["category"], json.loads(v["payload"])
                        ),
                        "evidence": v["evidence"]
                        if permitted(db, actor, batch["category"], p, "identity")
                        else "依据已脱敏",
                        "actor_id": v["actor_id"],
                        "created_at": v["created_at"],
                        "state": v["state"],
                        "error": v["error"],
                        "confirmed_at": v["confirmed_at"],
                    }
                )
            result.append(
                {
                    "id": r["id"],
                    "row_number": r["row_number"],
                    "state": r["state"],
                    "error": r["error"],
                    "original": mask(
                        db, actor, batch["category"], json.loads(r["raw_json"])
                    ),
                    "data": mask(db, actor, batch["category"], p),
                    "revisions": revisions,
                }
            )
        if not result:
            raise HTTPException(404, "批次不存在或无权处理")
        return {"id": batch_id, "category": batch["category"], "rows": result}

    @app.get("/api/resolutions/{batch_id}")
    def get_batch(batch_id: int, request: Request):
        with connection(path) as db:
            actor, _ = current(db, request)
            return view(db, actor["id"], batch_id)

    @app.post("/api/resolutions/rows/{row_id}/validate")
    def validate(row_id: int, body: Correction, request: Request):
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            aid = actor["id"]
            r = access(db, aid, row_id)
            p = json.loads(r["normalized_json"])
            c = r["category"]
            if r["state"] not in ("invalid", "conflict", "ready", "pending"):
                raise HTTPException(409, "已成功或重复行不可再次提交")
            table = "course_records" if c == "courses" else "milestone_records"
            if (
                c != "basic"
                and db.execute(
                    f"SELECT 1 FROM {table} WHERE source_row_id=? AND student_id IS NOT NULL",
                    (row_id,),
                ).fetchone()
            ):
                raise HTTPException(409, "已入库记录请使用正式记录更正")
            if not permitted(db, aid, c, p, "identity") and not (
                r["uploaded_by"] == aid
                and (not p.get("所属学院") or not p.get("专业"))
                and set(body.data).issubset({"所属学院", "专业"})
            ):
                raise HTTPException(403, "纠错需要身份权限")
            if not body.evidence.strip():
                raise HTTPException(422, "请填写人工核实依据")
            candidate = {**p, **body.data}
            if set(body.data) - set(p):
                raise HTTPException(422, "未知字段")
            if not permitted(db, aid, c, candidate) or not permitted(
                db, aid, c, candidate, "identity"
            ):
                raise HTTPException(403, "修正范围未授权")
            latest = db.execute(
                "SELECT COALESCE(MAX(version),0) FROM import_resolutions WHERE row_id=?",
                (row_id,),
            ).fetchone()[0]
            if latest != body.version:
                raise HTTPException(409, "修订版本已变化")
            state, error = classify_row(db, c, candidate, row_id)
            db.execute(
                "INSERT INTO import_resolutions(row_id,version,payload,evidence,actor_id,created_at,state,error) VALUES (?,?,?,?,?,?,?,?)",
                (
                    row_id,
                    latest + 1,
                    json.dumps(candidate, ensure_ascii=False),
                    body.evidence.strip(),
                    aid,
                    int(time.time()),
                    state,
                    error,
                ),
            )
            audit(db, aid, "import.resolve.validate", str(row_id))
            return view(db, aid, r["batch_id"])

    @app.post("/api/resolutions/rows/{row_id}/confirm")
    def confirm(row_id: int, body: Confirmation, request: Request):
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            aid = actor["id"]
            r = access(db, aid, row_id)
            c = r["category"]
            v = db.execute(
                "SELECT * FROM import_resolutions WHERE row_id=? ORDER BY version DESC LIMIT 1",
                (row_id,),
            ).fetchone()
            if not v or v["version"] != body.version:
                raise HTTPException(409, "请先校验最新修订")
            if v["confirmed_at"]:
                return view(db, aid, r["batch_id"])
            if c != "basic":
                table = "course_records" if c == "courses" else "milestone_records"
                if db.execute(
                    f"SELECT 1 FROM {table} WHERE source_row_id=? AND student_id IS NOT NULL",
                    (row_id,),
                ).fetchone():
                    raise HTTPException(409, "已关联正式档案，请使用正式记录更正")
            p = json.loads(v["payload"])
            if not permitted(db, aid, c, p) or not permitted(db, aid, c, p, "identity"):
                raise HTTPException(403, "修正范围未授权")
            state, error = classify_row(db, c, p, row_id)
            if state not in ("ready", "pending"):
                raise HTTPException(409, error or "记录不可提交")
            payload = v["payload"]
            sid = None
            if c == "basic":
                cursor = db.execute(
                    "INSERT INTO students(research_id,student_number,name,college,major,level,entry_year,payload) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        "R-" + uuid.uuid4().hex,
                        p["学号"],
                        p["姓名"],
                        p["所属学院"],
                        p["专业"],
                        p["培养层次"],
                        int(p["入学年份"]),
                        payload,
                    ),
                )
                sid = cursor.lastrowid
                db.execute(
                    "INSERT INTO student_revisions(student_id,version,payload,source_row_id,created_at,actor_id) VALUES (?,1,?,?,?,?)",
                    (sid, payload, row_id, int(time.time()), aid),
                )
                state = "imported"
            else:
                s = db.execute(
                    "SELECT id FROM students WHERE student_number=?", (p["学号"],)
                ).fetchone()
                sid = s["id"] if s else None
                if c == "courses":
                    state = "linked" if sid else "pending"
                    db.execute(
                        "INSERT INTO course_records(student_number,course_code,term,attempt,student_id,payload,state,source_row_id) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(source_row_id) DO UPDATE SET student_number=excluded.student_number,course_code=excluded.course_code,term=excluded.term,attempt=excluded.attempt,student_id=excluded.student_id,payload=excluded.payload,state=excluded.state",
                        (*key(p), sid, payload, state, row_id),
                    )
                else:
                    db.execute(
                        "INSERT INTO milestone_records(category,student_number,assessment_batch,student_id,payload,source_row_id) VALUES (?,?,?,?,?,?) ON CONFLICT(source_row_id) DO UPDATE SET student_number=excluded.student_number,assessment_batch=excluded.assessment_batch,student_id=excluded.student_id,payload=excluded.payload",
                        (c, p["学号"], p["考核批次"], sid, payload, row_id),
                    )
                    state = "imported" if sid else "pending"
            db.execute(
                "UPDATE import_rows SET normalized_json=?,state=?,error=?,student_id=? WHERE id=?",
                (payload, state, "", sid, row_id),
            )
            db.execute(
                "UPDATE import_resolutions SET confirmed_at=? WHERE id=?",
                (int(time.time()), v["id"]),
            )
            from aqp.courses import reconcile_courses
            from aqp.milestones import reconcile_milestones

            reconcile_courses(db, aid)
            reconcile_milestones(db, aid)
            audit(db, aid, "import.resolve.confirm", str(row_id))
            return view(db, aid, r["batch_id"])

    @app.get("/api/resolutions/{batch_id}/errors.xlsx")
    def report(batch_id: int, request: Request):
        with connection(path) as db:
            actor, _ = current(db, request)
            aid = actor["id"]
            data = view(db, aid, batch_id)
            if not any(
                permitted(
                    db,
                    aid,
                    data["category"],
                    json.loads(
                        db.execute(
                            "SELECT normalized_json FROM import_rows WHERE id=?",
                            (r["id"],),
                        ).fetchone()[0]
                    ),
                    "export",
                )
                for r in data["rows"]
            ):
                raise HTTPException(403, "没有错误报告导出权限")
            wb = Workbook()
            ws = wb.active
            ws.append(["行号", "状态", "错误", "原始行", "当前值"])
            for r in data["rows"]:
                p = json.loads(
                    db.execute(
                        "SELECT normalized_json FROM import_rows WHERE id=?", (r["id"],)
                    ).fetchone()[0]
                )
                if not permitted(db, aid, data["category"], p, "export"):
                    continue
                if r["state"] not in ("invalid", "conflict", "pending"):
                    continue
                ws.append(
                    [
                        r["row_number"],
                        r["state"],
                        r["error"],
                        json.dumps(r["original"], ensure_ascii=False),
                        json.dumps(r["data"], ensure_ascii=False),
                    ]
                )
                for cell in ws[ws.max_row]:
                    if isinstance(cell.value, str):
                        cell.data_type = "s"
            stream = BytesIO()
            wb.save(stream)
            audit(db, aid, "import.errors.export", str(batch_id))
            return Response(
                stream.getvalue(),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": 'attachment; filename="errors.xlsx"'},
            )
