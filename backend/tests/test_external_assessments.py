# ruff: noqa: F811
from test_accounts import client  # noqa: F401


def test_external_assessment_requires_session(client):
    assert client.get("/api/external-assessments").status_code == 401


def test_external_assessment_authenticated_empty_list(client):
    from test_accounts import login_admin

    login_admin(client)
    response = client.get("/api/external-assessments")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["template"]["simulation"] is True


def test_write_duplicate_conflict_and_current_permissions(client):
    from uuid import uuid4

    from test_accounts import login_admin
    from test_attachments import pdf, setup_record

    headers = login_admin(client)
    setup_record(client, headers)

    def grant(operations):
        user = client.get("/api/me").json()["user"]
        grants = [
            {
                "category": "papers",
                "operation": op,
                "college": "示例学院",
                "major": "计算机",
            }
            for op in ["maintain", "view", "identity"]
        ]
        grants += [
            {
                "category": "blind_reviews",
                "operation": op,
                "college": "示例学院",
                "major": "计算机",
            }
            for op in operations
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
        assert response.status_code == 200, response.text

    grant(["maintain", "view"])
    paper = client.post(
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
    assert paper.status_code == 200, paper.text
    body = {
        "category": "blind_reviews",
        "paper_version_id": paper.json()["id"],
        "batch": "模拟2026",
        "anonymous_code": "R01",
        "scores": {"quality": 85},
        "comment": "原文意见",
        "source": "模拟来源",
    }
    result = client.post("/api/external-assessments", headers=headers, json=body)
    assert result.status_code == 200, result.text
    assert (
        client.post("/api/external-assessments", headers=headers, json=body).json()[
            "duplicate"
        ]
        is True
    )
    assert (
        client.post(
            "/api/external-assessments",
            headers=headers,
            json={**body, "comment": "修改"},
        ).status_code
        == 409
    )
    item = client.get("/api/external-assessments").json()["items"][0]
    assert item["scores"] == {"quality": 85}
    assert "comment" not in item and "name" not in item
    grant(["view", "download"])
    item = client.get("/api/external-assessments").json()["items"][0]
    assert item["comment"] == "原文意见" and "name" not in item
    assert (
        client.post("/api/external-assessments", headers=headers, json=body).status_code
        == 403
    )
    grant(["view", "identity"])
    item = client.get("/api/external-assessments").json()["items"][0]
    assert "name" in item and "comment" not in item
    grant([])
    assert client.get("/api/external-assessments").json()["items"] == []
