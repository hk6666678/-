# ruff: noqa: F811
from test_accounts import client, login_admin  # noqa: F401


def test_six_signal_trial_uses_milestones_and_withholds_incomplete_total():
    from aqp.evaluation import (
        SOURCE_CATEGORY,
        screened_trial_decision,
        six_signal_trial,
    )

    inputs = [{"feature": feature, "normalized": 1, "value": 1} for feature in SOURCE_CATEGORY]
    signals = {
        "milestone_trends": [{"label": label, "observations": [{"mean": 80}]} for label in ("选题", "中期")],
        "course_trend": {"observations": [{"mean": 70}, {"mean": 90}]},
    }
    assert six_signal_trial(inputs, signals)["total"] == 91.67
    assert six_signal_trial(inputs, {})["total"] is None
    assert six_signal_trial(inputs[:-1], signals)["total"] is None
    trial = six_signal_trial(inputs, signals)
    assert screened_trial_decision([{"status": "通过"}], trial) == "拔尖潜力（模拟分数段）"
    assert "待核查" in screened_trial_decision([{"status": "待核查"}], trial)
    assert "未通过" in screened_trial_decision([{"status": "待核查"}, {"status": "未通过"}], trial)
    assert "证据不足" in screened_trial_decision([{"status": "通过"}], six_signal_trial(inputs, {}))

def test_student_clusters_use_separate_holdout_and_respect_missing_scores():
    from aqp.student_clustering_demo import DIMENSIONS, cluster_student_demo

    inputs = [{"name": name, "normalized": value} for name, value in zip(DIMENSIONS, (0.88, 0.36, 0.41), strict=True)]
    snapshot = {"ahp": {"dimensions": inputs}, "total": 58, "stale": False, "rule_currently_enabled": True}
    result = cluster_student_demo(snapshot)
    assert result["cluster"]["name"] == "学术基础较强"
    assert result["validation"]["training_count"] == 240 and result["validation"]["holdout_count"] == 90
    assert result["validation"]["matching_profiles"] <= 90
    assert cluster_student_demo({**snapshot, "stale": True})["cluster"] is None
    assert cluster_student_demo({**snapshot, "ahp": {}})["cluster"] is None

def test_simulation_bands_and_peer_percentiles():
    from aqp.evaluation import simulation_band, simulation_percentiles

    assert simulation_band(None, []) == "数据不完整"
    assert simulation_band(85, []) == "拔尖潜力（模拟分数段）"
    assert simulation_band(73, [0.8, 0.91, 0.4]) == "偏科特长型（模拟分数段）"
    assert simulation_band(73, [0.8]) == "待核查维度表现"
    assert simulation_band(69.9, []) == "常规培养（模拟分数段）"
    assert simulation_percentiles([10, 20, 30, 40, 50]) == {"p50": 30, "p75": 40, "p90": 46}
    assert simulation_percentiles([20, 30]) is None

def test_automatic_simulation_reuses_builtin_rule_without_activation_permission(client, tmp_path):
    from uuid import uuid4

    from aqp.store import connection

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload) "
            "VALUES(1,'R1','S1','Synthetic','synthetic','synthetic','master',2025,'{}')"
        )
    assert client.put(
        f"/api/users/{me['id']}/grants",
        headers=headers,
        json={
            "expected_version": me["version"],
            "request_id": str(uuid4()),
            "grants": [
                {"category": category, "operation": op, "college": "synthetic", "major": "synthetic"}
                for category in ("basic", "talent_evaluation", "courses", "research_papers", "patents", "awards", "conferences")
                for op in ("view", "identity", "analyze")
            ],
        },
    ).status_code == 200
    first = client.post("/api/evaluation-snapshots", headers=headers, json={"student_id": 1})
    assert first.status_code == 200, first.text
    second = client.post("/api/evaluation-snapshots", headers=headers, json={"student_id": 1})
    assert second.status_code == 200, second.text
    assert first.json()["rule_name"] == "内置多维模拟评分 v2"
    assert first.json()["ahp"]["consistency_ratio"] < 0.10
    assert [round(entry["weight"], 8) for entry in first.json()["ahp"]["dimensions"]] == [0.4, 0.4, 0.2]
    assert len(first.json()["inputs"]) == 6
    assert second.json()["rule_id"] == first.json()["rule_id"]
    assert first.json()["total"] is None
    evidence = client.get(f"/api/evaluation-snapshots/{first.json()['id']}").json()["signals"]
    assert len(evidence) == 6
    assert evidence[0]["items"][0]["value"] is None
    assert evidence[3]["items"] == []
    assert first.json()["inputs"][0]["missing"]


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
            (
                "P1",
                json.dumps({"title": "Synthetic Patent", "participants": [participant]}),
            ),
        )
        db.commit()
    score = client.post("/api/evaluation-snapshots", headers=headers, json=body).json()
    assert score["total"] == 25
    dashboard = client.get("/api/evaluation-snapshots/dashboard").json()["items"]
    assert len(dashboard) == 1
    assert dashboard[0]["id"] == score["id"]
    assert dashboard[0]["total"] == 25 and dashboard[0]["current"] is True
    drilldown = score["inputs"][0]["evidence"][0]
    assert drilldown["record_id"] == 1
    assert drilldown["business_key"] == "P1"
    assert drilldown["title"] == "Synthetic Patent"
    # Direct inserts carry no version history: the department stays null
    # instead of being fabricated.
    assert drilldown["source_department"] is None
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


