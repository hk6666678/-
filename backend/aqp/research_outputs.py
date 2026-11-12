"""Published research outputs are independent of degree-paper samples."""

import json
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request

from aqp.authorization import allowed, student_allowed
from aqp.store import connection


def register_research_outputs(app: FastAPI, path: Path, current: Callable) -> None:
    @app.get("/api/research-outputs")
    def listing(request: Request) -> dict:
        with connection(path) as db:
            user, _ = current(db, request)
            items = []
            count = 0
            for row in db.execute("SELECT * FROM research_outputs WHERE active=1"):
                payload = json.loads(row["payload"])
                participants = []
                for participant in payload["participants"]:
                    student = db.execute(
                        "SELECT id FROM students WHERE student_number=? AND active=1",
                        (participant["student_number"],),
                    ).fetchone()
                    if not student_allowed(
                        db, user["id"], student["id"] if student else None
                    ):
                        continue
                    if not allowed(
                        db,
                        user["id"],
                        "research_papers",
                        "view",
                        participant["college"],
                        participant["major"],
                    ):
                        continue
                    visible = dict(participant)
                    visible["association"] = "linked" if student else "pending"
                    if not allowed(
                        db,
                        user["id"],
                        "research_papers",
                        "identity",
                        participant["college"],
                        participant["major"],
                    ):
                        visible.pop("student_number", None)
                        visible.pop("name", None)
                    participants.append(visible)
                if participants:
                    count += len(participants)
                    items.append(
                        {
                            "id": row["id"],
                            "version": row["version"],
                            "business_key": row["business_key"],
                            "title": payload["title"],
                            "participants": participants,
                        }
                    )
            return {
                "items": items,
                "personal_participations": count,
                "distinct_outputs": len(items),
            }
