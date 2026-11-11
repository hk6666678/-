import os
import subprocess
import sys
from pathlib import Path

import pytest
from aqp.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    database = tmp_path / "accounts.sqlite3"
    result = subprocess.run(
        [sys.executable, "-m", "aqp.cli", "bootstrap", "--username", "trial-admin"],
        input="Synthetic-password-123!\nSynthetic-password-123!\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=15,
        check=False,
        env={**os.environ, "AQP_DB": str(database), "PYTHONPATH": "backend"},
    )
    assert result.returncode == 0, result.stderr
    return TestClient(create_app(database))


def test_admin_can_login_and_logout(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401
    headers = login_admin(client)
    session = client.get("/api/me").json()
    assert session["user"]["roles"] == ["platform_admin"]
    assert session["user"]["business_permissions"] == []
    assert client.post("/api/logout", headers=headers).status_code == 204
    assert client.get("/api/me").status_code == 401


def login_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/login",
        json={"username": "trial-admin", "password": "Synthetic-password-123!"},
    )
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_create_combined_roles_and_disable_revokes_session(client: TestClient) -> None:
    headers = login_admin(client)
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "synthetic-user",
            "password": "Synthetic-user-password!",
            "roles": ["college_data_admin", "college_analyst"],
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    with TestClient(client.app) as member:
        assert (
            member.post(
                "/api/login",
                json={
                    "username": "synthetic-user",
                    "password": "Synthetic-user-password!",
                },
            ).status_code
            == 200
        )
        assert member.get("/api/users").status_code == 403
        assert set(member.get("/api/me").json()["user"]["roles"]) == {
            "college_data_admin",
            "college_analyst",
        }
        assert (
            client.patch(
                f"/api/users/{user_id}",
                headers=headers,
                json={"active": False, "roles": ["college_analyst"]},
            ).status_code
            == 200
        )
        assert member.get("/api/me").status_code == 401
        assert (
            member.post(
                "/api/login",
                json={
                    "username": "synthetic-user",
                    "password": "Synthetic-user-password!",
                },
            ).status_code
            == 401
        )
    events = client.get("/api/account-audit").json()
    assert any(
        event["action"] == "user.create" and event["target"] == str(user_id)
        for event in events
    )
    assert any(
        event["action"] == "user.update" and event["target"] == str(user_id)
        for event in events
    )
    assert "password" not in str(events).lower()
    response = client.post(
        "/api/login",
        json={"username": "trial-admin", "password": "Synthetic-password-123!"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["roles"] == ["platform_admin"]
    assert response.json()["user"]["business_permissions"] == []
    assert "httponly" in response.headers["set-cookie"].lower()
    csrf = response.json()["csrf_token"]
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/me").status_code == 401


def test_csrf_last_admin_and_duplicate_guards(client: TestClient) -> None:
    headers = login_admin(client)
    body = {
        "username": "synthetic-analyst",
        "password": "Synthetic-password-123!",
        "roles": ["college_analyst"],
    }
    assert client.post("/api/users", json=body).status_code == 403
    assert client.post("/api/users", json=body, headers=headers).status_code == 201
    body["username"] = "SYNTHETIC-ANALYST"
    assert client.post("/api/users", json=body, headers=headers).status_code == 409
    user_id = client.get("/api/me").json()["user"]["id"]
    assert (
        client.patch(
            f"/api/users/{user_id}",
            json={"active": False, "roles": ["platform_admin"]},
            headers=headers,
        ).status_code
        == 409
    )
    assert client.get("/api/me").status_code == 200
    assert (
        client.post(
            "/api/login",
            json={"username": "trial-admin", "password": "Synthetic-password-123!"},
            headers={"Origin": "https://other.invalid"},
        ).status_code
        == 403
    )


def test_roles_persist_and_change_invalidates_session(
    client: TestClient, tmp_path: Path
) -> None:
    headers = login_admin(client)
    created = client.post(
        "/api/users",
        json={
            "username": "second-admin",
            "password": "Synthetic-password-123!",
            "roles": ["platform_admin"],
        },
        headers=headers,
    ).json()
    with TestClient(create_app(tmp_path / "accounts.sqlite3")) as restarted:
        response = restarted.post(
            "/api/login",
            json={"username": "second-admin", "password": "Synthetic-password-123!"},
        )
        assert response.status_code == 200
        assert (
            client.patch(
                f"/api/users/{created['id']}",
                json={"active": True, "roles": ["college_analyst"]},
                headers=headers,
            ).status_code
            == 200
        )
        assert restarted.get("/api/me").status_code == 401


def test_failed_logins_are_limited_and_audited(client: TestClient) -> None:
    login_admin(client)
    for _ in range(10):
        assert (
            client.post(
                "/api/login", json={"username": "trial-admin", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/login", json={"username": "trial-admin", "password": "wrong"}
        ).status_code
        == 429
    )
    events = client.get("/api/account-audit").json()
    assert (
        sum(
            event["action"] == "login" and event["outcome"] == "denied"
            for event in events
        )
        == 10
    )
