from uuid import uuid4

from fastapi.testclient import TestClient
from test_accounts import client, login_admin  # noqa: F401


def test_non_admin_cannot_assign_or_read_other_grants(client: TestClient) -> None:  # noqa: F811
    headers = login_admin(client)
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "synthetic-reader",
            "password": "Synthetic-password-123!",
            "roles": ["college_analyst"],
            "request_id": str(uuid4()),
        },
    )
    assert created.status_code == 201
    with TestClient(client.app) as reader:
        login = reader.post(
            "/api/login",
            json={
                "username": "synthetic-reader",
                "password": "Synthetic-password-123!",
            },
        )
        assert login.status_code == 200
        assert reader.get("/api/access/grants").json() == []
        assert reader.get("/api/users/1/grants").status_code == 403
        assert (
            reader.put(
                "/api/users/1/grants",
                headers={"X-CSRF-Token": login.json()["csrf_token"]},
                json={
                    "expected_version": 1,
                    "request_id": str(uuid4()),
                    "grants": [
                        {
                            "category": "papers",
                            "operation": "review",
                            "college": "示例学院",
                            "major": "",
                        }
                    ],
                },
            ).status_code
            == 403
        )
        assert reader.get("/api/access-demo/students").status_code == 403


def test_scope_identity_and_revocation(client: TestClient) -> None:  # noqa: F811
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    assert client.get("/api/access-demo/students").status_code == 403
    grants = [
        {
            "category": "basic",
            "operation": "view",
            "college": "示例学院",
            "major": "计算机",
        }
    ]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": grants,
        },
    )
    assert response.status_code == 200
    rows = client.get("/api/access-demo/students").json()
    assert len(rows) == 1
    assert rows[0]["research_id"] == "SYN-001"
    assert "name" not in rows[0] and "student_number" not in rows[0]
    version = response.json()["version"]
    grants.append(
        {
            "category": "basic",
            "operation": "identity",
            "college": "示例学院",
            "major": "计算机",
        }
    )
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": version,
            "request_id": str(uuid4()),
            "grants": grants,
        },
    )
    assert client.get("/api/access-demo/students").json()[0]["name"] == "示例学生甲"
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": version,
                "request_id": str(uuid4()),
                "grants": [],
            },
        ).status_code
        == 409
    )
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": response.json()["version"],
                "request_id": str(uuid4()),
                "grants": [],
            },
        ).status_code
        == 200
    )
    assert client.get("/api/access-demo/students").status_code == 403
    assert any(
        row["action"] == "grants.replace"
        for row in client.get("/api/account-audit").json()
    )
