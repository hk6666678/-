import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def database_path() -> Path:
    return Path(os.environ.get("AQP_DB", "data/aqp.sqlite3"))


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def migrate(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS migrations (version TEXT PRIMARY KEY)")
        for script in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM migrations WHERE version=?", (script.name,)
            ).fetchone():
                for statement in script.read_text(encoding="utf-8").split(";"):
                    if statement.strip():
                        db.execute(statement)
                db.execute("INSERT INTO migrations VALUES (?)", (script.name,))
            db.commit()


def audit(
    db: sqlite3.Connection,
    actor: int | None,
    action: str,
    target: str,
    outcome: str = "success",
    details: dict[str, object] | None = None,
) -> None:
    db.execute(
        "INSERT INTO audit(actor_id,action,target,outcome,created_at,details) VALUES (?,?,?,?,?,?)",
        (actor, action, target, outcome, int(time.time()), json.dumps(details or {})),
    )
