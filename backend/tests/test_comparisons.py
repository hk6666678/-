# ruff: noqa: F811
from uuid import uuid4

from test_accounts import client  # noqa: F401
from test_papers import paper_setup, text_pdf, upload_paper


def grant_comparison(client, headers):
    me = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{me['id']}/grants",
        headers=headers,
        json={
            "expected_version": me["version"],
            "request_id": str(uuid4()),
            "grants": [
                {
                    "category": "papers",
                    "operation": op,
                    "college": "示例学院",
                    "major": "计算机",
                }
                for op in [
                    "view",
                    "identity",
                    "analyze",
                    "labels",
                    "maintain",
                    "download",
                ]
            ],
        },
    )
    assert response.status_code == 200


def test_pending_label_history_missing_groups_and_stale_target(client):
    headers = paper_setup(client)
    item = upload_paper(client, headers, text_pdf()).json()
    grant_comparison(client, headers)
    ident = item["id"]
    assert client.get(f"/api/papers/{ident}/labels").json()["label"] == "待评"
    first = client.post(
        f"/api/papers/{ident}/comparisons", headers=headers, json={}
    ).json()
    assert first["sufficient"] is False
    assert first["groups"] == {}
    body = {
        "label": "优秀",
        "confirmed_by": "合成专家",
        "basis": "合成书面确认",
        "expected_version": 0,
    }
    label = client.post(f"/api/papers/{ident}/labels", headers=headers, json=body)
    assert label.status_code == 200
    assert label.json()["entered_by"] == client.get("/api/me").json()["user"]["id"]
    assert (
        client.post(
            f"/api/papers/{ident}/labels", headers=headers, json=body
        ).status_code
        == 409
    )

    assert client.get(f"/api/paper-comparisons/{first['id']}").json()["stale"] is True
    assert (
        client.get(f"/api/papers/{ident}/labels").json()["items"][0]["basis"]
        == "合成书面确认"
    )


def test_same_group_counts_missing_year_and_self_exclusion(client, tmp_path):
    from io import BytesIO

    from aqp.paper_worker import run_once
    from openpyxl import Workbook
    from test_accounts import login_admin

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    grants = [
        {"category": cat, "operation": op, "college": "示例学院", "major": "计算机"}
        for cat in ["basic", "papers"]
        for op in ["maintain", "view", "identity", "analyze", "labels"]
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
    for i in range(1, 6):
        ws.append([str(i), "合成样本" + str(i), "示例学院", "计算机", "硕士", "2025"])
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
    for i in range(1, 6):
        item = client.post(
            "/api/papers",
            headers=headers,
            data={
                "student_id": i,
                "title": "合成论文",
                "expected_version": 0,
                "covered_student_ids": f"[{i}]",
                "level": "硕士",
                "discipline": "数学" if i == 5 else "计算机",
                "year": "2024" if i == 4 else "2025",
            },
            files={"file": ("synthetic.pdf", text_pdf() if i != 3 else b"broken")},
        ).json()
        ids.append(item["id"])
        assert run_once(tmp_path / "accounts.sqlite3")
        if i != 4:
            assert (
                client.post(
                    f"/api/papers/{item['id']}/labels",
                    headers=headers,
                    json={
                        "label": "优秀" if i in (1, 2, 5) else "普通",
                        "confirmed_by": "合成专家",
                        "basis": "合成确认",
                        "expected_version": 0,
                    },
                ).status_code
                == 200
            )
    result = client.post(
        f"/api/papers/{ids[0]}/comparisons", headers=headers, json={"year": "2025"}
    ).json()
    assert result["groups"]["优秀"]["sample_count"] == 1
    assert result["groups"]["普通"]["sample_count"] == 1
    assert result["groups"]["待评"]["sample_count"] == 0
    assert result["groups"]["优秀"]["features"]["page_count"] == {
        "missing": 0,
        "denominator": 1,
        "mean": 1.0,
    }
    assert result["groups"]["普通"]["features"]["page_count"] == {
        "missing": 1,
        "denominator": 0,
        "mean": None,
    }


def test_labels_require_independent_permission(client):
    headers = paper_setup(client)
    paper = upload_paper(client, headers, text_pdf()).json()
    response = client.post(
        f"/api/papers/{paper['id']}/labels",
        headers=headers,
        json={
            "label": "优秀",
            "confirmed_by": "合成专家",
            "basis": "合成专家书面确认",
            "expected_version": 0,
        },
    )
    assert response.status_code == 403
