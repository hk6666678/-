import hashlib
import secrets
import sqlite3
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from aqp.accounts import DUMMY_HASH, PASSWORDS, public_user
from aqp.store import audit, connection, database_path, migrate


class Login(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=128)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_app(db_path: Path | None = None) -> FastAPI:
    path = db_path or database_path()
    migrate(path)
    app = FastAPI(title="AQP-PGS", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def protect(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        origin = request.headers.get("origin")
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and origin
            and origin != str(request.base_url).rstrip("/")
        ):
            return Response("跨来源请求已拒绝", status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def current(db: sqlite3.Connection, request: Request) -> tuple[sqlite3.Row, str]:
        session = db.execute(
            "SELECT * FROM sessions WHERE token_hash=? AND expires_at>?",
            (token_hash(request.cookies.get("aqp_session", "")), int(time.time())),
        ).fetchone()
        user = (
            db.execute(
                "SELECT * FROM users WHERE id=? AND active=1", (session["user_id"],)
            ).fetchone()
            if session
            else None
        )
        if user is None:
            raise HTTPException(401, "请先登录")
        if request.method not in {"GET", "HEAD"} and not secrets.compare_digest(
            request.headers.get("X-CSRF-Token", ""), session["csrf"]
        ):
            raise HTTPException(403, "请求校验失败，请刷新页面")
        return user, session["csrf"]

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response) -> dict[str, object]:
        now = int(time.time())
        address = request.client.host if request.client else "unknown"
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE created_at<?", (now - 300,))
            failures = db.execute(
                "SELECT COUNT(*) FROM login_attempts WHERE address=?", (address,)
            ).fetchone()[0]
            if failures >= 10:
                raise HTTPException(429, "登录尝试过多，请五分钟后重试")
            user = db.execute(
                "SELECT * FROM users WHERE username=?", (body.username,)
            ).fetchone()
            valid = PASSWORDS.verify(
                body.password, user["password_hash"] if user else DUMMY_HASH
            )
            if not user or not valid or not user["active"]:
                db.execute("INSERT INTO login_attempts VALUES (?,?)", (address, now))
                audit(db, None, "login", body.username, "denied")
                db.commit()
                raise HTTPException(401, "用户名或密码错误，或账号已停用")
            db.execute(
                "DELETE FROM sessions WHERE token_hash=? OR expires_at<=?",
                (token_hash(request.cookies.get("aqp_session", "")), now),
            )
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                (token_hash(token), user["id"], csrf, now + 28800),
            )
            audit(db, user["id"], "login", str(user["id"]))
            response.set_cookie(
                "aqp_session",
                token,
                httponly=True,
                samesite="strict",
                max_age=28800,
                secure=request.url.scheme == "https",
            )
            return {"user": public_user(user, db), "csrf_token": csrf}

    @app.get("/api/me")
    def me(request: Request) -> dict[str, object]:
        with connection(path) as db:
            user, csrf = current(db, request)
            return {"user": public_user(user, db), "csrf_token": csrf}

    @app.post("/api/logout", status_code=204)
    def logout(request: Request) -> Response:
        with connection(path) as db:
            user, _ = current(db, request)
            db.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (token_hash(request.cookies.get("aqp_session", "")),),
            )
            audit(db, user["id"], "logout", str(user["id"]))
        response = Response(status_code=204)
        response.delete_cookie("aqp_session")
        return response

    # Account management routes are registered before the static application.
    from aqp.management import register_management

    register_management(app, path, current)
    from aqp.authorization import register_authorization

    register_authorization(app, path, current)
    from aqp.audit_viewer import register_audit_viewer

    register_audit_viewer(app, path, current)
    from aqp.students import register_students

    register_students(app, path, current)
    from aqp.milestones import register_milestones

    register_milestones(app, path, current)

    from aqp.attachments import register_attachments

    register_attachments(app, path, current)

    from aqp.courses import register_courses

    register_courses(app, path, current)

    from aqp.model_connection import register_model_connection

    register_model_connection(app, path, current)
    from aqp.papers import register_papers

    register_papers(app, path, current)
    from aqp.comparisons import register_comparisons

    paper_access, comparison_snapshot = register_comparisons(app, path, current)
    from aqp.candidates import register_candidates

    candidate_access = register_candidates(
        app, path, current, paper_access, comparison_snapshot
    )
    from aqp.reviews import register_reviews

    register_reviews(app, path, current, paper_access, candidate_access)
    from aqp.resolutions import register_resolutions

    register_resolutions(app, path, current)
    from aqp.records import register_records

    register_records(app, path, current)
    from aqp.analysis import register_analysis

    register_analysis(app, path, current)
    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
