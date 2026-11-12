"""Repeatable synthetic trial-scale validation and recovery report."""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from aqp.app import create_app
from aqp.paper_worker import run_once
from aqp.store import connection

ROOT = Path(__file__).resolve().parents[2]
COLLEGE = "规模合成学院"
MAJOR = "规模合成专业"
LEVEL = "硕士"
YEAR = "2025"
PASSWORD = "Synthetic-password-123!"


@dataclass
class Step:
    name: str
    milliseconds: int
    detail: dict[str, Any]


def now_ms() -> int:
    return int(time.perf_counter() * 1000)


def timed(steps: list[Step], name: str, detail: dict[str, Any] | None = None) -> None:
    steps.append(Step(name, now_ms(), detail or {}))


def elapsed(steps: list[Step], name: str) -> int:
    previous = steps[-1].milliseconds if steps else now_ms()
    start = now_ms()
    return start - previous


def workbook_bytes(
    category: str, headers: list[str], rows: list[list[object]]
) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "合成基线"
    ws.append(["AQP-PGS", category, "1"])
    ws.append(headers)
    for row in rows:
        ws.append(row)
        number = ws.max_row
        ws.cell(number, 1).number_format = "@"
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def basic_rows() -> list[list[object]]:
    return [
        [f"SYN-SCALE-{i:04d}", f"合成学生{i:04d}", COLLEGE, MAJOR, LEVEL, YEAR]
        for i in range(1, 1001)
    ]


def course_rows(start: int, stop: int) -> list[list[object]]:
    rows: list[list[object]] = []
    for index in range(start, stop):
        rows.append(
            [
                f"SYN-SCALE-{(index % 1000) + 1:04d}",
                f"合成学生{(index % 1000) + 1:04d}",
                f"C{index // 30:04d}",
                f"合成课程{index // 30:04d}",
                f"2025-{index % 10}",
                1,
                "百分制",
                80,
                "通过",
                2,
                COLLEGE,
                MAJOR,
            ]
        )
    return rows


def milestone_rows(category: str) -> list[list[object]]:
    rows: list[list[object]] = []
    for index in range(2000):
        rows.append(
            [
                f"SYN-SCALE-{(index % 1000) + 1:04d}",
                f"合成学生{(index % 1000) + 1:04d}",
                f"{category[0].upper()}-{index + 1:04d}",
                f"合成{category}",
                "百分制",
                80 if index % 5 else "",
                "通过" if index % 5 else "",
                COLLEGE,
                MAJOR,
            ]
        )
    return rows


def synthetic_pdf() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    output = BytesIO()
    writer.write(output)
    # A blank PDF is intentionally invalid for local parsing; task 14 covers a
    # text PDF separately. Trial scale uses the API/worker state machine.
    return output.getvalue()


def child_env(database: Path) -> dict[str, str]:
    return {
        **os.environ,
        "AQP_DB": str(database),
        "AQP_ATTACHMENTS": str(database.parent / "attachments"),
        "PYTHONPATH": str(ROOT / "backend"),
        "PYTHONUTF8": "1",
    }


def bootstrap(database: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aqp.cli", "bootstrap", "--username", "trial-admin"],
        input=f"{PASSWORD}\n{PASSWORD}\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        check=True,
        cwd=ROOT,
        env=child_env(database),
    )
    del result


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/login", json={"username": "trial-admin", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    return {"X-CSRF-Token": csrf}


def replace_grants(
    client: TestClient, headers: dict[str, str], grants: list[dict[str, str]]
) -> None:
    user = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": grants,
        },
    )
    assert response.status_code == 200, response.text


def admin_grants() -> list[dict[str, str]]:
    operations = [
        "maintain",
        "view",
        "identity",
        "analyze",
        "export",
        "download",
        "pass_rules",
        "labels",
        "candidate_rules",
        "review",
    ]
    return [
        {
            "category": category,
            "operation": operation,
            "college": COLLEGE,
            "major": MAJOR,
        }
        for category in ["basic", "courses", "topic", "midterm", "papers"]
        for operation in operations
        if not (category != "courses" and operation == "pass_rules")
    ]


