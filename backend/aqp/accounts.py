import json
import sqlite3
import time

from fastapi import HTTPException
from pwdlib import PasswordHash

PASSWORDS = PasswordHash.recommended()
ROLES = {"platform_admin", "college_data_admin", "college_analyst"}
DUMMY_HASH = PASSWORDS.hash("not-a-login-password")


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128:
        raise ValueError("密码长度须为 12～128 个字符")


def create_user(
    db: sqlite3.Connection, username: str, password: str, roles: list[str]
) -> int:
    validate_password(password)
    if not roles or not set(roles) <= ROLES:
        raise ValueError("请选择有效角色")
    cursor = db.execute(
        "INSERT INTO users(username,password_hash,roles,created_at) VALUES (?,?,?,?)",
        (
            username,
            PASSWORDS.hash(password),
            json.dumps(sorted(set(roles))),
            int(time.time()),
        ),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def public_user(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "username": row["username"],
        "roles": json.loads(row["roles"]),
        "active": bool(row["active"]),
        "version": row["version"],
        "business_permissions": [],
    }


def require_admin(row: sqlite3.Row) -> None:
    if "platform_admin" not in json.loads(row["roles"]):
        raise HTTPException(403, "需要平台管理员权限")
