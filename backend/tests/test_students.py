from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from openpyxl import Workbook
from test_accounts import client, login_admin  # noqa: F401


def workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["AQP-PGS", "basic", "1"])
    ws.append(["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"])
    ws.append(["001", "合成学生", "示例学院", "计算机", "硕士", "2025"])
    ws.append(["002", "", "示例学院", "计算机", "硕士", "2025"])
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_preview_confirm_and_masked_source(client: TestClient) -> None:  # noqa: F811
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {"category": "basic", "operation": op, "college": "示例学院", "major": "计算机"}
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
    response = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成数据源"},
        files={"file": ("synthetic.xlsx", workbook())},
    )
    assert response.status_code == 200
    batch = response.json()
    assert batch["counts"] == {"ready": 1, "invalid": 1}
    assert client.get("/api/students").json()["total"] == 0
    committed = client.post(f"/api/imports/{batch['id']}/confirm", headers=headers)
    assert committed.status_code == 200
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    rows = client.get("/api/students").json()
    assert rows["total"] == 1
    student = rows["items"][0]
    assert "student_number" not in student and "姓名" not in str(student)
    detail = client.get(f"/api/students/{student['id']}").json()
    assert "学号" not in detail["data"]
    assert "学号" not in detail["history"][0]["original_row"]
    repeated = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成数据源"},
        files={"file": ("synthetic.xlsx", workbook())},
    )
    assert repeated.json()["counts"] == {"duplicate": 1, "invalid": 1}
    stream = BytesIO(workbook())
    wb = __import__("openpyxl").load_workbook(stream)
    wb.active.cell(3, 2).value = "另一合成姓名"
    changed = BytesIO()
    wb.save(changed)
    conflict = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成数据源"},
        files={"file": ("synthetic.xlsx", changed.getvalue())},
    )
    assert conflict.json()["counts"] == {"conflict": 1, "invalid": 1}
    assert client.get("/api/students").json()["total"] == 1
