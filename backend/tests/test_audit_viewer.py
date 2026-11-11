from uuid import uuid4

from fastapi.testclient import TestClient
from test_accounts import client, login_admin  # noqa: F401


def test_admin_can_filter_and_page_audit(client: TestClient) -> None:  # noqa: F811
    login_admin(client)
    response = client.get("/api/audit", params={"action": "login", "page_size": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "login"
    assert (
        client.get("/api/audit", params={"action": "nonexistent"}).json()["total"] == 0
    )
    assert (
        client.get("/api/audit", params={"started_at": 1, "ended_at": 0}).status_code
        == 422
    )
    assert client.get("/api/audit", params={"page_size": 101}).status_code == 422
    event = body["items"][0]
    exact = client.get(
        "/api/audit",
        params={
            "actor_id": event["actor_id"],
            "target": event["target"],
            "started_at": event["created_at"],
            "ended_at": event["created_at"],
            "action": "login",
        },
    ).json()
    assert any(row["id"] == event["id"] for row in exact["items"])


def test_analyst_cannot_access_management_audit(client: TestClient) -> None:  # noqa: F811
    headers = login_admin(client)
    response = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "synthetic-auditor",
            "password": "Synthetic-password-123!",
            "roles": ["college_analyst"],
            "request_id": str(uuid4()),
        },
    )
    assert response.status_code == 201
    with TestClient(client.app) as analyst:
        assert (
            analyst.post(
                "/api/login",
                json={
                    "username": "synthetic-auditor",
                    "password": "Synthetic-password-123!",
                },
            ).status_code
            == 200
        )
        assert analyst.get("/api/audit").status_code == 403
        assert analyst.get("/api/account-audit").status_code == 403
