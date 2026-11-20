import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.accounts import PASSWORDS, require_admin
from aqp.store import audit, connection


class BindingUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    request_id: str = Field(min_length=16, max_length=64)
    student_bindings: list[str] = Field(max_length=200)


def student_bindings_for(db: sqlite3.Connection, user_id: int) -> list[str]:
    return [
        row["research_id"]
        for row in db.execute(
            "SELECT s.research_id FROM user_student_bindings b JOIN students s ON s.id=b.student_id WHERE b.user_id=? ORDER BY s.research_id",
            (user_id,),
        )
    ]


def register_student_bindings(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    @app.get("/api/users/{user_id}/student_bindings")
    def user_student_bindings(user_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_admin(actor)
            target = db.execute(
                "SELECT version FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if target is None:
                raise HTTPException(404, "账号不存在")
            return {
                "version": target["version"],
                "student_bindings": student_bindings_for(db, user_id),
            }

    @app.put("/api/users/{user_id}/student_bindings")
    def replace_student_bindings(
        user_id: int, body: BindingUpdate, request: Request
    ) -> dict[str, object]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            require_admin(actor)
            fingerprint = f"student_bindings:{user_id}:" + body.model_dump_json()
            previous = db.execute(
                "SELECT * FROM account_mutations WHERE actor_id=? AND request_id=?",
                (actor["id"], body.request_id),
            ).fetchone()
            if previous:
                if not PASSWORDS.verify(fingerprint, previous["fingerprint"]):
                    raise HTTPException(409, "重试标识已用于不同操作")
                result: dict[str, object] = json.loads(previous["response"])
                return result
            target = db.execute(
                "SELECT version FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if target is None:
                raise HTTPException(404, "账号不存在")
            if target["version"] != body.expected_version:
                raise HTTPException(409, "授权已变化，请重新加载后修改")
            students = {
                row["research_id"]: row["id"]
                for row in db.execute(
                    "SELECT id,research_id FROM students WHERE active=1"
                )
            }
            if len(set(body.student_bindings)) != len(body.student_bindings):
                raise HTTPException(422, "学生研究编号不得重复")
            if any(value not in students for value in body.student_bindings):
                raise HTTPException(422, "学生研究编号不存在或已停用")
            before = student_bindings_for(db, user_id)
            db.execute("DELETE FROM user_student_bindings WHERE user_id=?", (user_id,))
            for research_id in body.student_bindings:
                db.execute(
                    "INSERT INTO user_student_bindings(user_id,student_id) VALUES (?,?)",
                    (user_id, students[research_id]),
                )
            db.execute("UPDATE users SET version=version+1 WHERE id=?", (user_id,))
            after = student_bindings_for(db, user_id)
            audit(
                db,
                actor["id"],
                "student_bindings.replace",
                str(user_id),
                details={
                    "before": before,
                    "after": after,
                    "version": body.expected_version + 1,
                },
            )
            result = {"version": body.expected_version + 1, "student_bindings": after}
            db.execute(
                "INSERT INTO account_mutations VALUES (?,?,?,?)",
                (
                    actor["id"],
                    body.request_id,
                    PASSWORDS.hash(fingerprint),
                    json.dumps(result),
                ),
            )
            return result
