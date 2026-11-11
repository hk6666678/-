import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.accounts import PASSWORDS, require_admin
from aqp.store import audit, connection

Category = Literal["basic", "courses", "topic", "midterm", "papers"]
Operation = Literal[
    "maintain",
    "view",
    "analyze",
    "identity",
    "export",
    "download",
    "pass_rules",
    "labels",
    "candidate_rules",
    "review",
]


class Grant(BaseModel):
    category: Category
    operation: Operation
    college: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    major: str = Field(default="", max_length=100)


class GrantUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    request_id: str = Field(min_length=16, max_length=64)
    grants: list[Grant] = Field(max_length=200)


def grants_for(db: sqlite3.Connection, user_id: int) -> list[dict[str, str]]:
    return [
        dict(row)
        for row in db.execute(
            "SELECT category,operation,college,major FROM grants WHERE user_id=? ORDER BY category,operation,college,major",
            (user_id,),
        )
    ]


def allowed(
    db: sqlite3.Connection,
    user_id: int,
    category: str,
    operation: str,
    college: str,
    major: str,
) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM grants WHERE user_id=? AND category=? AND operation=? AND college=? AND (major=? OR major='')",
            (user_id, category, operation, college, major),
        ).fetchone()
        is not None
    )


def register_authorization(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    @app.get("/api/access/grants")
    def own_grants(request: Request) -> list[dict[str, str]]:
        with connection(path) as db:
            user, _ = current(db, request)
            return grants_for(db, user["id"])

    @app.get("/api/users/{user_id}/grants")
    def user_grants(user_id: int, request: Request) -> dict[str, object]:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_admin(actor)
            target = db.execute(
                "SELECT version FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if target is None:
                raise HTTPException(404, "账号不存在")
            return {"version": target["version"], "grants": grants_for(db, user_id)}

    @app.put("/api/users/{user_id}/grants")
    def replace_grants(
        user_id: int, body: GrantUpdate, request: Request
    ) -> dict[str, object]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            require_admin(actor)
            fingerprint = f"grants:{user_id}:" + body.model_dump_json()
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
            before = grants_for(db, user_id)
            db.execute("DELETE FROM grants WHERE user_id=?", (user_id,))
            for grant in body.grants:
                db.execute(
                    "INSERT OR IGNORE INTO grants VALUES (?,?,?,?,?)",
                    (
                        user_id,
                        grant.category,
                        grant.operation,
                        grant.college,
                        grant.major,
                    ),
                )
            db.execute("UPDATE users SET version=version+1 WHERE id=?", (user_id,))
            after = grants_for(db, user_id)
            audit(
                db,
                actor["id"],
                "grants.replace",
                str(user_id),
                details={
                    "before": before,
                    "after": after,
                    "version": body.expected_version + 1,
                },
            )
            result = {"version": body.expected_version + 1, "grants": after}
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

    @app.get("/api/access-demo/students")
    def demo_students(request: Request) -> list[dict[str, object]]:
        with connection(path) as db:
            user, _ = current(db, request)
            samples = [
                ("SYN-001", "示例学生甲", "SYN0001", "示例学院", "计算机"),
                ("SYN-002", "示例学生乙", "SYN0002", "示例学院", "数学"),
                ("SYN-003", "示例学生丙", "SYN0003", "其他示例学院", "计算机"),
            ]
            rows: list[dict[str, object]] = []
            for research_id, name, number, college, major in samples:
                if allowed(db, user["id"], "basic", "view", college, major):
                    row: dict[str, object] = {
                        "research_id": research_id,
                        "college": college,
                        "major": major,
                        "synthetic": True,
                    }
                    if allowed(db, user["id"], "basic", "identity", college, major):
                        row.update(name=name, student_number=number)
                    rows.append(row)
            audit(
                db,
                user["id"],
                "demo.query",
                "synthetic-students",
                outcome="success" if rows else "denied",
            )
            db.commit()
            if not rows:
                raise HTTPException(403, "没有示例记录的查看权限")
            return rows


def compatible_scope(
    db: sqlite3.Connection, actor: int, category: str, payload: dict[str, object]
) -> bool:
    """Only an upload holding area may use this check; never grants identity."""
    return any(
        g["category"] == category
        and g["operation"] == "maintain"
        and (not payload.get("所属学院") or g["college"] == payload["所属学院"])
        and (not payload.get("专业") or not g["major"] or g["major"] == payload["专业"])
        for g in grants_for(db, actor)
    )
