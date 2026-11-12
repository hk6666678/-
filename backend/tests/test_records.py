from uuid import uuid4

from test_accounts import client, login_admin  # noqa: F401
from test_students import workbook


def test_record_preview_confirm_conflict_history_and_void(client):  # noqa: F811
    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    grants = [
        {"category": "basic", "operation": op, "college": "示例学院", "major": "计算机"}
        for op in ["maintain", "view", "identity"]
    ]

    def grant(items):
        user = client.get("/api/me").json()["user"]
        return client.put(
            f"/api/users/{u['id']}/grants",
            headers=h,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": items,
            },
        )

    assert grant(grants).status_code == 200
    b = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    client.post(f"/api/imports/{b['id']}/confirm", headers=h)
    rows = client.get("/api/records/basic").json()
    rid = rows["items"][0]["id"]
    url = f"/api/records/basic/{rid}"
    p = client.post(
        url + "/preview",
        headers=h,
        json={
            "expected_version": 1,
            "data": {"研究方向": "合成方向"},
            "reason": "合成核实依据",
        },
    )
    assert p.status_code == 200, p.text
    assert p.json()["changes"]["研究方向"]["after"] == "合成方向"
    assert client.get(url).json()["version"] == 1
    body = {"proposal_id": p.json()["proposal_id"], "expected_version": 1}
    assert client.post(url + "/confirm", headers=h, json=body).status_code == 200
    assert client.post(url + "/confirm", headers=h, json=body).status_code == 409
    detail = client.get(url).json()
    assert detail["version"] == 2 and len(detail["revisions"]) == 1
    assert detail["revisions"][0]["before"]["姓名"] == "合成学生"
    void = {"expected_version": 2, "reason": "合成重复档案", "confirmed": True}
    assert client.post(url + "/void", headers=h, json=void).status_code == 403
    assert (
        grant(
            grants
            + [
                {
                    "category": "basic",
                    "operation": "void",
                    "college": "示例学院",
                    "major": "计算机",
                }
            ]
        ).status_code
        == 200
    )
    assert client.post(url + "/void", headers=h, json=void).status_code == 200
    assert client.get("/api/records/basic").json()["items"] == []
    assert client.get(url).json()["active"] is False


import pytest
from test_courses import course_file
from test_milestones import sheet


@pytest.mark.parametrize("category", ["courses", "topic", "midterm"])
def test_formal_business_records_keep_versions_and_source(client, category):  # noqa: F811
    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    assert (
        client.put(
            f"/api/users/{u['id']}/grants",
            headers=h,
            json={
                "expected_version": u["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": c,
                        "operation": op,
                        "college": "示例学院",
                        "major": "计算机",
                    }
                    for c in ["basic", category]
                    for op in ["maintain", "view", "identity", "void"]
                ],
            },
        ).status_code
        == 200
    )
    b = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    assert client.post(f"/api/imports/{b['id']}/confirm", headers=h).status_code == 200
    url = (
        "/api/imports/courses"
        if category == "courses"
        else f"/api/milestones/{category}"
    )
    content = (
        course_file([["001", "SYNTH", "2025一", "1", "百分制", "70", "合成学生"]])
        if category == "courses"
        else sheet(category)
    )
    batch = client.post(
        url + "/preview",
        headers=h,
        data={
            "source_department": "合成来源",
            "college": "示例学院",
            "major": "计算机",
        },
        files={"file": ("synthetic.xlsx", content)},
    ).json()
    confirm = (
        f"/api/imports/courses/{batch['id']}/confirm"
        if category == "courses"
        else f"/api/milestone-imports/{batch['id']}/confirm"
    )
    response = client.post(confirm, headers=h)
    assert response.status_code == 200, response.text
    rows = client.get(f"/api/records/{category}").json()["items"]
    assert len(rows) == 1
    url = f"/api/records/{category}/{rows[0]['id']}"
    bad = client.post(
        url + "/preview",
        headers=h,
        json={
            "expected_version": 1,
            "data": {"姓名": "另一个合成人"},
            "reason": "合成人工证据",
        },
    )
    assert bad.status_code == 409
    p = client.post(
        url + "/preview",
        headers=h,
        json={
            "expected_version": 1,
            "data": {"原始成绩": "81"},
            "reason": "合成成绩核实",
        },
    )
    assert p.status_code == 200, p.text
    assert client.get(url).json()["current"]["原始成绩"] != "81"
    body = {"proposal_id": p.json()["proposal_id"], "expected_version": 1}
    assert client.post(url + "/confirm", headers=h, json=body).status_code == 200
    assert client.post(url + "/confirm", headers=h, json=body).status_code == 409
    current = client.get(url).json()
    assert current["current"]["原始成绩"] == "81"
    assert current["revisions"][0]["source"]["source_department"] == "合成来源"
    assert current["dependency_token"].endswith(":2:1")
    assert (
        client.post(
            url + "/void",
            headers=h,
            json={"expected_version": 2, "reason": "合成作废", "confirmed": True},
        ).status_code
        == 200
    )
    assert client.get(f"/api/records/{category}").json()["items"] == []
    assert len(client.get(url).json()["revisions"]) == 2
