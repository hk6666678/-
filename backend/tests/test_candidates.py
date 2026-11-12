# ruff: noqa: F811
from test_accounts import client  # noqa: F401
from test_papers import paper_setup


def test_rule_configuration_requires_independent_authorization(client):
    headers = paper_setup(client)
    response = client.post(
        "/api/candidate-rules",
        headers=headers,
        json={
            "name": "合成验证规则",
            "college": "示例学院",
            "major": "计算机",
            "level": "硕士",
            "conditions": [{"feature": "page_count", "operator": "gte", "value": 1}],
            "required_evidence": ["pages"],
            "minimum_samples": 1,
            "missing_policy": "insufficient",
            "synthetic": True,
        },
    )
    assert response.status_code == 403


def synthetic_rule(**changes):
    return {
        "name": "合成验证规则（非业务标准）",
        "college": "示例学院",
        "major": "计算机",
        "level": "硕士",
        "conditions": [{"feature": "page_count", "operator": "gte", "value": 1}],
        "required_evidence": ["pages"],
        "minimum_samples": 1,
        "missing_policy": "insufficient",
        "synthetic": True,
        **changes,
    }


def candidate_setup(client, tmp_path):
    from io import BytesIO
    from uuid import uuid4

    from aqp.paper_worker import run_once
    from openpyxl import Workbook
    from test_accounts import login_admin
    from test_papers import text_pdf

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    grants = [
        {"category": cat, "operation": op, "college": "示例学院", "major": "计算机"}
        for cat in ["basic", "papers"]
        for op in [
            "maintain",
            "view",
            "identity",
            "analyze",
            "labels",
            "candidate_rules",
            "download",
        ]
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
    wb = Workbook()
    ws = wb.active
    ws.append(["AQP-PGS", "basic", "1"])
    ws.append(["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"])
    for i in range(1, 4):
        ws.append([str(i), "合成样本", "示例学院", "计算机", "硕士", "2025"])
    out = BytesIO()
    wb.save(out)
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("synthetic.xlsx", out.getvalue())},
    ).json()
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    ids = []
    for i in range(1, 4):
        r = client.post(
            "/api/papers",
            headers=headers,
            data={
                "student_id": i,
                "title": "合成论文",
                "expected_version": 0,
                "covered_student_ids": f"[{i}]",
                "level": "硕士",
                "discipline": "计算机",
                "year": "2025",
            },
            files={"file": ("synthetic.pdf", text_pdf())},
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
        assert run_once(tmp_path / "accounts.sqlite3")
        if i > 1:
            assert (
                client.post(
                    f"/api/papers/{ids[-1]}/labels",
                    headers=headers,
                    json={
                        "label": "优秀" if i == 2 else "普通",
                        "confirmed_by": "合成专家",
                        "basis": "合成书面依据",
                        "expected_version": 0,
                    },
                ).status_code
                == 200
            )
    return headers, ids


def test_candidate_versions_explain_conditions_and_recheck_evidence_access(
    client, tmp_path
):
    headers, ids = candidate_setup(client, tmp_path)
    comp = client.post(
        f"/api/papers/{ids[0]}/comparisons", headers=headers, json={}
    ).json()

    def evaluate():
        r = client.post(
            "/api/candidate-results",
            headers=headers,
            json={"comparison_id": comp["id"]},
        )
        assert r.status_code == 200, r.text
        return r.json()

    empty = evaluate()
    assert empty["recommended"] is False
    rule = client.post(
        "/api/candidate-rules", headers=headers, json=synthetic_rule()
    ).json()
    assert rule["enabled"] == 0
    assert evaluate()["recommended"] is False
    confirmation = {
        "confirmed_by": "合成专家",
        "basis": "软件合成测试确认，不是业务标准",
    }
    assert (
        client.post(
            f"/api/candidate-rules/{rule['id']}/enable",
            headers=headers,
            json=confirmation,
        ).status_code
        == 200
    )
    hit = evaluate()
    assert hit["recommended"] is True
    assert hit["rules"][0]["checks"][0]["status"] == "命中"
    assert (
        hit["file_sha256"]
        and hit["evidence_versions"]
        and hit["groups"]["优秀"]["sample_count"] == 1
    )
    assert client.get(hit["evidence_url"]).status_code == 200
    assert client.get(f"/api/candidate-results/{empty['id']}").json()["stale"] is True
    revised = client.post(
        "/api/candidate-rules",
        headers=headers,
        json=synthetic_rule(
            previous_id=rule["id"],
            conditions=[{"feature": "page_count", "operator": "gte", "value": 2}],
        ),
    ).json()
    assert revised["version"] == 2
    assert (
        client.post(
            f"/api/candidate-rules/{revised['id']}/enable",
            headers=headers,
            json=confirmation,
        ).status_code
        == 200
    )
    assert client.get(f"/api/candidate-results/{hit['id']}").json()["stale"] is True
    miss = evaluate()
    assert miss["id"] != hit["id"] and miss["recommended"] is False
    assert miss["rules"][0]["checks"][0]["status"] == "未命中"
    insufficient = client.post(
        "/api/candidate-rules",
        headers=headers,
        json=synthetic_rule(previous_id=revised["id"], minimum_samples=2),
    ).json()
    client.post(
        f"/api/candidate-rules/{insufficient['id']}/enable",
        headers=headers,
        json=confirmation,
    )
    assert evaluate()["rules"][0]["checks"][0]["status"] == "证据不足"
    from uuid import uuid4

    me = client.get("/api/me").json()["user"]
    grants = client.get("/api/access/grants").json()
    assert (
        client.put(
            f"/api/users/{me['id']}/grants",
            headers=headers,
            json={
                "expected_version": me["version"],
                "request_id": str(uuid4()),
                "grants": [g for g in grants if g["operation"] != "identity"],
            },
        ).status_code
        == 200
    )
    assert client.get(f"/api/candidate-results/{hit['id']}").status_code == 403


def test_rule_rejects_executable_conditions(client):
    headers = paper_setup(client)
    assert (
        client.post(
            "/api/candidate-rules",
            headers=headers,
            json=synthetic_rule(
                conditions=[{"feature": "__import__", "operator": "eval", "value": 1}]
            ),
        ).status_code
        == 422
    )


def test_missing_pages_and_changed_comparison_never_recommend(client, tmp_path):
    from aqp.paper_worker import run_once
    from test_attachments import pdf

    headers, ids = candidate_setup(client, tmp_path)
    rule = client.post(
        "/api/candidate-rules", headers=headers, json=synthetic_rule()
    ).json()
    client.post(
        f"/api/candidate-rules/{rule['id']}/enable",
        headers=headers,
        json={"confirmed_by": "合成专家", "basis": "合成测试"},
    )
    response = client.post(
        "/api/papers",
        headers=headers,
        data={
            "student_id": 1,
            "title": "缺失原页合成样本",
            "expected_version": 1,
            "covered_student_ids": "[1]",
            "level": "硕士",
            "discipline": "计算机",
            "year": "2025",
        },
        files={"file": ("synthetic.pdf", pdf())},
    )
    assert response.status_code == 200, response.text
    assert run_once(tmp_path / "accounts.sqlite3")
    target = response.json()["id"]
    comp = client.post(
        f"/api/papers/{target}/comparisons", headers=headers, json={}
    ).json()
    result = client.post(
        "/api/candidate-results", headers=headers, json={"comparison_id": comp["id"]}
    ).json()
    assert result["recommended"] is False
    assert "pages" in result["rules"][0]["missing"]
    assert result["rules"][0]["checks"][0]["status"] == "证据不足"
    client.post(
        f"/api/papers/{ids[1]}/labels",
        headers=headers,
        json={
            "label": "普通",
            "confirmed_by": "合成专家",
            "basis": "合成更正",
            "expected_version": 1,
        },
    )
    assert client.get(f"/api/candidate-results/{result['id']}").json()["stale"] is True
    assert (
        client.post(
            "/api/candidate-results",
            headers=headers,
            json={"comparison_id": comp["id"]},
        ).status_code
        == 409
    )
