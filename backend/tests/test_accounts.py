import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from aqp.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    database = tmp_path / "accounts.sqlite3"
    result = subprocess.run(
        [sys.executable, "-m", "aqp.cli", "bootstrap", "--username", "trial-admin"],
        input="Synthetic-password-123!\nSynthetic-password-123!\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=15,
        check=False,
        env={**os.environ, "AQP_DB": str(database), "PYTHONPATH": "backend"},
    )
    assert result.returncode == 0, result.stderr
    return TestClient(create_app(database))


def test_account_presets_apply_scoped_permissions_and_clear_on_downgrade(
    client: TestClient,
) -> None:
    headers = login_admin(client)
    body = {
        "username": "preset-account",
        "password": "Synthetic-password-123!",
        "roles": ["college_analyst"],
        "preset": "full",
        "college": "示例学院",
        "request_id": str(uuid4()),
    }
    response = client.post("/api/users", headers=headers, json=body)
    assert response.status_code == 201
    user = response.json()
    assert user["roles"] == ["platform_admin"]
    path = f"/api/users/{user['id']}"
    grants = client.get(path + "/grants").json()["grants"]
    assert {row["college"] for row in grants} == {"示例学院"}
    assert {"identity", "maintain", "export", "download"} <= {
        row["operation"] for row in grants
    }
    changed = client.patch(
        path,
        headers=headers,
        json={
            "active": True,
            "roles": ["platform_admin"],
            "preset": "ordinary",
            "college": "另一学院",
            "expected_version": user["version"],
            "request_id": str(uuid4()),
        },
    )
    assert changed.status_code == 200
    assert changed.json()["roles"] == ["college_analyst"]
    grants = client.get(path + "/grants").json()["grants"]
    assert {row["college"] for row in grants} == {"另一学院"}
    assert {row["operation"] for row in grants} == {"view", "analyze"}


