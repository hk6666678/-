"""Enable approved synthetic-only model use; credentials remain process-local."""

import getpass
import json
import os
import socket
import subprocess
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def enable_config(path: Path) -> int:
    from aqp.model_connection import ModelConfig, config_from
    from aqp.store import audit, connection

    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        actor = next(
            (
                row
                for row in db.execute("SELECT id,roles FROM users WHERE active=1")
                if "platform_admin" in json.loads(row["roles"])
            ),
            None,
        )
        if actor is None:
            raise ValueError("No active platform administrator")
        _, version = config_from(db)
        config = ModelConfig(
            expected_version=version,
            enabled=True,
            approved=True,
            approval_reference="User approved: Bailian synthetic materials only, 2026-11-13",
            external_authorized=True,
            endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen3.8-max-0902",
            key_env="AQP_MODEL_KEY_BAILIAN",
            allowed_purposes=["agent", "papers"],
            max_input_chars=16000,
            max_output_tokens=1024,
            timeout_seconds=60,
        )
        db.execute(
            "INSERT INTO model_configs VALUES (?,?,?,?)",
            (
                version + 1,
                config.model_dump_json(),
                actor["id"],
                int(time.time()),
            ),
        )
        audit(
            db,
            actor["id"],
            "model.configure",
            str(version + 1),
            details={
                "enabled": True,
                "approved": True,
                "allowed_purposes": ["agent", "papers"],
                "source": "local-user-authorized-launcher",
                "synthetic_only": True,
            },
        )
    return version + 1


def main() -> int:
    os.chdir(ROOT)
    if os.environ.get("AQP_DB") or os.environ.get("AQP_ATTACHMENTS"):
        print(
            "Remove database/attachment overrides; this launcher targets data/aqp.sqlite3."
        )
        return 2
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            print("Port 8000 is occupied. Stop the current AQP backend first.")
            return 2
    print("Bailian: SYNTHETIC MATERIALS ONLY. Calls are billed by provider.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            key = getpass.getpass("Bailian API key (hidden): ").strip()
        except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
            print("Secure input cancelled or unavailable.")
            return 2
    if not key:
        return 2
    sys.path.insert(0, str(ROOT / "backend"))
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend"),
        "PYTHONUTF8": "1",
        "AQP_MODEL_KEY_BAILIAN": key,
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    }
    version = enable_config(ROOT / "data/aqp.sqlite3")
    log_path = ROOT / "data/bailian-server.log"
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "aqp.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    env.pop("AQP_MODEL_KEY_BAILIAN", None)
    for _ in range(40):
        if process.poll() is not None:
            print(
                "Backend exited; configuration saved, service NOT running. Check local server log."
            )
            return 1
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", 8000)) == 0:
                with log_path.open("ab") as worker_log:
                    worker = subprocess.Popen(
                        [sys.executable, "-m", "aqp.paper_worker"],
                        cwd=ROOT,
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=worker_log,
                        stderr=worker_log,
                        creationflags=subprocess.CREATE_NO_WINDOW
                        if os.name == "nt"
                        else 0,
                    )
                print(
                    f"Enabled config v{version}; backend PID {process.pid}; http://127.0.0.1:8000"
                )
                print(
                    f"Paper worker PID {worker.pid}; stop both services before restarting."
                )
                print("On restart, run this launcher again. No key saved to disk.")
                return 0
        time.sleep(0.25)
    process.terminate()
    process.wait(timeout=10)
    print("Startup timed out; backend stopped. Configuration remains saved.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
