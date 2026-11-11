"""Isolated browser fixture: synthetic accounts, no production database."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from aqp.app import create_app

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="aqp-browser-") as directory:
        database = Path(directory) / "fixture.sqlite3"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "aqp.cli",
                "bootstrap",
                "--username",
                "synthetic-admin",
            ],
            input="Synthetic-password-123!\nSynthetic-password-123!\n",
            text=True,
            encoding="utf-8",
            check=True,
            cwd=ROOT,
            env={
                **os.environ,
                "AQP_DB": str(database),
                "PYTHONPATH": str(ROOT / "backend"),
                "PYTHONUTF8": "1",
            },
        )
        uvicorn.run(create_app(database), host="127.0.0.1", port=8011)
