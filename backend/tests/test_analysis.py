from uuid import uuid4

from test_accounts import client, login_admin  # noqa: F401


def test_analysis_rules_and_immutable_unknown_snapshot(client):  # noqa: F811
    h = login_admin(client)
    body = {
        "college": "合成学院",
        "major": "合成专业",
        "course_code": "SYN",
        "grading": "百分制",
        "threshold": 70,
        "confirmed": True,
        "reason": "合成业务确认",
    }
    assert client.post("/api/pass-rules", headers=h, json=body).status_code == 403
    u = client.get("/api/me").json()["user"]
    grants = [
        {
            "category": "courses",
            "operation": op,
            "college": "合成学院",
            "major": "合成专业",
        }
        for op in ["view", "analyze", "pass_rules"]
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
    snapshot = client.post(
        "/api/analyses/courses",
        headers=h,
        json={"college": "合成学院", "major": "合成专业"},
    )
    assert snapshot.status_code == 200
    sid = snapshot.json()["id"]
    assert snapshot.json()["result"]["pass_rate"] is None
    assert client.post("/api/pass-rules", headers=h, json=body).status_code == 200
    old = client.get(f"/api/analyses/{sid}").json()
    assert old["stale"] is True
    assert old["result"]["pass_rate"] is None
    u = client.get("/api/me").json()["user"]
    client.put(
        f"/api/users/{u['id']}/grants",
        headers=h,
        json={
            "expected_version": u["version"],
            "request_id": str(uuid4()),
            "grants": [],
        },
    )
    assert client.get(f"/api/analyses/{sid}").status_code == 403


def test_eight_assessments_distribution_evidence_and_changes(client):  # noqa: F811
    from io import BytesIO

    from openpyxl import Workbook
    from test_students import workbook

    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    grants = [
        {"category": c, "operation": op, "college": "示例学院", "major": "计算机"}
        for c in ["basic", "courses"]
        for op in ["maintain", "view", "analyze", "void"]
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
    b = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("basic.xlsx", workbook())},
    ).json()
    client.post(f"/api/imports/{b['id']}/confirm", headers=h)
    wb = Workbook()
    ws = wb.active
    ws.append(["AQP-PGS", "courses", "1"])
    ws.append(
        [
            "学号",
            "姓名",
            "课程编号",
            "课程名称",
            "修读学期",
            "考核次数",
            "评分制度",
            "原始成绩",
            "业务通过结果",
        ]
    )
    for i, status in enumerate(["通过"] * 4 + ["不通过"] * 2 + ["", ""]):
        ws.append(
            [
                "001",
                "合成学生",
                "SYN",
                "合成课程",
                "2025秋",
                i + 1,
                "百分制",
                "" if i > 5 else 80,
                status,
            ]
        )
    stream = BytesIO()
    wb.save(stream)
    b = client.post(
        "/api/imports/courses/preview",
        headers=h,
        data={"source_department": "合成", "college": "示例学院", "major": "计算机"},
        files={"file": ("courses.xlsx", stream.getvalue())},
    ).json()
    client.post(f"/api/imports/courses/{b['id']}/confirm", headers=h)
    result = client.post(
        "/api/analyses/courses",
        headers=h,
        json={"college": "示例学院", "major": "计算机"},
    ).json()
    assert result["result"]["assessment_count"] == 8
    assert result["result"]["student_count"] == 1
    assert result["result"]["pass_rate"] == 66.67
    assert result["result"]["unknown"] == 2
    assert result["result"]["missing_scores"] == 2
    assert result["result"]["groups"][0]["mean"] == 80
    assert "学号" not in result["evidence"][0]["payload"]
    assert client.get(f"/api/analyses/{result['id']}/export").status_code == 403
    rid = result["evidence"][0]["id"]
    assert (
        client.post(
            f"/api/records/courses/{rid}/void",
            headers=h,
            json={"expected_version": 1, "reason": "合成作废", "confirmed": True},
        ).status_code
        == 200
    )
    old = client.get(f"/api/analyses/{result['id']}").json()
    assert old["stale"] is True
    assert old["result"]["assessment_count"] == 8
    new = client.post(
        "/api/analyses/courses",
        headers=h,
        json={"college": "示例学院", "major": "计算机"},
    ).json()
    assert new["id"] != old["id"]
    assert new["result"]["assessment_count"] == 7


