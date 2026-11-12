"""Independent blind-review and defense records; no candidate-label coupling."""

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.store import audit, connection


class AssessmentInput(BaseModel):
    category: Literal["blind_reviews", "defenses"]
    paper_version_id: int
    batch: str = Field(min_length=1, max_length=100)
    anonymous_code: str = Field(min_length=1, max_length=100)
    template_version: Literal["simulation-v1"] = "simulation-v1"
    scores: dict[str, float]
    comment: str = Field(max_length=10000)
    source: str = Field(min_length=1, max_length=1000)


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
            paper = db.execute(
                "SELECT p.id AS paper_version_id,p.student_id,s.college,s.major FROM paper_versions p JOIN students s ON s.id=p.student_id WHERE p.id=? AND s.active=1",
                (body.paper_version_id,),
            ).fetchone()
            if not paper or not permitted(
                db, actor["id"], {**dict(paper), "category": body.category}, "maintain"
            ):
                raise HTTPException(403, "无维护权限或学生未绑定")
            if (
                set(body.scores) != {"quality"}
                or not 0 <= body.scores["quality"] <= 100
            ):
                raise HTTPException(422, "模拟模板quality分数必须为0至100")
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
