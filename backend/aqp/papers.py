"""Paper API: immutable originals and current authorization at every evidence read."""

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from aqp.attachments import authorize_students, read_version_blob, storage_root
from aqp.authorization import allowed
from aqp.store import audit, connection


def comparison_passages(result: dict[str, Any]) -> list[tuple[int, str, set[str]]]:
    passages: list[tuple[int, str, set[str]]] = []
    for page in result.get("pages", []):
        for line in page["text"].splitlines():
            if re.fullmatch(r"\s*(References|Bibliography|参考文献)\s*", line, re.IGNORECASE):
                return passages
            excerpt = line.strip()[:500]
            normalized = "".join(c for c in excerpt.casefold() if c.isalnum())
            if len(normalized) >= 12:
                passages.append((page["page"], excerpt, {a + b for a, b in pairwise(normalized)}))
                if len(passages) >= 120:
                    return passages
    return passages


def register_papers(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> tuple[Callable[..., dict[str, object]], Callable[..., dict[str, Any]]]:
    root = storage_root(path)

    def access(
        db: sqlite3.Connection, actor: int, row: sqlite3.Row, ops: tuple[str, ...]
    ) -> None:
        authorize_students(
            db, actor, "papers", json.loads(row["covered_student_ids"]), ops
        )

    def metadata(row: sqlite3.Row, identity: bool) -> dict[str, object]:
        result = json.loads(row["result"]) if row["result"] else None
        safe = {
            key: row[key]
            for key in (
                "id",
                "version",
                "level",
                "discipline",
                "year",
                "status",
                "failure_code",
            )
        }
        safe["semantic_features"] = "智能特征独立保存；请查看智能特征与历史依据"
        safe["features"] = (
            {
                k: result[k]
                for k in (
                    "page_count",
                    "character_count",
                    "section_count",
                    "reference_count",
                )
            }
            if result
            else None
        )
        if identity:
            safe.update(
                {
                    key: row[key]
                    for key in (
                        "student_id",
                        "title",
                        "original_filename",
                        "created_at",
                        "sha256",
                    )
                }
            )
        return safe

    @app.get("/api/papers")
    def history(request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            items = []
            for row in db.execute(
                "SELECT p.*,s.college,s.major FROM paper_versions p JOIN students s ON s.id=p.student_id WHERE s.active=1 ORDER BY p.id DESC"
            ).fetchall():
                if not allowed(
                    db, actor["id"], "papers", "view", row["college"], row["major"]
                ):
                    continue
                try:
                    access(db, actor["id"], row, ("view",))
                except HTTPException:
                    continue
                try:
                    access(db, actor["id"], row, ("view", "identity"))
                    identity = True
                except HTTPException:
                    identity = False
                items.append(metadata(row, identity))
            audit(db, actor["id"], "paper.history", "papers")
            return {"items": items}

    @app.post("/api/papers")
    async def upload(
        request: Request,
        file: Annotated[UploadFile, File()],
        student_id: Annotated[int, Form()],
        expected_version: Annotated[int, Form()],
        covered_student_ids: Annotated[str, Form()],
        title: Annotated[str, Form()],
        level: Annotated[str, Form()] = "",
        discipline: Annotated[str, Form()] = "",
        year: Annotated[str, Form()] = "",
    ) -> dict[str, object]:
        content = await file.read(20 * 1024 * 1024 + 1)
        filename = (file.filename or "").replace("\\", "/").split("/")[-1]
        if (
            not filename.lower().endswith(".pdf")
            or len(filename) > 200
            or any(ord(c) < 32 for c in filename)
        ):
            raise HTTPException(422, "仅支持PDF，文件名无效")
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(413, "文件超过20MB")
        if not title.strip() or any(
            len(v) > 500 for v in (title, level, discipline, year)
        ):
            raise HTTPException(422, "请检查论文元信息")
        try:
            ids = json.loads(covered_student_ids)
            if (
                not isinstance(ids, list)
                or not ids
                or len(ids) > 1000
                or any(type(i) is not int for i in ids)
                or student_id not in ids
            ):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(422, "请声明包含绑定学生的全体学生ID") from None
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            authorize_students(db, actor["id"], "papers", ids, ("maintain", "identity"))
            version = db.execute(
                "SELECT COALESCE(MAX(version),0) FROM paper_versions WHERE student_id=?",
                (student_id,),
            ).fetchone()[0]
            if version != expected_version:
                raise HTTPException(409, "论文版本已变化，请刷新")
            root.mkdir(parents=True, exist_ok=True)
            relative = uuid4().hex + ".pdf"
            target = root / relative
            try:
                target.write_bytes(content)
                cur = db.execute(
                    "INSERT INTO paper_versions(student_id,version,title,level,discipline,year,relative_path,sha256,original_filename,size,covered_student_ids,uploaded_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        student_id,
                        version + 1,
                        title,
                        level,
                        discipline,
                        year,
                        relative,
                        hashlib.sha256(content).hexdigest(),
                        filename,
                        len(content),
                        json.dumps(sorted(set(ids))),
                        actor["id"],
                        int(time.time()),
                    ),
                )
                db.execute(
                    "INSERT INTO paper_jobs(version_id) VALUES (?)", (cur.lastrowid,)
                )
                audit(db, actor["id"], "paper.upload", str(cur.lastrowid))
                db.commit()
            except Exception:
                target.unlink(missing_ok=True)
                raise
            return metadata(
                db.execute(
                    "SELECT * FROM paper_versions WHERE id=?", (cur.lastrowid,)
                ).fetchone(),
                True,
            )

    def record(db: sqlite3.Connection, version_id: int) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM paper_versions WHERE id=?", (version_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "论文版本不存在")
        assert isinstance(row, sqlite3.Row)
        return row

    @app.post("/api/papers/{version_id}/retry")
    def retry(version_id: int, request: Request) -> dict[str, str]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            row = record(db, version_id)
            access(db, actor["id"], row, ("maintain", "identity"))
            if row["status"] != "failed":
                raise HTTPException(409, "只有失败任务可重试")
            db.execute(
                "UPDATE paper_versions SET status='queued', failure_code=NULL WHERE id=?",
                (version_id,),
            )
            db.execute(
                "UPDATE paper_jobs SET state='queued',lease_until=0,token=NULL WHERE version_id=?",
                (version_id,),
            )
            audit(db, actor["id"], "paper.retry", str(version_id))
            return {"status": "queued"}

    @app.post("/api/papers/{version_id}/semantic")
    def semantic_extract(version_id: int, request: Request) -> dict[str, object]:
        from aqp.paper_semantics import extract

        with connection(path) as db:
            actor, _ = current(db, request)
            row = record(db, version_id)
            access(db, actor["id"], row, ("maintain", "view", "identity", "download"))
            read_version_blob(root, row)
            if row["status"] != "succeeded":
                raise HTTPException(409, "请先完成本地解析")
            # Keep authorization stable through dispatch, then recheck before delivery.
            result = extract(path, row, actor["id"])
            access(db, actor["id"], row, ("view", "identity", "download"))
            return result

    def semantic_history_for(
        db: sqlite3.Connection, actor: int, version_id: int
    ) -> dict[str, object]:
        row = record(db, version_id)
        access(db, actor, row, ("view", "identity", "download"))
        read_version_blob(root, row)
        items = [
            {**json.loads(r["result"]), "id": r["id"], "created_at": r["created_at"]}
            for r in db.execute(
                "SELECT * FROM paper_semantic_runs WHERE version_id=? ORDER BY id DESC",
                (version_id,),
            )
        ]
        audit(db, actor, "paper.semantic.history", str(version_id))
        return {"items": items}

    @app.get("/api/papers/{version_id}/semantic")
    def semantic_history(version_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return semantic_history_for(db, actor["id"], version_id)

    @app.get("/api/papers/{version_id}/evidence")
    def evidence(version_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            row = record(db, version_id)
            access(db, actor["id"], row, ("view", "identity", "download"))
            read_version_blob(root, row)
            audit(db, actor["id"], "paper.evidence", str(version_id))
            return {
                "version_id": version_id,
                "result": json.loads(row["result"]) if row["result"] else None,
            }

    @app.get("/api/papers/{version_id}/download")
    def download(version_id: int, request: Request) -> Response:
        with connection(path) as db:
            actor, _ = current(db, request)
            row = record(db, version_id)
            access(db, actor["id"], row, ("view", "identity", "download"))
            content = read_version_blob(root, row)
            audit(db, actor["id"], "paper.download", str(version_id))
            return Response(
                content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''"
                    + quote(row["original_filename"]),
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "sandbox; default-src 'none'",
                },
            )

    @app.get("/api/papers/{version_id}/classification-demo")
    def classification_demo(
        version_id: int, request: Request, model_version: str = "synthetic-logistic-v1",
    ) -> dict[str, Any]:
        from aqp.paper_classification_demo import (
            PAPER_MODEL_VERSIONS,
            classifier_artifact,
            classify_demo,
        )
        from aqp.simulation_model_artifacts import load_or_train

        with connection(path) as db:
            actor, _ = current(db, request)
            row = record(db, version_id)
            access(db, actor["id"], row, ("view", "analyze"))
            if row["status"] != "succeeded" or not row["result"]:
                raise HTTPException(409, "论文需先完成本地解析")
            if model_version not in PAPER_MODEL_VERSIONS:
                raise HTTPException(422, "未知的论文分类模型版本")
            artifact, trained_at = load_or_train(db, model_version, classifier_artifact)
            audit(db, actor["id"], "paper.classification_demo", f"{version_id}/{model_version}")
            return {**classify_demo(json.loads(row["result"]), model_version, artifact), "trained_at": trained_at}

    def text_comparison_data(db: sqlite3.Connection, actor: int, version_id: int, other_id: int) -> dict[str, Any]:
        if version_id == other_id:
            raise HTTPException(422, "请选择两个不同的论文版本")
        versions = [record(db, ident) for ident in (version_id, other_id)]
        for row in versions:
            access(db, actor, row, ("view", "identity", "download"))
            read_version_blob(root, row)
            if row["status"] != "succeeded" or not row["result"]:
                raise HTTPException(409, "两篇论文都需完成本地文字解析")
        left, right = [comparison_passages(json.loads(row["result"])) for row in versions]
        matches: list[dict[str, Any]] = []
        for left_page, left_text, left_pairs in left:
            for right_page, right_text, right_pairs in right:
                similarity = len(left_pairs & right_pairs) / len(left_pairs | right_pairs)
                if similarity >= 0.4:
                    matches.append({
                        "left": {"page": left_page, "text": left_text},
                        "right": {"page": right_page, "text": right_text},
                        "similarity": round(similarity, 3),
                    })
        matches.sort(key=lambda match: match["similarity"], reverse=True)
        audit(db, actor, "paper.text_compare", f"{version_id}/{other_id}")
        return {"matches": matches[:10], "passage_counts": [len(left), len(right)]}

    @app.get("/api/papers/{version_id}/text-comparison")
    def compare_text(version_id: int, other_id: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            return text_comparison_data(db, actor["id"], version_id, other_id)

    return semantic_history_for, text_comparison_data
