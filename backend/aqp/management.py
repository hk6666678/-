import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Literal, get_args

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from aqp.accounts import PASSWORDS, ROLES, create_user, public_user, require_admin
from aqp.authorization import Category, Operation, grants_for
from aqp.store import audit, connection


class AccountRoles(BaseModel):
    roles: list[str] = Field(min_length=1, max_length=6)
    preset: Literal["ordinary", "full"] | None = None
    scope: Literal["college", "school"] = "college"
    college: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def resolve_preset(self) -> "AccountRoles":
        if self.preset:
            self.college = self.college.strip()
            if self.scope == "college" and not self.college:
                raise ValueError("请选择所属学院")
            self.roles = [
                "platform_admin"
                if self.preset == "full"
                else "school_analyst"
                if self.scope == "school"
                else "college_analyst"
            ]
        return self


def preset_operations(preset: str) -> tuple[str, ...]:
    return get_args(Operation) if preset == "full" else ("view", "analyze")


def apply_preset(
    db: sqlite3.Connection, user_id: int, body: AccountRoles
) -> dict[str, object]:
    if body.preset is None:
        return {}
    before = grants_for(db, user_id)
    operations = preset_operations(body.preset)
    db.execute("DELETE FROM grants WHERE user_id=?", (user_id,))
    db.execute(
        "UPDATE users SET school_view=?, school_full=? WHERE id=?",
        (
            body.scope == "school",
            body.scope == "school" and body.preset == "full",
            user_id,
        ),
    )
    if body.scope == "college":
        db.executemany(
            "INSERT INTO grants(user_id,category,operation,college,major) VALUES (?,?,?,?,'')",
            (
                (user_id, category, operation, body.college)
                for category in get_args(Category)
                for operation in operations
            ),
        )
    return {
        "preset": body.preset,
        "scope": body.scope,
        "grants_before": before,
        "grants_after": grants_for(db, user_id),
    }


class UserCreate(AccountRoles):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    request_id: str = Field(min_length=16, max_length=64)


class UserUpdate(AccountRoles):
    active: bool
    school_view: bool | None = None
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
            result = []
            for row in db.execute("SELECT * FROM users ORDER BY id"):
                account = public_user(row)
                if account.get("account_scope") == "school":
                    result.append(account)
                    continue
                roles = account["roles"]
                grants = grants_for(db, row["id"])
                colleges = {grant["college"] for grant in grants}
                account["account_colleges"] = sorted(colleges)
                preset = (
                    "full"
                    if roles == ["platform_admin"]
                    else "ordinary"
                    if roles == ["college_analyst"]
                    else None
                )
                if (
                    preset
                    and len(colleges) == 1
                    and all(not g["major"] for g in grants)
                ):
                    pairs = {(g["category"], g["operation"]) for g in grants}
                    if pairs == {
                        (category, operation)
                        for category in get_args(Category)
                        for operation in preset_operations(preset)
                    }:
                        account.update(
                            account_preset=preset, preset_college=next(iter(colleges))
                        )
                result.append(account)
            return result

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
            preset_details = apply_preset(db, user_id, body)
            result = public_user(
                db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            )
            audit(
                db,
                user["id"],
                "user.create",
                str(user_id),
                details={"roles": body.roles, "version": 1, **preset_details},
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
            if body.school_view and "platform_admin" not in body.roles:
                raise HTTPException(422, "只有管理员可以开启全校查看")
            school_view = bool(
                {"platform_admin", "school_analyst"} & set(body.roles)
            ) and (
                bool(target["school_view"])
                if body.school_view is None
                else body.school_view
            )
            if removing_admin and "platform_admin" in json.loads(target["roles"]):
                school_view = False
            school_full = (
                bool(target["school_full"])
                and "platform_admin" in body.roles
                and school_view
            )
            changed = bool(target["active"]) != body.active or target["roles"] != roles
            db.execute(
                "UPDATE users SET active=?,roles=?,school_view=?,school_full=?,version=version+1 WHERE id=?",
                (body.active, roles, school_view, school_full, user_id),
            )
            preset_details = apply_preset(db, user_id, body)
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
                    **preset_details,
                    "before": {
                        "active": bool(target["active"]),
                        "roles": json.loads(target["roles"]),
                        "school_view": bool(target["school_view"]),
                        "version": target["version"],
                    },
                    "after": {
                        "active": body.active,
                        "roles": json.loads(roles),
                        "school_view": result["school_view"],
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
