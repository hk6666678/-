# ruff: noqa: F811
from uuid import uuid4

from test_accounts import client, login_admin  # noqa: F401
from test_attachments import pdf, setup_record


def test_paper_queue_and_worker_failure_retains_version(client, tmp_path):
    headers = login_admin(client)
    setup_record(client, headers)
    user = client.get("/api/me").json()["user"]
    grants = [
        {
            "category": "papers",
            "operation": op,
            "college": "示例学院",
            "major": "计算机",
        }
        for op in ["view", "maintain", "identity", "download"]
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
    response = client.post(
        "/api/papers",
        headers=headers,
        data={
            "student_id": 1,
            "title": "合成论文",
            "expected_version": 0,
            "covered_student_ids": "[1]",
        },
        files={"file": ("synthetic.pdf", pdf())},
    )
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["status"] == "queued"
    from aqp.paper_worker import run_once

    assert run_once(tmp_path / "accounts.sqlite3")
    result = client.get("/api/papers").json()["items"][0]
    assert result["status"] == "failed"
    assert result["failure_code"] == "no_text"
    assert client.get(f"/api/papers/{item['id']}/download").status_code == 200
    assert (
        client.post(f"/api/papers/{item['id']}/retry", headers=headers).status_code
        == 200
    )
    assert run_once(tmp_path / "accounts.sqlite3")
    assert not run_once(tmp_path / "accounts.sqlite3")


def text_pdf(encrypted=False):
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 12 Tf 10 250 Td (1 Introduction) Tj 0 -20 Td (Synthetic text) Tj 0 -20 Td (References) Tj 0 -20 Td ([1] Synthetic source) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("synthetic")
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def paper_setup(client):
    headers = login_admin(client)
    setup_record(client, headers)
    update_grants(client, headers, ["view", "maintain", "identity", "download"])
    return headers


def update_grants(client, headers, ops):
    user = client.get("/api/me").json()["user"]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": "papers",
                        "operation": op,
                        "college": "示例学院",
                        "major": "计算机",
                    }
                    for op in ops
                ],
            },
        ).status_code
        == 200
    )


def upload_paper(client, headers, content, version=0, ids="[1]"):
    return client.post(
        "/api/papers",
        headers=headers,
        data={
            "student_id": 1,
            "title": "合成姓名论文",
            "expected_version": version,
            "covered_student_ids": ids,
        },
        files={"file": ("合成姓名.pdf", content)},
    )


def test_success_evidence_versions_and_live_grants(client, tmp_path):
    from aqp.paper_worker import run_once

    headers = paper_setup(client)
    item = upload_paper(client, headers, text_pdf()).json()
    assert run_once(tmp_path / "accounts.sqlite3")
    result = client.get(f"/api/papers/{item['id']}/evidence").json()["result"]
    assert result["pages"][0]["page"] == 1
    assert "Synthetic text" in result["pages"][0]["text"]
    assert result["section_count"] == 2
    assert result["reference_count"] == 1
    assert result["semantic_features"] == "未提取"
    assert upload_paper(client, headers, b"broken", 0).status_code == 409
    upload_paper(client, headers, text_pdf(True), 1).json()
    assert run_once(tmp_path / "accounts.sqlite3")
    assert client.get("/api/papers").json()["items"][0]["failure_code"] == "encrypted"
    assert client.get(f"/api/papers/{item['id']}/evidence").json()["result"] == result
    update_grants(client, headers, ["view"])
    assert client.get(f"/api/papers/{item['id']}/evidence").status_code == 403
    assert client.get(f"/api/papers/{item['id']}/download").status_code == 403
    safe = client.get("/api/papers").json()
    assert "合成姓名" not in str(safe)
    assert safe["items"][1]["features"]["page_count"] == 1
    assert upload_paper(client, headers, b"broken", 2).status_code == 403


def test_invalid_scope_does_not_publish_and_damaged_retry(client, tmp_path):
    from aqp.paper_worker import run_once

    headers = paper_setup(client)
    assert upload_paper(client, headers, b"broken", ids="[1,9999]").status_code == 403
    assert client.get("/api/papers").json()["items"] == []
    item = upload_paper(client, headers, b"broken").json()
    assert run_once(tmp_path / "accounts.sqlite3")
    assert (
        client.get("/api/papers").json()["items"][0]["failure_code"]
        == "damaged_or_unavailable"
    )
    assert client.get(f"/api/papers/{item['id']}/download").content == b"broken"


def test_independent_worker_cli_and_concurrent_claim(client, tmp_path):
    import os
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor

    from aqp.paper_worker import run_once

    headers = paper_setup(client)
    upload_paper(client, headers, text_pdf())
    path = tmp_path / "accounts.sqlite3"
    completed = subprocess.run(
        [sys.executable, "-m", "aqp.paper_worker", "--once"],
        env={**os.environ, "AQP_DB": str(path), "PYTHONPATH": "backend"},
        check=False,
        capture_output=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert client.get("/api/papers").json()["items"][0]["status"] == "succeeded"
    upload_paper(client, headers, text_pdf(), 1)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run_once, [path, path]))
    assert sorted(results) == [False, True]
    assert len(client.get("/api/papers").json()["items"]) == 2


def test_worker_interruption_recovers_persisted_processing(client, tmp_path):
    import os
    import subprocess
    import sys
    import time
    from io import BytesIO

    from aqp.paper_worker import run_once
    from pypdf import PdfWriter

    headers = paper_setup(client)
    writer = PdfWriter()
    for _ in range(5000):
        writer.add_blank_page(width=72, height=72)
    out = BytesIO()
    writer.write(out)
    upload_paper(client, headers, out.getvalue())
    path = tmp_path / "accounts.sqlite3"
    worker = subprocess.Popen(
        [sys.executable, "-m", "aqp.paper_worker", "--once", "--lease-seconds", "1"],
        env={**os.environ, "AQP_DB": str(path), "PYTHONPATH": "backend"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            status = client.get("/api/papers").json()["items"][0]["status"]
            if status == "processing":
                break
            time.sleep(0.01)
        assert status == "processing"
    finally:
        worker.terminate()
        worker.wait(timeout=5)
    time.sleep(2)
    assert run_once(path)
    assert client.get("/api/papers").json()["items"][0]["status"] == "failed"
    assert not run_once(path)
