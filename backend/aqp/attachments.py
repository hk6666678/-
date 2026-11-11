"""Immutable local file versions; all original/evidence access rechecks live grants."""

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZipFile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pypdf import PdfReader

from aqp.authorization import allowed
from aqp.store import audit, connection


def storage_root(path: Path) -> Path:
    return Path(
        os.environ.get("AQP_ATTACHMENTS", str(path.parent / "attachments"))
    ).resolve()


def authorize_students(
    db: sqlite3.Connection,
    actor: int,
    category: str,
    ids: list[int],
    operations: tuple[str, ...],
) -> None:
    """Reusable evidence boundary: require every subject and every operation."""
    if not ids:
        raise HTTPException(403, "文件涉及的学生范围未核对")
    for student_id in ids:
        student = db.execute(
            "SELECT * FROM students WHERE id=? AND active=1", (student_id,)
        ).fetchone()
        if not student or not all(
            allowed(db, actor, category, op, student["college"], student["major"])
            for op in operations
        ):
            audit(db, actor, "attachment.access", "restricted", "denied")
            db.commit()
            raise HTTPException(403, "文件涉及的全体学生范围或身份权限不足")


def validate_document(content: bytes, suffix: str) -> str:
    try:
        if suffix == ".pdf":
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted or not reader.pages:
                raise ValueError()
            return "application/pdf"
        if suffix == ".docx":
            with ZipFile(BytesIO(content)) as archive:
                if (
                    len(archive.infolist()) > 2000
                    or sum(i.file_size for i in archive.infolist()) > 40 * 1024 * 1024
                ):
                    raise ValueError()
                for name in ("[Content_Types].xml", "word/document.xml"):
                    xml = archive.read(name)
                    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                        raise ValueError()
                    ElementTree.fromstring(xml)
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    except Exception as exc:
        raise HTTPException(422, "文件不是有效的未加密PDF或DOCX") from exc
    raise HTTPException(422, "仅支持PDF、DOCX")


def read_version_blob(root: Path, row: sqlite3.Row) -> bytes:
    """Read an authorized immutable version, checking containment and integrity."""
    root = root.resolve()
    target = (root / str(row["relative_path"])).resolve()
    if target.parent != root or not target.is_file():
        raise HTTPException(404, "文件不可用")
    content = target.read_bytes()
    if hashlib.sha256(content).hexdigest() != row["sha256"]:
        raise HTTPException(409, "文件完整性校验失败")
    return content


