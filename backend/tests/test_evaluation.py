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


def test_score_evidence_missing_stale_and_current_access(client, tmp_path):
    import json
    from uuid import uuid4

    from aqp.store import connection

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    grants = [
        {"category": cat, "operation": op, "college": "synthetic", "major": "synthetic"}
        for cat in ["basic", "talent_evaluation", "patents"]
        for op in ["view", "identity", "analyze", "maintain", "activate_evaluation"]
    ]
    assert (
        client.put(
            f"/api/users/{me['id']}/grants",
            headers=headers,
            json={
                "expected_version": me["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        ).status_code
        == 200
    )
    dbpath = tmp_path / "accounts.sqlite3"
    participant = {
        "student_number": "S1",
        "name": "Synthetic",
        "college": "synthetic",
        "major": "synthetic",
    }
    with connection(dbpath) as db:
        db.execute(
            "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload) VALUES(1,'R1','S1','Synthetic','synthetic','synthetic','master',2025,'{}')"
        )
        db.commit()
    rule = client.post(
        "/api/evaluation-rules",
        headers=headers,
        json={
            "name": "simulation",
            "college": "synthetic",
            "major": "synthetic",
            "mode": "simulation",
            "expected_version": 0,
            "metrics": [
                {"feature": "patent_count", "weight": 2, "minimum": 0, "maximum": 4}
            ],
        },
    ).json()
    body = {"student_id": 1, "rule_id": rule["id"]}
    assert (
        client.post("/api/evaluation-snapshots", headers=headers, json=body).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/evaluation-rules/{rule['id']}/activate",
            headers=headers,
            json={
                "expected_version": 1,
                "confirmed_by": "expert",
                "basis": "synthetic only",
                "acknowledge_simulation": True,
            },
        ).status_code
        == 200
    )
    missing = client.post(
        "/api/evaluation-snapshots", headers=headers, json=body
    ).json()
    assert missing["total"] is None
    assert missing["inputs"][0]["value"] is None
    with connection(dbpath) as db:
        db.execute(
            "INSERT INTO patents_outputs(business_key,payload) VALUES(?,?)",
            ("P1", json.dumps({"participants": [participant]})),
        )
        db.commit()
    score = client.post("/api/evaluation-snapshots", headers=headers, json=body).json()
    assert score["total"] == 25
    assert score["inputs"][0]["evidence"][0]["record_id"] == 1
    assert (
        client.get(f"/api/evaluation-snapshots/{missing['id']}").json()["stale"] is True
    )
    with connection(dbpath) as db:
        db.execute("UPDATE patents_outputs SET active=0 WHERE id=1")
        db.commit()
    assert (
        client.get(f"/api/evaluation-snapshots/{score['id']}").json()["stale"] is True
    )
    me = client.get("/api/me").json()["user"]
    assert (
        client.put(
            f"/api/users/{me['id']}/grants",
            headers=headers,
            json={
                "expected_version": me["version"],
                "request_id": str(uuid4()),
                "grants": [],
            },
        ).status_code
        == 200
    )
    assert client.get(f"/api/evaluation-snapshots/{score['id']}").status_code == 403
