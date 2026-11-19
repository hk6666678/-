import json
from io import BytesIO

import pytest
from aqp import model_connection
from fastapi.testclient import TestClient
from openpyxl import Workbook
from test_accounts import client, login_admin  # noqa: F401
from test_agent import enable_agent, replace_grants
from test_students import workbook

SCOPE = {"college": "示例学院", "major": "计算机"}


def test_rank_correlation_and_logistic_simulation():
    from aqp.cultivation_models import fit_factors

    points = [
        (float(i), float((i * 7) % 11), float(70 + 2 * i))
        for i in range(1, 15)
    ]
    fitted = fit_factors(points)
    assert fitted["rank_correlations"][0]["rho"] == pytest.approx(1)
    binary = fitted["logistic"]
    assert binary["positive"] == 7 and binary["negative"] == 7
    assert binary["factors"][0]["odds_ratio"] > 1
    assert "notice" in fit_factors(points[:6])["logistic"]


def test_personal_control_limits_exclude_the_current_observation():
    from aqp.cultivation_models import personal_control_limits

    assert personal_control_limits([79, 80, 81, 80, 80, 60])["signal"] == "低于控制下限"
    assert personal_control_limits([79, 80])["signal"] == "历史观测不足"


def grants_for(categories: list[str], operations: list[str]) -> list[dict]:
    return [
        {"category": category, "operation": operation, **SCOPE}
        for category in categories
        for operation in operations
    ]


def plan_runner(monkeypatch: pytest.MonkeyPatch, plan: dict, summary: str, calls: list):
    def runner(config: object, text: str) -> str:
        calls.append(text)
        # 摘要阶段提示词包含 tool_result，据此区分计划/摘要两次调用
        if "tool_result" in text:
            return summary
        return json.dumps(plan, ensure_ascii=False)

    monkeypatch.setattr(model_connection, "default_runner", runner)


def ask(http: TestClient, headers: dict, question: str):
    return http.post("/api/agent/query", headers=headers, json={"question": question})


def test_agent_cultivation_factors_dispatch_and_revocation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch  # noqa: F811
):
    headers = login_admin(client)
    replace_grants(
        client,
        headers,
        grants_for(
            ["basic", "topic", "midterm", "talent_evaluation"], ["view", "analyze"]
        ),
    )
    enable_agent(client, headers, monkeypatch)
    calls: list[str] = []
    plan_runner(
        monkeypatch,
        {
            "tool": "cultivation_factors",
            "college": SCOPE["college"],
            "major": SCOPE["major"],
            "entry_year": 2025,
        },
        "合成摘要：样本不足，无法回归。",
        calls,
    )
    response = ask(client, headers, "示例学院计算机2025级选题中期与评分的关系")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["plan"]["tool"] == "cultivation_factors"
    assert result["plan"]["entry_year"] == 2025
    tool_result = result["tool_result"]
    assert "完整样本不足 5 人" in tool_result["notice"]
    assert tool_result["sample_size"] == 0
    assert tool_result["filters"] == {**SCOPE, "entry_year": 2025}
    assert "统计关联" in tool_result["limitations"]
    events = client.get("/api/audit", params={"action": "cultivation.factors"})
    assert events.status_code == 200
    assert events.json()["items"], "cultivation.factors audit missing"

    replace_grants(
        client,
        headers,
        grants_for(["basic", "midterm", "talent_evaluation"], ["view", "analyze"]),
    )
    revoked = ask(client, headers, "示例学院计算机2025级选题中期与评分的关系")
    assert revoked.status_code == 403
    assert len(calls) == 3, "撤权后不得再调用模型发送摘要"