def test_school_presets_grant_and_revoke_cross_college_operations(
    client: TestClient,
) -> None:
    from io import BytesIO

    from openpyxl import Workbook

    headers = login_admin(client)
    response = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "school-preset",
            "password": "Synthetic-password-123!",
            "roles": ["platform_admin"],
            "preset": "full",
            "scope": "school",
            "request_id": str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    target = response.json()
    with TestClient(client.app) as member:
        login = member.post(
            "/api/login",
            json={
                "username": "school-preset",
                "password": "Synthetic-password-123!",
            },
        )
        assert login.status_code == 200
        member_headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert member.get("/api/templates/basic").status_code == 200
        colleges = ["测试甲学院", "测试乙学院"]
        wb = Workbook()
        sheet = wb.active
        sheet.append(["AQP-PGS", "basic", "1"])
        sheet.append(["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"])
        for index, college in enumerate(colleges):
            sheet.append(
                [
                    f"school-{index}",
                    f"模拟学生{index}",
                    college,
                    "计算机",
                    "硕士",
                    "2025",
                ]
            )
        stream = BytesIO()
        wb.save(stream)
        batch = member.post(
            "/api/imports/basic/preview",
            headers=member_headers,
            data={"source_department": "模拟"},
            files={"file": ("school.xlsx", stream.getvalue())},
        )
        assert batch.status_code == 200, batch.text
        confirmed = member.post(
            f"/api/imports/{batch.json()['id']}/confirm", headers=member_headers
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["counts"] == {"imported": 2}
        assert all(
            "姓名" in row["data"] for row in member.get("/api/students").json()["items"]
        )
        for college in colleges:
            report = member.post(
                "/api/analyses/courses",
                headers=member_headers,
                json={"college": college},
            )
            assert report.status_code == 200, report.text
        saved = client.patch(
            f"/api/users/{target['id']}",
            headers=headers,
            json={
                "active": True,
                "roles": ["college_analyst"],
                "preset": "ordinary",
                "scope": "school",
                "expected_version": target["version"],
                "request_id": str(uuid4()),
            },
        )
        assert saved.status_code == 200, saved.text
        assert member.get("/api/students").status_code == 401
        assert (
            member.post(
                "/api/login",
                json={
                    "username": "school-preset",
                    "password": "Synthetic-password-123!",
                },
            ).status_code
            == 200
        )
        visible = member.get("/api/students")
        assert visible.status_code == 200
        items = [row["data"] for row in visible.json()["items"]]
        assert {row["所属学院"] for row in items} == set(colleges)
        assert all("姓名" not in row and "学号" not in row for row in items)
        assert member.get("/api/templates/basic").status_code == 403
        assert member.get("/api/users").status_code == 403


def test_admin_school_view_is_schoolwide_and_read_only(client: TestClient) -> None:
    from io import BytesIO

    from openpyxl import Workbook

    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    assert client.get("/api/students").status_code == 403
    path = f"/api/users/{user['id']}"
    colleges = ["示例学院", "另一学院"]
    granted = client.put(
        path + "/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {"category": "basic", "operation": "maintain", "college": name}
                for name in colleges
            ],
        },
    )
    assert granted.status_code == 200
    wb = Workbook()
    sheet = wb.active
    sheet.append(["AQP-PGS", "basic", "1"])
    sheet.append(["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"])
    for index, name in enumerate(colleges):
        sheet.append(
            [f"test-{index}", f"合成学生{index}", name, "计算机", "硕士", "2025"]
        )
    buf = BytesIO()
    wb.save(buf)
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "模拟"},
        files={"file": ("demo.xlsx", buf.getvalue())},
    )
    assert batch.status_code == 200
    assert (
        client.post(
            f"/api/imports/{batch.json()['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    user = client.get("/api/me").json()["user"]
    cleared = client.put(
        path + "/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [],
        },
    )
    assert cleared.status_code == 200
    user = client.get("/api/me").json()["user"]
    saved = client.patch(
        f"/api/users/{user['id']}",
        headers=headers,
        json={
            "active": True,
            "roles": user["roles"],
            "school_view": True,
            "expected_version": user["version"],
            "request_id": str(uuid4()),
        },
    )
    assert saved.status_code == 200
    assert saved.json()["school_view"] is True
    result = client.get("/api/students")
    assert result.status_code == 200
    students = [item["data"] for item in result.json()["items"]]
    assert {student["所属学院"] for student in students} == set(colleges)
    assert all("姓名" not in student and "学号" not in student for student in students)
    assert client.get("/api/templates/basic").status_code == 403
    for college in colleges:
        report = client.post(
            "/api/analyses/courses", headers=headers, json={"college": college}
        )
        assert report.status_code == 200, report.text
    disabled = client.patch(
        path,
        headers=headers,
        json={
            "active": True,
            "roles": user["roles"],
            "school_view": False,
            "expected_version": saved.json()["version"],
            "request_id": str(uuid4()),
        },
    )
    assert disabled.status_code == 200
    assert client.get("/api/students").status_code == 403


def test_admin_can_login_and_logout(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401
    headers = login_admin(client)
    session = client.get("/api/me").json()
    assert session["user"]["roles"] == ["platform_admin"]
    assert session["user"]["business_permissions"] == []
    assert client.post("/api/logout", headers=headers).status_code == 204
    assert client.get("/api/me").status_code == 401


def login_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/login",
        json={"username": "trial-admin", "password": "Synthetic-password-123!"},
    )
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_create_combined_roles_and_disable_revokes_session(client: TestClient) -> None:
    headers = login_admin(client)
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "synthetic-user",
            "password": "Synthetic-user-password!",
            "roles": ["college_data_admin", "college_analyst"],
            "request_id": str(uuid4()),
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    with TestClient(client.app) as member:
        assert (
            member.post(
                "/api/login",
                json={
                    "username": "synthetic-user",
                    "password": "Synthetic-user-password!",
                },
            ).status_code
            == 200
        )
        assert member.get("/api/users").status_code == 403
        assert set(member.get("/api/me").json()["user"]["roles"]) == {
            "college_data_admin",
            "college_analyst",
        }
        assert (
            client.patch(
                f"/api/users/{user_id}",
                headers=headers,
                json={
                    "active": False,
                    "roles": ["college_analyst"],
                    "expected_version": 1,
                    "request_id": str(uuid4()),
                },
            ).status_code
            == 200
        )
        assert member.get("/api/me").status_code == 401
        assert (
            member.post(
                "/api/login",
                json={
                    "username": "synthetic-user",
                    "password": "Synthetic-user-password!",
                },
            ).status_code
            == 401
        )
    events = client.get("/api/account-audit").json()
    assert any(
        event["action"] == "user.create" and event["target"] == str(user_id)
        for event in events
    )
    assert any(
        event["action"] == "user.update" and event["target"] == str(user_id)
        for event in events
    )
    assert "password" not in str(events).lower()
    response = client.post(
        "/api/login",
        json={"username": "trial-admin", "password": "Synthetic-password-123!"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["roles"] == ["platform_admin"]
    assert response.json()["user"]["business_permissions"] == []
    assert "httponly" in response.headers["set-cookie"].lower()
    csrf = response.json()["csrf_token"]
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/me").status_code == 401


def test_csrf_last_admin_and_duplicate_guards(client: TestClient) -> None:
    headers = login_admin(client)
    body = {
        "username": "synthetic-analyst",
        "password": "Synthetic-password-123!",
        "roles": ["college_analyst"],
        "request_id": str(uuid4()),
    }
    assert client.post("/api/users", json=body).status_code == 403
    assert client.post("/api/users", json=body, headers=headers).status_code == 201
    body["username"] = "SYNTHETIC-ANALYST"
    body["request_id"] = str(uuid4())
    assert client.post("/api/users", json=body, headers=headers).status_code == 409
    user_id = client.get("/api/me").json()["user"]["id"]
    assert (
        client.patch(
            f"/api/users/{user_id}",
            json={
                "active": False,
                "roles": ["platform_admin"],
                "expected_version": 1,
                "request_id": str(uuid4()),
            },
            headers=headers,
        ).status_code
        == 409
    )
    assert client.get("/api/me").status_code == 200
    assert (
        client.post(
            "/api/login",
            json={"username": "trial-admin", "password": "Synthetic-password-123!"},
            headers={"Origin": "https://other.invalid"},
        ).status_code
        == 403
    )


def test_roles_persist_and_change_invalidates_session(
    client: TestClient, tmp_path: Path
) -> None:
    headers = login_admin(client)
    created = client.post(
        "/api/users",
        json={
            "username": "second-admin",
            "password": "Synthetic-password-123!",
            "roles": ["platform_admin"],
            "request_id": str(uuid4()),
        },
        headers=headers,
    ).json()
    with TestClient(create_app(tmp_path / "accounts.sqlite3")) as restarted:
        response = restarted.post(
            "/api/login",
            json={"username": "second-admin", "password": "Synthetic-password-123!"},
        )
        assert response.status_code == 200
        assert (
            client.patch(
                f"/api/users/{created['id']}",
                json={
                    "active": True,
                    "roles": ["college_analyst"],
                    "expected_version": 1,
                    "request_id": str(uuid4()),
                },
                headers=headers,
            ).status_code
            == 200
        )
        assert restarted.get("/api/me").status_code == 401


def test_failed_logins_are_limited_and_audited(client: TestClient) -> None:
    login_admin(client)
    for _ in range(10):
        assert (
            client.post(
                "/api/login", json={"username": "trial-admin", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/login", json={"username": "trial-admin", "password": "wrong"}
        ).status_code
        == 429
    )
    events = client.get("/api/account-audit").json()
    assert (
        sum(
            event["action"] == "login" and event["outcome"] == "denied"
            for event in events
        )
        == 10
    )


def test_stale_account_update_cannot_reenable_disabled_user(client: TestClient) -> None:
    headers = login_admin(client)
    create_body = {
        "username": "synthetic-target",
        "password": "Synthetic-password-123!",
        "roles": ["college_analyst"],
        "request_id": str(uuid4()),
    }
    created = client.post("/api/users", json=create_body, headers=headers)
    assert created.status_code == 201
    assert (
        client.post("/api/users", json=create_body, headers=headers).json()
        == created.json()
    )
    user = created.json()
    url = f"/api/users/{user['id']}"
    disable = {
        "active": False,
        "roles": ["college_analyst"],
        "expected_version": user["version"],
        "request_id": str(uuid4()),
    }
    disabled = client.patch(url, json=disable, headers=headers)
    assert disabled.status_code == 200
    assert client.patch(url, json=disable, headers=headers).json() == disabled.json()
    stale = {
        "active": True,
        "roles": ["college_data_admin"],
        "expected_version": user["version"],
        "request_id": str(uuid4()),
    }
    assert client.patch(url, json=stale, headers=headers).status_code == 409
    current = next(
        row for row in client.get("/api/users").json() if row["id"] == user["id"]
    )
    assert current["active"] is False
    assert current["version"] == 2
    events = [
        row
        for row in client.get("/api/account-audit").json()
        if row["action"] == "user.update" and row["target"] == str(user["id"])
    ]
    assert len(events) == 1
    details = json.loads(events[0]["details"])
    assert details["before"]["active"] is True
    assert details["after"]["active"] is False
    assert details["before"]["version"] == 1
    assert details["after"]["version"] == 2


def test_student_bindings_configuration(client: TestClient, tmp_path: Path) -> None:
    from aqp.store import connection

    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "INSERT INTO students(research_id,student_number,name,college,major,level,entry_year,payload) VALUES (?,?,?,?,?,?,?,?)",
            (
                "SYN-BIND",
                "SYN-TEST",
                "合成学生",
                "示例学院",
                "数学",
                "硕士",
                2026,
                "{}",
            ),
        )
    headers = login_admin(client)
    user_id = client.get("/api/me").json()["user"]["id"]
    url = f"/api/users/{user_id}/student_bindings"
    initial = client.get(url).json()
    assert initial["student_bindings"] == []
    body = {
        "expected_version": initial["version"],
        "request_id": str(uuid4()),
        "student_bindings": ["SYN-NOT-FOUND"],
    }
    assert client.put(url, headers=headers, json=body).status_code == 422
    body["student_bindings"] = ["SYN-BIND"]
    saved = client.put(url, headers=headers, json=body)
    assert saved.status_code == 200
    assert saved.json()["version"] == initial["version"] + 1
    assert saved.json()["student_bindings"] == ["SYN-BIND"]
    assert client.get(url).json()["student_bindings"] == ["SYN-BIND"]
    revoke = {
        "expected_version": saved.json()["version"],
        "request_id": str(uuid4()),
        "student_bindings": [],
    }
    assert (
        client.put(url, headers=headers, json=revoke).json()["student_bindings"] == []
    )
    body["request_id"] = str(uuid4())
    assert client.put(url, headers=headers, json=body).status_code == 409
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "binding-member",
            "password": "Synthetic-user-password!",
            "roles": ["college_analyst"],
            "request_id": str(uuid4()),
        },
    )
    assert created.status_code == 201
    with TestClient(client.app) as member:
        result = member.post(
            "/api/login",
            json={"username": "binding-member", "password": "Synthetic-user-password!"},
        )
        member_headers = {"X-CSRF-Token": result.json()["csrf_token"]}
        assert member.get(url).status_code == 403
        assert member.put(url, headers=member_headers, json=body).status_code == 403
