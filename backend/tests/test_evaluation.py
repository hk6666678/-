# ruff: noqa: F811
from test_accounts import client, login_admin  # noqa: F401


def test_evaluation_requires_business_grant(client):
    headers = login_admin(client)
    body = {
        "name": "simulation",
        "college": "synthetic",
        "major": "synthetic",
        "mode": "simulation",
        "expected_version": 0,
        "metrics": [
            {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 10}
        ],
    }
    assert (
        client.post("/api/evaluation-rules", json=body, headers=headers).status_code
        == 403
    )
    body["mode"] = "official"
    assert (
        client.post("/api/evaluation-rules", json=body, headers=headers).status_code
        == 422
    )


def test_simulation_draft_activation_and_conflicts(client):
    from uuid import uuid4

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    assert (
        client.put(
            f"/api/users/{me['id']}/grants",
            headers=headers,
            json={
                "expected_version": me["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": "talent_evaluation",
                        "operation": op,
                        "college": "synthetic",
                        "major": "synthetic",
                    }
                    for op in ["maintain", "activate_evaluation"]
                ],
            },
        ).status_code
        == 200
    )
    body = {
        "name": "simulation",
        "college": "synthetic",
        "major": "synthetic",
        "mode": "simulation",
        "expected_version": 0,
        "metrics": [
            {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 10}
        ],
    }
    response = client.post("/api/evaluation-rules", json=body, headers=headers)
    assert response.status_code == 200
    rule = response.json()
    assert rule["enabled"] is False
    confirmation = {
        "expected_version": 2,
        "confirmed_by": "synthetic expert",
        "basis": "simulation only",
        "acknowledge_simulation": True,
    }
    url = f"/api/evaluation-rules/{rule['id']}/activate"
    assert client.post(url, json=confirmation, headers=headers).status_code == 409
    confirmation["expected_version"] = 1
    assert (
        client.post(
            url, json={**confirmation, "basis": " "}, headers=headers
        ).status_code
        == 422
    )
    result = client.post(url, json=confirmation, headers=headers)
    assert result.status_code == 200
    assert result.json()["mode"] == "simulation"
    assert client.post(url, json=confirmation, headers=headers).status_code == 409
    body.update(previous_id=rule["id"], expected_version=1)
    assert (
        client.post("/api/evaluation-rules", json=body, headers=headers).json()[
            "version"
        ]
        == 2
    )
    assert (
        client.post("/api/evaluation-rules", json=body, headers=headers).status_code
        == 409
    )
