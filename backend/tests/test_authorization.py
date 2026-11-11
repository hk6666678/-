from uuid import uuid4

from fastapi.testclient import TestClient
from test_accounts import client, login_admin  # noqa: F401


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
