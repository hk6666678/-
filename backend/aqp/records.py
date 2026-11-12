"""Versioned formal records. Immutable proposals and revisions; no deletion API."""

import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.authorization import allowed, student_allowed
from aqp.courses import OPTIONAL, REQUIRED, classify, visible
from aqp.milestones import BASIC_OPTIONAL as M_OPTIONAL
from aqp.milestones import BASIC_REQUIRED as M_REQUIRED
from aqp.milestones import classify_milestone
from aqp.milestones import masked as milestone_masked
from aqp.store import audit, connection
from aqp.students import BASIC_OPTIONAL, BASIC_REQUIRED, masked


class Proposal(BaseModel):
    expected_version: int = Field(ge=1)
    data: dict[str, str]
    reason: str = Field(min_length=1, max_length=2000)
    identity_confirmed: bool = False


class Confirm(BaseModel):
    proposal_id: str
    expected_version: int


class Void(BaseModel):
    expected_version: int
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: bool = False


def table(category: str) -> str:
    if category not in ("basic", "courses", "topic", "midterm"):
        raise HTTPException(404, "类别不存在")
    return (
        "students"
        if category == "basic"
        else "course_records"
        if category == "courses"
        else "milestone_records"
    )


def register_records(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    def permit(
        db: sqlite3.Connection, aid: int, c: str, p: dict[str, Any], op: str
    ) -> bool:
        student = db.execute(
            "SELECT id FROM students WHERE student_number=?", (p.get("学号", ""),)
        ).fetchone()
        if not student_allowed(db, aid, student["id"] if student else None):
            return False
        return allowed(db, aid, c, op, p.get("所属学院", ""), p.get("专业", ""))

    def mask(
        db: sqlite3.Connection, aid: int, c: str, p: dict[str, Any]
    ) -> dict[str, Any]:
        return (
            masked(db, aid, p)
            if c == "basic"
            else visible(db, aid, p)
            if c == "courses"
            else milestone_masked(db, aid, p, c)
        )

    def load(
        db: sqlite3.Connection, aid: int, c: str, rid: int, op: str
    ) -> sqlite3.Row:
        r = db.execute(f"SELECT * FROM {table(c)} WHERE id=?", (rid,)).fetchone()
        if (
            not r
            or (c in ("topic", "midterm") and r["category"] != c)
            or (c != "basic" and r["student_id"] is None)
        ):
            raise HTTPException(404, "正式记录不存在")
        if not permit(db, aid, c, json.loads(r["payload"]), op):
            raise HTTPException(403, "操作范围未授权")
        return cast(sqlite3.Row, r)

    def detail(
        db: sqlite3.Connection, aid: int, c: str, r: sqlite3.Row
    ) -> dict[str, Any]:
        p = json.loads(r["payload"])
        revisions = []
        for v in db.execute(
            "SELECT * FROM record_revisions WHERE category=? AND record_id=? ORDER BY version",
            (c, r["id"]),
        ):
            before, after = (
                json.loads(v["before_payload"]),
                json.loads(v["after_payload"]),
            )
            if not permit(db, aid, c, before, "view") or not permit(
                db, aid, c, after, "view"
            ):
                continue
            source = db.execute(
                "SELECT i.batch_id,i.row_number,b.source_department FROM import_rows i JOIN import_batches b ON b.id=i.batch_id WHERE i.id=?",
                (v["source_row_id"],),
            ).fetchone()
            revisions.append(
                {
                    "revision_id": v["id"],
                    "version": v["version"],
                    "before": mask(db, aid, c, before),
                    "after": mask(db, aid, c, after),
                    "reason": v["reason"]
                    if permit(db, aid, c, before, "identity")
                    and permit(db, aid, c, after, "identity")
                    else "依据已脱敏",
                    "operation": v["operation"],
                    "actor_id": v["actor_id"],
                    "created_at": v["created_at"],
                    "source": dict(source),
                }
            )
        return {
            "id": r["id"],
            "category": c,
            "version": r["version"],
            "dependency_token": f"{c}:{r['id']}:{r['version']}:{r['active']}",
            "active": bool(r["active"]),
            "current": mask(db, aid, c, p),
            "revisions": revisions,
        }

    @app.get("/api/records/{category}")
    def listing(
        category: str,
        request: Request,
        include_void: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        with connection(path) as db:
            user, _ = current(db, request)
            items = []
            for r in db.execute(f"SELECT * FROM {table(category)} ORDER BY id"):
                if category in ("topic", "midterm") and r["category"] != category:
                    continue
                if category != "basic" and r["student_id"] is None:
                    continue
                if (r["active"] or include_void) and permit(
                    db, user["id"], category, json.loads(r["payload"]), "view"
                ):
                    items.append(detail(db, user["id"], category, r))
            audit(db, user["id"], "record.list", category)
            return {
                "items": items[
                    max(0, offset) : max(0, offset) + min(200, max(1, limit))
                ],
                "total": len(items),
            }

    @app.get("/api/records/{category}/{rid}")
    def get(category: str, rid: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            u, _ = current(db, request)
            r = load(db, u["id"], category, rid, "view")
            audit(db, u["id"], "record.history", f"{category}:{rid}")
            return detail(db, u["id"], category, r)

    def validate(
        db: sqlite3.Connection,
        aid: int,
        c: str,
        r: sqlite3.Row,
        p: dict[str, Any],
        identity: bool,
    ) -> None:
        old = json.loads(r["payload"])
        if not permit(db, aid, c, p, "maintain"):
            raise HTTPException(403, "更正目标范围未授权")
        changed_identity = any(old.get(k) != p.get(k) for k in ("学号", "姓名"))
        if changed_identity and (
            not identity
            or not permit(db, aid, c, old, "identity")
            or not permit(db, aid, c, p, "identity")
        ):
            raise HTTPException(409, "身份字段须人工确认并填写核实依据")
        if c != "basic" and old.get("学号") != p.get("学号"):
            raise HTTPException(
                409, "禁止移动正式业务记录的学生归属；请核实后作废并重新导入"
            )
        if c == "basic":
            if set(p) - set(BASIC_REQUIRED + BASIC_OPTIONAL) or any(
                not p.get(k) for k in BASIC_REQUIRED
            ):
                raise HTTPException(422, "未知或缺失字段")
            try:
                if not 1900 <= int(p["入学年份"]) <= 2100:
                    raise ValueError
            except ValueError:
                raise HTTPException(422, "年份无效") from None
            if old["学号"] != p["学号"] and (
                db.execute(
                    "SELECT 1 FROM course_records WHERE student_id=? UNION SELECT 1 FROM milestone_records WHERE student_id=?",
                    (r["id"], r["id"]),
                ).fetchone()
            ):
                raise HTTPException(409, "已有业务关联，禁止更改学号造成归属漂移")
            if db.execute(
                "SELECT 1 FROM students WHERE student_number=? AND id!=?",
                (p["学号"], r["id"]),
            ).fetchone():
                raise HTTPException(409, "禁止合并不同学生")
        else:
            if c == "courses" and set(p) - set(REQUIRED + OPTIONAL):
                raise HTTPException(422, "未知字段")
            if c in ("topic", "midterm") and set(p) - set(M_REQUIRED + M_OPTIONAL):
                raise HTTPException(422, "未知字段")
            state, error = (
                classify(db, p, r["source_row_id"])
                if c == "courses"
                else classify_milestone(db, p, c, r["source_row_id"])
            )
            if state not in ("ready", "linked"):
                raise HTTPException(409, error or "记录校验失败")

    @app.post("/api/records/{category}/{rid}/preview")
    def preview(
        category: str, rid: int, body: Proposal, request: Request
    ) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            u, _ = current(db, request)
            r = load(db, u["id"], category, rid, "maintain")
            if not r["active"] or r["version"] != body.expected_version:
                raise HTTPException(409, "版本已变化或记录已作废")
            if not body.reason.strip():
                raise HTTPException(422, "请填写更正依据")
            old = json.loads(r["payload"])
            p = {**old, **body.data}
            validate(db, u["id"], category, r, p, body.identity_confirmed)
            pid = uuid.uuid4().hex
            db.execute(
                "INSERT INTO record_proposals VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    pid,
                    category,
                    rid,
                    r["version"],
                    json.dumps(p, ensure_ascii=False),
                    body.reason,
                    u["id"],
                    body.identity_confirmed,
                    int(time.time()),
                ),
            )
            changes = {
                k: {"before": mask(db, u["id"], category, old).get(k), "after": v}
                for k, v in mask(db, u["id"], category, p).items()
                if old.get(k) != p.get(k)
            }
            audit(db, u["id"], "record.preview", f"{category}:{rid}")
            return {
                "proposal_id": pid,
                "expected_version": r["version"],
                "changes": changes,
                "identity_confirmation_required": any(
                    old.get(k) != p.get(k) for k in ("学号", "姓名")
                ),
            }

    def apply(
        db: sqlite3.Connection,
        aid: int,
        c: str,
        r: sqlite3.Row,
        p: dict[str, Any],
        reason: str,
        operation: str,
    ) -> None:
        if c == "basic":
            source = db.execute(
                "SELECT source_row_id FROM student_revisions WHERE student_id=? ORDER BY version DESC LIMIT 1",
                (r["id"],),
            ).fetchone()[0]
        else:
            source = r["source_row_id"]
        version = r["version"] + 1
        db.execute(
            "INSERT INTO record_revisions(category,record_id,version,before_payload,after_payload,operation,reason,actor_id,created_at,source_row_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                c,
                r["id"],
                version,
                r["payload"],
                json.dumps(p, ensure_ascii=False),
                operation,
                reason,
                aid,
                int(time.time()),
                source,
            ),
        )
        db.execute(
            f"UPDATE {table(c)} SET payload=?,version=?,active=? WHERE id=?",
            (json.dumps(p, ensure_ascii=False), version, operation != "void", r["id"]),
        )
        if operation != "void":
            if c == "basic":
                db.execute(
                    "UPDATE students SET student_number=?,name=?,college=?,major=?,level=?,entry_year=? WHERE id=?",
                    (
                        p["学号"],
                        p["姓名"],
                        p["所属学院"],
                        p["专业"],
                        p["培养层次"],
                        int(p["入学年份"]),
                        r["id"],
                    ),
                )
                db.execute(
                    "INSERT INTO student_revisions(student_id,version,payload,source_row_id,created_at,actor_id) VALUES (?,?,?,?,?,?)",
                    (
                        r["id"],
                        version,
                        json.dumps(p, ensure_ascii=False),
                        source,
                        int(time.time()),
                        aid,
                    ),
                )
            elif c == "courses":
                db.execute(
                    "UPDATE course_records SET course_code=?,term=?,attempt=? WHERE id=?",
                    (p["课程编号"], p["修读学期"], int(p["考核次数"]), r["id"]),
                )
            else:
                db.execute(
                    "UPDATE milestone_records SET assessment_batch=? WHERE id=?",
                    (p["考核批次"], r["id"]),
                )
        audit(
            db,
            aid,
            "record." + operation,
            f"{c}:{r['id']}",
            details={"version": version, "reason": reason},
        )

    @app.post("/api/records/{category}/{rid}/confirm")
    def confirm(
        category: str, rid: int, body: Confirm, request: Request
    ) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            u, _ = current(db, request)
            aid = u["id"]
            r = load(db, aid, category, rid, "maintain")
            v = db.execute(
                "SELECT * FROM record_proposals WHERE id=? AND category=? AND record_id=? AND actor_id=?",
                (body.proposal_id, category, rid, aid),
            ).fetchone()
            if (
                not r["active"]
                or not v
                or r["version"] != body.expected_version
                or v["expected_version"] != r["version"]
            ):
                raise HTTPException(409, "修订版本已变化，请重新预览")
            p = json.loads(v["payload"])
            validate(db, aid, category, r, p, bool(v["identity_confirmed"]))
            apply(db, aid, category, r, p, v["reason"], "correct")
            return {"version": r["version"] + 1}

    @app.post("/api/records/{category}/{rid}/void")
    def void(category: str, rid: int, body: Void, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            u, _ = current(db, request)
            r = load(db, u["id"], category, rid, "void")
            if not body.confirmed or not body.reason.strip():
                raise HTTPException(422, "作废须明确确认并填写原因")
            if not r["active"] or r["version"] != body.expected_version:
                raise HTTPException(409, "版本已变化或记录已作废")
            apply(
                db, u["id"], category, r, json.loads(r["payload"]), body.reason, "void"
            )
            return {"version": r["version"] + 1, "active": False}
