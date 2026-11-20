"""Synthetic scope planning and redacted denial diagnosis; no network."""

# ruff: noqa: F811
import json

from aqp import model_connection
from aqp.store import connection
from test_accounts import client, login_admin  # noqa: F401
from test_agent import enable_agent, synthetic_student_and_analysis


def test_planner_receives_exact_authorized_scope_names(client, monkeypatch):
    headers = login_admin(client)
    synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    prompts = []

    def runner(config, text):
        prompts.append(json.loads(text))
        if len(prompts) == 1:
            assert prompts[0]["scope_options"] == [
                {"college": "示例学院", "major": "计算机"}
            ]
            assert "身份" not in json.dumps(
                prompts[0]["scope_options"], ensure_ascii=False
            )
            return json.dumps(
                {"tool": "student_counts", "college": "示例学院", "major": "计算机"}
            )
        return "模拟统计结果。"

    monkeypatch.setattr(model_connection, "default_runner", runner)
    response = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "统计示例学院计算机专业学生人数"},
    )
    assert response.status_code == 200
    assert response.json()["tool_result"]["total"] == 1


def test_wrong_model_scope_remains_denied_and_is_diagnosable(
    client, tmp_path, monkeypatch
):
    headers = login_admin(client)
    synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    calls = []

    def runner(config, text):
        calls.append(text)
        return json.dumps(
            {"tool": "student_counts", "college": "示例学院", "major": "计算机专业"}
        )

    monkeypatch.setattr(model_connection, "default_runner", runner)
    response = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "统计示例学院计算机专业学生人数"},
    )
    assert response.status_code == 403
    assert len(calls) == 1
    with connection(tmp_path / "accounts.sqlite3") as db:
        row = db.execute(
            "SELECT details FROM audit WHERE action='agent.plan_denied'"
        ).fetchone()
    assert row is not None
    details = json.loads(row[0])
    assert details == {
        "tool": "student_counts",
        "model_version": 1,
        "college_matches_grant": True,
        "scope_matches_grant": False,
    }
    assert "计算机" not in row[0]
