"""Published research outputs are independent of degree-paper samples."""

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any
from zipfile import BadZipFile

from fastapi import FastAPI, Request
from fastapi.responses import Response

from aqp.authorization import allowed, student_allowed
from aqp.store import connection


def register_research_outputs(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    @app.get("/api/research-outputs")
    def listing(request: Request, voided: bool = False) -> dict[str, Any]:
        with connection(path) as db:
            user, _ = current(db, request)
            items = []
            count = 0
            for row in db.execute(
                "SELECT * FROM research_outputs WHERE active=?", (0 if voided else 1,)
            ):
                payload = json.loads(row["payload"])
                participants = []
                for participant in payload["participants"]:
                    student = db.execute(
                        "SELECT id,college,major,name FROM students WHERE student_number=? AND active=1",
                        (participant["student_number"],),
                    ).fetchone()
                    if not student_allowed(
                        db, user["id"], student["id"] if student else None
                    ):
                        continue
                    if not allowed(
                        db,
                        user["id"],
                        "research_papers",
                        "view",
                        participant["college"],
                        participant["major"],
                    ):
                        continue
                    if student and (
                        not allowed(
                            db,
                            user["id"],
                            "research_papers",
                            "view",
                            student["college"],
                            student["major"],
                        )
                        or student["college"] != participant["college"]
                        or student["major"] != participant["major"]
                        or student["name"] != participant["name"]
                    ):
                        continue
                    visible = dict(participant)
                    visible["association"] = "linked" if student else "pending"
                    if not allowed(
                        db,
                        user["id"],
                        "research_papers",
                        "identity",
                        participant["college"],
                        participant["major"],
                    ):
                        visible.pop("student_number", None)
                        visible.pop("name", None)
                    participants.append(visible)
                if participants:
                    count += len(participants)
                    items.append(
                        {
                            "id": row["id"],
                            "version": row["version"],
                            "business_key": row["business_key"],
                            "title": payload["title"],
                            "participants": participants,
                        }
                    )
            return {
                "items": items,
                "personal_participations": 0 if voided else count,
                "distinct_outputs": 0 if voided else len(items),
            }

    @app.get("/api/research-outputs/template")
    def template(request: Request) -> Response:
        from io import BytesIO

        from fastapi.responses import Response
        from openpyxl import Workbook

        with connection(path) as db:
            current(db, request)
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.append(["AQP-PGS", "research_papers", "1"])
        ws.append(
            [
                "业务编号/DOI",
                "论文标题",
                "学号",
                "姓名",
                "作者次序",
                "参与角色",
                "所属学院",
                "专业",
            ]
        )
        stream = BytesIO()
        wb.save(stream)
        return Response(
            stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=research_papers-v1.xlsx"
            },
        )

    from fastapi import Body, File, Form, HTTPException, UploadFile

    from aqp.store import audit

    def maintain(
        db: sqlite3.Connection,
        actor: int,
        payload: dict[str, Any],
        *,
        historical: bool = False,
    ) -> None:
        for participant in payload["participants"]:
            student = db.execute(
                "SELECT id,college,major,name FROM students WHERE student_number=? AND active=1",
                (participant["student_number"],),
            ).fetchone()
            if (
                student
                and not historical
                and (
                    student["college"] != participant["college"]
                    or student["major"] != participant["major"]
                    or student["name"] != participant["name"]
                )
            ):
                raise HTTPException(409, "学生身份或当前学院专业冲突，请纠正后预览")
            if not student_allowed(
                db, actor, student["id"] if student else None
            ) or not allowed(
                db,
                actor,
                "research_papers",
                "maintain",
                participant["college"],
                participant["major"],
            ):
                raise HTTPException(403, "缺少全部参与者维护范围")
            if student and not allowed(
                db,
                actor,
                "research_papers",
                "maintain",
                student["college"],
                student["major"],
            ):
                raise HTTPException(403, "缺少参与者当前学院维护范围")

    @app.post("/api/research-outputs/preview")
    async def preview(
        request: Request,
        file: Annotated[UploadFile, File()],
        source_department: Annotated[str, Form()],
    ) -> dict[str, Any]:
        from io import BytesIO
        from uuid import uuid4

        from openpyxl import load_workbook

        raw = await file.read(8_000_001)
        if len(raw) > 8_000_000 or not source_department.strip():
            raise HTTPException(422, "文件过大或来源部门为空")
        try:
            wb = load_workbook(BytesIO(raw), read_only=True, data_only=True)
            ws = wb.active
            if ws is None:
                raise ValueError()
            rows = iter(ws.values)
            if tuple(next(rows))[:3] != ("AQP-PGS", "research_papers", "1"):
                raise ValueError()
            if tuple(next(rows)) != (
                "业务编号/DOI",
                "论文标题",
                "学号",
                "姓名",
                "作者次序",
                "参与角色",
                "所属学院",
                "专业",
            ):
                raise ValueError()
            grouped: dict[str, Any] = {}
            for row in rows:
                if all(value is None for value in row):
                    continue
                key, title, number, name, order, role, college, major = [
                    str(value or "").strip() for value in row
                ]
                key = key.lower().removeprefix("https://doi.org/").removeprefix("doi:")
                if (
                    not all([key, title, number, name, role, college, major])
                    or int(order) < 1
                ):
                    raise ValueError()
                output = grouped.setdefault(key, {"title": title, "participants": []})
                if output["title"] != title or any(
                    p["student_number"] == number or p["order"] == int(order)
                    for p in output["participants"]
                ):
                    raise ValueError()
                output["participants"].append(
                    {
                        "student_number": number,
                        "name": name,
                        "order": int(order),
                        "role": role,
                        "college": college,
                        "major": major,
                    }
                )
                if len(grouped) > 5000:
                    raise ValueError()
        except (ValueError, TypeError, StopIteration, BadZipFile, KeyError):
            raise HTTPException(422, "模板版本、字段或参与者次序无效") from None
        with connection(path) as db:
            actor, _ = current(db, request)
            items = []
            for key, payload in grouped.items():
                payload["participants"].sort(key=lambda p: p["order"])
                maintain(db, actor["id"], payload)
                old = db.execute(
                    "SELECT * FROM research_outputs WHERE business_key=?", (key,)
                ).fetchone()
                if old:
                    maintain(
                        db, actor["id"], json.loads(old["payload"]), historical=True
                    )
                    if not old["active"]:
                        raise HTTPException(409, "业务编号已有作废历史，不可重新导入")
                items.append(
                    {
                        "business_key": key,
                        "payload": payload,
                        "expected_version": old["version"] if old else 0,
                        "status": "duplicate"
                        if old and json.loads(old["payload"]) == payload
                        else "change"
                        if old
                        else "new",
                    }
                )
            identifier = str(uuid4())
            db.execute(
                "INSERT INTO research_output_previews(id,actor_id,payload) VALUES (?,?,?)",
                (
                    identifier,
                    actor["id"],
                    json.dumps(
                        {"items": items, "source_department": source_department},
                        ensure_ascii=False,
                    ),
                ),
            )
            audit(
                db,
                actor["id"],
                "research_outputs.preview",
                identifier,
                details={"outputs": len(items)},
            )
            return {"id": identifier, "items": items}

    @app.post("/api/research-outputs/previews/{identifier}/confirm")
    def confirm(
        identifier: str, request: Request, body: Annotated[dict[str, Any], Body()]
    ) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            batch = db.execute(
                "SELECT * FROM research_output_previews WHERE id=? AND actor_id=?",
                (identifier, actor["id"]),
            ).fetchone()
            if not batch:
                raise HTTPException(404, "预览不存在")
            saved = json.loads(batch["payload"])
            for item in saved["items"]:
                maintain(db, actor["id"], item["payload"])
            if batch["confirmed"]:
                return {"confirmed": True}
            for item in saved["items"]:
                old = db.execute(
                    "SELECT * FROM research_outputs WHERE business_key=?",
                    (item["business_key"],),
                ).fetchone()
                if old:
                    maintain(
                        db, actor["id"], json.loads(old["payload"]), historical=True
                    )
                    if not old["active"]:
                        raise HTTPException(409, "业务编号已有作废历史，不可重新导入")
                if (old["version"] if old else 0) != item["expected_version"]:
                    raise HTTPException(409, "成果已变化，请重新预览")
                if item["status"] == "duplicate":
                    continue
                if (
                    item["status"] == "change"
                    and body.get("accept_changes") is not True
                ):
                    raise HTTPException(409, "需明确确认变更")
                payload = json.dumps(item["payload"], ensure_ascii=False)
                version = item["expected_version"] + 1
                if old:
                    db.execute(
                        "UPDATE research_outputs SET payload=?,version=? WHERE id=?",
                        (payload, version, old["id"]),
                    )
                    output_id = old["id"]
                else:
                    output_id = db.execute(
                        "INSERT INTO research_outputs(business_key,payload) VALUES (?,?)",
                        (item["business_key"], payload),
                    ).lastrowid
                db.execute(
                    "INSERT INTO research_output_versions VALUES (?,?,?,?,?)",
                    (
                        output_id,
                        version,
                        payload,
                        saved["source_department"],
                        actor["id"],
                    ),
                )
                audit(
                    db,
                    actor["id"],
                    "research_outputs.confirm",
                    str(output_id),
                    details={
                        "version": version,
                        "source_department": saved["source_department"],
                    },
                )
            db.execute(
                "UPDATE research_output_previews SET confirmed=1 WHERE id=?",
                (identifier,),
            )
            return {"confirmed": True}

    @app.post("/api/research-outputs/{output_id}/void")
    def void(
        output_id: int, request: Request, body: Annotated[dict[str, Any], Body()]
    ) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            output = db.execute(
                "SELECT * FROM research_outputs WHERE id=?", (output_id,)
            ).fetchone()
            if not output:
                raise HTTPException(404, "成果不存在")
            payload = json.loads(output["payload"])
            maintain(db, actor["id"], payload, historical=True)
            for participant in payload["participants"]:
                if not allowed(
                    db,
                    actor["id"],
                    "research_papers",
                    "void",
                    participant["college"],
                    participant["major"],
                ):
                    raise HTTPException(403, "缺少全部参与者作废权限")
                student = db.execute(
                    "SELECT college,major FROM students WHERE student_number=? AND active=1",
                    (participant["student_number"],),
                ).fetchone()
                if student and not allowed(
                    db,
                    actor["id"],
                    "research_papers",
                    "void",
                    student["college"],
                    student["major"],
                ):
                    raise HTTPException(403, "缺少参与者当前学院作废权限")
            if (
                body.get("expected_version") != output["version"]
                or not output["active"]
            ):
                raise HTTPException(409, "成果已变化，请刷新")
            reason = body.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise HTTPException(422, "请填写作废依据")
            payload["void_reason"] = reason.strip()
            version = output["version"] + 1
            serialized = json.dumps(payload, ensure_ascii=False)
            source = db.execute(
                "SELECT source_department FROM research_output_versions WHERE output_id=? ORDER BY version DESC LIMIT 1",
                (output_id,),
            ).fetchone()[0]
            db.execute(
                "UPDATE research_outputs SET active=0,version=?,payload=? WHERE id=?",
                (version, serialized, output_id),
            )
            db.execute(
                "INSERT INTO research_output_versions VALUES (?,?,?,?,?)",
                (output_id, version, serialized, source, actor["id"]),
            )
            audit(
                db,
                actor["id"],
                "research_outputs.void",
                str(output_id),
                details={"version": version, "reason": reason.strip()},
            )
            return {"voided": True, "version": version}

    @app.get("/api/research-outputs/{output_id}/history")
    def history(output_id: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            output = db.execute(
                "SELECT * FROM research_outputs WHERE id=?", (output_id,)
            ).fetchone()
            if not output:
                raise HTTPException(404, "成果不存在")
            versions = []
            for row in db.execute(
                "SELECT version,payload,source_department FROM research_output_versions WHERE output_id=? ORDER BY version",
                (output_id,),
            ):
                payload = json.loads(row["payload"])
                for participant in payload["participants"]:
                    student = db.execute(
                        "SELECT * FROM students WHERE student_number=? AND active=1",
                        (participant["student_number"],),
                    ).fetchone()
                    if not student_allowed(
                        db, actor["id"], student["id"] if student else None
                    ):
                        raise HTTPException(403, "历史包含范围外参与者")
                    for operation in ["view", "identity"]:
                        if not allowed(
                            db,
                            actor["id"],
                            "research_papers",
                            operation,
                            participant["college"],
                            participant["major"],
                        ) or (
                            student
                            and not allowed(
                                db,
                                actor["id"],
                                "research_papers",
                                operation,
                                student["college"],
                                student["major"],
                            )
                        ):
                            raise HTTPException(403, "历史包含范围外参与者")
                versions.append(
                    {
                        "version": row["version"],
                        "payload": payload,
                        "source_department": row["source_department"],
                    }
                )
            return {"items": versions}
