from io import BytesIO
from uuid import uuid4

from openpyxl import Workbook
from test_accounts import client, login_admin  # noqa: F401
from test_students import workbook


def course_file(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["AQP-PGS", "courses", "1"])
    ws.append(
        [
            "学号",
            "课程编号",
            "修读学期",
            "考核次数",
            "评分制度",
            "原始成绩",
            "姓名",
            "课程名称",
        ]
    )
    for row in rows:
        ws.append([*row, "合成课程"])
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_pending_courses_link_without_inventing_student(client):  # noqa: F811
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {
            "category": category,
            "operation": op,
            "college": "示例学院",
            "major": "计算机",
        }
        for category in ["basic", "courses"]
        for op in ["maintain", "view"]
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
    data = {"source_department": "合成教务", "college": "示例学院", "major": "计算机"}
    response = client.post(
        "/api/imports/courses/preview",
        headers=headers,
        data=data,
        files={
            "file": (
                "synthetic.xlsx",
                course_file(
                    [
                        ["001", "C1", "2025秋", "1", "百分制", "", "合成学生"],
                        ["001", "C1", "2025秋", "2", "百分制", "80", "合成学生"],
                    ]
                ),
            )
        },
    )
    assert response.status_code == 200
    batch = response.json()
    assert batch["counts"] == {"pending": 2}
    assert (
        client.post(
            f"/api/imports/courses/{batch['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    assert client.get("/api/students").json()["total"] == 0
    basic = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成基础"},
        files={"file": ("basic.xlsx", workbook())},
    ).json()
    client.post(f"/api/imports/{basic['id']}/confirm", headers=headers)
    student = client.get("/api/students").json()["items"][0]
    records = client.get(f"/api/students/{student['id']}/courses").json()["items"]
    assert len(records) == 2
    assert records[0]["data"]["原始成绩"] == ""
    assert "学号" not in str(records)
    assert records[0]["source"]["row_number"] == 3


def test_course_conflicts_duplicates_and_scope_are_explicit(client):  # noqa: F811
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {
            "category": "courses",
            "operation": op,
            "college": "示例学院",
            "major": "计算机",
        }
        for op in ["maintain", "view", "identity"]
    ]
    client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": grants,
        },
    )
    data = {"source_department": "合成教务", "college": "示例学院", "major": "计算机"}

    def preview(rows, form=data):
        return client.post(
            "/api/imports/courses/preview",
            headers=headers,
            data=form,
            files={"file": ("synthetic.xlsx", course_file(rows))},
        )

    first = ["009", "C1", "2025秋", "1", "百分制", "80", "合成学生"]
    batch = preview(
        [first, first, ["009", "C2", "2025秋", "1", "百分制", "101", "合成学生"]]
    ).json()
    assert batch["counts"] == {"pending": 1, "duplicate": 1, "invalid": 1}
    committed = client.post(
        f"/api/imports/courses/{batch['id']}/confirm", headers=headers
    ).json()
    assert (
        client.post(
            f"/api/imports/courses/{batch['id']}/confirm", headers=headers
        ).json()
        == committed
    )
    assert preview([first]).json()["counts"] == {"duplicate": 1}
    changed = first.copy()
    changed[5] = "90"
    assert preview([changed]).json()["counts"] == {"conflict": 1}
    assert preview([first], {"source_department": "合成教务"}).status_code == 403
    assert preview([first], {**data, "college": "其他学院"}).status_code == 403
    conflict = preview([["010", *first[1:]], ["010", *changed[1:]]]).json()
    assert conflict["counts"] == {"conflict": 2}


def test_course_identity_conflict_stays_manual_after_basic_arrives(client):  # noqa: F811
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {
            "category": category,
            "operation": op,
            "college": "示例学院",
            "major": "计算机",
        }
        for category in ["basic", "courses"]
        for op in ["maintain", "view"]
    ]
    client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": grants,
        },
    )
    batch = client.post(
        "/api/imports/courses/preview",
        headers=headers,
        data={
            "source_department": "合成教务",
            "college": "示例学院",
            "major": "计算机",
        },
        files={
            "file": (
                "synthetic.xlsx",
                course_file([["001", "C1", "2025秋", "1", "百分制", "80", "不同姓名"]]),
            )
        },
    ).json()
    client.post(f"/api/imports/courses/{batch['id']}/confirm", headers=headers)
    basic = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成基础"},
        files={"file": ("basic.xlsx", workbook())},
    ).json()
    assert client.get(f"/api/imports/courses/{basic['id']}").status_code == 404
    client.post(f"/api/imports/{basic['id']}/confirm", headers=headers)
    assert client.get(f"/api/imports/courses/{batch['id']}").json()["counts"] == {
        "conflict": 1
    }
    student = client.get("/api/students").json()["items"][0]
    assert client.get(f"/api/students/{student['id']}/courses").json()["total"] == 0
