# ruff: noqa: F811
from uuid import uuid4

from test_accounts import client, login_admin  # noqa: F401


def test_directory_requires_explicit_grants_and_redacts_identity(client):
    headers = login_admin(client)
    actor = client.get("/api/me").json()["user"]["id"]
    body = {
        "number": "SYN-M1",
        "name": "Synthetic",
        "college": "Example",
        "major": "Math",
    }
    endpoint = "/api/mentor-groups/directory/mentors"
    assert client.post(endpoint, headers=headers, json=body).status_code == 403
    grants = [
        {
            "category": "mentor_groups",
            "operation": op,
            "college": "Example",
            "major": "Math",
        }
        for op in ["maintain", "view"]
    ]
    version = client.get(f"/api/users/{actor}/grants").json()["version"]
    response = client.put(
        f"/api/users/{actor}/grants",
        headers=headers,
        json={
            "expected_version": version,
            "request_id": str(uuid4()),
            "grants": grants,
        },
    )
    assert response.status_code == 200, response.text
    assert client.post(endpoint, headers=headers, json=body).status_code == 200
    assert client.post(endpoint, headers=headers, json=body).status_code == 409
    rows = client.get(endpoint).json()
    assert len(rows) == 1
    assert "name" not in rows[0]
    assert "mentor_number" not in rows[0]
    assert client.get("/api/access/grants").json() == grants


def test_relation_dates_history_conflicts_and_current_revocation(client):
    from test_students import workbook

    headers = login_admin(client)
    actor = client.get("/api/me").json()["user"]["id"]
    grants = [
        {
            "category": category,
            "operation": operation,
            "college": "示例学院",
            "major": "计算机",
        }
        for category in [
            "basic",
            "mentor_groups",
            "research_papers",
            "patents",
            "awards",
            "conferences",
        ]
        for operation in ["maintain", "view", "identity", "analyze"]
    ]

    def authorize(values):
        version = client.get(f"/api/users/{actor}/grants").json()["version"]
        response = client.put(
            f"/api/users/{actor}/grants",
            headers=headers,
            json={
                "expected_version": version,
                "request_id": str(uuid4()),
                "grants": values,
            },
        )
        assert response.status_code == 200, response.text

    authorize(grants)
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "Synthetic"},
        files={"file": ("synthetic.xlsx", workbook())},
    ).json()
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    student_id = client.get("/api/students").json()["items"][0]["id"]
    directories = []
    for kind in ["mentors", "groups"]:
        response = client.post(
            f"/api/mentor-groups/directory/{kind}",
            headers=headers,
            json={
                "number": "SYN-1",
                "name": "Synthetic",
                "college": "示例学院",
                "major": "计算机",
            },
        )
        assert response.status_code == 200
        directories.append(response.json()["id"])
    body = {
        "student_id": student_id,
        "mentor_id": directories[0],
        "group_id": directories[1],
        "start_date": "2025-09-01",
        "end_date": None,
        "source_department": "Synthetic",
        "reason": "Synthetic initial relationship",
    }
    endpoint = "/api/mentor-groups/relations"
    for invalid in ["2025-2-01", "2025-02-30", "2025-01-01T00:00:00Z"]:
        assert (
            client.post(
                endpoint, headers=headers, json={**body, "start_date": invalid}
            ).status_code
            == 422
        )
    assert (
        client.post(
            endpoint, headers=headers, json={**body, "end_date": "2024-01-01"}
        ).status_code
        == 422
    )
    created = client.post(endpoint, headers=headers, json=body)
    assert created.status_code == 200, created.text
    rid = created.json()["id"]
    assert client.post(endpoint, headers=headers, json=body).status_code == 409
    assert (
        client.put(
            f"{endpoint}/{rid}",
            headers=headers,
            json={**body, "end_date": "2026-06-30", "expected_version": 1},
        ).json()["version"]
        == 2
    )
    assert (
        client.put(
            f"{endpoint}/{rid}", headers=headers, json={**body, "expected_version": 1}
        ).status_code
        == 409
    )
    history = client.get(f"{endpoint}/{rid}/history").json()["items"]
    assert [item["version"] for item in history] == [1, 2]
    assert history[0]["data"]["end_date"] is None
    assert history[1]["data"]["end_date"] == "2026-06-30"
    facts = client.get("/api/mentor-groups/facts?as_of=2026-01-01").json()
    assert facts["student_count"] == 1
    assert facts["graduation"]["status"] == "missing"
    assert facts["delay"]["status"] == "missing"
    from io import BytesIO

    from openpyxl import load_workbook

    for category, endpoint_name in [
        ("research_papers", "research-outputs"),
        ("patents", "patents"),
        ("awards", "awards"),
        ("conferences", "conferences"),
    ]:
        book = load_workbook(
            BytesIO(client.get(f"/api/{endpoint_name}/template").content)
        )
        sheet = book.active
        extra = {
            "research_papers": ["2026"],
            "patents": ["发明", "2026-01-01"],
            "awards": ["国家级", "2026"],
            "conferences": ["口头报告", "2026-01-01"],
        }[category]
        sheet.append(
            [
                "SYN-OUTPUT-1",
                "Synthetic output",
                "001",
                "合成学生",
                1,
                "第一作者",
                "示例学院",
                "计算机",
                *extra,
            ]
        )
        stream = BytesIO()
        book.save(stream)
        preview = client.post(
            f"/api/{endpoint_name}/preview",
            headers=headers,
            data={"source_department": "Synthetic"},
            files={"file": ("synthetic.xlsx", stream.getvalue())},
        )
        assert preview.status_code == 200, preview.text
        confirmed = client.post(
            f"/api/{endpoint_name}/previews/{preview.json()['id']}/confirm",
            headers=headers,
            json={"accept_changes": False},
        )
        assert confirmed.status_code == 200, confirmed.text
        category_facts = client.get("/api/mentor-groups/facts?as_of=2026-01-01").json()[
            "categories"
        ][category]
        assert category_facts["student_count"] == 1
        assert category_facts["distinct_outputs"] == 1
        assert category_facts["items"][0]["title"] == "Synthetic output"
    assert (
        client.get("/api/mentor-groups/facts?as_of=2026-09-01").json()["student_count"]
        == 0
    )
    authorize([])
    assert client.get(endpoint).json()["items"] == []
    assert client.get(f"{endpoint}/{rid}/history").status_code == 404
    assert (
        client.get("/api/mentor-groups/facts?as_of=2026-01-01").json()["student_count"]
        == 0
    )


