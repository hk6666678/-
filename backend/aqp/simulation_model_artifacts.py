"""Immutable artifacts trained only from the built-in synthetic datasets."""

import json
import sqlite3
import time
from collections.abc import Callable
from typing import Any


def load_or_train(
    db: sqlite3.Connection, version: str, train: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    row = db.execute(
        "SELECT trained_at,artifact FROM simulation_model_artifacts WHERE model_version=?", (version,)
    ).fetchone()
    if row is None:
        artifact = train(version)
        db.execute(
            "INSERT OR IGNORE INTO simulation_model_artifacts VALUES (?,?,?)",
            (version, int(time.time()), json.dumps(artifact, allow_nan=False)),
        )
        row = db.execute(
            "SELECT trained_at,artifact FROM simulation_model_artifacts WHERE model_version=?", (version,)
        ).fetchone()
    assert row is not None
    return json.loads(row["artifact"]), row["trained_at"]
