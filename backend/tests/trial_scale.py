"""Repeatable synthetic scale probe through a real loopback HTTP server.

Run from repo root with PYTHONPATH=backend. Output is retained for recovery probes.
"""

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from aqp.app import create_app
from aqp.paper_worker import run_once
from openpyxl import load_workbook
from test_papers import text_pdf

COLLEGE = "合成试用学院"
MAJOR = "合成专业"
PASSWORD = "Synthetic-password-123!"
ROOT = Path(__file__).resolve().parents[2]


def checked(response, status=200):
    assert response.status_code == status, (response.status_code, response.text)
    return response.json()


def login(client, username):
    return {
        "X-CSRF-Token": checked(
            client.post("/api/login", json={"username": username, "password": PASSWORD})
        )["csrf_token"]
    }


def grant(client, headers, user, grants):
    checked(
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        )
    )


def workbook(template, category, count, students, offset=0):
    book = load_workbook(BytesIO(template))
    sheet = book.active
    columns = [cell.value for cell in sheet[2]]
    if sheet.max_row > 2:
        sheet.delete_rows(3, sheet.max_row - 2)
    for i in range(offset, offset + count):
        number = i % students + 1
        row = {
            "学号": f"SYN-SCALE-{number:04}",
            "姓名": f"合成学生{number:04}",
            "所属学院": COLLEGE,
            "专业": MAJOR,
            "培养层次": "硕士",
            "入学年份": 2025,
            "课程编号": f"SYN-C{i // students:04}",
            "课程名称": f"合成课程{i // students:04}",
            "修读学期": "2025秋",
            "考核次数": 1,
            "评分制度": "百分制",
            "原始成绩": 80,
            "业务通过结果": "通过",
            "学分": 2,
            "考核批次": f"合成批次{i // students:04}",
            "选题标题": "合成选题",
        }
        sheet.append([row.get(column, "") for column in columns])
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def run(output, small):
    output.mkdir(parents=True, exist_ok=False)
    database = output / "aqp.sqlite3"
    report = {
        "synthetic": True,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "sqlite": __import__("sqlite3").sqlite_version,
            "httpx": httpx.__version__,
            "uvicorn": uvicorn.__version__,
        },
        "steps": [],
        "failures": [],
    }
    start = time.perf_counter()

    def save():
        report["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def step(name, began, **detail):
        report["steps"].append(
            {"name": name, "seconds": round(time.perf_counter() - began, 3), **detail}
        )
        save()
        print(name, report["steps"][-1]["seconds"], flush=True)

    server = None
    thread = None
    try:
        subprocess.run(
            [sys.executable, "-m", "aqp.cli", "bootstrap", "--username", "trial-admin"],
            input=f"{PASSWORD}\n{PASSWORD}\n",
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            env={**os.environ, "AQP_DB": str(database)},
            timeout=30,
        )
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
        while not server.started:
            assert time.monotonic() < deadline, "HTTP startup timeout"
            time.sleep(0.05)
        url = f"http://127.0.0.1:{port}"
        report["http_url"] = url
        report["database"] = str(database)
        report["attachments"] = str(output / "attachments")
        report["synthetic_account"] = "trial-admin"
        students, courses, milestones, papers = (
            (10, 30, 20, 2) if small else (1000, 30000, 2000, 100)
        )
        grants = [
            {"category": c, "operation": op, "college": COLLEGE, "major": MAJOR}
            for c in ["basic", "courses", "topic", "midterm", "papers"]
            for op in ["maintain", "view", "identity", "analyze", "download"]
        ]
        with httpx.Client(base_url=url, timeout=300, trust_env=False) as client:
            headers = login(client, "trial-admin")
            grant(client, headers, checked(client.get("/api/me"))["user"], grants)
            for category, template_url, preview_url, confirm_prefix, count in [
                (
                    "basic",
                    "/api/templates/basic",
                    "/api/imports/basic/preview",
                    "/api/imports",
                    students,
                ),
                (
                    "courses",
                    "/api/templates/courses",
                    "/api/imports/courses/preview",
                    "/api/imports/courses",
                    courses,
                ),
                (
                    "topic",
                    "/api/templates/milestones/topic",
                    "/api/milestones/topic/preview",
                    "/api/milestone-imports",
                    milestones,
                ),
                (
                    "midterm",
                    "/api/templates/milestones/midterm",
                    "/api/milestones/midterm/preview",
                    "/api/milestone-imports",
                    milestones,
                ),
            ]:
                began = time.perf_counter()
                template = client.get(template_url)
                assert template.status_code == 200, template.text
                (output / f"template-{category}.xlsx").write_bytes(template.content)
                batches = []
                for offset in range(0, count, 10000):
                    content = workbook(
                        template.content,
                        category,
                        min(10000, count - offset),
                        students,
                        offset,
                    )
                    name = f"synthetic-{category}-{offset}.xlsx"
                    (output / name).write_bytes(content)
                    preview = checked(
                        client.post(
                            preview_url,
                            headers=headers,
                            data={
                                "source_department": "合成数据提供部门",
                                "college": COLLEGE,
                                "major": MAJOR,
                            },
                            files={"file": (name, content)},
                        )
                    )
                    assert not preview["counts"].get("invalid", 0), preview
                    confirmed = checked(
                        client.post(
                            f"{confirm_prefix}/{preview['id']}/confirm", headers=headers
                        )
                    )
                    batches.append(
                        {
                            "preview": preview["counts"],
                            "confirmed": {
                                "id": confirmed["id"],
                                "counts": confirmed["counts"],
                            },
                        }
                    )
                step(f"import-{category}", began, batches=batches)
            listing = checked(client.get("/api/students", params={"limit": 200}))
            assert listing["total"] == students, listing
            report["observed_counts"] = {"students": listing["total"]}
            report["analysis_ids"] = {}
            for category, expected in [
                ("courses", courses),
                ("topic", milestones),
                ("midterm", milestones),
            ]:
                began = time.perf_counter()
                analysis = checked(
                    client.post(
                        f"/api/analyses/{category}",
                        headers=headers,
                        json={"college": COLLEGE, "major": MAJOR, "category": category},
                    )
                )
                actual = analysis["result"]["assessment_count"]
                report["observed_counts"][category] = actual
                report["analysis_ids"][category] = analysis["id"]
                assert actual == expected, analysis
                step(f"query-{category}", began, assessment_count=actual)
            began = time.perf_counter()
            student_ids = [item["id"] for item in listing["items"]]
            assert len(student_ids) >= papers
            pdf = text_pdf()
            (output / "synthetic-text.pdf").write_bytes(pdf)
            paper_ids = []
            for student_id in student_ids[:papers]:
                uploaded = checked(
                    client.post(
                        "/api/papers",
                        headers=headers,
                        data={
                            "student_id": student_id,
                            "expected_version": 0,
                            "covered_student_ids": json.dumps([student_id]),
                            "title": "Synthetic scale paper",
                        },
                        files={"file": ("synthetic-text.pdf", pdf, "application/pdf")},
                    )
                )
                paper_ids.append(uploaded["id"])
            processed = 0
            while run_once(database):
                processed += 1
            observed = checked(client.get("/api/papers"))["items"]
            assert len(observed) == papers and processed == papers, (
                len(observed),
                processed,
            )
            assert all(item["status"] == "succeeded" for item in observed), observed
            for ident in paper_ids:
                evidence = client.get(f"/api/papers/{ident}/evidence")
                assert evidence.status_code == 200 and "Synthetic text" in evidence.text
            report["paper_ids"] = paper_ids
            report["observed_counts"]["papers"] = len(observed)
            step(
                "papers-upload-worker-evidence",
                began,
                processed=processed,
                succeeded=len(observed),
            )
            members = []
            for number in range(5):
                username = f"scale-user-{number}"
                user = checked(
                    client.post(
                        "/api/users",
                        headers=headers,
                        json={
                            "username": username,
                            "password": PASSWORD,
                            "roles": ["college_analyst"],
                            "request_id": str(uuid4()),
                        },
                    ),
                    201,
                )
                grant(client, headers, user, grants)
                member = httpx.Client(base_url=url, timeout=300, trust_env=False)
                member_headers = login(member, username)
                members.append((member, member_headers))
            barrier = threading.Barrier(5)

            def probe(member):
                user, csrf = member
                barrier.wait(timeout=30)
                began = time.perf_counter()
                response = user.post(
                    "/api/analyses/courses",
                    headers=csrf,
                    json={"college": COLLEGE, "major": MAJOR},
                )
                body = (
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                return {
                    "status": response.status_code,
                    "seconds": round(time.perf_counter() - began, 3),
                    "count": body.get("result", {}).get("assessment_count"),
                    "analysis_id": body.get("id"),
                    "error": response.text[:1000]
                    if response.status_code != 200
                    else None,
                }

            began = time.perf_counter()
            try:
                with ThreadPoolExecutor(max_workers=5) as pool:
                    results = list(pool.map(probe, members))
                failures = [
                    r for r in results if r["status"] != 200 or r["count"] != courses
                ]
                report["concurrency"] = {
                    "users": len(members),
                    "requests": results,
                    "failures": len(failures),
                }
                step("five-account-concurrent-analysis-write", began, requests=results)
                assert not failures, failures
                assert len({r["analysis_id"] for r in results}) == 5, results
            finally:
                for member, _ in members:
                    member.close()
            report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["failures"].append(
            {"type": type(error).__name__, "message": str(error)[:6000]}
        )
        raise
    finally:
        if server:
            server.should_exit = True
        if thread:
            thread.join(timeout=20)
            report["server_stopped"] = not thread.is_alive()
        save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--small", action="store_true")
    args = parser.parse_args()
    run(args.output.resolve(), args.small)