def test_agent_student_alerts_dispatch_links_and_revocation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch  # noqa: F811
):
    headers = login_admin(client)
    replace_grants(
        client, headers, grants_for(["basic"], ["maintain", "view", "analyze"])
    )
    from openpyxl import load_workbook

    sample = load_workbook(BytesIO(workbook())).active
    for offset, (label, value) in enumerate(
        {"盲审送审批次": "模拟批次", "盲审论文应交日期": "2025-01-01", "盲审论文提交状态": "未提交"}.items(),
        sample.max_column + 1,
    ):
        sample.cell(2, offset, label)
        sample.cell(3, offset, value)
    stream = BytesIO()
    sample.parent.save(stream)
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "Agent synthetic source"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    ).json()
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    replace_grants(
        client,
        headers,
        grants_for(["basic"], ["view", "analyze", "identity"])
        + grants_for(["papers"], ["view", "analyze"])
        + grants_for(
            ["research_papers", "patents", "awards", "conferences"],
            ["view", "analyze"],
        ),
    )
    enable_agent(client, headers, monkeypatch)
    calls: list[str] = []
    plan_runner(
        monkeypatch,
        {"tool": "student_alerts", "student_id": 1},
        "合成摘要：该生无学籍异动，同届可比人数不足。",
        calls,
    )
    response = ask(client, headers, "001号学生的预警信号")
    assert response.status_code == 200, response.text
    result = response.json()
    tool_result = result["tool_result"]
    assert tool_result["mobility"] is None
    assert tool_result["blind_review"]["status"] == "未提交且已逾期"
    assert "不足 3 人" in tool_result["notice"]
    assert tool_result["filters"] == {"student_id": 1}
    assert "course_control_chart" in tool_result["limitations"]
    assert result["evidence_links"] == [
        {"label": "学生档案", "url": "/api/students/1"}
    ]
    events = client.get("/api/audit", params={"action": "cultivation.signals"})
    assert events.status_code == 200
    assert events.json()["items"], "cultivation.signals audit missing"

    replace_grants(client, headers, grants_for(["courses"], ["view", "analyze"]))
    revoked = ask(client, headers, "001号学生的预警信号")
    assert revoked.status_code == 403
    assert len(calls) == 2

    calls.clear()
    plan_runner(monkeypatch, {"tool": "mentor_course_comparison", "student_id": 1}, "课程对比摘要", calls)
    denied = ask(client, headers, "查看记录编号 1 的同导师组课程对比")
    assert denied.status_code == 403
    replace_grants(client, headers, grants_for(["basic", "courses"], ["view", "analyze"]))
    comparison = ask(client, headers, "查看记录编号 1 的同导师组课程对比")
    assert comparison.status_code == 200, comparison.text
    comparison_result = comparison.json()
    assert comparison_result["tool_result"]["has_group"] is False
    assert comparison_result["tool_result"]["items"] == []
    link = comparison_result["evidence_links"][0]["url"]
    assert client.get(link).status_code == 200

    calls.clear()
    replace_grants(client, headers, grants_for(["courses"], ["view", "analyze"]))
    plan_runner(monkeypatch, {"tool": "student_report", "student_id": 1}, "报告摘要", calls)
    blocked = ask(client, headers, "查看学生发展报告，学生记录编号 1")
    assert blocked.status_code == 403
    replace_grants(client, headers, grants_for(["basic"], ["view"]))
    report = ask(client, headers, "查看学生发展报告，学生记录编号 1")
    assert report.status_code == 200, report.text
    assert report.json()["evidence_links"][0]["url"] == "/api/reports/students/1"
    assert "student_number" not in report.json()["tool_result"]

    calls.clear()
    plan_runner(monkeypatch, {"tool": "college_report", "college": "示例学院", "major": "计算机"}, "报告摘要", calls)
    college = ask(client, headers, "查看示例学院计算机的学院学科报告")
    assert college.status_code == 200, college.text
    assert college.json()["tool_result"]["sections"]["students"]["count"] == 1
    link = college.json()["evidence_links"][0]["url"]
    assert client.get(link).status_code == 200


def test_agent_rejects_incomplete_cultivation_plans(
    client: TestClient, monkeypatch: pytest.MonkeyPatch  # noqa: F811
):
    headers = login_admin(client)
    enable_agent(client, headers, monkeypatch)
    for plan in (
        {"tool": "cultivation_factors", "college": "示例学院", "major": "计算机"},
        {"tool": "mentor_effectiveness", "mentor_id": 1},
        {"tool": "course_control_chart"},
        {"tool": "milestone_alerts"},
    ):
        monkeypatch.setattr(
            model_connection,
            "default_runner",
            lambda config, text, plan=plan: json.dumps(plan, ensure_ascii=False),
        )
        response = ask(client, headers, "查询培养情况")
        assert response.status_code == 502, plan
        assert response.json()["detail"] == "Agent 计划无效或不可执行"


