from uuid import uuid4

from test_accounts import client, login_admin  # noqa: F401
from test_students import workbook


def test_resolution_preserves_raw_and_requires_second_confirmation(client):  # noqa: F811
    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    client.put(
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
                for op in ["maintain", "identity"]
            ],
        },
    )
    b = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    row = client.get(f"/api/resolutions/{b['id']}").json()["rows"][0]
    assert row["original"]["姓名"]
    assert (
        client.post(
            f"/api/resolutions/rows/{row['id']}/confirm", headers=h, json={"version": 1}
        ).status_code
        == 409
    )
    invalid = client.get(f"/api/resolutions/{b['id']}").json()["rows"][1]
    fixed = {**invalid["data"], "姓名": "合成修复学生"}
    response = client.post(
        f"/api/resolutions/rows/{invalid['id']}/validate",
        headers=h,
        json={"data": fixed, "evidence": "合成学籍清单人工核实", "version": 0},
    )
    assert response.status_code == 200, response.text
    v = response.json()["rows"][1]
    assert v["original"]["姓名"] == ""
    assert v["data"]["姓名"] == ""
    assert v["revisions"][0]["data"]["姓名"] == "合成修复学生"
    assert v["revisions"][0]["actor_id"] == u["id"]
    assert client.get("/api/students").status_code == 403
    assert (
        client.post(
            f"/api/resolutions/rows/{invalid['id']}/confirm",
            headers=h,
            json={"version": 1},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/resolutions/rows/{invalid['id']}/confirm",
            headers=h,
            json={"version": 1},
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/resolutions/{b['id']}").json()["rows"][1]["state"]
        == "imported"
    )
    assert (
        client.post(
            f"/api/resolutions/rows/{invalid['id']}/validate",
            headers=h,
            json={"data": fixed, "evidence": "合成", "version": 1},
        ).status_code
        == 409
    )


import pytest
from test_courses import course_file
from test_milestones import sheet


@pytest.mark.parametrize("category", ["courses", "topic", "midterm"])
def test_correct_all_business_categories_without_reinserting_success(client, category):  # noqa: F811
    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    client.put(
        f"/api/users/{u['id']}/grants",
        headers=h,
        json={
            "expected_version": u["version"],
            "request_id": str(uuid4()),
            "grants": [
                {
                    "category": category,
                    "operation": op,
                    "college": "示例学院",
                    "major": "计算机",
                }
                for op in ["maintain", "identity", "export"]
            ],
        },
    )
    if category == "courses":
        url = "/api/imports/courses/preview"
        blob = course_file([["001", "C1", "2025秋", "1", "百分制", "-1", "合成学生"]])
        data = {"source_department": "合成", "college": "示例学院", "major": "计算机"}
    else:
        url = f"/api/milestones/{category}/preview"
        blob = sheet(
            category,
            [
                [
                    "001",
                    "合成学生",
                    "2025一",
                    "合成题目",
                    "百分制",
                    "-1",
                    "示例学院",
                    "计算机",
                ]
            ],
        )
        data = {"source_department": "合成"}
    preview = client.post(
        url, headers=h, data=data, files={"file": ("synthetic.xlsx", blob)}
    )
    assert preview.status_code == 200, preview.text
    batch = preview.json()
    row = batch["rows"][0]
    result = client.post(
        f"/api/resolutions/rows/{row['id']}/validate",
        headers=h,
        json={"data": {"原始成绩": "80"}, "evidence": "合成成绩单核实", "version": 0},
    )
    assert result.status_code == 200, result.text
    assert result.json()["rows"][0]["revisions"][0]["state"] == "pending"
    url = f"/api/resolutions/rows/{row['id']}/confirm"
    assert client.post(url, headers=h, json={"version": 1}).status_code == 200
    assert client.post(url, headers=h, json={"version": 1}).status_code == 200
    assert (
        client.get(f"/api/resolutions/{batch['id']}").json()["rows"][0]["original"][
            "原始成绩"
        ]
        == "-1"
    )
    assert client.get(f"/api/resolutions/{batch['id']}/errors.xlsx").status_code == 200


def test_unknown_scope_is_redacted_and_correctable_only_after_authorization(client):  # noqa: F811
    from io import BytesIO

    from openpyxl import load_workbook

    h = login_admin(client)
    u = client.get("/api/me").json()["user"]

    def grants(operations):
        current = client.get("/api/me").json()["user"]
        return client.put(
            f"/api/users/{u['id']}/grants",
            headers=h,
            json={
                "expected_version": current["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": "basic",
                        "operation": op,
                        "college": "示例学院",
                        "major": "计算机",
                    }
                    for op in operations
                ],
            },
        )

    grants(["maintain", "identity", "export"])
    wb = load_workbook(BytesIO(workbook()))
    ws = wb.active
    ws.cell(3, 3).value = ""
    ws.cell(3, 2).value = '=HYPERLINK("https://synthetic.invalid")'
    stream = BytesIO()
    wb.save(stream)
    result = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert result.status_code == 200, result.text
    batch = result.json()
    row = client.get(f"/api/resolutions/{batch['id']}").json()["rows"][0]
    assert "姓名" not in row["original"] and "学号" not in row["data"]
    result = client.post(
        f"/api/resolutions/rows/{row['id']}/validate",
        headers=h,
        json={"data": {"所属学院": "其他学院"}, "evidence": "合成", "version": 0},
    )
    assert result.status_code == 403
    result = client.post(
        f"/api/resolutions/rows/{row['id']}/validate",
        headers=h,
        json={
            "data": {"所属学院": "示例学院"},
            "evidence": "合成范围核实",
            "version": 0,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["rows"][0]["revisions"][0]["data"]["姓名"].startswith("=")
    assert (
        client.post(
            f"/api/resolutions/rows/{row['id']}/confirm", headers=h, json={"version": 2}
        ).status_code
        == 409
    )
    grants(["maintain"])
    assert (
        client.post(
            f"/api/resolutions/rows/{row['id']}/confirm", headers=h, json={"version": 1}
        ).status_code
        == 403
    )


def test_identity_conflict_must_be_resolved_without_merging_archive(client):  # noqa: F811
    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    client.put(
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
                for op in ["maintain", "identity", "view"]
            ],
        },
    )

    def preview():
        return client.post(
            "/api/imports/basic/preview",
            headers=h,
            data={"source_department": "合成"},
            files={"file": ("synthetic.xlsx", workbook())},
        ).json()

    batch = preview()
    client.post(f"/api/imports/{batch['id']}/confirm", headers=h)
    original = client.get("/api/students").json()["items"][0]
    batch = preview()
    row = batch["rows"][1]
    result = client.post(
        f"/api/resolutions/rows/{row['id']}/validate",
        headers=h,
        json={
            "data": {"学号": "001", "姓名": "合成另一人"},
            "evidence": "合成同号多人核查",
            "version": 0,
        },
    )
    assert result.json()["rows"][1]["revisions"][0]["state"] == "conflict"
    assert (
        client.post(
            f"/api/resolutions/rows/{row['id']}/confirm", headers=h, json={"version": 1}
        ).status_code
        == 409
    )
    assert client.get("/api/students").json()["items"][0] == original


