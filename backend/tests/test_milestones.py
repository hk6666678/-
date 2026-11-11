from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient
from openpyxl import Workbook
from test_accounts import client, login_admin  # noqa: F401


def sheet(category="topic", rows=None):
    wb = Workbook()
    ws = wb.active
    ws.append(["AQP-PGS", category, "1"])
    ws.append(
        [
            "学号",
            "姓名",
            "考核批次",
            "选题标题",
            "评分制度",
            "原始成绩",
            "所属学院",
            "专业",
        ]
    )
    for row in rows or [
        ["001", "合成学生", "2025一", "合成选题", "百分制", "", "示例学院", "计算机"]
    ]:
        ws.append(row)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def grant(client, headers):  # noqa: F811
    user = client.get("/api/me").json()["user"]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": cat,
                        "operation": op,
                        "college": "示例学院",
                        "major": "计算机",
                    }
                    for cat in ["basic", "topic", "midterm"]
                    for op in ["maintain", "view", "identity"]
                ],
            },
        ).status_code
        == 200
    )


def test_pending_then_associate_and_preserve_batches(client: TestClient):  # noqa: F811
    headers = login_admin(client)
    grant(client, headers)
    batch = client.post(
        "/api/milestones/topic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("sample.xlsx", sheet())},
    )
    assert batch.status_code == 200
    assert batch.json()["counts"] == {"pending": 1}
    batch_id = batch.json()["id"]
    assert client.post(
        f"/api/milestone-imports/{batch_id}/confirm", headers=headers
    ).json()["counts"] == {"pending": 1}
    from test_students import workbook

    basic = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("basic.xlsx", workbook())},
    ).json()
    client.post(f"/api/imports/{basic['id']}/confirm", headers=headers)
    records = client.get("/api/milestones").json()["items"]
    assert len(records) == 1 and records[0]["student_id"] is not None
    assert records[0]["data"]["原始成绩"] == ""
    assert client.post(
        "/api/milestones/topic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("sample.xlsx", sheet())},
    ).json()["counts"] == {"duplicate": 1}


def test_validation_conflicts_and_multiple_assessments(client: TestClient):  # noqa: F811
    headers = login_admin(client)
    grant(client, headers)

    def preview(rows, category="topic"):
        return client.post(
            f"/api/milestones/{category}/preview",
            headers=headers,
            data={"source_department": "合成来源"},
            files={"file": ("sample.xlsx", sheet(category, rows))},
        )

    rows = [
        ["001", "合成学生", "甲", "合成选题", "百分制", "80", "示例学院", "计算机"],
        ["001", "合成学生", "乙", "合成选题", "百分制", "", "示例学院", "计算机"],
        ["002", "合成学生", "甲", "合成选题", "百分制", "101", "示例学院", "计算机"],
    ]
    batch = preview(rows).json()
    assert batch["counts"] == {"pending": 2, "invalid": 1}
    assert (
        client.post(
            f"/api/milestone-imports/{batch['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    assert client.post(
        f"/api/milestone-imports/{batch['id']}/confirm", headers=headers
    ).json()["counts"] == {"pending": 2, "invalid": 1}
    rows[0][5] = "81"
    assert preview([rows[0]]).json()["counts"] == {"conflict": 1}
    assert client.get("/api/milestones").json()["total"] == 2
    assert preview([rows[0]], "midterm").json()["counts"] == {"pending": 1}
    assert client.get(f"/api/milestone-imports/{batch['id']}").status_code == 200


def test_category_isolation_and_masking(client: TestClient):  # noqa: F811
    headers = login_admin(client)
    grant(client, headers)
    batch = client.post(
        "/api/milestones/topic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("sample.xlsx", sheet())},
    ).json()
    client.post(f"/api/milestone-imports/{batch['id']}/confirm", headers=headers)
    user = client.get("/api/me").json()["user"]
    client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {
                    "category": "topic",
                    "operation": op,
                    "college": "示例学院",
                    "major": "计算机",
                }
                for op in ["view", "maintain"]
            ],
        },
    )
    record = client.get("/api/milestones").json()["items"][0]
    assert "学号" not in record["data"] and "选题标题" not in record["data"]
    view = client.get(f"/api/milestone-imports/{batch['id']}").json()
    assert view["filename"] == "名称已脱敏"
    assert "姓名" not in view["rows"][0]["data"]
    assert (
        client.post(
            "/api/milestones/midterm/preview",
            headers=headers,
            data={"source_department": "合成来源"},
            files={"file": ("sample.xlsx", sheet("midterm"))},
        ).status_code
        == 403
    )