def test_snapshot_listing_and_independent_export(client, tmp_path):
    import json
    from io import BytesIO
    from uuid import uuid4

    from aqp.store import connection
    from openpyxl import load_workbook

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]

    def update_grants(operations):
        nonlocal me
        assert (
            client.put(
                f"/api/users/{me['id']}/grants",
                headers=headers,
                json={
                    "expected_version": me["version"],
                    "request_id": str(uuid4()),
                    "grants": [
                        {
                            "category": category,
                            "operation": operation,
                            "college": "synthetic",
                            "major": "synthetic",
                        }
                        for category in ["basic", "talent_evaluation", "patents"]
                        for operation in operations
                    ],
                },
            ).status_code
            == 200
        )
        me = client.get("/api/me").json()["user"]

    update_grants(
        ["view", "identity", "analyze", "maintain", "activate_evaluation"]
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
        db.execute(
            "INSERT INTO patents_outputs(business_key,payload) VALUES(?,?)",
            ("P1", json.dumps({"participants": [participant]})),
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
                {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 4}
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
                "basis": "synthetic only",
                "acknowledge_simulation": True,
            },
        ).status_code
        == 200
    )
    score = client.post(
        "/api/evaluation-snapshots",
        headers=headers,
        json={"student_id": 1, "rule_id": rule["id"]},
    ).json()
    assert score["total"] == 25
    assert client.get("/api/evaluation-snapshots", headers=headers).json()[
        "items"
    ] == [
        {
            "id": score["id"],
            "student_id": 1,
            "research_id": "R1",
            "rule_id": rule["id"],
            "family_id": 1,
            "rule_version": 1,
            "mode": "simulation",
            "total": 25,
            "as_of": score["as_of"],
        }
    ]
    # A fresh snapshot is not stale, and presentation-only evidence edits do
    # not change the semantic data digest.
    fresh = client.get(f"/api/evaluation-snapshots/{score['id']}", headers=headers)
    assert fresh.status_code == 200
    assert fresh.json()["stale"] is False
    assert fresh.json()["family_id"] == 1
    report_url = "/api/reports/students/1"
    assert client.get(report_url, headers=headers).json()["sections"]["evaluation"]["total"] == 25
    assert client.get(report_url + "/export", headers=headers).status_code == 403

    with connection(dbpath) as db:
        row = json.loads(
            db.execute("SELECT payload FROM patents_outputs WHERE id=1").fetchone()[0]
        )
        row["title"] = "Renamed Synthetic Patent"
        db.execute(
            "UPDATE patents_outputs SET payload=? WHERE id=1",
            (json.dumps(row),),
        )
        db.commit()
    assert (
        client.get(f"/api/evaluation-snapshots/{score['id']}", headers=headers).json()[
            "stale"
        ]
        is False
    )
    # Full analysis access never grants the report download by itself.
    export = client.get(
        f"/api/evaluation-snapshots/{score['id']}/export", headers=headers
    )
    assert export.status_code == 403
    update_grants(
        ["view", "identity", "analyze", "maintain", "activate_evaluation", "export"]
    )
    export = client.get(
        f"/api/evaluation-snapshots/{score['id']}/export", headers=headers
    )
    assert export.status_code == 200
    assert export.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    workbook = load_workbook(BytesIO(export.content))
    cells = [
        cell.value
        for row in workbook.active.iter_rows()
        for cell in row
        if cell.value is not None
    ]
    workbook.close()
    assert any("模拟演示" in str(cell) for cell in cells)
    assert 25 in cells
    assert client.get(report_url + "/export", headers=headers).status_code == 200
    from test_agent import replace_grants

    full = ["view", "identity", "analyze", "export"]
    replace_grants(client, headers, [
        {"category": category, "operation": operation,
         "college": "synthetic", "major": "synthetic"}
        for category in ["basic", "talent_evaluation", "patents"]
        for operation in full
        if (category, operation) != ("patents", "export")
    ])
    assert client.get(report_url + "/export", headers=headers).status_code == 403
    assert client.get(report_url, headers=headers).json()["sections"]["evaluation"]["total"] == 25
    for revoked in ["view", "identity", "analyze"]:
        replace_grants(client, headers, [
            {"category": category, "operation": operation,
             "college": "synthetic", "major": "synthetic"}
            for category in ["basic", "talent_evaluation", "patents"]
            for operation in full
            if (category, operation) != ("patents", revoked)
        ])
        section = client.get(report_url, headers=headers).json()["sections"]["evaluation"]
        assert "total" not in section
    me = client.get("/api/me").json()["user"]
    update_grants(full)

    with connection(dbpath) as db:
        db.execute("UPDATE patents_outputs SET active=0 WHERE id=1")
        db.commit()
    stale_section = client.get(report_url, headers=headers).json()["sections"]["evaluation"]
    assert stale_section["status"] != "ok"
    assert "total" not in stale_section
    dashboard = client.get("/api/evaluation-snapshots/dashboard").json()["items"]
    assert dashboard[0]["total"] is None and dashboard[0]["current"] is False

    update_grants([])
    assert client.get("/api/evaluation-snapshots/dashboard").json() == {"items": []}
    assert client.get("/api/evaluation-snapshots", headers=headers).json() == {
        "items": []
    }
    assert (
        client.get(
            f"/api/evaluation-snapshots/{score['id']}/export", headers=headers
        ).status_code
        == 403
    )


