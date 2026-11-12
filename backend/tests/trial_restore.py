"""22C: offline CLI recovery and independent Chrome verification of 22B data.

Run after trial_scale exits: uv run python backend/tests/trial_restore.py
--manifest data/trial-22b-small/report.json --output data/trial-22c-small
All inputs are synthetic. No model acceptance is implied.
"""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from aqp.app import create_app
from playwright.sync_api import expect, sync_playwright
from trial_scale import COLLEGE, MAJOR, PASSWORD, checked, grant, login

ROOT = Path(__file__).resolve().parents[2]


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


@contextmanager
def serving(database):
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
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, (
                "HTTP startup failed"
            )
            time.sleep(0.05)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=20)
        assert not thread.is_alive(), "service must stop before offline backup"


def maintenance(*args):
    result = subprocess.run(
        [sys.executable, "-m", "aqp.backup", *map(str, args)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "backend")},
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return {
        "command": ["python", "-m", "aqp.backup", *map(str, args)],
        "returncode": result.returncode,
        "stdout": result.stdout,
    }


def run(manifest, output):
    source = json.loads(manifest.read_text(encoding="utf-8"))
    assert (
        source["server_stopped"]
        and source.get("paper_ids")
        and source.get("analysis_ids")
    ), "22B must finish baseline and stop first"
    assert source["synthetic"] is True
    database = Path(source["database"]).resolve()
    attachments = Path(source["attachments"]).resolve()
    assert attachments == database.parent / "attachments", (
        "isolated default attachment layout required"
    )
    assert not os.environ.get("AQP_ATTACHMENTS"), (
        "unset AQP_ATTACHMENTS to avoid cross-library access"
    )
    assert (ROOT / "frontend/dist/index.html").exists(), (
        "build frontend before browser verification"
    )
    output.mkdir(parents=True, exist_ok=False)
    target = output / "restored"
    report = {
        "synthetic": True,
        "model_acceptance": False,
        "source_manifest": str(manifest),
        "source_scale_status": source["status"],
        "status": "running",
        "checks": [],
        "failures": [],
    }
    started = time.perf_counter()
    try:
        with (
            serving(database) as url,
            httpx.Client(base_url=url, timeout=300, trust_env=False) as client,
        ):
            headers = login(client, source["synthetic_account"])
            old_cookies = dict(client.cookies)
            # Source preparation is distinct from recovery verification: add a real
            # persisted candidate/review through the same public API used by the UI.
            grants = checked(client.get("/api/access/grants"))
            grant(
                client,
                headers,
                checked(client.get("/api/me"))["user"],
                [
                    *grants,
                    {
                        "category": "papers",
                        "operation": "review",
                        "college": COLLEGE,
                        "major": MAJOR,
                    },
                ],
            )
            paper = source["paper_ids"][0]
            comparison = checked(
                client.post(
                    f"/api/papers/{paper}/comparisons", headers=headers, json={}
                )
            )
            candidate = checked(
                client.post(
                    "/api/candidate-results",
                    headers=headers,
                    json={"comparison_id": comparison["id"]},
                )
            )
            review = checked(
                client.post(
                    f"/api/candidate-results/{candidate['id']}/reviews",
                    headers=headers,
                    json={
                        "decision": "待补充材料",
                        "comment": "合成恢复核验意见（非业务评审）",
                        "expected_version": 0,
                        "request_id": str(uuid4()),
                    },
                )
            )
            assert (
                review["evidence"]["paper_version_id"] == paper
                and review["version"] == 1
            )
            report["source_preparation"] = {
                "comparison_id": comparison["id"],
                "candidate_id": candidate["id"],
                "review_id": review["id"],
                "paper_version_id": paper,
            }
            listing = checked(client.get("/api/students?limit=200"))
            student = listing["items"][0]["id"]
            paths = [
                "/api/students?limit=200",
                f"/api/students/{student}",
                f"/api/students/{student}/courses",
                f"/api/papers/{paper}/evidence",
                f"/api/paper-comparisons/{comparison['id']}",
                f"/api/candidate-results/{candidate['id']}",
                f"/api/candidate-results/{candidate['id']}/reviews",
            ]
            paths += [
                f"/api/analyses/{ident}" for ident in source["analysis_ids"].values()
            ]
            snapshots = {path: checked(client.get(path)) for path in paths}
            pdf = client.get(f"/api/papers/{paper}/download")
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
            pdf_hash = hashlib.sha256(pdf.content).hexdigest()
            assert listing["total"] == source["observed_counts"]["students"]
            evidence = snapshots[f"/api/papers/{paper}/evidence"]
            assert evidence["version_id"] == paper
            pages = evidence["result"]["pages"]
            assert [p["page"] for p in pages] == list(range(1, len(pages) + 1))
            assert "Synthetic text" in pages[0]["text"]
        report["source_services_stopped_before_backup"] = True
        report["backup"] = maintenance(
            "create",
            "--db",
            database,
            "--attachments",
            attachments,
            "--archive",
            output / "backup.zip",
            "--services-stopped",
        )
        assert not target.exists() and target.resolve() != database.parent
        report["restore"] = maintenance(
            "restore", "--archive", output / "backup.zip", "--target", target
        )
        with serving(target / "aqp.sqlite3") as url, sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context()
            context.add_cookies(
                [
                    {"name": key, "value": value, "url": url}
                    for key, value in old_cookies.items()
                ]
            )
            page = context.new_page()
            page.goto(url)
            old = page.evaluate("async () => (await fetch('/api/me')).status")
            assert old == 401, old
            report["old_session_status"] = old
            context.clear_cookies()
            page.reload()
            page.get_by_label("用户名", exact=True).fill(source["synthetic_account"])
            page.get_by_label("密码", exact=True).fill(PASSWORD)
            page.get_by_role("button", name="登录平台 →").click()
            page.get_by_role("button", name="基础导入与学生档案", exact=True).click()
            page.get_by_role("button", name="查询学生档案").click()
            expect(
                page.get_by_role(
                    "cell", name=listing["items"][0]["research_id"], exact=True
                )
            ).to_be_visible()
            page.get_by_role("button", name="查看来源").first.click()
            expect(
                page.locator("pre").filter(has_text="合成数据提供部门")
            ).to_be_visible()
            for path, before in snapshots.items():
                response = page.evaluate(
                    "async path => {const r=await fetch(path);return {status:r.status, body:await r.json()}}",
                    path,
                )
                assert response["status"] == 200, (path, response)
                assert response["body"] == before, f"restored content differs: {path}"
                report["checks"].append(
                    {
                        "path": path,
                        "source_sha256": digest(before),
                        "restored_sha256": digest(response["body"]),
                    }
                )
            page.get_by_role("button", name="论文上传与解析", exact=True).click()
            page.get_by_role("button", name="查看页序证据").first.click()
            expect(
                page.locator("pre").filter(has_text="Synthetic text").last
            ).to_be_visible()
            # Download from the exact restored version, rather than accepting HTTP 200 alone.
            downloaded = page.evaluate(
                "async path => {const r=await fetch(path); const b=await r.arrayBuffer(); return {status:r.status, bytes:Array.from(new Uint8Array(b))}}",
                f"/api/papers/{paper}/download",
            )
            assert downloaded["status"] == 200
            assert hashlib.sha256(bytes(downloaded["bytes"])).hexdigest() == pdf_hash
            report["download"] = {
                "paper_version_id": paper,
                "bytes": len(downloaded["bytes"]),
                "sha256": pdf_hash,
            }
            page.get_by_label("历史候选结果ID", exact=True).fill(str(candidate["id"]))
            page.get_by_role("button", name="读取并检查历史结果", exact=True).click()
            page.get_by_role("button", name="读取复核历史", exact=True).click()
            expect(page.get_by_label("复核历史", exact=True)).to_contain_text(
                review["comment"]
            )
            expect(page.get_by_label("复核历史", exact=True)).to_contain_text(
                "paper_version_id"
            )
            page.screenshot(path=str(output / "restored-review.png"), full_page=True)
            report["browser"] = {
                "engine": "Chrome",
                "student_research_id": listing["items"][0]["research_id"],
                "review_version": review["version"],
                "screenshot": str(output / "restored-review.png"),
            }
            browser.close()
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["failures"].append(
            {"type": type(error).__name__, "message": str(error)[:6000]}
        )
        raise
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.manifest.resolve(), args.output.resolve())
