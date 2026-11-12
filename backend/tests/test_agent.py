import json
from uuid import uuid4

import pytest
from aqp import model_connection
from fastapi.testclient import TestClient
from test_accounts import client, login_admin  # noqa: F401
from test_students import workbook


def replace_grants(client: TestClient, headers: dict[str, str], rows: list[dict]) -> None:  # noqa: F811
    user = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": rows,
        },
    )
    assert response.status_code == 200


def enable_agent(
    client: TestClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    monkeypatch.setenv("AQP_MODEL_KEY_AGENT_TEST", "Synthetic-secret")
    current = client.get("/api/model/config").json()
    config = {
        **current,
        "expected_version": current["version"],
        "enabled": True,
        "approved": True,
        "approval_reference": "Synthetic approval",
        "endpoint": "http://127.0.0.1:9999/v1",
        "model": "synthetic-agent",
        "allowed_purposes": ["agent"],
        "key_env": "AQP_MODEL_KEY_AGENT_TEST",
    }
    assert client.put("/api/model/config", headers=headers, json=config).status_code == 200


def synthetic_student_and_analysis(
    client: TestClient, headers: dict[str, str]  # noqa: F811
) -> tuple[int, int]:
    replace_grants(
        client,
        headers,
        [
            {
                "category": category,
                "operation": operation,
                "college": "示例学院",
                "major": "计算机",
            }
            for category in ["basic", "courses"]
            for operation in ["view", "analyze", "maintain"]
        ],
    )
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "Agent synthetic source"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    assert client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code == 200
    analysis = client.post(
        "/api/analyses/courses",
        headers=headers,
        json={"college": "示例学院", "major": "计算机"},
    )
    assert analysis.status_code == 200
    return batch["id"], analysis.json()["id"]


def test_agent_disabled_until_approved_and_configured(client: TestClient):  # noqa: F811
    headers = login_admin(client)
    response = client.post(
        "/api/agent/query", headers=headers, json={"question": "统计合成学生人数"}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Agent 未启用"


def test_agent_counts_students_from_controlled_tool(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch
):
    headers = login_admin(client)
    synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    outputs = [
        json.dumps(
            {"tool": "student_counts", "college": "示例学院", "major": "计算机"},
            ensure_ascii=False,
        ),
        "合成模型摘要：当前范围共有1名学生。",
    ]
    prompts: list[str] = []

    def fake_runner(config: object, text: str) -> str:
        prompts.append(text)
        return outputs.pop(0)

    monkeypatch.setattr(model_connection, "default_runner", fake_runner)
    response = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "统计示例学院计算机专业学生人数"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["answer"].startswith("合成模型摘要：当前范围共有1名学生。")
    assert "系统依据" in result["answer"]
    assert result["plan"]["tool"] == "student_counts"
    assert result["tool_result"]["total"] == 1
    assert result["tool_result"]["filters"] == {
        "college": "示例学院",
        "major": "计算机",
        "grade": "",
        "level": "",
    }
    assert result["evidence_links"] == []
    assert result["model_version"] >= 1
    assert '"total": 1' in prompts[1]


def test_agent_explains_snapshot_with_version_and_drilldown(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch
):
    headers = login_admin(client)
    _, analysis_id = synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    outputs = [
        json.dumps({"tool": "analysis_explanation", "analysis_id": analysis_id}),
        "合成模型说明：该分析版本当前无有效考核记录。",
    ]
    monkeypatch.setattr(
        model_connection,
        "default_runner",
        lambda config, text: outputs.pop(0),
    )
    result = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": f"解释分析版本{analysis_id}的口径"},
    ).json()
    assert result["plan"]["tool"] == "analysis_explanation"
    assert result["tool_result"]["id"] == analysis_id
    assert result["tool_result"]["result"]["assessment_count"] == 0
    assert result["evidence_links"] == [
        {"label": "分析证据下钻", "url": f"/api/analyses/{analysis_id}/evidence"}
    ]
    assert result["tool_result"]["created_at"] > 0


def test_agent_refuses_write_and_invalid_model_plan(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch
):
    headers = login_admin(client)
    enable_agent(client, headers, monkeypatch)
    outputs = [
        json.dumps(
            {"tool": "refuse", "reason": "成绩修改须进入授权维护页面"},
            ensure_ascii=False,
        )
    ]
    monkeypatch.setattr(
        model_connection,
        "default_runner",
        lambda config, text: outputs.pop(0),
    )
    refused = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "把001的合成课程成绩改成90"},
    )
    assert refused.status_code == 200
    assert refused.json()["answer"] == "成绩修改须进入授权维护页面"
    assert refused.json()["tool_result"] is None

    monkeypatch.setattr(model_connection, "default_runner", lambda config, text: "not-json")
    invalid = client.post(
        "/api/agent/query", headers=headers, json={"question": "统计人数"}
    )
    assert invalid.status_code == 502
    assert invalid.json()["detail"] == "Agent 计划无效或不可执行"

    injected = json.dumps(
        {
            "tool": "student_counts",
            "college": "示例学院",
            "sql": "DROP TABLE students",
        }
    )
    monkeypatch.setattr(
        model_connection, "default_runner", lambda config, text: injected
    )
    response = client.post(
        "/api/agent/query", headers=headers, json={"question": "统计人数"}
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "Agent 计划无效或不可执行"


def test_agent_rerevokes_snapshot_access(client: TestClient, monkeypatch: pytest.MonkeyPatch):  # noqa: F811
    headers = login_admin(client)
    _, analysis_id = synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    replace_grants(client, headers, [])
    outputs = [json.dumps({"tool": "analysis_explanation", "analysis_id": analysis_id})]
    monkeypatch.setattr(
        model_connection,
        "default_runner",
        lambda config, text: outputs.pop(0),
    )
    response = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": f"读取分析{analysis_id}"},
    )
    assert response.status_code == 403


