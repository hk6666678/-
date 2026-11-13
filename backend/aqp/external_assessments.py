"""Independent blind-review and defense records; no candidate-label coupling."""

import io
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

from aqp.authorization import allowed
from aqp.store import audit, connection


class AssessmentInput(BaseModel):
    category: Literal["blind_reviews", "defenses"]
    paper_version_id: int
    batch: str = Field(min_length=1, max_length=100)
    anonymous_code: str = Field(min_length=1, max_length=100)
    template_version: str = Field(default="simulation-v1", min_length=1, max_length=100)
    scores: dict[str, float]
    comment: str = Field(max_length=10000)
    source: str = Field(min_length=1, max_length=1000)


class TemplateInput(BaseModel):
    version: str = Field(min_length=1, max_length=100)
    category: Literal["blind_reviews", "defenses"]
    college: str = Field(min_length=1, max_length=100)
    major: str = Field(min_length=1, max_length=100)
    items: dict[str, float]
    simulation: bool = True


class TemplateActivation(BaseModel):
    confirmed_by: str = Field(min_length=1, max_length=100)
    basis: str = Field(min_length=1, max_length=1000)


def register_external_assessments(
    app: FastAPI, path: Path, current: Callable[..., Any]
) -> None:
    def template(db: sqlite3.Connection, version: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM external_assessment_templates WHERE version=?", (version,)
        ).fetchone()
        return {
            "version": row["version"],
            "simulation": bool(row["simulation"]),
            "items": json.loads(row["items"]),
        }

    def permitted(db: sqlite3.Connection, actor: int, row: Any, operation: str) -> bool:
        from aqp.attachments import authorize_students

        paper = db.execute(
            "SELECT covered_student_ids FROM paper_versions WHERE id=?",
            (row["paper_version_id"],),
        ).fetchone()
        try:
            authorize_students(
                db,
                actor,
                row["category"],
                json.loads(paper["covered_student_ids"]),
                (operation,),
            )
            return True
        except HTTPException:
            return False

    @app.get("/api/external-assessments/template")
    def workbook_template(request: Request) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            book = Workbook()
            sheet = book.active
            assert sheet is not None
            sheet.title = "考核记录"
            sheet.append(list(AssessmentInput.model_fields))
            instructions = book.create_sheet("说明")
            instructions.append(
                ["模拟评分模板 simulation-v1；quality范围0至100；不代表正式业务标准"]
            )
            instructions.append(
                [
                    "category填写blind_reviews或defenses；paper_version_id填写已上传论文版本ID"
                ]
            )
            instructions.append(
                [
                    'scores填写JSON，例如 {"quality":85}；batch、anonymous_code、source必填'
                ]
            )
            output = io.BytesIO()
            book.save(output)
            audit(db, actor["id"], "external_assessment.template", "simulation-v1")
            return Response(
                output.getvalue(),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": 'attachment; filename="assessment-simulation-v1.xlsx"'
                },
            )

    @app.get("/api/external-assessments")
    def listing(request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            items = []
            for row in db.execute(
                "SELECT e.*,p.student_id,s.college,s.major,s.student_number,s.name FROM external_assessments e JOIN paper_versions p ON p.id=e.paper_version_id JOIN students s ON s.id=p.student_id WHERE s.active=1 ORDER BY e.id DESC"
            ):
                if not permitted(db, actor["id"], row, "view"):
                    continue
                item = {
                    k: row[k]
                    for k in (
                        "id",
                        "category",
                        "paper_version_id",
                        "batch",
                        "anonymous_code",
                        "template_version",
                    )
                }
                item["scores"] = json.loads(row["scores"])
                if permitted(db, actor["id"], row, "download"):
                    item["comment"] = row["comment"]
                    item["source"] = row["source"]
                if permitted(db, actor["id"], row, "identity"):
                    item.update(student_no=row["student_number"], name=row["name"])
                items.append(item)
            audit(db, actor["id"], "external_assessment.list", "external_assessments")
            return {
                "items": items,
                "count": len(items),
                "template": template(db, "simulation-v1"),
            }

    @app.post("/api/external-assessments")
    def create(body: AssessmentInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            return persist(db, actor, body)

    def persist(
        db: sqlite3.Connection, actor: Any, body: AssessmentInput
    ) -> dict[str, Any]:
        paper = db.execute(
            "SELECT p.id AS paper_version_id,p.student_id,s.college,s.major FROM paper_versions p JOIN students s ON s.id=p.student_id WHERE p.id=? AND s.active=1",
            (body.paper_version_id,),
        ).fetchone()
        if not paper or not permitted(
            db, actor["id"], {**dict(paper), "category": body.category}, "maintain"
        ):
            raise HTTPException(403, "无维护权限或学生未绑定")
        configuration = db.execute(
            "SELECT * FROM external_assessment_templates WHERE version=?",
            (body.template_version,),
        ).fetchone()
        if not configuration or configuration["state"] != "active":
            raise HTTPException(422, "评分模板未启用")
        if configuration["category"] is not None and (
            configuration["category"] != body.category
            or configuration["college"] != paper["college"]
            or configuration["major"] != paper["major"]
        ):
            raise HTTPException(422, "评分模板范围不匹配")
        limits = json.loads(configuration["items"])
        if set(body.scores) != set(limits) or any(
            not 0 <= score <= limits[key] for key, score in body.scores.items()
        ):
            raise HTTPException(422, "分项成绩与模板或评分范围不匹配")
        previous = db.execute(
            "SELECT * FROM external_assessments WHERE category=? AND paper_version_id=? AND batch=? AND anonymous_code=?",
            (body.category, body.paper_version_id, body.batch, body.anonymous_code),
        ).fetchone()
        if previous:
            if (
                all(
                    previous[k] == v
                    for k, v in body.model_dump(exclude={"scores"}).items()
                )
                and json.loads(previous["scores"]) == body.scores
            ):
                return {"id": previous["id"], "duplicate": True}
            raise HTTPException(409, "业务键已存在且内容不同，需业务确认更正")
        values = body.model_dump()
        values["scores"] = json.dumps(body.scores)
        cur = db.execute(
            "INSERT INTO external_assessments(category,paper_version_id,batch,anonymous_code,template_version,scores,comment,source,recorded_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (*values.values(), actor["id"]),
        )
        audit(db, actor["id"], "external_assessment.create", str(cur.lastrowid))
        return {"id": cur.lastrowid, "duplicate": False}

    def owned_batch(db: sqlite3.Connection, request: Request, batch_id: str) -> Any:
        actor, _ = current(db, request)
        row = db.execute(
            "SELECT * FROM assessment_import_batches WHERE id=? AND actor_id=?",
            (batch_id, actor["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "批次不存在")
        return actor, row

    @app.post("/api/external-assessments/import/preview")
    def preview(request: Request, file: UploadFile) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            try:
                book = load_workbook(file.file, read_only=True, data_only=False)
                sheet = (
                    book["考核记录"] if "考核记录" in book.sheetnames else book.active
                )
                assert sheet is not None
                values = list(sheet.values)
                if not values or list(values[0]) != list(AssessmentInput.model_fields):
                    raise ValueError("表头不匹配，请下载标准模板")
            except Exception as exc:
                raise HTTPException(422, "无法读取标准Excel模板") from exc
            rows, errors = [], []
            for number, cells in enumerate(values[1:], 2):
                if not any(v is not None for v in cells):
                    continue
                try:
                    raw: dict[str, Any] = dict(
                        zip(AssessmentInput.model_fields, cells, strict=True)
                    )
                    raw["scores"] = json.loads(raw["scores"])
                    body = AssessmentInput.model_validate(raw)
                    db.execute("SAVEPOINT preview_row")
                    try:
                        persist(db, actor, body)
                    finally:
                        db.execute("ROLLBACK TO preview_row")
                        db.execute("RELEASE preview_row")
                    rows.append(body.model_dump())
                except (ValueError, TypeError, HTTPException) as exc:
                    message = (
                        exc.detail
                        if isinstance(exc, HTTPException)
                        else "字段格式或评分无效"
                    )
                    errors.append({"row": number, "message": message})
            batch_id = str(uuid4())
            db.execute(
                "INSERT INTO assessment_import_batches(id,actor_id,rows_json,errors_json) VALUES (?,?,?,?)",
                (batch_id, actor["id"], json.dumps(rows), json.dumps(errors)),
            )
            audit(db, actor["id"], "external_assessment.preview", batch_id)
            return {"id": batch_id, "valid_count": len(rows), "errors": errors}

    @app.get("/api/external-assessments/import/{batch_id}/errors")
    def error_report(batch_id: str, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, batch = owned_batch(db, request, batch_id)
            audit(db, actor["id"], "external_assessment.errors", batch_id)
            return {"id": batch_id, "errors": json.loads(batch["errors_json"])}

    @app.post("/api/external-assessments/import/{batch_id}/confirm")
    def confirm(batch_id: str, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, batch = owned_batch(db, request, batch_id)
            if json.loads(batch["errors_json"]):
                raise HTTPException(422, "请修正错误后重新预览")
            if batch["confirmed"]:
                raise HTTPException(409, "批次已确认")
            results = [
                persist(db, actor, AssessmentInput.model_validate(row))
                for row in json.loads(batch["rows_json"])
            ]
            db.execute(
                "UPDATE assessment_import_batches SET confirmed=1 WHERE id=?",
                (batch_id,),
            )
            audit(db, actor["id"], "external_assessment.confirm", batch_id)
            return {"id": batch_id, "results": results}

    @app.get("/api/external-assessments/templates")
    def templates(request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            rows = []
            for row in db.execute(
                "SELECT * FROM external_assessment_templates ORDER BY version"
            ):
                if row["category"] is None or any(
                    allowed(
                        db,
                        actor["id"],
                        row["category"],
                        op,
                        row["college"],
                        row["major"],
                    )
                    for op in ("maintain", "view", "activate_templates")
                ):
                    rows.append({**dict(row), "items": json.loads(row["items"])})
            return {"items": rows}

    @app.post("/api/external-assessments/templates")
    def create_template(body: TemplateInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            if not allowed(
                db, actor["id"], body.category, "maintain", body.college, body.major
            ):
                raise HTTPException(403, "需要范围内维护权限")
            if not body.items or any(not 0 < v <= 10000 for v in body.items.values()):
                raise HTTPException(422, "分项上限必须大于0且不超过10000")
            if db.execute(
                "SELECT 1 FROM external_assessment_templates WHERE version=?",
                (body.version,),
            ).fetchone():
                raise HTTPException(409, "模板版本已存在，请创建新版本")
            db.execute(
                "INSERT INTO external_assessment_templates(version,simulation,items,category,college,major,created_by) VALUES (?,?,?,?,?,?,?)",
                (
                    body.version,
                    body.simulation,
                    json.dumps(body.items),
                    body.category,
                    body.college,
                    body.major,
                    actor["id"],
                ),
            )
            audit(db, actor["id"], "external_assessment.template.create", body.version)
            return {"version": body.version, "state": "draft"}

    @app.post("/api/external-assessments/templates/{version}/activate")
    def activate_template(
        version: str, body: TemplateActivation, request: Request
    ) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            row = db.execute(
                "SELECT * FROM external_assessment_templates WHERE version=?",
                (version,),
            ).fetchone()
            if (
                not row
                or not row["category"]
                or not allowed(
                    db,
                    actor["id"],
                    row["category"],
                    "activate_templates",
                    row["college"],
                    row["major"],
                )
            ):
                raise HTTPException(403, "需要独立评分模板启用权限")
            if row["state"] != "draft":
                raise HTTPException(409, "模板已启用，修改需创建新版本")
            db.execute(
                "UPDATE external_assessment_templates SET state='active',confirmed_by=?,basis=?,activated_by=?,activated_at=CURRENT_TIMESTAMP WHERE version=?",
                (body.confirmed_by, body.basis, actor["id"], version),
            )
            audit(db, actor["id"], "external_assessment.template.activate", version)
            return {"version": version, "state": "active"}
