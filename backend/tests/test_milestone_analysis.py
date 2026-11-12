from uuid import uuid4

from test_accounts import client, login_admin  # noqa: F401


def test_milestone_snapshot_requires_category_grants_and_keeps_history(client):  # noqa: F811
    h = login_admin(client)
    scope = {
        "college": "合成学院09",
        "major": "合成专业09",
        "grade": "2025",
        "level": "硕士",
    }
    assert client.post("/api/analyses/topic", headers=h, json=scope).status_code == 403
    u = client.get("/api/me").json()["user"]

    def grant(ops):
        user = client.get("/api/me").json()["user"]
        assert (
            client.put(
                f"/api/users/{u['id']}/grants",
                headers=h,
                json={
                    "expected_version": user["version"],
                    "request_id": str(uuid4()),
                    "grants": [
                        {
                            "category": "topic",
                            "operation": op,
                            "college": scope["college"],
                            "major": scope["major"],
                        }
                        for op in ops
                    ],
                },
            ).status_code
            == 200
        )

    grant(["view", "analyze", "pass_rules"])
    r = client.post("/api/analyses/topic", headers=h, json=scope)
    assert r.status_code == 200
    snapshot = r.json()
    assert snapshot["category"] == "topic"
    assert snapshot["result"]["unknown"] == 0
    assert snapshot["result"]["credit_progress"]["value"] is None
    assert "培养要求" in snapshot["result"]["credit_progress"]["missing_conditions"]
    assert (
        client.post(
            "/api/pass-rules",
            headers=h,
            json={
                **scope,
                "category": "topic",
                "course_code": "批次09",
                "grading": "百分制",
                "threshold": 75,
                "confirmed": True,
                "reason": "合成业务确认",
            },
        ).status_code
        == 200
    )
    assert client.get(f"/api/analyses/{snapshot['id']}").json()["stale"]
    grant([])
    assert client.get(f"/api/analyses/{snapshot['id']}").status_code == 403


