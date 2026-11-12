"""Versioned expert labels and scoped descriptive comparisons; never a quality score."""

import json
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.attachments import authorize_students
from aqp.store import audit, connection

FEATURES = ("page_count", "character_count", "section_count", "reference_count")


class LabelInput(BaseModel):
    label: Literal["优秀", "普通", "待评"]
    confirmed_by: str = Field(min_length=1, max_length=200, pattern=r".*\S.*")
    basis: str = Field(min_length=1, max_length=2000, pattern=r".*\S.*")
    expected_version: int = Field(ge=0)


class ComparisonInput(BaseModel):
    year: str = Field(default="", max_length=500)


def feature_values(row: sqlite3.Row) -> dict[str, Any]:
    """Adapter seam for additional versioned features once independently available."""
    result = json.loads(row["result"]) if row["result"] else {}
    return {key: result.get(key) for key in FEATURES}


def register_comparisons(
    app: FastAPI,
    path: Path,
    current: Callable[[sqlite3.Connection, Request], tuple[sqlite3.Row, str]],
) -> None:
    def paper(
        db: sqlite3.Connection, actor: int, ident: int, operations: tuple[str, ...]
    ) -> sqlite3.Row:
        row = db.execute("SELECT * FROM paper_versions WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise HTTPException(404, "论文不存在")
        authorize_students(
            db, actor, "papers", json.loads(row["covered_student_ids"]), operations
        )
        assert isinstance(row, sqlite3.Row)
        return row

    def labels(db: sqlite3.Connection, ident: int) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in db.execute(
                "SELECT * FROM paper_labels WHERE paper_id=? ORDER BY version DESC",
                (ident,),
            )
        ]

    @app.get("/api/papers/{ident}/labels")
    def label_history(ident: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            paper(db, actor["id"], ident, ("view", "identity"))
            audit(db, actor["id"], "paper.labels.history", str(ident))
            items = labels(db, ident)
            return {
                "label": items[0]["label"] if items else "待评",
                "version": items[0]["version"] if items else 0,
                "items": items,
            }

    @app.post("/api/papers/{ident}/labels")
    def set_label(ident: int, body: LabelInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            paper(db, actor["id"], ident, ("labels", "identity"))
            items = labels(db, ident)
            version = items[0]["version"] if items else 0
            if version != body.expected_version:
                raise HTTPException(409, "标签已变化，请刷新")
            db.execute(
                "INSERT INTO paper_labels(paper_id,version,label,confirmed_by,basis,entered_by,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    ident,
                    version + 1,
                    body.label,
                    body.confirmed_by,
                    body.basis,
                    actor["id"],
                    int(time.time()),
                ),
            )
            audit(db, actor["id"], "paper.label", str(ident))
            return labels(db, ident)[0]

    def snapshot(
        db: sqlite3.Connection, actor: int, target: sqlite3.Row, year: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = db.execute(
            "SELECT p.* FROM paper_versions p WHERE p.id=(SELECT MAX(q.id) FROM paper_versions q WHERE q.student_id=p.student_id) ORDER BY p.id"
        ).fetchall()
        members = []
        groups: dict[str, Any] = {}
        for row in rows:
            if (
                row["student_id"] == target["student_id"]
                or row["level"] != target["level"]
                or row["discipline"] != target["discipline"]
                or (year and row["year"] != year)
            ):
                continue
            try:
                paper(db, actor, row["id"], ("view", "analyze"))
            except HTTPException:
                continue
            history = labels(db, row["id"])
            label = history[0]["label"] if history else "待评"
            members.append(
                {
                    "version_id": row["id"],
                    "sha256": row["sha256"],
                    "label_version": history[0]["version"] if history else 0,
                    "label": label,
                    "features": feature_values(row),
                    "status": row["status"],
                }
            )
        for label in ("优秀", "普通", "待评"):
            group = [m for m in members if m["label"] == label]
            stats = {}
            for key in FEATURES:
                values = [
                    m["features"][key]
                    for m in group
                    if isinstance(m["features"][key], (int, float))
                ]
                stats[key] = {
                    "missing": len(group) - len(values),
                    "denominator": len(values),
                    "mean": sum(values) / len(values) if values else None,
                }
            groups[label] = {"sample_count": len(group), "features": stats}
        target_labels = labels(db, target["id"])
        members.append(
            {
                "target": True,
                "version_id": target["id"],
                "label_version": target_labels[0]["version"] if target_labels else 0,
                "features": feature_values(target),
            }
        )
        return members, groups

    @app.post("/api/papers/{ident}/comparisons")
    def compare(ident: int, body: ComparisonInput, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            actor, _ = current(db, request)
            target = paper(db, actor["id"], ident, ("view", "analyze"))
            members, groups = snapshot(db, actor["id"], target, body.year)
            sufficient = bool(
                target["level"]
                and target["discipline"]
                and all(value is not None for value in feature_values(target).values())
                and all(groups[k]["sample_count"] for k in ("优秀", "普通"))
                and all(
                    groups[k]["features"][feature]["denominator"]
                    for k in ("优秀", "普通")
                    for feature in FEATURES
                )
            )
            result = {
                "target_version_id": ident,
                "target_features": feature_values(target),
                "level": target["level"],
                "discipline": target["discipline"],
                "year": body.year,
                "groups": groups if target["level"] and target["discipline"] else {},
                "notice": "描述性计数差异不代表学术优秀；待评不计入普通组。"
                if sufficient
                else "信息不足或缺少同类对照组，不自动跨学科比较。",
                "evidence_versions": members
                if target["level"] and target["discipline"]
                else [],
                "sufficient": sufficient,
            }
            cur = db.execute(
                "INSERT INTO paper_comparisons(target_id,year,snapshot,result,created_by,created_at) VALUES (?,?,?,?,?,?)",
                (
                    ident,
                    body.year,
                    json.dumps(members, sort_keys=True),
                    json.dumps(result),
                    actor["id"],
                    int(time.time()),
                ),
            )
            audit(db, actor["id"], "paper.compare", str(cur.lastrowid))
            return {"id": cur.lastrowid, "stale": False, **result}

    @app.get("/api/paper-comparisons/{ident}")
    def comparison(ident: int, request: Request) -> dict[str, Any]:
        with connection(path) as db:
            actor, _ = current(db, request)
            row = db.execute(
                "SELECT * FROM paper_comparisons WHERE id=?", (ident,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "比较不存在")
            target = paper(db, actor["id"], row["target_id"], ("view", "analyze"))
            saved = json.loads(row["result"])
            for member in saved["evidence_versions"]:
                paper(db, actor["id"], member["version_id"], ("view", "analyze"))
            members, _ = snapshot(db, actor["id"], target, row["year"])
            newest = db.execute(
                "SELECT MAX(id) FROM paper_versions WHERE student_id=?",
                (target["student_id"],),
            ).fetchone()[0]
            stale = (
                newest != target["id"]
                or json.dumps(members, sort_keys=True) != row["snapshot"]
            )
            audit(db, actor["id"], "paper.comparison.read", str(ident))
            return {"id": ident, "stale": stale, **saved}