def test_directory_excel_preview_confirmation_and_revalidation(client):
    from io import BytesIO

    from openpyxl import load_workbook

    headers = login_admin(client)
    actor = client.get("/api/me").json()["user"]["id"]
    grants = [
        {
            "category": "mentor_groups",
            "operation": op,
            "college": "Example",
            "major": "Math",
        }
        for op in ["maintain", "view", "identity"]
    ]
    version = client.get(f"/api/users/{actor}/grants").json()["version"]
    assert (
        client.put(
            f"/api/users/{actor}/grants",
            headers=headers,
            json={
                "expected_version": version,
                "request_id": str(uuid4()),
                "grants": grants,
            },
        ).status_code
        == 200
    )
    book = load_workbook(
        BytesIO(client.get("/api/mentor-groups/templates/mentors").content)
    )
    book.active.append(["SYN-EXCEL-1", "Synthetic", "Example", "Math"])
    stream = BytesIO()
    book.save(stream)

    def preview():
        return client.post(
            "/api/mentor-groups/import/mentors",
            headers=headers,
            data={"source_department": "Synthetic"},
            files={"file": ("synthetic.xlsx", stream.getvalue())},
        )

    batch = preview()
    assert batch.status_code == 200, batch.text
    assert batch.json()["row_count"] == 1
    assert client.get("/api/mentor-groups/directory/mentors").json() == []
    confirmed = client.post(
        f"/api/mentor-groups/previews/{batch.json()['id']}/confirm", headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    row = client.get("/api/mentor-groups/directory/mentors").json()[0]
    assert row["mentor_number"] == "SYN-EXCEL-1"
    assert (
        client.post(
            f"/api/mentor-groups/previews/{batch.json()['id']}/confirm", headers=headers
        ).status_code
        == 409
    )
    assert preview().status_code == 409
    body = {
        "number": row["mentor_number"],
        "name": "Corrected synthetic",
        "college": "Example",
        "major": "Math",
        "expected_version": row["version"],
        "reason": "Synthetic correction",
    }
    assert (
        client.put(
            f"/api/mentor-groups/directory/mentors/{row['id']}",
            headers=headers,
            json=body,
        ).json()["version"]
        == 2
    )
    assert (
        client.put(
            f"/api/mentor-groups/directory/mentors/{row['id']}",
            headers=headers,
            json=body,
        ).status_code
        == 409
    )
