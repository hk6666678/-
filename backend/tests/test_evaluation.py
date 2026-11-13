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


def test_existing_260_database_upgrades_without_reset(client, tmp_path):
    from aqp.app import create_app
    from aqp.store import connection
    from fastapi.testclient import TestClient

    headers = login_admin(client)
    dbpath = tmp_path / "accounts.sqlite3"
    with connection(dbpath) as db:
        db.execute("DROP TABLE evaluation_snapshots")
        db.execute(
            "DELETE FROM migrations WHERE version='261_evaluation_snapshots.sql'"
        )
        db.commit()
    upgraded = TestClient(create_app(dbpath))
    upgraded.cookies.update(client.cookies)
    assert upgraded.get("/api/evaluation-rules").status_code == 200
    assert (
        upgraded.post(
            "/api/evaluation-snapshots",
            headers=headers,
            json={"student_id": 1, "rule_id": 1},
        ).status_code
        == 404
    )
    with connection(dbpath) as db:
        assert (
            db.execute("SELECT COUNT(*) FROM evaluation_snapshots").fetchone()[0] == 0
        )
        db.execute(
            "DELETE FROM migrations WHERE version='261_evaluation_snapshots.sql'"
        )
        db.commit()
    # Compatibility with the short-lived WIP that already created this table.
    assert TestClient(create_app(dbpath)).get("/api/me").status_code == 401


def test_metric_nonfinite_duplicate_and_ranges_rejected(client):
    headers = login_admin(client)
    body = {
        "name": "simulation",
        "college": "synthetic",
        "major": "synthetic",
        "mode": "simulation",
        "expected_version": 0,
        "metrics": [
            {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 4}
        ],
    }
    for changes in [
        {"weight": "NaN"},
        {"maximum": "Infinity"},
        {"minimum": "-Infinity"},
        {"minimum": 4},
        {"maximum": 0},
    ]:
        invalid = {**body, "metrics": [{**body["metrics"][0], **changes}]}
        assert (
            client.post(
                "/api/evaluation-rules", headers=headers, json=invalid
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/evaluation-rules",
            headers=headers,
            json={**body, "metrics": body["metrics"] * 2},
        ).status_code
        == 422
    )


def test_course_and_citation_versions_and_mentor_binding(client, tmp_path):
    import json
    from uuid import uuid4

    from aqp.store import connection

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    grants = [
        {"category": cat, "operation": op, "college": "synthetic", "major": "synthetic"}
        for cat in ["basic", "talent_evaluation", "courses", "research_papers"]
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
    with connection(dbpath) as db:
        db.execute(
            "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload) VALUES(1,'R1','S1','Synthetic','synthetic','synthetic','master',2025,'{}')"
        )
        db.execute(
            "INSERT INTO import_batches(id,category,template_version,source_department,filename,file_hash,original_file,uploaded_by,created_at) VALUES(1,'courses','1','synthetic','synthetic','synthetic',X'00',?,1)",
            (me["id"],),
        )
        for ident, status in [(1, "通过"), (2, "不通过"), (3, "")]:
            db.execute(
                "INSERT INTO import_rows(id,batch_id,sheet,row_number,raw_json,normalized_json,state) VALUES(?,1,'sheet',?,'{}','{}','linked')",
                (ident, ident),
            )
            payload = {
                "学院": "synthetic",
                "专业": "synthetic",
                "评分制度": "百分制",
                "业务通过结果": status,
            }
            db.execute(
                "INSERT INTO course_records(id,student_number,course_code,term,attempt,student_id,payload,state,source_row_id) VALUES(?,'S1',?,'2025',1,1,?,'linked',?)",
                (ident, str(ident), json.dumps(payload), ident),
            )
        db.execute(
            "INSERT INTO research_outputs(id,business_key,payload) VALUES(1,'R1',?)",
            (
                json.dumps(
                    {
                        "participants": [
                            {
                                "student_number": "S1",
                                "name": "Synthetic",
                                "college": "synthetic",
                                "major": "synthetic",
                            }
                        ]
                    }
                ),
            ),
        )
        for date, version, count in [
            ("2026-01-01", 1, 99),
            ("2026-02-01", 1, 4),
            ("2026-02-01", 2, 6),
        ]:
            db.execute(
                "INSERT INTO research_citations(output_id,snapshot_date,version,count,source_department,actor_id,reason) VALUES(1,?,?,?,?,?,'synthetic')",
                (date, version, count, "synthetic", me["id"]),
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
                {
                    "feature": "course_pass_ratio",
                    "weight": 1,
                    "minimum": 0,
                    "maximum": 1,
                },
                {
                    "feature": "latest_citation_count",
                    "weight": 3,
                    "minimum": 0,
                    "maximum": 10,
                },
            ],
        },
    ).json()
    assert (
        client.post(
            f"/api/evaluation-rules/{rule['id']}/activate",
            headers=headers,
            json={
                "expected_version": 1,
                "confirmed_by": "expert",
                "basis": "simulation only",
                "acknowledge_simulation": True,
            },
        ).status_code
        == 200
    )
    body = {"student_id": 1, "rule_id": rule["id"]}
    result = client.post("/api/evaluation-snapshots", headers=headers, json=body).json()
    assert result["total"] is None
    assert result["inputs"][1]["value"] == 6
    assert result["inputs"][1]["evidence"][0]["citation"]["version"] == 2
    with connection(dbpath) as db:
        db.execute("UPDATE course_records SET active=0 WHERE id=3")
        db.commit()
    result = client.post("/api/evaluation-snapshots", headers=headers, json=body).json()
    assert result["inputs"][0]["value"] == 0.5
    assert abs(result["total"] - 57.5) < 0.00001
    with connection(dbpath) as db:
        db.execute(
            "UPDATE users SET roles=? WHERE id=?",
            (json.dumps(["platform_admin", "mentor"]), me["id"]),
        )
        db.commit()
    assert client.get(f"/api/evaluation-snapshots/{result['id']}").status_code == 403
    with connection(dbpath) as db:
        db.execute(
            "INSERT INTO user_student_bindings(user_id,student_id) VALUES(?,1)",
            (me["id"],),
        )
        db.commit()
    assert client.get(f"/api/evaluation-snapshots/{result['id']}").status_code == 200