def test_agent_student_profile_is_masked_without_identity(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch
):
    headers = login_admin(client)
    synthetic_student_and_analysis(client, headers)
    students = client.get("/api/students", headers=headers).json()["items"]
    student = students[0]
    from io import BytesIO

    from openpyxl import Workbook

    course = Workbook()
    sheet = course.active
    assert sheet is not None
    sheet.append(["AQP-PGS", "courses", "1"])
    sheet.append(["学号", "姓名", "课程编号", "课程名称", "修读学期", "考核次数", "评分制度", "原始成绩", "业务通过结果", "学分"])
    sheet.append(["001", "合成学生", "AGENT-C17", "合成课程", "2025秋", 1, "百分制", 80, "通过", 2])
    output = BytesIO()
    course.save(output)
    course_batch = client.post(
        "/api/imports/courses/preview",
        headers=headers,
        data={
            "source_department": "Agent synthetic source",
            "college": "示例学院",
            "major": "计算机",
        },
        files={"file": ("synthetic.xlsx", output.getvalue())},
    ).json()
    assert (
        client.post(
            f"/api/imports/courses/{course_batch['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    enable_agent(client, headers, monkeypatch)
    outputs = [
        json.dumps({"tool": "student_profile", "student_id": student["id"]}),
        "合成模型摘要：已读取该学生的脱敏档案和课程记录。",
    ]
    prompts: list[str] = []

    def runner(config: object, text: str) -> str:
        prompts.append(text)
        return outputs.pop(0)

    monkeypatch.setattr(model_connection, "default_runner", runner)
    result = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": f"查询内部学生{student['id']}的档案和课程"},
    ).json()
    assert result["plan"]["tool"] == "student_profile"
    assert "学号" not in result["tool_result"]["data"]
    assert "姓名" not in result["tool_result"]["data"]
    assert result["tool_result"]["courses"]
    assert "学号" not in prompts[1].split('"courses"')[1].split('"milestones"')[0]


def test_agent_does_not_send_unauthorized_identity_to_planner(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
):
    headers = login_admin(client)
    synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    replace_grants(client, headers, [])

    def unexpected(config: object, text: str) -> str:
        raise AssertionError("unauthorized question must not reach model")

    monkeypatch.setattr(model_connection, "default_runner", unexpected)
    response = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "查询001合成学生的档案"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "问题包含当前无身份权限的学生标识"

def test_agent_training_summary_and_clarification(
    client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch
):
    headers = login_admin(client)
    _, analysis_id = synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    outputs = [
        json.dumps(
            {
                "tool": "training_statistics",
                "category": "courses",
                "college": "示例学院",
                "major": "计算机",
            }
        ),
        "合成模型摘要：已有课程分析版本当前没有有效考核记录。",
        json.dumps({"tool": "summarize_analysis", "analysis_id": analysis_id}),
        "合成模型摘要：按既有分析结果生成摘要。",
        json.dumps({"tool": "clarify", "clarification": "请说明统计对象和年份。"}),
    ]
    monkeypatch.setattr(
        model_connection, "default_runner", lambda config, text: outputs.pop(0)
    )
    training = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "查看示例学院计算机课程统计"},
    ).json()
    assert training["plan"]["tool"] == "training_statistics"
    assert training["tool_result"]["id"] == analysis_id
    assert training["tool_result"]["result"]["assessment_count"] == 0

    summary = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": f"总结分析版本{analysis_id}"},
    ).json()
    assert summary["plan"]["tool"] == "summarize_analysis"
    assert summary["tool_result"]["id"] == analysis_id
    assert summary["evidence_links"][0]["url"] == f"/api/analyses/{analysis_id}/evidence"

    clarify = client.post(
        "/api/agent/query", headers=headers, json={"question": "统计学生数量"}
    ).json()
    assert clarify["answer"] == "请说明统计对象和年份。"
    assert clarify["tool_result"] is None
