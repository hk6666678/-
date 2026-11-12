from io import BytesIO
from uuid import uuid4

from openpyxl import load_workbook
from test_accounts import client, login_admin  # noqa: F401


def test_excel_export_is_scoped_download_and_safe_text(client):  # noqa: F811
    h = login_admin(client)

    def grants(ops):
        u = client.get("/api/me").json()["user"]
        return client.put(
            f"/api/users/{u['id']}/grants",
            headers=h,
            json={
                "expected_version": u["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": "courses",
                        "operation": op,
                        "college": "=合成学院",
                        "major": "合成专业",
                    }
                    for op in ops
                ],
            },
        )

    grants(["view", "analyze", "export"])
    s = client.post(
        "/api/analyses/courses",
        headers=h,
        json={"college": "=合成学院", "major": "合成专业"},
    ).json()
    r = client.get(f"/api/analyses/{s['id']}/export")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    wb = load_workbook(BytesIO(r.content))
    cells = [c for ws in wb for row in ws for c in row]
    assert any(c.value == "=合成学院" and c.data_type == "s" for c in cells)
    assert {"generated_at", "data_version", "rule_version", "stale"} <= {
        c.value for c in cells if isinstance(c.value, str)
    }
    grants(["view", "analyze", "download"])
    assert client.get(f"/api/analyses/{s['id']}/export").status_code == 403


def test_original_excel_requires_download_identity_and_all_rows(client):  # noqa: F811
    from test_students import workbook

    h = login_admin(client)

    def grants(ops):
        u = client.get("/api/me").json()["user"]
        return client.put(
            f"/api/users/{u['id']}/grants",
            headers=h,
            json={
                "expected_version": u["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": "basic",
                        "operation": op,
                        "college": "示例学院",
                        "major": "计算机",
                    }
                    for op in ops
                ],
            },
        )

    grants(["maintain", "export"])
    original = workbook()
    b = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("synthetic.xlsx", original)},
    ).json()
    url = f"/api/imports/{b['id']}/download"
    assert client.get(url).status_code == 403
    grants(["maintain", "download", "identity"])
    r = client.get(url)
    assert r.status_code == 200
    assert r.content == original
    grants(["maintain", "download"])
    assert client.get(url).status_code == 403


def test_paper_reports_recheck_export_separately_from_originals(client, tmp_path):  # noqa: F811
    from test_candidates import candidate_setup

    h, ids = candidate_setup(client, tmp_path)
    s = client.post(f"/api/papers/{ids[0]}/comparisons", headers=h, json={}).json()
    candidate = client.post(
        "/api/candidate-results", headers=h, json={"comparison_id": s["id"]}
    ).json()
    urls = [
        f"/api/paper-comparisons/{s['id']}/export",
        f"/api/candidate-results/{candidate['id']}/export",
    ]
    assert all(client.get(url).status_code == 403 for url in urls)
    u = client.get("/api/me").json()["user"]
    grants = [
        {
            "category": "papers",
            "operation": op,
            "college": "示例学院",
            "major": "计算机",
        }
        for op in ["view", "analyze", "identity", "export"]
    ]
    client.put(
        f"/api/users/{u['id']}/grants",
        headers=h,
        json={
            "expected_version": u["version"],
            "request_id": str(uuid4()),
            "grants": grants,
        },
    )
    for url in urls:
        r = client.get(url)
        assert r.status_code == 200
        assert load_workbook(BytesIO(r.content)).active.max_row > 10
    assert client.get(f"/api/papers/{ids[0]}/download").status_code == 403


def test_original_rejects_untracked_sheet_rows(client):  # noqa: F811
    from test_students import workbook

    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    grants = [
        {"category": "basic", "operation": op, "college": "示例学院", "major": "计算机"}
        for op in ["maintain", "download", "identity"]
    ]
    assert (
        client.put(
            f"/api/users/{u['id']}/grants",
            headers=h,
            json={
                "expected_version": u["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        ).status_code
        == 200
    )
    wb = load_workbook(BytesIO(workbook()))
    ws = wb.create_sheet("未知资料")
    ws.append(["合成范围外学生", "其他学院"])
    output = BytesIO()
    wb.save(output)
    batch = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("synthetic.xlsx", output.getvalue())},
    ).json()
    assert client.get(f"/api/imports/{batch['id']}/download").status_code == 403


def test_original_checks_current_student_scope_after_correction(client):  # noqa: F811
    from test_students import workbook

    h = login_admin(client)

    def grant(colleges):
        u = client.get("/api/me").json()["user"]
        return client.put(
            f"/api/users/{u['id']}/grants",
            headers=h,
            json={
                "expected_version": u["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": "basic",
                        "operation": op,
                        "college": college,
                        "major": "计算机",
                    }
                    for college in colleges
                    for op in ["maintain", "view", "identity", "download"]
                ],
            },
        )

    assert grant(["示例学院", "合成新学院"]).status_code == 200
    b = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    assert client.post(f"/api/imports/{b['id']}/confirm", headers=h).status_code == 200
    rid = client.get("/api/records/basic").json()["items"][0]["id"]
    url = f"/api/records/basic/{rid}"
    proposal = client.post(
        url + "/preview",
        headers=h,
        json={
            "expected_version": 1,
            "data": {"所属学院": "合成新学院"},
            "reason": "合成范围更正",
        },
    )
    assert proposal.status_code == 200, proposal.text
    assert (
        client.post(
            url + "/confirm",
            headers=h,
            json={"expected_version": 1, "proposal_id": proposal.json()["proposal_id"]},
        ).status_code
        == 200
    )
    assert client.get(f"/api/imports/{b['id']}/download").status_code == 200
    assert grant(["示例学院"]).status_code == 200
    assert client.get(f"/api/imports/{b['id']}/download").status_code == 403
