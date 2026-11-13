"""Business directories never confer account access or student bindings."""

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field, field_validator, model_validator

from aqp.authorization import allowed, student_allowed
from aqp.research_outputs import current_participant
from aqp.store import audit, connection


class DirectoryEntry(BaseModel):
    number: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    college: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    major: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")


class DirectoryUpdate(DirectoryEntry):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500, pattern=r".*\S.*")


class RelationInput(BaseModel):
    student_id: int = Field(ge=1)
    mentor_id: int = Field(ge=1)
    group_id: int = Field(ge=1)
    start_date: str
    end_date: str | None = None
    source_department: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    reason: str = Field(min_length=1, max_length=500, pattern=r".*\S.*")

    @field_validator("start_date", "end_date")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("日期必须为YYYY-MM-DD")
            date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def ordered_dates(self) -> "RelationInput":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class RelationUpdate(RelationInput):
    expected_version: int = Field(ge=1)


def relation_allowed(
    db: sqlite3.Connection, actor: int, op: str, relation: Any
) -> bool:
    student = db.execute(
        "SELECT * FROM students WHERE id=? AND active=1", (relation["student_id"],)
    ).fetchone()
    if student is None or not student_allowed(db, actor, student["id"]):
        return False
    scopes = [student]
    for table, key in [
        ("mentor_directory", "mentor_id"),
        ("research_groups", "group_id"),
    ]:
        row = db.execute(
            f"SELECT * FROM {table} WHERE id=?", (relation[key],)
        ).fetchone()
        if row is None:
            return False
        scopes.append(row)
    return all(
        allowed(db, actor, "mentor_groups", op, scope["college"], scope["major"])
        for scope in scopes
    )


