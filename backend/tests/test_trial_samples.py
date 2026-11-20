# ruff: noqa: F811
"""Task 22 small synthetic package through the public import boundaries."""

from uuid import uuid4

from test_accounts import client, login_admin  # noqa: F401
from trial_samples import sample_workbook


def test_four_category_small_package(client):
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {"category": c, "operation": op, "college": "合成试用学院", "major": "合成专业"}
        for c in ["basic", "courses", "topic", "midterm"]
        for op in ["maintain", "view", "analyze", "identity"]
    ]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        ).status_code
        == 200
    )
    for category, template_url, preview_url, confirm_prefix in [
        ("basic", "/api/templates/basic", "/api/imports/basic/preview", "/api/imports"),
        (
            "courses",
            "/api/templates/courses",
            "/api/imports/courses/preview",
            "/api/imports/courses",
        ),
        (
            "topic",
            "/api/templates/milestones/topic",
            "/api/milestones/topic/preview",
            "/api/milestone-imports",
        ),
        (
            "midterm",
            "/api/templates/milestones/midterm",
            "/api/milestones/midterm/preview",
            "/api/milestone-imports",
        ),
    ]:
        template = client.get(template_url)
        assert template.status_code == 200
        data = {
            "source_department": "合成数据提供部门",
            "college": "合成试用学院",
            "major": "合成专业",
        }
        response = client.post(
            preview_url,
            headers=headers,
            data=data,
            files={
                "file": ("synthetic.xlsx", sample_workbook(template.content, category))
            },
        )
        assert response.status_code == 200, response.text
        batch = response.json()
        confirmed = client.post(
            f"{confirm_prefix}/{batch['id']}/confirm", headers=headers
        )
        assert confirmed.status_code == 200, confirmed.text
        response = client.post(
            preview_url,
            headers=headers,
            data=data,
            files={
                "file": (
                    "synthetic-errors.xlsx",
                    sample_workbook(template.content, category, invalid=True),
                )
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["counts"].get("invalid", 0) > 0, response.text
        from trial_samples import error_workbook

        for error in [
            "missing-column",
            "bad-format",
            "duplicate",
            "identity-conflict",
            "wrong-version",
            "unparseable",
            "changed-key",
        ]:
            response = client.post(
                preview_url,
                headers=headers,
                data=data,
                files={
                    "file": (
                        f"{error}.xlsx",
                        error_workbook(template.content, category, error),
                    )
                },
            )
            if error in {"missing-column", "wrong-version", "unparseable"}:
                assert response.status_code == 422, response.text
                continue
            assert response.status_code == 200, (category, error, response.text)
            assert (
                response.json()["counts"].get(
                    {
                        "missing-column": "invalid",
                        "bad-format": "invalid",
                        "duplicate": "duplicate",
                        "identity-conflict": "conflict",
                        "changed-key": "conflict",
                    }[error],
                    0,
                )
                > 0
            ), (category, error, response.text)
    students = client.get("/api/students").json()
    assert students["total"] == 1
    for category, count in [("courses", 8), ("topic", 1), ("midterm", 1)]:
        response = client.post(
            f"/api/analyses/{category}",
            headers=headers,
            json={"college": "合成试用学院", "major": "合成专业", "category": category},
        )
        assert response.status_code == 200, response.text
        result = response.json()["result"]
        assert result["assessment_count"] == count
        if category == "courses":
            assert result["passed"] == 4
            assert result["failed"] == 2
            assert result["unknown"] == 2
            assert result["pass_rate"] == 66.67


def test_text_paper_round_trip(client, tmp_path):
    from aqp.paper_worker import run_once
    from test_papers import paper_setup, text_pdf

    headers = paper_setup(client)
    user = client.get("/api/me").json()["user"]
    grants = client.get("/api/access/grants").json()
    grants.append(
        {
            "category": "basic",
            "operation": "view",
            "college": "示例学院",
            "major": "计算机",
        }
    )
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        ).status_code
        == 200
    )
    student = client.get("/api/students").json()["items"][0]
    response = client.post(
        "/api/papers",
        headers=headers,
        data={
            "student_id": student["id"],
            "title": "Synthetic trial paper",
            "expected_version": 0,
            "covered_student_ids": f"[{student['id']}]",
        },
        files={"file": ("synthetic-text.pdf", text_pdf(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    ident = response.json()["id"]
    assert run_once(tmp_path / "accounts.sqlite3")
    papers = client.get("/api/papers").json()["items"]
    paper = next(item for item in papers if item["id"] == ident)
    assert paper["status"] == "succeeded", paper
    evidence = client.get(f"/api/papers/{ident}/evidence")
    assert evidence.status_code == 200
    assert "Synthetic text" in evidence.text
    original = client.get(f"/api/papers/{ident}/download")
    assert original.status_code == 200
    assert original.content.startswith(b"%PDF")


def test_scale_refuses_external_attachment_root(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    output = tmp_path / "scale"
    result = subprocess.run(
        [
            sys.executable,
            "backend/tests/trial_scale.py",
            "--small",
            "--output",
            str(output),
        ],
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": "backend",
            "AQP_ATTACHMENTS": str(tmp_path / "foreign"),
        },
        capture_output=True,
        text=True,
        timeout=15,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode != 0
    assert "AQP_ATTACHMENTS" in result.stderr
    assert not output.exists()