def test_review_fixes_scope_lock_partial_grants_deactivation_audit(client, tmp_path):
    import json
    from uuid import uuid4

    from aqp.store import connection

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
                        "category": category,
                        "operation": operation,
                        "college": "synthetic",
                        "major": "synthetic",
                    }
                    for category in ["basic", "talent_evaluation", "patents"]
                    for operation in [
                        "view",
                        "identity",
                        "analyze",
                        "maintain",
                        "activate_evaluation",
                    ]
                ]
                + [
                    {
                        "category": "talent_evaluation",
                        "operation": "maintain",
                        "college": "elsewhere",
                        "major": "elsewhere",
                    }
                ],
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
            "INSERT INTO patents_outputs(business_key,payload) VALUES(?,?)",
            (
                "P1",
                json.dumps(
                    {
                        "title": "Synthetic Patent",
                        "participants": [
                            {
                                "student_number": "S1",
                                "name": "Synthetic",
                                "college": "synthetic",
                                "major": "synthetic",
                            }
                        ],
                    }
                ),
            ),
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
                {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 4}
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
                "basis": "synthetic",
                "acknowledge_simulation": True,
            },
        ).status_code
        == 200
    )
    score = client.post(
        "/api/evaluation-snapshots",
        headers=headers,
        json={"student_id": 1, "rule_id": rule["id"]},
    ).json()
    # Revisions may not change scope: a family activation retires the whole
    # family, so a scope change would silently disable another scope's rule.
    assert (
        client.post(
            "/api/evaluation-rules",
            headers=headers,
            json={
                "name": "scope shift",
                "college": "elsewhere",
                "major": "elsewhere",
                "mode": "simulation",
                "metrics": [
                    {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 4}
                ],
                "previous_id": rule["id"],
                "expected_version": 1,
            },
        ).status_code
        == 409
    )
    # Missing grants for one metric's source category refuse the whole score
    # without leaking any partially collected evidence.
    two_metrics = client.post(
        "/api/evaluation-rules",
        headers=headers,
        json={
            "name": "partial",
            "college": "synthetic",
            "major": "synthetic",
            "mode": "simulation",
            "expected_version": 0,
            "metrics": [
                {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 4},
                {
                    "feature": "course_pass_ratio",
                    "weight": 1,
                    "minimum": 0,
                    "maximum": 1,
                },
            ],
        },
    ).json()
    assert (
        client.post(
            f"/api/evaluation-rules/{two_metrics['id']}/activate",
            headers=headers,
            json={
                "expected_version": 1,
                "confirmed_by": "expert",
                "basis": "synthetic",
                "acknowledge_simulation": True,
            },
        ).status_code
        == 200
    )
    refused = client.post(
        "/api/evaluation-snapshots",
        headers=headers,
        json={"student_id": 1, "rule_id": two_metrics["id"]},
    )
    assert refused.status_code == 403
    assert "inputs" not in refused.json()
    # Deactivated students lose export access even with grants intact.
    with connection(dbpath) as db:
        db.execute("UPDATE students SET active=0 WHERE id=1")
        db.commit()
    assert (
        client.get(
            f"/api/evaluation-snapshots/{score['id']}/export", headers=headers
        ).status_code
        == 403
    )
    with connection(dbpath) as db:
        db.execute("UPDATE students SET active=1 WHERE id=1")
        db.commit()
    # Lists, reads and denials leave audit trails like the analysis module.
    assert (
        client.get(f"/api/evaluation-snapshots/{score['id']}", headers=headers).status_code
        == 200
    )
    assert client.get("/api/evaluation-snapshots", headers=headers).status_code == 200
    assert client.get("/api/evaluation-rules", headers=headers).status_code == 200
    with connection(dbpath) as db:
        actions = {
            row[0]
            for row in db.execute(
                "SELECT action FROM audit WHERE action LIKE 'evaluation.%'"
            )
        }
        denials = db.execute(
            "SELECT COUNT(*) FROM audit WHERE action='evaluation.access' AND outcome='denied'"
        ).fetchone()[0]
    assert {"evaluation.list", "evaluation.read", "evaluation.score"} <= actions
    assert denials >= 1


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
                "所属学院": "synthetic",
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
                    "weight": 1e308,
                    "minimum": 0,
                    "maximum": 1,
                },
                {
                    "feature": "latest_citation_count",
                    "weight": 1e308,
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
    assert abs(result["total"] - 55) < 0.00001
    reread = client.get(f"/api/evaluation-snapshots/{result['id']}")
    assert reread.status_code == 200
    assert abs(reread.json()["total"] - 55) < 0.00001
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


def test_course_scope_mismatch_excluded_with_disclosure(client, tmp_path):
    import json
    from uuid import uuid4

    from aqp.store import connection

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    grants = [
        {"category": cat, "operation": op, "college": "synthetic", "major": "synthetic"}
        for cat in [
            "basic",
            "talent_evaluation",
            "courses",
            "research_papers",
            "patents",
            "awards",
            "conferences",
        ]
        for op in ["view", "identity", "analyze"]
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
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload) VALUES(1,'R1','S1','Synthetic','synthetic','synthetic','master',2025,'{}')"
        )
        db.execute(
            "INSERT INTO import_batches(id,category,template_version,source_department,filename,file_hash,original_file,uploaded_by,created_at) VALUES(1,'courses','1','synthetic','synthetic','synthetic',X'00',?,1)",
            (me["id"],),
        )
        for ident, college, result in [
            (1, "synthetic", "通过"),
            (2, "旧学院", "通过"),
        ]:
            db.execute(
                "INSERT INTO import_rows(id,batch_id,sheet,row_number,raw_json,normalized_json,state) VALUES(?,1,'sheet',?,'{}','{}','linked')",
                (ident, ident),
            )
            db.execute(
                "INSERT INTO course_records(id,student_number,course_code,term,attempt,student_id,payload,state,source_row_id) VALUES(?,'S1',?,'2025',1,1,?,'linked',?)",
                (
                    ident,
                    str(ident),
                    json.dumps(
                        {
                            "所属学院": college,
                            "专业": "synthetic",
                            "评分制度": "百分制",
                            "业务通过结果": result,
                        }
                    ),
                    ident,
                ),
            )
    response = client.post(
        "/api/evaluation-snapshots", headers=headers, json={"student_id": 1}
    )
    assert response.status_code == 200, response.text
    snapshot = response.json()
    ratio = next(
        input for input in snapshot["inputs"] if input["feature"] == "course_pass_ratio"
    )
    assert ratio["value"] == 1.0
    statuses = {
        (entry["record_id"], entry["status"]) for entry in ratio["evidence"]
    }
    assert (1, "通过") in statuses
    assert (2, "范围不一致已排除") in statuses
