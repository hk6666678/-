from uuid import uuid4

import pytest
from test_accounts import client, login_admin  # noqa: F401
from test_courses import course_file
from test_milestones import sheet


@pytest.mark.parametrize("category", ["courses", "topic", "midterm"])
def test_basic_route_cannot_bypass_other_import_categories(client, category):  # noqa: F811
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {
            "category": cat,
            "operation": "maintain",
            "college": "示例学院",
            "major": "计算机",
        }
        for cat in ["basic", category]
    ]

    def save_grants(values):
        version = client.get("/api/me").json()["user"]["version"]
        response = client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": version,
                "request_id": str(uuid4()),
                "grants": values,
            },
        )
        assert response.status_code == 200

    save_grants(grants)
    if category == "courses":
        url = "/api/imports/courses/preview"
        data = course_file([["009", "C1", "2025秋", "1", "百分制", "80", "合成学生"]])
    else:
        url = f"/api/milestones/{category}/preview"
        data = sheet(category)
    response = client.post(
        url,
        headers=headers,
        data={
            "source_department": "合成来源",
            "college": "示例学院",
            "major": "计算机",
        },
        files={"file": ("synthetic.xlsx", data)},
    )
    assert response.status_code == 200
    batch_id = response.json()["id"]
    assert client.get(f"/api/imports/{batch_id}").status_code == 404
    assert (
        client.post(f"/api/imports/{batch_id}/confirm", headers=headers).status_code
        == 404
    )
    save_grants([grants[0]])
    own_url = (
        f"/api/imports/courses/{batch_id}"
        if category == "courses"
        else f"/api/milestone-imports/{batch_id}"
    )
    assert client.get(own_url).status_code in {403, 404}
