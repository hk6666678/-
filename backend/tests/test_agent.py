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


@pytest.mark.parametrize("remaining_major, expected_status", [(None, 403), ("数学", 409)])
def test_agent_does_not_send_summary_after_tool_scope_changes(
    client: TestClient,  # noqa: F811
    monkeypatch,
    remaining_major,
    expected_status,
):
    from aqp import agent

    headers = login_admin(client)
    synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    original = agent.execute_plan
    reads = []
    model_calls = []

    def revoke_after_read(*args):
        result = original(*args)
        if not reads:
            assert result[0]["total"] == 1
            reads.append(result)
            replace_grants(
                client,
                headers,
                [
                    {
                        "category": "basic",
                        "operation": "view",
                        "college": "示例学院",
                        "major": remaining_major,
                    }
                ]
                if remaining_major
                else [],
            )
        return result

    def runner(config, text):
        model_calls.append(text)
        if len(model_calls) == 1:
            plan = {"tool": "student_counts", "college": "示例学院"}
            if remaining_major is None:
                plan["major"] = "计算机"
            return json.dumps(plan)
        return "模拟摘要"

    monkeypatch.setattr(agent, "execute_plan", revoke_after_read)
    monkeypatch.setattr(model_connection, "default_runner", runner)
    response = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "统计示例学院授权范围内的学生人数"},
    )
    assert response.status_code == expected_status
    assert len(reads) == 1
    assert len(model_calls) == 1
    if expected_status == 409:
        events = client.get("/api/audit", params={"action": "agent.answer"})
        assert events.status_code == 200
        assert [row["outcome"] for row in events.json()["items"]] == ["changed"]


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


def seed_agent_student(db, ident: int, number: str) -> None:
    db.execute(
        "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload)"
        " VALUES(?,?,?,?,'synthetic','synthetic','master',2025,?)",
        (
            ident,
            f"R{ident}",
            number,
            f"Synthetic{ident}",
            json.dumps({"所属学院": "synthetic", "专业": "synthetic"}),
        ),
    )


def seed_agent_output(db, key: str, number: str) -> None:
    db.execute(
        "INSERT INTO patents_outputs(business_key,payload) VALUES(?,?)",
        (
            key,
            json.dumps(
                {
                    "title": f"Patent {key}",
                    "participants": [
                        {
                            "student_number": number,
                            "name": f"Synthetic{number[1:]}",
                            "college": "synthetic",
                            "major": "synthetic",
                        }
                    ],
                }
            ),
        ),
    )


def agent_grants(test_client, headers, categories, operations) -> None:
    replace_grants(
        test_client,
        headers,
        [
            {
                "category": category,
                "operation": operation,
                "college": "synthetic",
                "major": "synthetic",
            }
            for category in categories
            for operation in operations
        ],
    )


def test_agent_output_statistics_and_missing_grants(
    client: TestClient,  # noqa: F811
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from aqp.store import connection

    headers = login_admin(client)
    dbpath = tmp_path / "accounts.sqlite3"
    with connection(dbpath) as db:
        seed_agent_student(db, 1, "S1")
        seed_agent_output(db, "AP1", "S1")
        db.commit()
    agent_grants(client, headers, ["basic", "patents"], ["view", "analyze"])
    enable_agent(client, headers, monkeypatch)
    outputs = [
        json.dumps({"tool": "output_statistics", "college": "synthetic"}, ensure_ascii=False),
        "合成摘要：专利去重1项。",
    ]
    monkeypatch.setattr(
        model_connection, "default_runner", lambda config, text: outputs.pop(0)
    )
    result = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "统计synthetic学院成果"},
    ).json()
    assert result["tool_result"]["student_total"] == 1
    assert result["tool_result"]["categories"]["patents"]["distinct_outputs"] == 1
    assert result["tool_result"]["categories"]["patents"]["authorized_students"] == 1
    assert (
        result["tool_result"]["categories"]["awards"]["authorized_students"] == 0
    )
    assert "无该类别可统计学生" in result["tool_result"]["categories"]["awards"]["notice"]
    agent_grants(client, headers, ["patents"], ["view", "analyze"])
    outputs.append(json.dumps({"tool": "output_statistics", "college": "synthetic"}, ensure_ascii=False))
    outputs.append("again")
    denied = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "统计synthetic学院成果"},
    )
    assert denied.status_code == 403


