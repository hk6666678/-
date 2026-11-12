"""Replay five-account analysis contention against a retained synthetic scale DB."""

import argparse
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import uvicorn
from aqp.app import create_app
from trial_scale import COLLEGE, MAJOR, login


def run(database, output):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(database), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    clients = []
    report = {"synthetic": True, "database": str(database), "requests": []}
    began = time.perf_counter()
    try:
        while not server.started:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        for number in range(5):
            member = httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=120, trust_env=False
            )
            clients.append((member, login(member, f"scale-user-{number}")))
        barrier = threading.Barrier(5)

        def probe(member):
            client, csrf = member
            barrier.wait(timeout=30)
            start = time.perf_counter()
            response = client.post(
                "/api/analyses/courses",
                headers=csrf,
                json={"college": COLLEGE, "major": MAJOR},
            )
            body = response.json() if response.status_code == 200 else {}
            return {
                "status": response.status_code,
                "seconds": round(time.perf_counter() - start, 3),
                "count": body.get("result", {}).get("assessment_count"),
                "id": body.get("id"),
                "error": response.text[:500] if response.status_code != 200 else None,
            }

        with ThreadPoolExecutor(max_workers=5) as pool:
            report["requests"] = list(pool.map(probe, clients))
        report["failures"] = sum(
            r["status"] != 200 or r["count"] != 30000 for r in report["requests"]
        )
        assert report["failures"] == 0, report["requests"]
        assert len({r["id"] for r in report["requests"]}) == 5
        report["status"] = "passed"
    finally:
        for client, _ in clients:
            client.close()
        server.should_exit = True
        thread.join(timeout=20)
        report["server_stopped"] = not thread.is_alive()
        report["seconds"] = round(time.perf_counter() - began, 3)
        report.setdefault("status", "failed")
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    run(args.database.resolve(), args.report.resolve())
