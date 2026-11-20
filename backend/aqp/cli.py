import argparse
import getpass
import io
import re
import sqlite3
import sys

from aqp.accounts import create_user
from aqp.store import audit, connection, database_path, migrate


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="AQP-PGS 本机管理")
    parser.add_argument("command", choices=["migrate", "bootstrap"])
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    path = database_path()
    migrate(path)
    if args.command == "migrate":
        print("数据库迁移完成")
        return
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", args.username):
        parser.error("用户名须为 3～64 位字母、数字、点、下划线或短横线")

    def read_password(prompt: str) -> str:
        return (
            getpass.getpass(prompt)
            if sys.stdin.isatty()
            else sys.stdin.readline().rstrip("\r\n")
        )

    password = read_password("设置管理员密码（至少12位）: ")
    if password != read_password("再次输入密码: "):
        parser.error("两次密码不一致")
    try:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                parser.error("平台已有账号，禁止再次初始化")
            user_id = create_user(db, args.username, password, ["platform_admin"])
            audit(db, user_id, "bootstrap", str(user_id))
    except (ValueError, sqlite3.IntegrityError) as error:
        parser.error(str(error))
    print("管理员已创建，请在浏览器登录")


if __name__ == "__main__":
    main()