def test_agent_mentor_group_facts_and_evaluation_snapshot(
    client: TestClient,  # noqa: F811
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    import time as time_module

    from aqp.store import connection

    headers = login_admin(client)
    dbpath = tmp_path / "accounts.sqlite3"
    today = time_module.strftime("%Y-%m-%d")
    with connection(dbpath) as db:
        seed_agent_student(db, 1, "S1")
        db.execute(
            "INSERT INTO mentor_directory(id,mentor_number,name,college,major) VALUES(1,'AM1','Agent Mentor','synthetic','synthetic')"
        )
        db.execute(
            "INSERT INTO research_groups(id,group_number,name,college,major) VALUES(1,'AG1','Agent Group','synthetic','synthetic')"
        )
        db.execute(
            "INSERT INTO mentor_group_relations(id,student_id,mentor_id,group_id,start_date,source_department) "
            "VALUES(1,1,1,1,'2020-01-01','synthetic')"
        )
        db.execute(
            "INSERT INTO evaluation_rules(id,family_id,version,config,enabled,created_by,created_at) "
            "VALUES(1,1,1,?,1,1,0)",
            (
                json.dumps(
                    {
                        "name": "agent",
                        "college": "synthetic",
                        "major": "synthetic",
                        "mode": "simulation",
                        "metrics": [
                            {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 4}
                        ],
                    }
                ),
            ),
        )
        db.execute(
            "INSERT INTO evaluation_snapshots(id,student_id,rule_id,result,data_digest,created_by,created_at) "
            "VALUES(1,1,1,?,?,1,0)",
            (
                json.dumps(
                    {
                        "mode": "simulation",
                        "student_id": 1,
                        "rule_id": 1,
                        "rule_version": 1,
                        "as_of": 0,
                        "inputs": [],
                        "total": 25,
                    }
                ),
                "digest",
            ),
        )
        seed_agent_output(db, "P1", "S1")
        db.commit()
    agent_grants(
        client,
        headers,
        ["basic", "patents", "mentor_groups", "talent_evaluation"],
        ["view", "identity", "analyze"],
    )
    scored = client.post("/api/evaluation-snapshots", headers=headers,
                         json={"student_id": 1, "rule_id": 1})
    assert scored.status_code == 200, scored.text
    enable_agent(client, headers, monkeypatch)
    outputs = [
        json.dumps({"tool": "mentor_group_facts", "as_of": today, "mentor_id": 1}),
        "合成摘要：当前1名学生。",
        json.dumps({"tool": "evaluation_snapshot", "research_id": "R1"}),
        "合成摘要：最新模拟总分25，仅模拟。",
    ]
    monkeypatch.setattr(
        model_connection, "default_runner", lambda config, text: outputs.pop(0)
    )
    facts = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": f"查看{today}的导师组事实"},
    ).json()
    assert facts["tool_result"]["student_count"] == 1
    snapshot = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "R1最新评分"},
    ).json()
    assert snapshot["tool_result"]["snapshot"]["total"] == 25
    assert "模拟" in snapshot["tool_result"]["notice"]
    assert snapshot["tool_result"]["snapshot"]["stale"] is False
    with connection(dbpath) as db:
        db.execute("UPDATE patents_outputs SET active=0")
        db.commit()
    outputs.extend([json.dumps({"tool": "evaluation_snapshot", "research_id": "R1"}), "old"])
    stale = client.post("/api/agent/query", headers=headers,
                        json={"question": "R1 evaluation"})
    assert stale.status_code == 200
    assert stale.json()["tool_result"]["snapshot"]["stale"] is True
    assert "\u8fc7\u671f" in stale.json()["tool_result"]["notice"]
    assert "\u6a21\u62df\u6f14\u793a" in stale.json()["tool_result"]["notice"]
    agent_grants(client, headers, ["basic", "talent_evaluation"],
                 ["view", "identity", "analyze"])
    outputs.extend([json.dumps({"tool": "evaluation_snapshot", "research_id": "R1"})])
    denied = client.post("/api/agent/query", headers=headers,
                         json={"question": "R1 evaluation"})
    assert denied.status_code == 403