def register_mentor_groups(
    app: FastAPI, path: Path, current: Callable[..., Any]
) -> None:
    tables = {
        "mentors": ("mentor_directory", "mentor_number"),
        "groups": ("research_groups", "group_number"),
    }

    @app.get("/api/mentor-groups/students")
    def student_options(request: Request) -> list[dict[str, Any]]:
        with connection(path) as db:
            actor, _ = current(db, request)
            result = []
            for row in db.execute("SELECT * FROM students WHERE active=1 ORDER BY id"):
                if not student_allowed(db, actor["id"], row["id"]) or not allowed(
                    db,
                    actor["id"],
                    "mentor_groups",
                    "view",
                    row["college"],
                    row["major"],
                ):
                    continue
                identity = allowed(
                    db,
                    actor["id"],
                    "mentor_groups",
                    "identity",
                    row["college"],
                    row["major"],
                )
                result.append(
                    {
                        "id": row["id"],
                        "label": f"{row['student_number']} · {row['name']}"
                        if identity
                        else row["research_id"],
                    }
                )
            return result

    @app.get("/api/mentor-groups/directory/{kind}")
    def directory(
        kind: Literal["mentors", "groups"], request: Request
    ) -> list[dict[str, Any]]:
        table, number = tables[kind]
        with connection(path) as db:
            actor, _ = current(db, request)
            result = []
            for row in db.execute(f"SELECT * FROM {table} ORDER BY id"):
                if not allowed(
                    db,
                    actor["id"],
                    "mentor_groups",
                    "view",
                    row["college"],
                    row["major"],
                ):
                    continue
                item = dict(row)
                if not allowed(
                    db,
                    actor["id"],
                    "mentor_groups",
                    "identity",
                    row["college"],
                    row["major"],
                ):
                    item.pop("name")
                    item.pop(number)
                    item.pop("user_id", None)
                result.append(item)
            return result

    @app.post("/api/mentor-groups/directory/{kind}")
    def create_entry(
        kind: Literal["mentors", "groups"], body: DirectoryEntry, request: Request
    ) -> dict[str, int]:
        table, number = tables[kind]
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            if not allowed(
                db, actor["id"], "mentor_groups", "maintain", body.college, body.major
            ):
                raise HTTPException(403, "缺少导师课题组维护权限")
            try:
                cursor = db.execute(
                    f"INSERT INTO {table}({number},name,college,major) VALUES (?,?,?,?)",
                    (body.number, body.name, body.college, body.major),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, "业务编号已存在") from exc
            assert cursor.lastrowid is not None
            audit(
                db,
                actor["id"],
                "mentor_groups.directory.create",
                f"{kind}:{cursor.lastrowid}",
            )
            return {"id": cursor.lastrowid, "version": 1}

    def save_relation(
        db: sqlite3.Connection,
        actor: int,
        body: RelationInput,
        relation_id: int | None = None,
    ) -> dict[str, int]:
        data = body.model_dump(exclude={"reason", "expected_version"})
        if not relation_allowed(db, actor, "maintain", data):
            raise HTTPException(403, "缺少目录或学生当前范围的维护权限")
        version = 1
        if relation_id is not None:
            old = db.execute(
                "SELECT * FROM mentor_group_relations WHERE id=?", (relation_id,)
            ).fetchone()
            if old is None or not relation_allowed(db, actor, "maintain", old):
                raise HTTPException(404, "关系不存在或无权维护")
            if (
                not isinstance(body, RelationUpdate)
                or body.expected_version != old["version"]
            ):
                raise HTTPException(409, "关系版本已变化，请重新加载")
            version = old["version"] + 1
        overlap = db.execute(
            "SELECT id FROM mentor_group_relations WHERE student_id=? AND mentor_id=? AND group_id=? AND id!=? AND start_date<=? AND COALESCE(end_date,'9999-12-31')>=?",
            (
                body.student_id,
                body.mentor_id,
                body.group_id,
                relation_id or -1,
                body.end_date or "9999-12-31",
                body.start_date,
            ),
        ).fetchone()
        if overlap:
            raise HTTPException(409, "同学生、导师与课题组的日期重叠，需人工确认")
        if relation_id is None:
            cursor = db.execute(
                "INSERT INTO mentor_group_relations(student_id,mentor_id,group_id,start_date,end_date,source_department) VALUES (?,?,?,?,?,?)",
                tuple(data.values()),
            )
            assert cursor.lastrowid is not None
            relation_id = cursor.lastrowid
        else:
            db.execute(
                "UPDATE mentor_group_relations SET student_id=?,mentor_id=?,group_id=?,start_date=?,end_date=?,source_department=?,version=? WHERE id=?",
                (*data.values(), version, relation_id),
            )
        db.execute(
            "INSERT INTO mentor_group_history(relation_id,version,payload,actor_id,reason) VALUES (?,?,?,?,?)",
            (relation_id, version, json.dumps(data), actor, body.reason),
        )
        audit(
            db,
            actor,
            "mentor_groups.relation.save",
            str(relation_id),
            details={"version": version, "reason": body.reason},
        )
        return {"id": relation_id, "version": version}

    @app.post("/api/mentor-groups/relations")
    def create_relation(body: RelationInput, request: Request) -> dict[str, int]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            return save_relation(db, actor["id"], body)

    @app.put("/api/mentor-groups/relations/{relation_id}")
    def update_relation(
        relation_id: int, body: RelationUpdate, request: Request
    ) -> dict[str, int]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            return save_relation(db, actor["id"], body, relation_id)

    def visible_relation(
        db: sqlite3.Connection, actor: int, row: Any
    ) -> dict[str, Any]:
        item = dict(row)
        if not relation_allowed(db, actor, "identity", row):
            item.pop("student_id", None)
        return item

    @app.get("/api/mentor-groups/relations")
    def relations(request: Request, as_of: date | None = None) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            rows = [
                visible_relation(db, actor["id"], row)
                for row in db.execute(
                    "SELECT * FROM mentor_group_relations ORDER BY id"
                )
                if relation_allowed(db, actor["id"], "view", row)
                and (
                    as_of is None
                    or row["start_date"]
                    <= as_of.isoformat()
                    <= (row["end_date"] or "9999-12-31")
                )
            ]
            return {"items": rows}

    @app.get("/api/mentor-groups/relations/{relation_id}/history")
    def history(relation_id: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            current_row = db.execute(
                "SELECT * FROM mentor_group_relations WHERE id=?", (relation_id,)
            ).fetchone()
            if current_row is None or not relation_allowed(
                db, actor["id"], "view", current_row
            ):
                raise HTTPException(404, "关系不存在或无权查看")
            items = []
            for row in db.execute(
                "SELECT * FROM mentor_group_history WHERE relation_id=? ORDER BY version",
                (relation_id,),
            ):
                data = json.loads(row["payload"])
                if relation_allowed(db, actor["id"], "view", data):
                    items.append(
                        {
                            "version": row["version"],
                            "data": visible_relation(db, actor["id"], data),
                            "reason": row["reason"],
                            "created_at": row["created_at"],
                        }
                    )
            return {"items": items}

    @app.get("/api/mentor-groups/facts")
    def facts(
        request: Request,
        as_of: date,
        mentor_id: int | None = None,
        group_id: int | None = None,
    ) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            students: dict[int, sqlite3.Row] = {}
            relation_ids = []
            for row in db.execute("SELECT * FROM mentor_group_relations ORDER BY id"):
                if (mentor_id is not None and mentor_id != row["mentor_id"]) or (
                    group_id is not None and group_id != row["group_id"]
                ):
                    continue
                if not (
                    row["start_date"]
                    <= as_of.isoformat()
                    <= (row["end_date"] or "9999-12-31")
                ):
                    continue
                if not relation_allowed(
                    db, actor["id"], "view", row
                ) or not relation_allowed(db, actor["id"], "analyze", row):
                    continue
                student = db.execute(
                    "SELECT * FROM students WHERE id=? AND active=1",
                    (row["student_id"],),
                ).fetchone()
                assert student is not None
                students[student["id"]] = student
                relation_ids.append(row["id"])
            categories = {}
            for category, table in [
                ("research_papers", "research"),
                ("patents", "patents"),
                ("awards", "awards"),
                ("conferences", "conferences"),
            ]:
                participants: set[int] = set()
                outputs = []
                for output in db.execute(
                    f"SELECT * FROM {table}_outputs WHERE active=1"
                ):
                    payload = json.loads(output["payload"])
                    output_students: set[int] = set()
                    for participant in payload["participants"]:
                        viewable, student = current_participant(
                            db, actor["id"], category, "view", participant
                        )
                        analyzable, _ = current_participant(
                            db, actor["id"], category, "analyze", participant
                        )
                        if (
                            viewable
                            and analyzable
                            and student is not None
                            and student["id"] in students
                        ):
                            output_students.add(student["id"])
                    if output_students:
                        participants.update(output_students)
                        outputs.append(
                            {
                                "id": output["id"],
                                "version": output["version"],
                                "business_key": output["business_key"],
                                "title": payload["title"],
                                "participant_count": len(output_students),
                            }
                        )
                categories[category] = {
                    "student_count": len(participants),
                    "distinct_outputs": len(outputs),
                    "items": outputs,
                }
            return {
                "as_of": as_of.isoformat(),
                "student_count": len(students),
                "relation_ids": relation_ids,
                "categories": categories,
                "graduation": {
                    "status": "missing",
                    "reason": "缺少已确认的毕业口径与完整毕业事实",
                },
                "delay": {
                    "status": "missing",
                    "reason": "缺少应毕业日期与已确认的延期口径",
                },
                "basis": "指定日期有效关系；学生按当前授权去重；成果按当前有效业务记录去重，参与者须匹配当前学生身份与院系专业并具有对应查看及分析权限。关系日期不代表成果发生日期，不作优劣排名。",
            }

    @app.put("/api/mentor-groups/directory/{kind}/{entry_id}")
    def update_entry(
        kind: Literal["mentors", "groups"],
        entry_id: int,
        body: DirectoryUpdate,
        request: Request,
    ) -> dict[str, int]:
        table, number = tables[kind]
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            old = db.execute(
                f"SELECT * FROM {table} WHERE id=?", (entry_id,)
            ).fetchone()
            if old is None or not allowed(
                db,
                actor["id"],
                "mentor_groups",
                "maintain",
                old["college"],
                old["major"],
            ):
                raise HTTPException(404, "目录不存在或无权维护")
            if not allowed(
                db, actor["id"], "mentor_groups", "maintain", body.college, body.major
            ):
                raise HTTPException(403, "缺少目标院系专业维护权限")
            if old["version"] != body.expected_version:
                raise HTTPException(409, "目录版本已变化")
            try:
                db.execute(
                    f"UPDATE {table} SET {number}=?,name=?,college=?,major=?,version=version+1 WHERE id=?",
                    (body.number, body.name, body.college, body.major, entry_id),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, "业务编号已存在") from exc
            audit(
                db,
                actor["id"],
                "mentor_groups.directory.update",
                f"{kind}:{entry_id}",
                details={
                    "before": dict(old),
                    "after": body.model_dump(),
                    "version": old["version"] + 1,
                },
            )
            return {"id": entry_id, "version": old["version"] + 1}

    headers_by_kind = {
        "mentors": ["导师业务编号", "导师姓名", "所属学院", "专业"],
        "groups": ["课题组编号", "课题组名称", "所属学院", "专业"],
        "relations": [
            "学号",
            "导师业务编号",
            "课题组编号",
            "开始日期",
            "结束日期",
            "来源部门",
            "说明",
        ],
    }

    @app.get("/api/mentor-groups/templates/{kind}")
    def template(
        kind: Literal["mentors", "groups", "relations"], request: Request
    ) -> Response:
        with connection(path) as db:
            current(db, request)
        book = Workbook()
        sheet = book.active
        assert sheet is not None
        sheet.append(["AQP-PGS", "mentor_groups", kind, "1"])
        sheet.append(headers_by_kind[kind])
        stream = BytesIO()
        book.save(stream)
        return Response(
            stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="mentor-groups-{kind}.xlsx"'
            },
        )

    @app.post("/api/mentor-groups/import/{kind}")
    async def import_excel(
        kind: Literal["mentors", "groups", "relations"],
        request: Request,
        file: Annotated[UploadFile, File()],
        source_department: Annotated[str, Form(min_length=1, max_length=100)],
        dry_run: Annotated[bool, Form()] = True,
        preview_id: Annotated[int | None, Form()] = None,
    ) -> dict[str, Any]:
        raw = await file.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            raise HTTPException(413, "文件超过5MB")
        try:
            book = load_workbook(BytesIO(raw), read_only=True, data_only=False)
            sheet = book.active
            assert sheet is not None
            rows = list(sheet.values)
            if (
                list(rows[0])[:4] != ["AQP-PGS", "mentor_groups", kind, "1"]
                or list(rows[1]) != headers_by_kind[kind]
            ):
                raise ValueError("模板版本或列名不匹配")
            records: list[tuple[int, list[str]]] = []
            for index, row in enumerate(rows[2:], 3):
                if not any(value is not None for value in row):
                    continue
                if len(records) >= 2000:
                    raise ValueError("每次最多2000行")
                values = [
                    str(value).strip() if value is not None else "" for value in row
                ]
                if any(value.startswith("=") for value in values):
                    raise ValueError(f"第{index}行含公式")
                records.append((index, values))
        except Exception as exc:
            raise HTTPException(422, "Excel无法读取或模板不匹配") from exc
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            state = json.dumps(
                {
                    table: [
                        dict(row)
                        for row in db.execute(f"SELECT * FROM {table} ORDER BY id")
                    ]
                    for table in [
                        "students",
                        "mentor_directory",
                        "research_groups",
                        "mentor_group_relations",
                    ]
                },
                sort_keys=True,
            )
            if not dry_run:
                preview = db.execute(
                    "SELECT * FROM mentor_group_imports WHERE id=? AND actor_id=? AND kind=?",
                    (preview_id, actor["id"], kind),
                ).fetchone()
                if (
                    preview is None
                    or preview["confirmed"]
                    or preview["original_file"] != raw
                    or preview["source_department"] != source_department
                    or preview["state"] != state
                ):
                    raise HTTPException(
                        409, "预览不存在、已确认或数据已变化，请重新预览"
                    )
            db.execute("SAVEPOINT imported_rows")
            imported = []
            for row_number, values in records:
                try:
                    if kind == "relations":
                        student = db.execute(
                            "SELECT id FROM students WHERE student_number=? AND active=1",
                            (values[0],),
                        ).fetchone()
                        mentor = db.execute(
                            "SELECT id FROM mentor_directory WHERE mentor_number=?",
                            (values[1],),
                        ).fetchone()
                        group = db.execute(
                            "SELECT id FROM research_groups WHERE group_number=?",
                            (values[2],),
                        ).fetchone()
                        if student is None or mentor is None or group is None:
                            raise HTTPException(422, "学生或目录编号不存在")
                        body = RelationInput(
                            student_id=student["id"],
                            mentor_id=mentor["id"],
                            group_id=group["id"],
                            start_date=values[3],
                            end_date=values[4] or None,
                            source_department=values[5] or source_department,
                            reason=values[6],
                        )
                        imported.append(save_relation(db, actor["id"], body))
                    else:
                        entry = DirectoryEntry(
                            number=values[0],
                            name=values[1],
                            college=values[2],
                            major=values[3],
                        )
                        if not allowed(
                            db,
                            actor["id"],
                            "mentor_groups",
                            "maintain",
                            entry.college,
                            entry.major,
                        ):
                            raise HTTPException(403, "缺少目录维护权限")
                        table, number = tables[kind]
                        cursor = db.execute(
                            f"INSERT INTO {table}({number},name,college,major) VALUES (?,?,?,?)",
                            (entry.number, entry.name, entry.college, entry.major),
                        )
                        assert cursor.lastrowid is not None
                        imported.append({"id": cursor.lastrowid, "version": 1})
                except HTTPException as exc:
                    raise HTTPException(
                        exc.status_code, f"第{row_number}行：{exc.detail}"
                    ) from exc
                except (ValueError, sqlite3.IntegrityError, IndexError) as exc:
                    raise HTTPException(
                        409,
                        f"第{row_number}行无效或编号已存在，请核对后重试；整批未写入",
                    ) from exc
            if dry_run:
                db.execute("ROLLBACK TO imported_rows")
                db.execute("RELEASE imported_rows")
                cursor = db.execute(
                    "INSERT INTO mentor_group_imports(actor_id,kind,source_department,original_file,state) VALUES (?,?,?,?,?)",
                    (actor["id"], kind, source_department, raw, state),
                )
                audit(
                    db,
                    actor["id"],
                    "mentor_groups.import.preview",
                    str(cursor.lastrowid),
                    details={
                        "kind": kind,
                        "source_department": source_department,
                        "rows": len(imported),
                    },
                )
                return {
                    "id": cursor.lastrowid,
                    "row_count": len(imported),
                    "source_department": source_department,
                    "status": "ready",
                    "items": [],
                }
            db.execute("RELEASE imported_rows")
            db.execute(
                "UPDATE mentor_group_imports SET confirmed=1 WHERE id=?", (preview_id,)
            )
            audit(
                db,
                actor["id"],
                "mentor_groups.import",
                kind,
                details={
                    "source_department": source_department,
                    "rows": len(imported),
                    "batch_id": preview_id,
                    "items": imported,
                },
            )
            return {"items": imported, "source_department": source_department}

    @app.post("/api/mentor-groups/previews/{preview_id}/confirm")
    async def confirm_import(preview_id: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            preview = db.execute(
                "SELECT * FROM mentor_group_imports WHERE id=? AND actor_id=?",
                (preview_id, actor["id"]),
            ).fetchone()
            if preview is None:
                raise HTTPException(404, "预览不存在")
            kind = preview["kind"]
            source = preview["source_department"]
            raw = preview["original_file"]
        return await import_excel(
            kind,
            request,
            UploadFile(BytesIO(raw), filename="preview.xlsx"),
            source,
            False,
            preview_id,
        )
