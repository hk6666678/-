import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.accounts import PASSWORDS, ROLES, create_user, public_user, require_admin
from aqp.store import audit, connection


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    roles: list[str] = Field(min_length=1, max_length=6)
    request_id: str = Field(min_length=16, max_length=64)


class UserUpdate(BaseModel):
    active: bool
    roles: list[str] = Field(min_length=1, max_length=6)
    expected_version: int = Field(ge=1)
    request_id: str = Field(min_length=16, max_length=64)


def register_management(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    def previous_result(
        db: sqlite3.Connection, actor: int, request_id: str, fingerprint: str
    ) -> dict[str, object] | None:
        previous = db.execute(
            "SELECT * FROM account_mutations WHERE actor_id=? AND request_id=?",
            (actor, request_id),
        ).fetchone()
        if previous:
            if not PASSWORDS.verify(fingerprint, previous["fingerprint"]):
                raise HTTPException(409, "相同重试标识不能用于不同操作")
            result: dict[str, object] = json.loads(previous["response"])
            return result
        return None

    def remember(
        db: sqlite3.Connection,
        actor: int,
        request_id: str,
        fingerprint: str,
        result: dict[str, object],
    ) -> None:
        db.execute(
            "INSERT INTO account_mutations VALUES (?,?,?,?)",
            (actor, request_id, PASSWORDS.hash(fingerprint), json.dumps(result)),
        )

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
            db.execute("BEGIN IMMEDIATE")
            user, _ = current(db, request)
            require_admin(user)
            fingerprint = "create:" + body.model_dump_json()
            previous = previous_result(db, user["id"], body.request_id, fingerprint)
            if previous is not None:
                return previous
            try:
                user_id = create_user(db, body.username, body.password, body.roles)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            except sqlite3.IntegrityError as error:
                raise HTTPException(409, "用户名已存在") from error
            result = public_user(
                db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            )
            audit(
                db,
                user["id"],
                "user.create",
                str(user_id),
                details={"roles": body.roles, "version": 1},
            )
            remember(db, user["id"], body.request_id, fingerprint, result)
            return result

    @app.patch("/api/users/{user_id}")
    def update_user(
        user_id: int, body: UserUpdate, request: Request
    ) -> dict[str, object]:
        if not set(body.roles) <= ROLES:
            raise HTTPException(422, "无效角色")
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            require_admin(actor)
            fingerprint = f"update:{user_id}:" + body.model_dump_json()
            previous = previous_result(db, actor["id"], body.request_id, fingerprint)
            if previous is not None:
                return previous
            target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if target is None:
                raise HTTPException(404, "账号不存在")
            if target["version"] != body.expected_version:
                raise HTTPException(409, "账号已被其他操作更新，请刷新列表后重试")
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
                "UPDATE users SET active=?,roles=?,version=version+1 WHERE id=?",
                (body.active, roles, user_id),
            )
            if changed:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            result = public_user(
                db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            )
            audit(
                db,
                actor["id"],
                "user.update",
                str(user_id),
                details={
                    "before": {
                        "active": bool(target["active"]),
                        "roles": json.loads(target["roles"]),
                        "version": target["version"],
                    },
                    "after": {
                        "active": body.active,
                        "roles": json.loads(roles),
                        "version": result["version"],
                    },
                },
            )
            remember(db, actor["id"], body.request_id, fingerprint, result)
            return result

    @app.get("/api/account-audit")
    def account_audit(request: Request) -> list[dict[str, object]]:
        from aqp.audit_viewer import safe_details

        with connection(path) as db:
            actor, _ = current(db, request)
            require_admin(actor)
            result = []
            for row in db.execute(
                "SELECT * FROM audit WHERE action IN ('bootstrap','login','logout','user.create','user.update','grants.replace') ORDER BY id DESC LIMIT 100"
            ):
                item = dict(row)
                item["details"] = json.dumps(safe_details(json.loads(row["details"])))
                result.append(item)
            return result