def test_agent_correlation_computed_by_tool_with_limits(
    client: TestClient,  # noqa: F811
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from aqp.store import connection

    headers = login_admin(client)
    dbpath = tmp_path / "accounts.sqlite3"
    with connection(dbpath) as db:
        db.execute(
            "INSERT INTO import_batches(id,category,template_version,source_department,filename,file_hash,original_file,uploaded_by,created_at) VALUES(1,'courses','1','synthetic','synthetic','synthetic',X'00',?,1)",
            (1,),
        )
        # Three students: course pass ratio 1.0/0.5/0.0 with 1/2/3 patents is
        # a perfect negative relation: r=-1, y = 3 - 2x, R2 = 1.
        for ident, number, ratio, patents in [
            (1, "S1", "通过", 1),
            (2, "S2", "mixed", 2),
            (3, "S3", "不通过", 3),
        ]:
            seed_agent_student(db, ident, number)
            for index in range(patents):
                seed_agent_output(db, f"AC{ident}-{index}", number)
            if ratio == "mixed":
                statuses = ["通过", "不通过"]
            else:
                statuses = [ratio] * 2
            for index, status in enumerate(statuses):
                payload = {
                    "学院": "synthetic",
                    "专业": "synthetic",
                    "评分制度": "百分制",
                    "业务通过结果": status,
                }
                db.execute(
                    "INSERT INTO import_rows(id,batch_id,sheet,row_number,raw_json,normalized_json,state) "
                    "VALUES(?,1,'sheet',?,'{}','{}','linked')",
                    (ident * 10 + index, ident * 10 + index),
                )
                db.execute(
                    "INSERT INTO course_records(student_number,course_code,term,attempt,student_id,payload,state,source_row_id) "
                    "VALUES(?,?,?,?,?,?, 'linked', ?)",
                    (number, f"C{ident}-{index}", "2025", 1, ident, json.dumps(payload), ident * 10 + index),
                )
        db.commit()
    with connection(dbpath) as db:
        db.execute(
            "INSERT INTO evaluation_rules(id,family_id,version,config,enabled,created_by,created_at) "
            "VALUES(1,1,1,?,1,1,0)",
            (
                json.dumps(
                    {
                        "name": "correlation",
                        "college": "synthetic",
                        "major": "synthetic",
                        "mode": "simulation",
                        "metrics": [
                            {"feature": "patent_count", "weight": 1, "minimum": 0, "maximum": 4}
                        ],
                    }
                ),
            ),
        )
        db.execute(
            "INSERT INTO evaluation_snapshots(student_id,rule_id,result,data_digest,created_by,created_at) "
            "VALUES(1,1,?,?,1,0)",
            (
                json.dumps(
                    {
                        "mode": "simulation",
                        "student_id": 1,
                        "rule_id": 1,
                        "rule_version": 1,
                        "as_of": 0,
                        "inputs": [],
                        "total": 25,
                    }
                ),
                "digest",
            ),
        )
        db.commit()
    agent_grants(
        client,
        headers,
        [
            "basic",
            "courses",
            "patents",
            "awards",
            "conferences",
            "research_papers",
            "talent_evaluation",
        ],
        ["view", "identity", "analyze"],
    )
    scored = client.post("/api/evaluation-snapshots", headers=headers,
                         json={"student_id": 1, "rule_id": 1})
    assert scored.status_code == 200, scored.text
    enable_agent(client, headers, monkeypatch)
    outputs = [
        json.dumps(
            {
                "tool": "correlation_analysis",
                "college": "synthetic",
                "x_variable": "course_pass_ratio",
                "y_variable": "output_count",
            }
        ),
        "合成摘要：r=-1，样本3，不表示因果。",
        json.dumps(
            {
                "tool": "correlation_analysis",
                "college": "synthetic",
                "x_variable": "course_pass_ratio",
                "y_variable": "output_count",
            }
        ),
        "again",
    ]
    monkeypatch.setattr(
        model_connection, "default_runner", lambda config, text: outputs.pop(0)
    )
    result = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "分析课程通过比例与专利数的关系"},
    ).json()
    assert "tool_result" in result, result
    tool = result["tool_result"]
    assert tool["sample_size"] == 3
    assert tool["excluded_missing"] == 0
    assert abs(tool["pearson_r"] - (-1.0)) < 1e-9
    assert abs(tool["regression"]["slope"] - (-2.0)) < 1e-9
    assert abs(tool["regression"]["intercept"] - 3.0) < 1e-9
    assert abs(tool["regression"]["r_squared"] - 1.0) < 1e-9
    assert "不表示因果" in tool["limitations"]
    assert tool["per_student"][0]["research_id"] == "R1"
    assert "四类成果个人参与人次合计" in tool["variable_definitions"]["y"]
    # Without a major the evidence link is omitted: the college report would
    # otherwise describe a different population (or refuse access).
    assert result["evidence_links"] == []
    # With only two complete samples the tool refuses to compute numbers.
    with connection(dbpath) as db:
        db.execute("UPDATE students SET active=0 WHERE id=3")
        db.execute("UPDATE patents_outputs SET active=0 WHERE business_key LIKE 'AC3-%'")
        db.commit()
    small = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "再分析一次课程通过比例与专利数的关系"},
    ).json()
    assert small["tool_result"]["sample_size"] == 2
    assert small["tool_result"]["regression"] is None
    assert "不足3个" in small["tool_result"]["notice"]
    # With an explicit major the referenced college report is reachable.
    outputs.append(
        json.dumps(
            {
                "tool": "correlation_analysis",
                "college": "synthetic",
                "major": "synthetic",
                "x_variable": "course_pass_ratio",
                "y_variable": "output_count",
            }
        )
    )
    outputs.append("again")
    linked = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "按专业分析课程通过比例与专利数的关系"},
    ).json()
    url = linked["evidence_links"][0]["url"]
    assert url == "/api/reports/colleges?college=synthetic&major=synthetic"
    assert client.get(url, headers=headers).status_code == 200
    # score_total only exists for the snapshotted student, so the variable
    # path runs but refuses to compute on a single complete sample.
    outputs.append(
        json.dumps(
            {
                "tool": "correlation_analysis",
                "college": "synthetic",
                "x_variable": "output_count",
                "y_variable": "score_total",
            }
        )
    )
    outputs.append("again")
    scores = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "分析专利数与评分总分的关系"},
    ).json()
    assert scores["tool_result"]["sample_size"] == 1
    assert scores["tool_result"]["excluded_missing"] == 1
    assert scores["tool_result"]["regression"] is None
    with connection(dbpath) as db:
        db.execute("UPDATE patents_outputs SET active=0")
        db.commit()
    outputs.extend([json.dumps({"tool": "correlation_analysis", "college": "synthetic",
                                "x_variable": "output_count", "y_variable": "score_total"}), "excluded"])
    stale_scores = client.post("/api/agent/query", headers=headers,
                               json={"question": "analyze scores"})
    assert stale_scores.status_code == 200
    assert stale_scores.json()["tool_result"]["sample_size"] == 0
    assert stale_scores.json()["tool_result"]["excluded_missing"] == 2

    assert "模拟演示" in scores["tool_result"]["variable_definitions"]["y"]
    # Without course analysis grants the tool refuses outright; output_count
    # itself needs every output category, so keep those grants in place.
    agent_grants(
        client,
        headers,
        ["basic", "patents", "awards", "conferences", "research_papers"],
        ["view", "analyze"],
    )
    outputs.append(
        json.dumps(
            {
                "tool": "correlation_analysis",
                "college": "synthetic",
                "x_variable": "course_pass_ratio",
                "y_variable": "output_count",
            }
        )
    )
    outputs.append("again")
    denied = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "最后一次分析课程通过比例与专利数的关系"},
    )
    assert denied.status_code == 403
 