def register_attachments(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    root = storage_root(path)

    def record(
        db: sqlite3.Connection,
        actor: int,
        milestone_id: int,
        operations: tuple[str, ...],
    ) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM milestone_records WHERE id=? AND active=1", (milestone_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "环节记录不存在")
        if row["student_id"] is None:
            raise HTTPException(409, "待关联记录须先完成身份核对")
        authorize_students(db, actor, row["category"], [row["student_id"]], operations)
        assert isinstance(row, sqlite3.Row)
        return row

    def metadata(row: sqlite3.Row) -> dict[str, object]:
        return {
            key: row[key]
            for key in (
                "id",
                "version",
                "original_filename",
                "sha256",
                "size",
                "created_at",
                "uploaded_by",
            )
        }

    @app.get("/api/milestones/{milestone_id}/attachments")
    def history(milestone_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            milestone = record(db, actor["id"], milestone_id, ("view",))
            rows = db.execute(
                "SELECT * FROM attachment_versions WHERE milestone_id=? ORDER BY version DESC",
                (milestone_id,),
            ).fetchall()
            # File names may contain identity of any person covered by the document.
            items = []
            for row in rows:
                try:
                    authorize_students(
                        db,
                        actor["id"],
                        milestone["category"],
                        json.loads(row["covered_student_ids"]),
                        ("view", "identity"),
                    )
                except HTTPException:
                    items.append(
                        {
                            "id": row["id"],
                            "version": row["version"],
                            "original_filename": "名称已脱敏",
                        }
                    )
                else:
                    items.append(metadata(row))
            audit(db, actor["id"], "attachment.history", str(milestone_id))
            return {"items": items}

    @app.post("/api/milestones/{milestone_id}/attachments")
    async def upload(
        milestone_id: int,
        request: Request,
        file: Annotated[UploadFile, File()],
        expected_version: Annotated[int, Form()],
        covered_student_ids: Annotated[str, Form()],
    ) -> dict[str, object]:
        content = await file.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(413, "文件超过20MB")
        filename = (file.filename or "").replace("\\", "/").split("/")[-1]
        if not filename or len(filename) > 200 or any(ord(c) < 32 for c in filename):
            raise HTTPException(422, "文件名无效")
        media = validate_document(content, Path(filename).suffix.lower())
        try:
            ids = json.loads(covered_student_ids)
            if (
                not isinstance(ids, list)
                or not ids
                or len(ids) > 1000
                or any(type(i) is not int for i in ids)
            ):
                raise ValueError()
            ids = sorted(set(ids))
        except (ValueError, TypeError):
            raise HTTPException(422, "请核对并填写文件涉及的全体学生ID") from None
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            milestone = record(db, actor["id"], milestone_id, ("maintain", "identity"))
            if milestone["student_id"] not in ids:
                raise HTTPException(422, "文件范围必须包含绑定学生")
            authorize_students(
                db, actor["id"], milestone["category"], ids, ("maintain", "identity")
            )
            version = db.execute(
                "SELECT COALESCE(MAX(version),0) FROM attachment_versions WHERE milestone_id=?",
                (milestone_id,),
            ).fetchone()[0]
            if version != expected_version:
                raise HTTPException(409, "附件版本已变化，请刷新历史")
            relative = uuid4().hex + Path(filename).suffix.lower()
            root.mkdir(parents=True, exist_ok=True)
            target = root / relative
            try:
                with target.open("xb") as output:
                    output.write(content)
                cursor = db.execute(
                    "INSERT INTO attachment_versions(milestone_id,version,relative_path,sha256,original_filename,media_type,size,covered_student_ids,uploaded_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        milestone_id,
                        version + 1,
                        relative,
                        hashlib.sha256(content).hexdigest(),
                        filename,
                        media,
                        len(content),
                        json.dumps(ids),
                        actor["id"],
                        int(time.time()),
                    ),
                )
                audit(
                    db,
                    actor["id"],
                    "attachment.upload",
                    str(cursor.lastrowid),
                    details={"milestone_id": milestone_id, "version": version + 1},
                )
                db.commit()
            except Exception:
                target.unlink(missing_ok=True)
                raise
            return metadata(
                db.execute(
                    "SELECT * FROM attachment_versions WHERE id=?", (cursor.lastrowid,)
                ).fetchone()
            )

    def access(version_id: int, request: Request, preview: bool) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            row = db.execute(
                "SELECT * FROM attachment_versions WHERE id=?", (version_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "文件版本不存在")
            milestone = record(
                db, actor["id"], row["milestone_id"], ("view", "identity", "download")
            )
            authorize_students(
                db,
                actor["id"],
                milestone["category"],
                json.loads(row["covered_student_ids"]),
                ("view", "identity", "download"),
            )
            content = read_version_blob(root, row)
            audit(
                db,
                actor["id"],
                "attachment.preview" if preview else "attachment.download",
                str(version_id),
            )
            if preview:
                # Render inert text; never embed an original PDF or execute document content.
                if row["media_type"] == "application/pdf":
                    text = "\n".join(
                        (p.extract_text() or "")
                        for p in PdfReader(BytesIO(content)).pages
                    )
                else:
                    with ZipFile(BytesIO(content)) as archive:
                        text = "".join(
                            ElementTree.fromstring(
                                archive.read("word/document.xml")
                            ).itertext()
                        )
                return Response(
                    text or "此文件无可提取文字，请授权下载查看。",
                    media_type="text/plain",
                    headers={
                        "X-Content-Type-Options": "nosniff",
                        "Cache-Control": "no-store",
                    },
                )
            from urllib.parse import quote

            return Response(
                content,
                media_type=row["media_type"],
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''"
                    + quote(row["original_filename"]),
                    "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "no-store",
                    "Content-Security-Policy": "sandbox; default-src 'none'",
                },
            )

    @app.get("/api/attachments/{version_id}/download")
    def download(version_id: int, request: Request) -> Response:
        return access(version_id, request, False)

    @app.get("/api/attachments/{version_id}/preview")
    def preview(version_id: int, request: Request) -> Response:
        return access(version_id, request, True)