def test_cross_major_analysis_uses_each_authorized_major_scope(client):  # noqa: F811
    from io import BytesIO

    from openpyxl import Workbook
    from test_milestones import sheet

    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    college = "跨专业合成学院09"
    majors = ["授权专业一", "授权专业二", "未授权专业三"]

    def replace_grants(rows):
        user = client.get("/api/me").json()["user"]
        assert (
            client.put(
                f"/api/users/{u['id']}/grants",
                headers=h,
                json={
                    "expected_version": user["version"],
                    "request_id": str(uuid4()),
                    "grants": rows,
                },
            ).status_code
            == 200
        )

    replace_grants(
        [
            {"category": "basic", "operation": op, "college": college, "major": major}
            for major in majors
            for op in ["maintain", "view", "identity"]
        ]
        + [
            {"category": category, "operation": op, "college": college, "major": major}
            for category in ["topic", "courses"]
            for major in majors
            for op in ["maintain", "view"]
        ]
    )
    basic = Workbook()
    ws = basic.active
    assert ws is not None
    ws.append(["AQP-PGS", "basic", "1"])
    ws.append(["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"])
    for i, major in enumerate(majors, 1):
        ws.append([f"SYN-CROSS-{i}", f"合成学生{i}", college, major, "硕士", "2025"])
    out = BytesIO()
    basic.save(out)
    imported = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成来源09"},
        files={"file": ("synthetic.xlsx", out.getvalue())},
    ).json()
    assert client.post(f"/api/imports/{imported['id']}/confirm", headers=h).status_code == 200
    milestone = client.post(
        "/api/milestones/topic/preview",
        headers=h,
        data={"source_department": "合成来源09"},
        files={
            "file": (
                "synthetic.xlsx",
                sheet(
                    rows=[
                        [f"SYN-CROSS-{i}", f"合成学生{i}", "批次09", "合成选题", "百分制", 85, college, major]
                        for i, major in enumerate(majors, 1)
                    ]
                ),
            )
        },
    ).json()
    assert client.post(f"/api/milestone-imports/{milestone['id']}/confirm", headers=h).status_code == 200
    course_book = Workbook()
    course_sheet = course_book.active
    assert course_sheet is not None
    course_sheet.append(["AQP-PGS", "courses", "1"])
    course_sheet.append(["学号", "姓名", "课程编号", "课程名称", "修读学期", "考核次数", "评分制度", "原始成绩", "业务通过结果", "学分"])
    for i, major in enumerate(majors, 1):
        course_sheet.append([f"SYN-CROSS-{i}", f"合成学生{i}", "CROSS-C09", "跨专业课程", "2025秋", 1, "百分制", 80, "通过", 3])
    course_out = BytesIO()
    course_book.save(course_out)
    course_batch = client.post(
        "/api/imports/courses/preview",
        headers=h,
        data={"source_department": "合成来源09"},
        files={"file": ("synthetic.xlsx", course_out.getvalue())},
    ).json()
    assert client.post(f"/api/imports/courses/{course_batch['id']}/confirm", headers=h).status_code == 200
    replace_grants(
        [
            {"category": "topic", "operation": "view", "college": college, "major": ""},
            {"category": "topic", "operation": "analyze", "college": college, "major": majors[0]},
        ]
    )
    limited = client.post(
        "/api/analyses/topic",
        headers=h,
        json={"college": college, "major": "", "group_by": "major"},
    ).json()
    assert limited["result"]["assessment_count"] == 1
    assert [group["group_value"] for group in limited["result"]["groups"]] == [majors[0]]

    replace_grants(
        [
            {"category": category, "operation": op, "college": college, "major": major}
            for category in ["topic", "courses"]
            for major in majors[:2]
            for op in ["view", "analyze", "pass_rules"]
        ]
    )
    response = client.post(
        "/api/analyses/topic",
        headers=h,
        json={"college": college, "major": "", "group_by": "major"},
    )
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["result"]["assessment_count"] == 2
    assert sorted(g["group_value"] for g in snapshot["result"]["groups"]) == majors[:2]

    for major, threshold in [(majors[0], 80), (majors[1], 90)]:
        assert (
            client.post(
                "/api/pass-rules",
                headers=h,
                json={
                    "college": college,
                    "major": major,
                    "category": "topic",
                    "course_code": "批次09",
                    "grading": "百分制",
                    "threshold": threshold,
                    "confirmed": True,
                    "reason": f"合成确认{major}",
                },
            ).status_code
            == 200
        )
    refreshed = client.post(
        "/api/analyses/topic",
        headers=h,
        json={"college": college, "major": "", "group_by": "major"},
    ).json()
    by_major = {g["group_value"]: g for g in refreshed["result"]["groups"]}
    assert by_major[majors[0]]["passed"] == 1
    assert by_major[majors[1]]["failed"] == 1
    blocked = client.post(
        "/api/analyses/courses",
        headers=h,
        json={"college": college, "major": "", "group_by": "major"},
    ).json()["result"]["credit_progress"]
    assert blocked["value"] is None
    assert "培养要求" in blocked["missing_conditions"]
    for major, required in [(majors[0], 10), (majors[1], 20)]:
        assert (
            client.post(
                "/api/training-requirements",
                headers=h,
                json={
                    "college": college,
                    "major": major,
                    "required_credits": required,
                    "repeat_policy": "max_passed_credits",
                    "confirmed": True,
                    "reason": f"合成培养要求{major}",
                },
            ).status_code
            == 200
        )
    course_result = client.post(
        "/api/analyses/courses",
        headers=h,
        json={"college": college, "major": "", "group_by": "major"},
    ).json()["result"]
    assert course_result["assessment_count"] == 2
    assert course_result["credit_progress"]["value"] == "available"
    assert sorted(
        item["progress_percent"]
        for item in course_result["credit_progress"]["students"]
    ) == [15, 30]
    assert isinstance(course_result["credit_progress"]["requirement_id"], list)

    replace_grants(
        [
            {"category": category, "operation": op, "college": college, "major": majors[0]}
            for category in ["topic", "courses"]
            for op in ["view", "analyze", "pass_rules"]
        ]
    )
    assert client.get(f"/api/analyses/{refreshed['id']}", headers=h).status_code == 403



def test_pass_rules_require_a_specific_major(client):  # noqa: F811
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
                        "category": "topic",
                        "operation": "pass_rules",
                        "college": "跨专业规则学院09",
                        "major": "",
                    }
                ],
            },
        ).status_code
        == 200
    )
    response = client.post(
        "/api/pass-rules",
        headers=h,
        json={
            "college": "跨专业规则学院09",
            "major": "",
            "category": "topic",
            "course_code": "批次09",
            "grading": "百分制",
            "threshold": 80,
            "confirmed": True,
            "reason": "合成确认",
        },
    )
    assert response.status_code == 422