def import_file(
    client: TestClient,
    headers: dict[str, str],
    endpoint: str,
    filename: str,
    content: bytes,
    data: dict[str, str],
) -> dict[str, Any]:
    preview = client.post(
        endpoint,
        headers=headers,
        data=data,
        files={"file": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    batch = preview.json()
    confirmed = client.post(f"/api/imports/{batch['id']}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    result: dict[str, Any] = confirmed.json()
    return result


def create_validation_package(output: Path) -> dict[str, Any]:
    package = output / "validation-package"
    package.mkdir(parents=True, exist_ok=True)
    files: dict[str, int] = {}
    files["baseline-basic.xlsx"] = len(
        workbook_bytes(
            "basic",
            ["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"],
            basic_rows(),
        )
    )
    (package / "baseline-basic.xlsx").write_bytes(
        workbook_bytes(
            "basic",
            ["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"],
            basic_rows(),
        )
    )
    course_headers = [
        "学号",
        "姓名",
        "课程编号",
        "课程名称",
        "修读学期",
        "考核次数",
        "评分制度",
        "原始成绩",
        "业务通过结果",
        "学分",
        "所属学院",
        "专业",
    ]
    for number in range(3):
        content = workbook_bytes(
            "courses", course_headers, course_rows(number * 10000, (number + 1) * 10000)
        )
        name = f"baseline-courses-{number + 1}.xlsx"
        (package / name).write_bytes(content)
        files[name] = len(content)
    for category in ["topic", "midterm"]:
        content = workbook_bytes(
            category,
            [
                "学号",
                "姓名",
                "考核批次",
                "选题标题",
                "评分制度",
                "原始成绩",
                "业务通过结果",
                "所属学院",
                "专业",
            ],
            milestone_rows(category),
        )
        name = f"baseline-{category}.xlsx"
        (package / name).write_bytes(content)
        files[name] = len(content)
    error_content = workbook_bytes(
        "basic",
        ["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"],
        [["SYN-SCALE-ERROR", "", COLLEGE, MAJOR, LEVEL, YEAR]],
    )
    (package / "errors-basic.xlsx").write_bytes(error_content)
    files["errors-basic.xlsx"] = len(error_content)
    hand_rows = [
        ["SYN-SCALE-SAMPLE", "手算学生", COLLEGE, MAJOR, LEVEL, YEAR]
    ]
    hand_content = workbook_bytes(
        "basic",
        ["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"],
        hand_rows,
    )
    (package / "hand-calculated-basic.xlsx").write_bytes(hand_content)
    files["hand-calculated-basic.xlsx"] = len(hand_content)
    expected = {
        "assessment_count": 8,
        "known_count": 6,
        "passed": 4,
        "failed": 2,
        "unknown": 2,
        "pass_rate_percent": 66.67,
        "source": "任务08手算样本，不由实现函数反推",
    }
    (package / "hand-calculated-expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"directory": str(package), "files": files}


def save_templates(client: TestClient, output: Path) -> dict[str, int]:
    directory = output / "templates"
    directory.mkdir(parents=True, exist_ok=True)
    result: dict[str, int] = {}
    for name, url in [
        ("basic", "/api/templates/basic"),
        ("courses", "/api/templates/courses"),
        ("topic", "/api/templates/milestones/topic"),
        ("midterm", "/api/templates/milestones/midterm"),
    ]:
        response = client.get(url)
        assert response.status_code == 200, response.text
        path = directory / f"{name}-v1.xlsx"
        path.write_bytes(response.content)
        result[name] = len(response.content)
    return result


def run_flow(database: Path, output: Path, browser: bool) -> tuple[dict[str, Any], list[Step]]:
    steps: list[Step] = []
    report: dict[str, Any] = {}
    start = now_ms()
    timed(steps, "bootstrap")
    bootstrap(database)
    client = TestClient(create_app(database))
    headers = login(client)
    replace_grants(client, headers, admin_grants())
    timed(steps, "bootstrap-and-grants", {"database_bytes": database.stat().st_size})

    timed(steps, "package")
    report["validation_package"] = create_validation_package(output)
    report["templates"] = save_templates(client, output)
    timed(steps, "package-and-templates", report["templates"])

    package = Path(report["validation_package"]["directory"])
    timed(steps, "basic-import")
    basic = import_file(
        client,
        headers,
        "/api/imports/basic/preview",
        "baseline-basic.xlsx",
        (package / "baseline-basic.xlsx").read_bytes(),
        {"source_department": "规模合成研究生院"},
    )
    timed(steps, "basic-import", {"batch_id": basic["id"], "total": basic["total"]})

    timed(steps, "course-import")
    course_batches = []
    for number in range(1, 4):
        course_batches.append(
            import_file(
                client,
                headers,
                "/api/imports/courses/preview",
                f"baseline-courses-{number}.xlsx",
                (package / f"baseline-courses-{number}.xlsx").read_bytes(),
                {"source_department": "规模合成研究生院"},
            )
        )
    timed(
        steps,
        "course-import",
        {"batches": [item["id"] for item in course_batches], "rows": 30000},
    )

    milestone_batches: dict[str, Any] = {}
    for category in ["topic", "midterm"]:
        timed(steps, f"{category}-import")
        milestone_batches[category] = import_file(
            client,
            headers,
            f"/api/milestones/{category}/preview",
            f"baseline-{category}.xlsx",
            (package / f"baseline-{category}.xlsx").read_bytes(),
            {"source_department": "规模合成学位办"},
        )
        timed(
            steps,
            f"{category}-import",
            {"batch_id": milestone_batches[category]["id"], "rows": 2000},
        )

    timed(steps, "paper-upload")
    pdf = synthetic_pdf()
    paper_ids: list[int] = []
    for index in range(1, 101):
        response = client.post(
            "/api/papers",
            headers=headers,
            data={
                "student_id": str(index),
                "expected_version": "0",
                "covered_student_ids": f"[{index}]",
                "title": f"合成规模论文{index:03d}",
                "level": LEVEL,
                "discipline": "计算机",
                "year": YEAR,
            },
            files={"file": ("synthetic.pdf", pdf, "application/pdf")},
        )
        assert response.status_code == 200, response.text
        paper_ids.append(response.json()["id"])
    timed(steps, "paper-upload", {"papers": len(paper_ids)})

    timed(steps, "paper-worker")
    worked = 0
    while run_once(database):
        worked += 1
    timed(steps, "paper-worker", {"jobs_processed": worked})

    timed(steps, "paper-workflow")
    for paper_id, label in [(paper_ids[1], "优秀"), (paper_ids[2], "普通")]:
        response = client.post(
            f"/api/papers/{paper_id}/labels",
            headers=headers,
            json={
                "label": label,
                "confirmed_by": "合成专家",
                "basis": "规模验证合成标签，非业务标准",
                "expected_version": 0,
            },
        )
        assert response.status_code == 200, response.text
    comparison = client.post(
        f"/api/papers/{paper_ids[0]}/comparisons", headers=headers, json={}
    )
    assert comparison.status_code == 200, comparison.text
    rule = client.post(
        "/api/candidate-rules",
        headers=headers,
        json={
            "name": "规模验证规则",
            "college": COLLEGE,
            "major": MAJOR,
            "level": LEVEL,
            "conditions": [{"feature": "page_count", "operator": "gte", "value": 1}],
            "required_evidence": ["pages"],
            "minimum_samples": 1,
            "missing_policy": "insufficient",
            "synthetic": True,
        },
    )
    assert rule.status_code == 200, rule.text
    enabled = client.post(
        f"/api/candidate-rules/{rule.json()['id']}/enable",
        headers=headers,
        json={"confirmed_by": "合成专家", "basis": "规模验证合成确认"},
    )
    assert enabled.status_code == 200, enabled.text
    candidate = client.post(
        "/api/candidate-results",
        headers=headers,
        json={"comparison_id": comparison.json()["id"]},
    )
    assert candidate.status_code == 200, candidate.text
    review = client.post(
        f"/api/candidate-results/{candidate.json()['id']}/reviews",
        headers=headers,
        json={
            "decision": "待补充材料",
            "comment": "规模验证合成复核意见",
            "expected_version": 0,
            "request_id": str(uuid4()),
        },
    )
    assert review.status_code == 200, review.text
    timed(
        steps,
        "paper-workflow",
        {
            "comparison_id": comparison.json()["id"],
            "candidate_id": candidate.json()["id"],
            "review_id": review.json()["id"],
        },
    )

    timed(steps, "analysis")
    requirement = client.post(
        "/api/training-requirements",
        headers=headers,
        json={
            "college": COLLEGE,
            "major": MAJOR,
            "required_credits": 60,
            "repeat_policy": "max_passed_credits",
            "confirmed": True,
            "reason": "规模验证合成培养要求",
        },
    )
    assert requirement.status_code == 200, requirement.text
    analysis = client.post(
        "/api/analyses/courses",
        headers=headers,
        json={"college": COLLEGE, "major": MAJOR, "group_by": "level"},
    )
    assert analysis.status_code == 200, analysis.text
    export = client.get(f"/api/analyses/{analysis.json()['id']}/export", headers=headers)
    assert export.status_code == 200 and "spreadsheetml" in export.headers["content-type"]
    agent_disabled = client.post(
        "/api/agent/query", headers=headers, json={"question": "统计学生人数"}
    )
    assert agent_disabled.status_code == 503
    timed(
        steps,
        "analysis-export-agent-disabled",
        {
            "analysis_id": analysis.json()["id"],
            "assessment_count": analysis.json()["result"]["assessment_count"],
            "student_count": analysis.json()["result"]["student_count"],
            "export_bytes": len(export.content),
            "agent_status": agent_disabled.status_code,
        },
    )

    timed(steps, "error-preview")
    error_preview = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "规模错误样例"},
        files={"file": ("errors-basic.xlsx", (package / "errors-basic.xlsx").read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert error_preview.status_code == 200
    timed(
        steps,
        "error-preview",
        {"batch_id": error_preview.json()["id"], "counts": error_preview.json()["counts"]},
    )

    timed(steps, "concurrency")
    users: list[TestClient] = []
    for number in range(1, 6):
        username = f"scale-user-{number}"
        created = client.post(
            "/api/users",
            headers=headers,
            json={
                "username": username,
                "password": PASSWORD,
                "roles": ["college_analyst"],
                "request_id": str(uuid4()),
            },
        )
        assert created.status_code == 201, created.text
        user_id = created.json()["id"]
        grants = [
            {"category": c, "operation": op, "college": COLLEGE, "major": MAJOR}
            for c in ["basic", "courses", "papers"]
            for op in ["view", "analyze", "identity"]
        ]
        response = client.put(
            f"/api/users/{user_id}/grants",
            headers=headers,
            json={
                "expected_version": created.json()["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        )
        assert response.status_code == 200, response.text
        user_client = TestClient(create_app(database))
        login_response = user_client.post(
            "/api/login", json={"username": username, "password": PASSWORD}
        )
        assert login_response.status_code == 200, login_response.text
        users.append(user_client)
    request_start = now_ms()
    concurrent: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(user.get, "/api/students?limit=1"): number
            for number, user in enumerate(users, 1)
        }
        for future in as_completed(futures):
            number = futures[future]
            response = future.result()
            concurrent.append(
                {
                    "user": number,
                    "status": response.status_code,
                    "total": response.json().get("total"),
                }
            )
    concurrent.sort(key=lambda item: item["user"])
    assert all(item["status"] == 200 and item["total"] == 1000 for item in concurrent)
    timed(
        steps,
        "five-user-concurrency",
        {
            "requests": concurrent,
            "elapsed_ms": now_ms() - request_start,
            "users": 5,
        },
    )

    archive = output / "trial-backup.zip"
    timed(steps, "backup")
    backup = subprocess.run(
        [
            sys.executable,
            "-m",
            "aqp.backup",
            "create",
            "--db",
            str(database),
            "--attachments",
            str(database.parent / "attachments"),
            "--archive",
            str(archive),
            "--services-stopped",
        ],
        cwd=ROOT,
        env=child_env(database),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert backup.returncode == 0, backup.stderr
    timed(steps, "backup", {"archive_bytes": archive.stat().st_size})

    restored_root = output / "restored"
    timed(steps, "restore")
    restore = subprocess.run(
        [
            sys.executable,
            "-m",
            "aqp.backup",
            "restore",
            "--archive",
            str(archive),
            "--target",
            str(restored_root),
        ],
        cwd=ROOT,
        env=child_env(database),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert restore.returncode == 0, restore.stderr
    restored_db = restored_root / "aqp.sqlite3"
    restored = TestClient(create_app(restored_db))
    restored_headers = login(restored)
    restored_students = restored.get("/api/students?limit=1", headers=restored_headers)
    restored_analysis = restored.get(
        f"/api/analyses/{analysis.json()['id']}", headers=restored_headers
    )
    restored_candidate = restored.get(
        f"/api/candidate-results/{candidate.json()['id']}", headers=restored_headers
    )
    restored_review = restored.get(
        f"/api/candidate-results/{candidate.json()['id']}/reviews",
        headers=restored_headers,
    )
    restored_paper = restored.get(
        f"/api/papers/{paper_ids[0]}/evidence", headers=restored_headers
    )
    assert restored_students.status_code == 200
    assert restored_analysis.status_code == 200
    assert restored_candidate.status_code == 200
    assert restored_review.status_code == 200
    assert restored_paper.status_code == 200
    timed(
        steps,
        "restore-api-checks",
        {
            "student_total": restored_students.json()["total"],
            "analysis_evidence_count": len(restored_analysis.json()["evidence"]),
            "candidate_recommended": restored_candidate.json()["recommended"],
            "review_version": restored_review.json()["version"],
            "paper_status": restored_paper.status_code,
        },
    )
    report["restoration"] = {
        "archive_bytes": archive.stat().st_size,
        "student_total": restored_students.json()["total"],
        "analysis_id": analysis.json()["id"],
        "candidate_id": candidate.json()["id"],
        "review_version": restored_review.json()["version"],
        "paper_evidence_status": restored_paper.status_code,
    }

    browser_result: dict[str, Any] = {"skipped": not browser}
    if browser:
        browser_result = browser_restore_check(restored_db, paper_ids[0])
    report["browser_restore_check"] = browser_result
    report["baseline"] = {
        "students": 1000,
        "courses": 30000,
        "topic": 2000,
        "midterm": 2000,
        "papers": 100,
        "concurrent_users": 5,
    }
    report["workflow_ids"] = {
        "analysis_id": analysis.json()["id"],
        "comparison_id": comparison.json()["id"],
        "candidate_id": candidate.json()["id"],
        "review_id": review.json()["id"],
        "paper_version_id": paper_ids[0],
    }
    report["total_milliseconds"] = now_ms() - start
    report["steps"] = [
        {"name": step.name, "milliseconds": step.milliseconds, "detail": step.detail}
        for step in steps
    ]
    return report, steps


def browser_restore_check(database: Path, paper_id: int) -> dict[str, Any]:
    import socket

    import uvicorn
    from playwright.sync_api import sync_playwright

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(create_app(database), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("restored browser server did not start")
        time.sleep(0.05)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/")
            page.get_by_label("用户名", exact=True).fill("trial-admin")
            page.get_by_label("密码", exact=True).fill(PASSWORD)
            page.get_by_role("button", name="登录平台 →").click()
            page.get_by_role("button", name="基础导入与学生档案", exact=True).click()
            page.locator("label").filter(has_text="专业筛选").locator("input").fill(MAJOR)
            page.get_by_role("button", name="查询学生档案").click()
            page.get_by_role("button", name="查看来源").first.click()
            page.wait_for_selector("pre")
            archive_visible = "archive" in page.locator("pre").first.inner_text()
            evidence = page.request.get(f"/api/papers/{paper_id}/evidence")
            page.get_by_role("button", name="Agent 查询").click()
            agent_disabled = page.get_by_text("Agent 未启用").first.is_visible()
            browser.close()
            return {
                "skipped": False,
                "url": f"http://127.0.0.1:{port}/",
                "archive_visible": archive_visible,
                "paper_evidence_status": evidence.status,
                "agent_disabled_visible": agent_disabled,
            }
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def markdown_report(report: dict[str, Any]) -> str:
    steps = report["steps"]
    lines = [
        "# 本机试用规模验证报告（合成数据）",
        "",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
        "",
        "## 基线",
        "",
        f"- 学生：{report['baseline']['students']}",
        f"- 课程记录：{report['baseline']['courses']}",
        f"- 选题：{report['baseline']['topic']}；中期：{report['baseline']['midterm']}",
        f"- 论文：{report['baseline']['papers']}",
        f"- 并发用户：{report['baseline']['concurrent_users']}",
        f"- 总耗时：{report['total_milliseconds']} ms",
        "",
        "## 关键步骤耗时",
        "",
        "| 步骤 | 记录毫秒 | 说明 |",
        "| --- | ---: | --- |",
    ]
    for step in steps:
        detail = json.dumps(step["detail"], ensure_ascii=False, sort_keys=True)
        lines.append(f"| {step['name']} | {step['milliseconds']} | {detail} |")
    lines.extend(
        [
            "",
            "## 恢复与浏览器核验",
            "",
            f"- 备份大小：{report['restoration']['archive_bytes']} bytes",
            f"- 恢复后学生总数：{report['restoration']['student_total']}",
            f"- 恢复后分析ID：{report['restoration']['analysis_id']}",
            f"- 恢复后候选ID：{report['restoration']['candidate_id']}；复核版本：{report['restoration']['review_version']}",
            f"- 浏览器档案追溯可见：{report['browser_restore_check'].get('archive_visible')}",
            f"- 浏览器论文证据状态：{report['browser_restore_check'].get('paper_evidence_status')}",
            f"- 浏览器Agent未启用可见：{report['browser_restore_check'].get('agent_disabled_visible')}",
            "",
            "## 结论边界",
            "",
            "以上均为明确标注的合成数据，验证公开API、页面、持久化、并发与恢复行为；不代表真实学生数据、真实专家规则或获准模型业务验收。未配置获准模型时Agent保持禁用。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "trial-validation-report.json")
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    output = args.output
    if output is None:
        temporary = tempfile.TemporaryDirectory(prefix="aqp-trial-validation-")
        output = Path(temporary.name)
    output.mkdir(parents=True, exist_ok=True)
    database = output / "aqp.sqlite3"
    try:
        report, _ = run_flow(database, output, not args.skip_browser)
        report["environment"] = {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor() or "unknown",
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "cwd": str(ROOT),
        }
        report["limitations"] = [
            "合成数据，不含真实学生隐私",
            "未配置获准模型，Agent仅验证禁用状态",
            "单机SQLite和约5并发基线，不作固定性能承诺",
            "真实数据、专家规则与获准模型验收留在任务23",
        ]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        markdown = args.report.with_suffix(".md")
        markdown.write_text(markdown_report(report), encoding="utf-8")
        print(f"PASS trial validation: {report['total_milliseconds']} ms")
        print(f"JSON report: {args.report}")
        print(f"Markdown report: {markdown}")
    finally:
        if temporary is not None and not args.keep_data:
            temporary.cleanup()


if __name__ == "__main__":
    main()