def test_other_authorized_maintainer_can_resolve_but_cannot_cross_scope(client):  # noqa: F811
    from fastapi.testclient import TestClient

    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    grant = [
        {"category": "basic", "operation": op, "college": "示例学院", "major": "计算机"}
        for op in ["maintain", "identity"]
    ]
    client.put(
        f"/api/users/{u['id']}/grants",
        headers=h,
        json={
            "expected_version": u["version"],
            "request_id": str(uuid4()),
            "grants": grant,
        },
    )
    batch = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    row = batch["rows"][1]
    user = client.post(
        "/api/users",
        headers=h,
        json={
            "username": "synthetic-resolver",
            "password": "Synthetic-password-123!",
            "roles": ["college_data_admin"],
            "request_id": str(uuid4()),
        },
    ).json()
    client.put(
        f"/api/users/{user['id']}/grants",
        headers=h,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": grant,
        },
    )
    with TestClient(client.app) as member:
        session = member.post(
            "/api/login",
            json={
                "username": "synthetic-resolver",
                "password": "Synthetic-password-123!",
            },
        ).json()
        mh = {"X-CSRF-Token": session["csrf_token"]}
        assert member.get(f"/api/resolutions/{batch['id']}").status_code == 200
        assert (
            member.get(f"/api/resolutions/{batch['id']}/errors.xlsx").status_code == 403
        )
        assert (
            member.post(
                f"/api/resolutions/rows/{row['id']}/validate",
                headers=mh,
                json={
                    "data": {"姓名": "合成修复", "所属学院": "无权学院"},
                    "version": 0,
                    "evidence": "合成",
                },
            ).status_code
            == 403
        )
        assert (
            member.post(
                f"/api/resolutions/rows/{row['id']}/validate",
                headers=mh,
                json={
                    "data": {"姓名": "合成修复"},
                    "version": 0,
                    "evidence": "合成清单核实",
                },
            ).status_code
            == 200
        )
        assert (
            member.post(
                f"/api/resolutions/rows/{row['id']}/confirm",
                headers=mh,
                json={"version": 1},
            ).status_code
            == 200
        )