def test_confirmed_scoped_rules_do_not_mix_grades_or_replace_business_result(client):  # noqa: F811
    from io import BytesIO

    from openpyxl import Workbook
    from test_students import workbook

    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    grants = [
        {"category": c, "operation": op, "college": "示例学院", "major": "计算机"}
        for c in ["basic", "courses"]
        for op in ["maintain", "view", "analyze", "pass_rules"]
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
    b = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成"},
        files={"file": ("basic.xlsx", workbook())},
    ).json()
    client.post(f"/api/imports/{b['id']}/confirm", headers=h)
    wb = Workbook()
    ws = wb.active
    ws.append(["AQP-PGS", "courses", "1"])
    ws.append(
        [
            "学号",
            "姓名",
            "课程编号",
            "课程名称",
            "修读学期",
            "考核次数",
            "评分制度",
            "原始成绩",
            "业务通过结果",
        ]
    )
    for i, (grading, score, status) in enumerate(
        [
            ("百分制", 65, ""),
            ("百分制", 90, "不通过"),
            ("百分制", "", ""),
            ("五级制", "优秀", ""),
        ]
    ):
        ws.append(
            [
                "001",
                "合成学生",
                "SYN",
                "合成课程",
                "2025秋",
                i + 1,
                grading,
                score,
                status,
            ]
        )
    stream = BytesIO()
    wb.save(stream)
    b = client.post(
        "/api/imports/courses/preview",
        headers=h,
        data={"source_department": "合成", "college": "示例学院", "major": "计算机"},
        files={"file": ("courses.xlsx", stream.getvalue())},
    ).json()
    client.post(f"/api/imports/courses/{b['id']}/confirm", headers=h)
    scope = {"college": "示例学院", "major": "计算机", "course_code": "SYN"}
    original = client.post("/api/analyses/courses", headers=h, json=scope).json()
    assert original["result"]["unknown"] == 3
    rule = {
        **scope,
        "grading": "百分制",
        "threshold": 70,
        "confirmed": False,
        "reason": "合成确认",
    }
    assert client.post("/api/pass-rules", headers=h, json=rule).status_code == 422
    assert (
        client.post(
            "/api/pass-rules", headers=h, json={**rule, "confirmed": True}
        ).json()["version"]
        == 1
    )
    grade = {
        **scope,
        "grading": "五级制",
        "passing_values": ["优秀", "良好"],
        "confirmed": True,
        "reason": "合成等级规则",
    }
    assert client.post("/api/pass-rules", headers=h, json=grade).status_code == 200
    current = client.post("/api/analyses/courses", headers=h, json=scope).json()
    assert current["result"]["passed"] == 1
    assert current["result"]["failed"] == 2
    assert current["result"]["unknown"] == 1
    assert [g["mean"] for g in current["result"]["groups"]] == [77.5, None]
    assert current["evidence"][1]["rule_id"] is None
    assert client.get(f"/api/analyses/{original['id']}").json()["stale"] is True
    assert (
        client.post(
            "/api/pass-rules",
            headers=h,
            json={**rule, "threshold": 60, "confirmed": True},
        ).json()["version"]
        == 2
    )
    latest = client.post("/api/analyses/courses", headers=h, json=scope).json()
    assert latest["result"]["passed"] == 2
    student = client.get("/api/records/basic").json()["items"][0]
    proposal = client.post(
        f"/api/records/basic/{student['id']}/preview",
        headers=h,
        json={
            "expected_version": student["version"],
            "data": {"入学年份": "2024"},
            "reason": "合成更正入学年份",
        },
    ).json()
    assert (
        client.post(
            f"/api/records/basic/{student['id']}/confirm",
            headers=h,
            json={
                "proposal_id": proposal["proposal_id"],
                "expected_version": student["version"],
            },
        ).status_code
        == 200
    )
    assert client.get(f"/api/analyses/{latest['id']}").json()["stale"] is True
