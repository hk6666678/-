import sqlite3
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.accounts import ROLES, create_user, public_user, require_admin
from aqp.store import audit, connection


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    roles: list[str] = Field(min_length=1, max_length=3)


class UserUpdate(BaseModel):
    active: bool
    roles: list[str] = Field(min_length=1, max_length=3)


def register_management(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    @app.get("/api/users")
    def users(request: Request) -> list[dict[str, object]]:
        with connection(path) as db:
            user, _ = current(db, request)
            require_admin(user)
            return [
                public_user(row)
                for row in db.execute("SELECT * FROM users ORDER BY id")
            ]

    @app.post("/api/users", status_code=201)
    def add_user(body: UserCreate, request: Request) -> dict[str, object]:
        with connection(path) as db:
            user, _ = current(db, request)
            require_admin(user)
            try:
                user_id = create_user(db, body.username, body.password, body.roles)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            except sqlite3.IntegrityError as error:
                raise HTTPException(409, "用户名已存在") from error
            audit(db, user["id"], "user.create", str(user_id))
            return public_user(
                db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            )

    @app.patch("/api/users/{user_id}")
    def update_user(
        user_id: int, body: UserUpdate, request: Request
    ) -> dict[str, object]:
        import json

        if not set(body.roles) <= ROLES:
            raise HTTPException(422, "无效角色")
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            require_admin(actor)
            target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if target is None:
                raise HTTPException(404, "账号不存在")
            removing_admin = not body.active or "platform_admin" not in body.roles
            active_admins = [
                row
                for row in db.execute("SELECT * FROM users WHERE active=1")
                if "platform_admin" in json.loads(row["roles"])
            ]
            if (
                removing_admin
                and target["active"]
                and "platform_admin" in json.loads(target["roles"])
                and len(active_admins) == 1
            ):
                raise HTTPException(409, "不能停用或移除最后一位有效平台管理员")
            roles = json.dumps(sorted(set(body.roles)))
            changed = bool(target["active"]) != body.active or target["roles"] != roles
            db.execute(
                "UPDATE users SET active=?,roles=? WHERE id=?",
                (body.active, roles, user_id),
            )
            if changed:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            audit(db, actor["id"], "user.update", str(user_id))
            return public_user(
                db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            )

    @app.get("/api/account-audit")
    def account_audit(request: Request) -> list[dict[str, object]]:
        with connection(path) as db:
            actor, _ = current(db, request)
            require_admin(actor)
            return [
                dict(row)
                for row in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")
            ]
