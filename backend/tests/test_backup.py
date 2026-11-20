# ruff: noqa: F811
import os
import subprocess
import sys
from pathlib import Path

from aqp.store import migrate
from test_accounts import client  # noqa: F401


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aqp.backup", *args],
        env={**os.environ, "PYTHONPATH": "backend"},
        capture_output=True,
        check=False,
        encoding="utf-8",
        text=True,
        timeout=30,
    )


def test_operator_round_trip_and_refuses_existing_target(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    migrate(source)
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    (blobs / "original").write_bytes(b"synthetic original evidence")
    archive = tmp_path / "backup.zip"
    result = cli(
        "create",
        "--db",
        str(source),
        "--attachments",
        str(blobs),
        "--archive",
        str(archive),
        "--services-stopped",
    )
    assert result.returncode == 0, result.stderr
    target = tmp_path / "restored"
    result = cli("restore", "--archive", str(archive), "--target", str(target))
    assert result.returncode == 0, result.stderr
    assert (
        target / "attachments" / "original"
    ).read_bytes() == b"synthetic original evidence"
    assert (target / "aqp.sqlite3").exists()
    assert (
        cli("restore", "--archive", str(archive), "--target", str(target)).returncode
        != 0
    )


def test_tampered_or_traversing_archive_never_publishes(tmp_path: Path) -> None:
    import json
    import zipfile

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape", b"bad")
        bundle.writestr("manifest.json", json.dumps({"format": 1, "files": {}}))
    target = tmp_path / "restored"
    assert (
        cli("restore", "--archive", str(archive), "--target", str(target)).returncode
        != 0
    )
    assert not target.exists()
    assert not (tmp_path / "escape").exists()


def test_restored_account_relogs_in_but_old_session_is_revoked(tmp_path: Path) -> None:
    from aqp.app import create_app
    from fastapi.testclient import TestClient

    source = tmp_path / "source.sqlite3"
    bootstrap = subprocess.run(
        [sys.executable, "-m", "aqp.cli", "bootstrap", "--username", "synthetic-admin"],
        input="Synthetic-password-123!\nSynthetic-password-123!\n",
        env={**os.environ, "AQP_DB": str(source), "PYTHONPATH": "backend"},
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=30,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr
    with TestClient(create_app(source)) as client:
        credentials = {
            "username": "synthetic-admin",
            "password": "Synthetic-password-123!",
        }
        assert client.post("/api/login", json=credentials).status_code == 200
        cookies = dict(client.cookies)
    blobs = tmp_path / "attachments"
    blobs.mkdir(exist_ok=True)
    archive = tmp_path / "backup.zip"
    assert (
        cli(
            "create",
            "--db",
            str(source),
            "--attachments",
            str(blobs),
            "--archive",
            str(archive),
            "--services-stopped",
        ).returncode
        == 0
    )
    target = tmp_path / "recovery"
    assert (
        cli("restore", "--archive", str(archive), "--target", str(target)).returncode
        == 0
    )
    with TestClient(create_app(target / "aqp.sqlite3")) as restored:
        restored.cookies.update(cookies)
        assert restored.get("/api/me").status_code == 401
        assert restored.post("/api/login", json=credentials).status_code == 200
        assert restored.get("/api/me").status_code == 200


def test_paper_evidence_survives_cli_restore(client, tmp_path):
    from aqp.app import create_app
    from aqp.paper_worker import run_once
    from fastapi.testclient import TestClient
    from test_accounts import login_admin
    from test_papers import paper_setup, text_pdf

    headers = paper_setup(client)
    content = text_pdf()
    response = client.post(
        "/api/papers",
        headers=headers,
        data={
            "student_id": 1,
            "title": "Synthetic recovery paper",
            "expected_version": 0,
            "covered_student_ids": "[1]",
        },
        files={"file": ("synthetic.pdf", content)},
    )
    assert response.status_code == 200
    version = response.json()["id"]
    assert run_once(tmp_path / "accounts.sqlite3")
    before = client.get(f"/api/papers/{version}/evidence").json()
    archive = tmp_path / "paper.zip"
    assert (
        cli(
            "create",
            "--db",
            str(tmp_path / "accounts.sqlite3"),
            "--attachments",
            str(tmp_path / "attachments"),
            "--archive",
            str(archive),
            "--services-stopped",
        ).returncode
        == 0
    )
    target = tmp_path / "paper-recovery"
    assert (
        cli("restore", "--archive", str(archive), "--target", str(target)).returncode
        == 0
    )
    assert not run_once(target / "aqp.sqlite3")
    with TestClient(create_app(target / "aqp.sqlite3")) as restored:
        login_admin(restored)
        assert restored.get(f"/api/papers/{version}/download").content == content
        assert restored.get(f"/api/papers/{version}/evidence").json() == before


def test_modified_database_hash_rejected_before_publish(tmp_path: Path) -> None:
    import zipfile

    source = tmp_path / "source.sqlite3"
    migrate(source)
    blobs = tmp_path / "attachments"
    blobs.mkdir()
    archive = tmp_path / "good.zip"
    assert (
        cli(
            "create",
            "--db",
            str(source),
            "--attachments",
            str(blobs),
            "--archive",
            str(archive),
            "--services-stopped",
        ).returncode
        == 0
    )
    damaged = tmp_path / "damaged.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(damaged, "w") as output:
        for name in original.namelist():
            output.writestr(
                name, b"corrupt" if name == "aqp.sqlite3" else original.read(name)
            )
    target = tmp_path / "not-published"
    assert (
        cli("restore", "--archive", str(damaged), "--target", str(target)).returncode
        != 0
    )
    assert not target.exists()


def test_interrupted_worker_is_recoverable_after_restore(client, tmp_path):
    import time
    from io import BytesIO

    from aqp.app import create_app
    from aqp.paper_worker import run_once
    from fastapi.testclient import TestClient
    from pypdf import PdfWriter
    from test_accounts import login_admin
    from test_papers import paper_setup, upload_paper

    headers = paper_setup(client)
    writer = PdfWriter()
    for _ in range(5000):
        writer.add_blank_page(width=72, height=72)
    output = BytesIO()
    writer.write(output)
    version = upload_paper(client, headers, output.getvalue()).json()["id"]
    source = tmp_path / "accounts.sqlite3"
    worker = subprocess.Popen(
        [sys.executable, "-m", "aqp.paper_worker", "--once"],
        env={**os.environ, "AQP_DB": str(source), "PYTHONPATH": "backend"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if client.get("/api/papers").json()["items"][0]["status"] == "processing":
                break
            time.sleep(0.01)
        assert client.get("/api/papers").json()["items"][0]["status"] == "processing"
    finally:
        worker.terminate()
        worker.wait(timeout=5)
    archive = tmp_path / "interrupted.zip"
    assert (
        cli(
            "create",
            "--db",
            str(source),
            "--attachments",
            str(tmp_path / "attachments"),
            "--archive",
            str(archive),
            "--services-stopped",
        ).returncode
        == 0
    )
    target = tmp_path / "recovered-job"
    assert (
        cli("restore", "--archive", str(archive), "--target", str(target)).returncode
        == 0
    )
    assert run_once(target / "aqp.sqlite3")
    assert not run_once(target / "aqp.sqlite3")
    with TestClient(create_app(target / "aqp.sqlite3")) as recovered:
        login_admin(recovered)
        items = recovered.get("/api/papers").json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == version
        assert items[0]["status"] == "failed"
        assert items[0]["failure_code"] == "no_text"
