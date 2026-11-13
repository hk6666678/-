import json

from aqp import model_connection
from aqp.store import connection
from test_accounts import client, login_admin  # noqa: F401
from test_agent import enable_agent, synthetic_student_and_analysis


def test_mentor_combined_role_agent_binding_revocation(client, tmp_path, monkeypatch):  # noqa: F811
    headers = login_admin(client)
    synthetic_student_and_analysis(client, headers)
    enable_agent(client, headers, monkeypatch)
    with connection(tmp_path / "accounts.sqlite3") as db:
        actor = db.execute("SELECT id FROM users").fetchone()[0]
        student = db.execute("SELECT id FROM students").fetchone()[0]
        db.execute(
            "UPDATE users SET roles=? WHERE id=?",
            (json.dumps(["platform_admin", "mentor"]), actor),
        )

    def runner(config, text):
        if "tool_result" in text or "系统依据" in text:
            return "合成摘要"
        return json.dumps(
            {"tool": "student_counts", "college": "示例学院", "major": "计算机"}
        )

    monkeypatch.setattr(model_connection, "default_runner", runner)

    def count():
        result = client.post(
            "/api/agent/query", headers=headers, json={"question": "统计学生人数"}
        )
        assert result.status_code == 200, result.text
        return result.json()["tool_result"]["total"]

    assert count() == 0
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("INSERT INTO user_student_bindings VALUES (?,?)", (actor, student))
    assert count() == 1
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("DELETE FROM user_student_bindings")
    assert count() == 0


def test_mentor_role_can_be_created_without_implicit_data_access(client):  # noqa: F811
    from uuid import uuid4

    headers = login_admin(client)
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "synthetic-mentor",
            "password": "Synthetic-mentor-password!",
            "roles": ["mentor"],
            "request_id": str(uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    client.post("/api/logout", headers=headers)
    signed = client.post(
        "/api/login",
        json={"username": "synthetic-mentor", "password": "Synthetic-mentor-password!"},
    )
    assert signed.status_code == 200
    assert client.get("/api/me").json()["user"]["roles"] == ["mentor"]
    assert client.get("/api/students").status_code == 403


def test_mentor_historical_analysis_evidence_rechecks_binding(client, tmp_path):  # noqa: F811
    headers = login_admin(client)
    from test_courses import course_file

    synthetic_student_and_analysis(client, headers)
    batch = client.post(
        "/api/imports/courses/preview",
        headers=headers,
        data={
            "source_department": "synthetic",
            "college": "示例学院",
            "major": "计算机",
        },
        files={
            "file": (
                "courses.xlsx",
                course_file([["001", "SYN", "2025秋", 1, "百分制", 80, "合成学生"]]),
            )
        },
    ).json()
    assert (
        client.post(
            f"/api/imports/courses/{batch['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    snapshot = client.post(
        "/api/analyses/courses",
        headers=headers,
        json={"college": "示例学院", "major": "计算机"},
    ).json()
    analysis_id = snapshot["id"]
    assert snapshot["evidence"]
    with connection(tmp_path / "accounts.sqlite3") as db:
        actor = db.execute("SELECT id FROM users").fetchone()[0]
        student = db.execute("SELECT id FROM students").fetchone()[0]
        db.execute(
            "UPDATE users SET roles=? WHERE id=?",
            (json.dumps(["platform_admin", "mentor"]), actor),
        )
        db.execute("INSERT INTO user_student_bindings VALUES (?,?)", (actor, student))
    for suffix in ["", "/evidence"]:
        assert (
            client.get(
                f"/api/analyses/{analysis_id}{suffix}", headers=headers
            ).status_code
            == 200
        )
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("DELETE FROM user_student_bindings WHERE user_id=?", (actor,))
    for suffix in ["", "/evidence"]:
        assert (
            client.get(
                f"/api/analyses/{analysis_id}{suffix}", headers=headers
            ).status_code
            == 403
        )