def courses_workbook(rows: list[tuple[str, str | float]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["AQP-PGS", "courses", "1"])
    sheet.append(
        [
            "学号",
            "姓名",
            "所属学院",
            "专业",
            "培养层次",
            "入学年份",
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
    for number, score in rows:
        sheet.append(
            [
                number,
                f"学生{number}",
                SCOPE["college"],
                SCOPE["major"],
                "硕士",
                "2025",
                "SYM-C1",
                "合成控制课程",
                "2025秋",
                1,
                "百分制",
                score,
                "",
                3,
            ]
        )
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def test_agent_course_control_chart_flags_outlier(
    client: TestClient, monkeypatch: pytest.MonkeyPatch  # noqa: F811
):
    headers = login_admin(client)
    replace_grants(
        client,
        headers,
        grants_for(["basic", "courses"], ["maintain", "view", "analyze"]),
    )
    basic_book = Workbook()
    sheet = basic_book.active
    assert sheet is not None
    sheet.append(["AQP-PGS", "basic", "1"])
    sheet.append(["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"])
    for index in range(1, 12):
        sheet.append([f"S{index}", f"学生S{index}", SCOPE["college"], SCOPE["major"], "硕士", "2025"])
    basic_stream = BytesIO()
    basic_book.save(basic_stream)
    basic_batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "Agent synthetic source"},
        files={"file": ("basic.xlsx", basic_stream.getvalue())},
    ).json()
    assert (
        client.post(
            f"/api/imports/{basic_batch['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    students = [(f"S{index}", 80.0) for index in range(1, 11)] + [("S11", 10.0)]
    batch = client.post(
        "/api/imports/courses/preview",
        headers=headers,
        data={"source_department": "Agent synthetic source"},
        files={"file": ("synthetic.xlsx", courses_workbook(students))},
    ).json()
    assert (
        client.post(
            f"/api/imports/courses/{batch['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    enable_agent(client, headers, monkeypatch)
    calls: list[str] = []
    plan_runner(
        monkeypatch,
        {"tool": "course_control_chart", **SCOPE},
        "合成摘要：SYM-C1 有一名学生低于控制下限。",
        calls,
    )
    response = ask(client, headers, "示例学院计算机的课程均分控制图")
    assert response.status_code == 200, response.text
    tool_result = response.json()["tool_result"]
    assert tool_result["courses_evaluated"] == 1
    assert tool_result["insufficient_baseline"] == 0
    assert len(tool_result["items"]) == 1
    chart = tool_result["items"][0]
    assert chart["course_code"] == "SYM-C1"
    assert chart["students"] == 11
    assert chart["above"] == []
    assert len(chart["below"]) == 1
    assert tool_result["filters"] == SCOPE
    assert "统计信号" in tool_result["limitations"]
    events = client.get("/api/audit", params={"action": "cultivation.control_chart"})
    assert events.json()["items"], "control chart audit missing"

    replace_grants(client, headers, grants_for(["basic"], ["view", "analyze"]))
    revoked = ask(client, headers, "示例学院计算机的课程均分控制图")
    assert revoked.status_code == 403
    assert len(calls) == 3


def test_agent_milestone_alerts_report_explicit_overdue(
    client: TestClient, monkeypatch: pytest.MonkeyPatch  # noqa: F811
):
    headers = login_admin(client)
    replace_grants(
        client,
        headers,
        grants_for(["basic", "topic", "midterm"], ["maintain", "view", "analyze"]),
    )
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "Agent synthetic source"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    records = Workbook()
    sheet = records.active
    assert sheet is not None
    sheet.append(["AQP-PGS", "topic", "1"])
    sheet.append(
        [
            "学号",
            "姓名",
            "考核批次",
            "评分制度",
            "原始成绩",
            "计划日期",
            "实际日期",
            "完成状态",
            "业务通过结果",
            "所属学院",
            "专业",
            "选题标题",
        ]
    )
    for index, score in enumerate((94, 95, 96, 95, 95), 1):
        sheet.append([
            "001", "合成学生", f"阶段-{index}", "百分制", score, "",
            f"2025-02-{index:02d}", "", "", SCOPE["college"], SCOPE["major"], "合成选题",
        ])
    sheet.append(
        [
            "001",
            "合成学生",
            "2025春选题",
            "百分制",
            80,
            "2025-01-10",
            "2025-03-01",
            "",
            "",
            SCOPE["college"],
            SCOPE["major"],
            "合成选题",
        ]
    )
    stream = BytesIO()
    records.save(stream)
    preview = client.post(
        "/api/milestones/topic/preview",
        headers=headers,
        data={"source_department": "Agent synthetic source"},
        files={"file": ("topic.xlsx", stream.getvalue())},
    ).json()
    assert (
        client.post(
            f"/api/milestone-imports/{preview['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    signals = client.get("/api/cultivation/students/1/signals").json()
    topic, midterm = signals["milestone_trends"]
    assert topic["signal"] == "低于控制下限" and len(topic["observations"]) == 6
    assert midterm["signal"] == "历史观测不足"
    enable_agent(client, headers, monkeypatch)
    calls: list[str] = []
    plan_runner(
        monkeypatch,
        {"tool": "milestone_alerts", **SCOPE},
        "合成摘要：一名学生选题明确超期。",
        calls,
    )
    response = ask(client, headers, "示例学院计算机的选题中期超期情况")
    assert response.status_code == 200, response.text
    result = response.json()
    tool_result = result["tool_result"]
    assert tool_result["summary"]["topic"]["explicit_overdue"] == 1
    assert tool_result["summary"]["topic"]["records"] == 1
    alert = tool_result["alerts"][0]
    assert alert["kind"] == "明确超期"
    assert alert["plan"] == "2025-01-10" and alert["actual"] == "2025-03-01"
    assert "student_id" not in alert, "内部编号不得透给模型"
    assert result["evidence_links"] == [
        {"label": f"培养记录 {alert['research_id']}", "url": "/api/milestones?student_id=1"}
    ]
    events = client.get("/api/audit", params={"action": "cultivation.milestone_alerts"})
    assert events.json()["items"], "milestone alerts audit missing"

    replace_grants(client, headers, grants_for(["basic", "midterm"], ["view", "analyze"]))
    revoked = ask(client, headers, "示例学院计算机的选题中期超期情况")
    assert revoked.status_code == 403
    assert len(calls) == 3


def test_agent_mentor_effectiveness_dispatch_and_revocation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch  # noqa: F811
):
    headers = login_admin(client)
    replace_grants(
        client,
        headers,
        grants_for(["basic", "mentor_groups"], ["maintain", "view", "analyze"]),
    )
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "Agent synthetic source"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    mentor = client.post(
        "/api/mentor-groups/directory/mentors",
        headers=headers,
        json={"number": "T-1", "name": "合成导师", **SCOPE},
    ).json()
    group = client.post(
        "/api/mentor-groups/directory/groups",
        headers=headers,
        json={"number": "G-1", "name": "合成课题组", **SCOPE},
    ).json()
    assert (
        client.post(
            "/api/mentor-groups/relations",
            headers=headers,
            json={
                "student_id": 1,
                "mentor_id": mentor["id"],
                "group_id": group["id"],
                "start_date": "2024-09-01",
                "source_department": "Agent synthetic source",
                "reason": "合成关系",
            },
        ).status_code
        == 200
    )
    enable_agent(client, headers, monkeypatch)
    calls: list[str] = []
    plan_runner(
        monkeypatch,
        {"tool": "mentor_effectiveness", "mentor_id": mentor["id"], "as_of": "2026-11-18"},
        "合成摘要：该导师当前有1名在读学生，暂无评分。",
        calls,
    )
    response = ask(client, headers, "合成导师的效能情况")
    assert response.status_code == 200, response.text
    tool_result = response.json()["tool_result"]
    assert tool_result["students"] == 1
    assert tool_result["scored"] == 0
    assert tool_result["filters"] == {"as_of": "2026-11-18", "mentor_id": mentor["id"]}
    assert "模拟评价" in tool_result["limitations"]

    replace_grants(client, headers, grants_for(["basic"], ["view", "analyze"]))
    revoked = ask(client, headers, "合成导师的效能情况")
    assert revoked.status_code in (200, 403)
    assert len(calls) >= 3
    if revoked.status_code == 200:
        assert (
            revoked.json()["tool_result"].get("notice")
            == "该导师或课题组在当前授权范围内无有效关系数据。"
        )
