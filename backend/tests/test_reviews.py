# ruff: noqa: F811
from test_accounts import client  # noqa: F401
from test_candidates import candidate_setup


def test_review_requires_independent_permission(client, tmp_path):
    headers, ids = candidate_setup(client, tmp_path)
    comp = client.post(
        f"/api/papers/{ids[0]}/comparisons", headers=headers, json={}
    ).json()
    candidate = client.post(
        "/api/candidate-results", headers=headers, json={"comparison_id": comp["id"]}
    ).json()
    response = client.post(
        f"/api/candidate-results/{candidate['id']}/reviews",
        headers=headers,
        json={
            "decision": "建议推荐",
            "comment": "合成复核意见",
            "expected_version": 0,
            "request_id": "synthetic-review-001",
        },
    )
    assert response.status_code == 403


def test_review_history_retry_revision_stale_and_identity(client, tmp_path):
    from uuid import uuid4

    headers, ids = candidate_setup(client, tmp_path)
    grants = client.get("/api/access/grants").json()

    def grant(items):
        me = client.get("/api/me").json()["user"]
        assert (
            client.put(
                f"/api/users/{me['id']}/grants",
                headers=headers,
                json={
                    "expected_version": me["version"],
                    "request_id": str(uuid4()),
                    "grants": items,
                },
            ).status_code
            == 200
        )

    grant(
        [
            *grants,
            {
                "category": "papers",
                "operation": "review",
                "college": "示例学院",
                "major": "计算机",
            },
        ]
    )
    comp = client.post(
        f"/api/papers/{ids[0]}/comparisons", headers=headers, json={}
    ).json()
    candidate = client.post(
        "/api/candidate-results", headers=headers, json={"comparison_id": comp["id"]}
    ).json()
    url = f"/api/candidate-results/{candidate['id']}/reviews"
    body = {
        "decision": "建议推荐",
        "comment": "合成：姓名与原文敏感意见",
        "expected_version": 0,
        "request_id": str(uuid4()),
    }
    first = client.post(url, headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert (
        first.json()["version"] == 1 and first.json()["confirmed_by"] == "trial-admin"
    )
    assert first.json()["evidence"]["paper_version_id"] == ids[0]
    assert (
        client.post(url, headers=headers, json=body).json()["id"] == first.json()["id"]
    )
    assert (
        client.post(
            url, headers=headers, json={**body, "comment": "不同内容"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            url, headers=headers, json={**body, "request_id": str(uuid4())}
        ).status_code
        == 409
    )
    assert (
        client.post(
            url,
            headers=headers,
            json={
                **body,
                "request_id": str(uuid4()),
                "expected_version": 1,
                "mode": "proxy",
            },
        ).status_code
        == 422
    )
    second = client.post(
        url,
        headers=headers,
        json={
            **body,
            "decision": "待补充材料",
            "comment": "合成修订",
            "request_id": str(uuid4()),
            "expected_version": 1,
            "mode": "proxy",
            "confirmed_by": "合成专家",
            "basis": "合成签字意见",
        },
    )
    assert second.status_code == 200, second.text
    items = client.get(url).json()["items"]
    assert len(items) == 2 and items[0]["comment"] == body["comment"]
    assert (
        items[0]["current_confirmation"] is False
        and items[1]["current_confirmation"] is True
    )
    client.post(
        f"/api/papers/{ids[1]}/labels",
        headers=headers,
        json={
            "label": "普通",
            "confirmed_by": "合成专家",
            "basis": "合成修订",
            "expected_version": 1,
        },
    )
    history = client.get(url).json()
    assert history["stale"] is True and not any(
        i["current_confirmation"] for i in history["items"]
    )
    assert (
        client.post(
            url,
            headers=headers,
            json={**body, "expected_version": 2, "request_id": str(uuid4())},
        ).status_code
        == 409
    )
    grant([g for g in grants if g["operation"] != "identity"])
    denied = client.get(url)
    assert denied.status_code == 403 and body["comment"] not in denied.text