def test_topic_distribution_filters_business_precedence_dates_and_void(client):  # noqa: F811
    from test_milestones import sheet
    from test_students import workbook

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
                    for c in ["basic", "topic", "midterm", "courses"]
                    for op in ["view", "analyze", "maintain", "void", "pass_rules"]
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
    client.post(f"/api/imports/{b['id']}/confirm", headers=h)
    b = client.post(
        "/api/milestones/topic/preview",
        headers=h,
        data={"source_department": "合成09"},
        files={
            "file": (
                "synthetic.xlsx",
                sheet(
                    rows=[
                        [
                            "001",
                            "合成学生",
                            "批次09",
                            "合成选题",
                            "百分制",
                            80,
                            "示例学院",
                            "计算机",
                        ],
                        [
                            "001",
                            "合成学生",
                            "批次10",
                            "合成选题",
                            "五级制",
                            "",
                            "示例学院",
                            "计算机",
                        ],
                    ]
                ),
            )
        },
    ).json()
    client.post(f"/api/milestone-imports/{b['id']}/confirm", headers=h)
    scope = {"college": "示例学院", "major": "计算机", "group_by": "level"}
    r = client.post("/api/analyses/topic", headers=h, json=scope).json()
    assert r["result"]["assessment_count"] == 2
    assert r["result"]["unknown"] == 2
    assert r["result"]["missing_scores"] == 1
    assert [g["mean"] for g in r["result"]["groups"]] == [80, None]
    assert r["result"]["groups"][0]["group_value"] == "硕士"
    assert "学号" not in r["evidence"][0]["payload"]
    assert (
        client.post(
            "/api/analyses/topic", headers=h, json={**scope, "grade": "1900"}
        ).json()["result"]["assessment_count"]
        == 0
    )
    rid = r["evidence"][0]["id"]
    proposal = client.post(
        f"/api/records/topic/{rid}/preview",
        headers=h,
        json={
            "expected_version": 1,
            "data": {
                "业务通过结果": "通过",
                "计划日期": "2025-01-01",
                "实际日期": "2025-01-02",
            },
            "reason": "合成明确日期",
        },
    ).json()
    assert (
        client.post(
            f"/api/records/topic/{rid}/confirm",
            headers=h,
            json={"proposal_id": proposal["proposal_id"], "expected_version": 1},
        ).status_code
        == 200
    )
    assert client.get(f"/api/analyses/{r['id']}").json()["stale"]
    new = client.post("/api/analyses/topic", headers=h, json=scope).json()
    assert new["result"]["passed"] == 1
    assert new["result"]["reminders"][0]["overdue"] is True
    assert new["result"]["reminders"][1]["overdue"] is None
    assert (
        client.post(
            f"/api/records/topic/{rid}/void",
            headers=h,
            json={"expected_version": 2, "reason": "合成作废", "confirmed": True},
        ).status_code
        == 200
    )
    assert client.get(f"/api/analyses/{new['id']}").json()["stale"]


def test_credit_requirement_is_confirmed_versioned_and_never_guessed(client):  # noqa: F811
    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    scope = {"college": "合成09", "major": "合成09"}
    client.put(
        f"/api/users/{u['id']}/grants",
        headers=h,
        json={
            "expected_version": u["version"],
            "request_id": str(uuid4()),
            "grants": [
                {"category": "courses", "operation": op, **scope}
                for op in ["view", "analyze", "pass_rules"]
            ],
        },
    )
    rule = {
        **scope,
        "required_credits": 30,
        "repeat_policy": "max_passed_credits",
        "reason": "合成培养要求",
        "confirmed": False,
    }
    assert (
        client.post("/api/training-requirements", headers=h, json=rule).status_code
        == 422
    )
    before = client.post("/api/analyses/courses", headers=h, json=scope).json()
    assert (
        client.post(
            "/api/training-requirements", headers=h, json={**rule, "confirmed": True}
        ).status_code
        == 200
    )
    assert client.get(f"/api/analyses/{before['id']}").json()["stale"]


def test_credit_progress_counts_each_passed_course_once_and_unknown_blocks(client):  # noqa: F811
    from io import BytesIO

    from openpyxl import Workbook
    from test_students import workbook

    h = login_admin(client)
    u = client.get("/api/me").json()["user"]
    scope = {"college": "示例学院", "major": "计算机"}
    client.put(
        f"/api/users/{u['id']}/grants",
        headers=h,
        json={
            "expected_version": u["version"],
            "request_id": str(uuid4()),
            "grants": [
                {"category": c, "operation": op, **scope}
                for c in ["basic", "courses"]
                for op in ["view", "analyze", "maintain", "pass_rules"]
            ],
        },
    )
    b = client.post(
        "/api/imports/basic/preview",
        headers=h,
        data={"source_department": "合成09"},
        files={"file": ("synthetic.xlsx", workbook())},
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
            "学分",
        ]
    )
    for attempt, credit in [(1, 2), (2, 3)]:
        ws.append(
            [
                "001",
                "合成学生",
                "C09",
                "合成课程",
                "2025秋",
                attempt,
                "百分制",
                80,
                "通过",
                credit,
            ]
        )
    out = BytesIO()
    wb.save(out)
    b = client.post(
        "/api/imports/courses/preview",
        headers=h,
        data={"source_department": "合成09"},
        files={"file": ("synthetic.xlsx", out.getvalue())},
    ).json()
    client.post(f"/api/imports/courses/{b['id']}/confirm", headers=h)
    assert (
        client.post(
            "/api/training-requirements",
            headers=h,
            json={
                **scope,
                "required_credits": 30,
                "repeat_policy": "max_passed_credits",
                "confirmed": True,
                "reason": "合成确认",
            },
        ).status_code
        == 200
    )
    result = client.post("/api/analyses/courses", headers=h, json=scope).json()[
        "result"
    ]["credit_progress"]
    assert result["missing_conditions"] == []
    assert result["students"][0]["earned_credits"] == 3
    assert result["students"][0]["progress_percent"] == 10
    partial = client.post(
        "/api/analyses/courses", headers=h, json={**scope, "course_code": "C09"}
    ).json()["result"]["credit_progress"]
    assert partial["value"] is None
    assert "完整课程范围" in partial["missing_conditions"]
