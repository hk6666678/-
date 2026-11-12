import json
from uuid import uuid4

from aqp.store import connection
from test_accounts import client, login_admin  # noqa: F401
from test_students import workbook


def test_mentor_binding_revokes_student_and_record_access(client, tmp_path):  # noqa: F811
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {"category": "basic", "operation": op, "college": "示例学院", "major": "计算机"}
        for op in ["view", "maintain", "identity", "void"]
    ]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        ).status_code
        == 200
    )
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "synthetic"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    sid = client.get("/api/students").json()["items"][0]["id"]
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "UPDATE users SET roles=? WHERE id=?",
            (json.dumps(["platform_admin", "mentor"]), user["id"]),
        )
    assert client.get("/api/students").json()["total"] == 0
    assert client.get(f"/api/students/{sid}").status_code == 404
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("INSERT INTO user_student_bindings VALUES (?,?)", (user["id"], sid))
    assert client.get("/api/students").json()["total"] == 1
    assert client.get(f"/api/students/{sid}").status_code == 200
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("DELETE FROM user_student_bindings")
    assert client.get("/api/students").json()["total"] == 0
    assert client.get(f"/api/records/basic/{sid}").status_code == 403


def test_mentor_mixed_course_and_milestone_batches_are_denied(client, tmp_path):  # noqa: F811
    from test_courses import course_file
    from test_milestones import sheet

    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {"category": cat, "operation": op, "college": "示例学院", "major": "计算机"}
        for cat in ["basic", "courses", "topic"]
        for op in ["view", "maintain", "identity"]
    ]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        ).status_code
        == 200
    )
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "synthetic"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    sid = client.get("/api/students").json()["items"][0]["id"]
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "UPDATE users SET roles=? WHERE id=?",
            (json.dumps(["platform_admin", "mentor"]), user["id"]),
        )
        db.execute("INSERT INTO user_student_bindings VALUES (?,?)", (user["id"], sid))
    course = course_file(
        [
            ["001", "C1", "2025秋", "1", "百分制", "80", "合成学生"],
            ["UNKNOWN", "C2", "2025秋", "1", "百分制", "80", "未知合成学生"],
        ]
    )
    result = client.post(
        "/api/imports/courses/preview",
        headers=headers,
        data={
            "source_department": "synthetic",
            "college": "示例学院",
            "major": "计算机",
        },
        files={"file": ("synthetic.xlsx", course)},
    )
    assert result.status_code == 403
    milestone = sheet(
        rows=[
            [
                "001",
                "合成学生",
                "2025一",
                "合成选题",
                "百分制",
                "80",
                "示例学院",
                "计算机",
            ],
            [
                "UNKNOWN",
                "未知合成学生",
                "2025一",
                "合成选题",
                "百分制",
                "80",
                "示例学院",
                "计算机",
            ],
        ]
    )
    result = client.post(
        "/api/milestones/topic/preview",
        headers=headers,
        data={"source_department": "synthetic"},
        files={"file": ("synthetic.xlsx", milestone)},
    )
    assert result.status_code == 403
