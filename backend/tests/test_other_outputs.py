from io import BytesIO

from openpyxl import load_workbook
from test_accounts import client, login_admin  # noqa: F401


def test_patent_template_has_application_number(client):  # noqa: F811
    login_admin(client)
    response = client.get("/api/patents/template")
    assert response.status_code == 200
    rows = list(load_workbook(BytesIO(response.content)).active.values)
    assert rows[0][:3] == ("AQP-PGS", "patents", "1")
    assert rows[1][0] == "申请号"


def test_patents_complete_lifecycle(client):  # noqa: F811
    from io import BytesIO
    from uuid import uuid4

    from openpyxl import load_workbook

    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {
                    "category": "patents",
                    "operation": op,
                    "college": "合成学院",
                    "major": "合成专业",
                }
                for op in ["maintain", "view", "identity", "void"]
            ],
        },
    )
    assert response.status_code == 200
    wb = load_workbook(BytesIO(client.get("/api/patents/template").content))
    wb.active.append(
        [
            "10.1234/demo",
            "合成科研论文",
            "001",
            "合成人员",
            1,
            "第一作者",
            "合成学院",
            "合成专业",
            "发明",
            "2026-01-01",
        ]
    )
    stream = BytesIO()
    wb.save(stream)

    def preview():
        response = client.post(
            "/api/patents/preview",
            headers=headers,
            data={"source_department": "合成科研处"},
            files={"file": ("synthetic.xlsx", stream.getvalue())},
        )
        assert response.status_code == 200, response.text
        return response.json()

    batch = preview()
    assert batch["items"][0]["status"] == "new"
    assert (
        client.post(
            f"/api/patents/previews/{batch['id']}/confirm",
            headers=headers,
            json={"accept_changes": False},
        ).status_code
        == 200
    )
    result = client.get("/api/patents").json()
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["participants"][0]["association"] == "pending"
    assert preview()["items"][0]["status"] == "duplicate"
    wb.active["B3"] = "合成科研论文更正"
    stream = BytesIO()
    wb.save(stream)
    change = preview()
    assert change["items"][0]["status"] == "change"
    url = f"/api/patents/previews/{change['id']}/confirm"
    assert (
        client.post(url, headers=headers, json={"accept_changes": False}).status_code
        == 409
    )
    assert (
        client.post(url, headers=headers, json={"accept_changes": True}).status_code
        == 200
    )
    result = client.get("/api/patents").json()
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["version"] == 2
    assert result["items"][0]["title"] == "合成科研论文更正"
    output_id = result["items"][0]["id"]
    void_url = f"/api/patents/{output_id}/void"
    assert (
        client.post(
            void_url,
            headers=headers,
            json={"expected_version": 1, "reason": "重复登记"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            void_url,
            headers=headers,
            json={"expected_version": 2, "reason": "重复登记"},
        ).status_code
        == 200
    )
    assert client.get("/api/patents").json()["distinct_outputs"] == 0
    history = client.get(f"/api/patents/{output_id}/history").json()["items"]
    assert len(history) == 3
    assert history[-1]["payload"]["void_reason"] == "重复登记"
    assert history[0]["payload"]["title"] == "合成科研论文"
    archived = client.get("/api/patents?voided=true").json()
    assert len(archived["items"]) == 1
    assert archived["distinct_outputs"] == 0
    retry = client.post(
        "/api/patents/preview",
        headers=headers,
        data={"source_department": "合成科研处"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert retry.status_code == 409
    assert "作废历史" in retry.json()["detail"]
    # A newly linked student in another college immediately revokes visibility;
    # the submitted participant scope cannot override the live student archive.
    from test_students import workbook

    user = client.get("/api/me").json()["user"]
    grants = client.get("/api/access/grants").json()
    grants.append(
        {
            "category": "basic",
            "operation": "maintain",
            "college": "示例学院",
            "major": "计算机",
        }
    )
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
    basic = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成档案"},
        files={"file": ("synthetic.xlsx", workbook())},
    )
    assert basic.status_code == 200
    assert (
        client.post(
            f"/api/imports/{basic.json()['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    assert client.get("/api/patents").json()["distinct_outputs"] == 0
    spoof = client.post(
        "/api/patents/preview",
        headers=headers,
        data={"source_department": "合成科研处"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert spoof.status_code == 409


def test_awards_complete_lifecycle(client):  # noqa: F811
    from io import BytesIO
    from uuid import uuid4

    from openpyxl import load_workbook

    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {
                    "category": "awards",
                    "operation": op,
                    "college": "合成学院",
                    "major": "合成专业",
                }
                for op in ["maintain", "view", "identity", "void"]
            ],
        },
    )
    assert response.status_code == 200
    wb = load_workbook(BytesIO(client.get("/api/awards/template").content))
    wb.active.append(
        [
            "10.1234/demo",
            "合成科研论文",
            "001",
            "合成人员",
            1,
            "第一作者",
            "合成学院",
            "合成专业",
            "一等奖",
            "2026",
        ]
    )
    stream = BytesIO()
    wb.save(stream)

    def preview():
        response = client.post(
            "/api/awards/preview",
            headers=headers,
            data={"source_department": "合成科研处"},
            files={"file": ("synthetic.xlsx", stream.getvalue())},
        )
        assert response.status_code == 200, response.text
        return response.json()

    batch = preview()
    assert batch["items"][0]["status"] == "new"
    assert (
        client.post(
            f"/api/awards/previews/{batch['id']}/confirm",
            headers=headers,
            json={"accept_changes": False},
        ).status_code
        == 200
    )
    result = client.get("/api/awards").json()
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["participants"][0]["association"] == "pending"
    assert preview()["items"][0]["status"] == "duplicate"
    wb.active["B3"] = "合成科研论文更正"
    stream = BytesIO()
    wb.save(stream)
    change = preview()
    assert change["items"][0]["status"] == "change"
    url = f"/api/awards/previews/{change['id']}/confirm"
    assert (
        client.post(url, headers=headers, json={"accept_changes": False}).status_code
        == 409
    )
    assert (
        client.post(url, headers=headers, json={"accept_changes": True}).status_code
        == 200
    )
    result = client.get("/api/awards").json()
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["version"] == 2
    assert result["items"][0]["title"] == "合成科研论文更正"
    output_id = result["items"][0]["id"]
    void_url = f"/api/awards/{output_id}/void"
    assert (
        client.post(
            void_url,
            headers=headers,
            json={"expected_version": 1, "reason": "重复登记"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            void_url,
            headers=headers,
            json={"expected_version": 2, "reason": "重复登记"},
        ).status_code
        == 200
    )
    assert client.get("/api/awards").json()["distinct_outputs"] == 0
    history = client.get(f"/api/awards/{output_id}/history").json()["items"]
    assert len(history) == 3
    assert history[-1]["payload"]["void_reason"] == "重复登记"
    assert history[0]["payload"]["title"] == "合成科研论文"
    archived = client.get("/api/awards?voided=true").json()
    assert len(archived["items"]) == 1
    assert archived["distinct_outputs"] == 0
    retry = client.post(
        "/api/awards/preview",
        headers=headers,
        data={"source_department": "合成科研处"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert retry.status_code == 409
    assert "作废历史" in retry.json()["detail"]
    # A newly linked student in another college immediately revokes visibility;
    # the submitted participant scope cannot override the live student archive.
    from test_students import workbook

    user = client.get("/api/me").json()["user"]
    grants = client.get("/api/access/grants").json()
    grants.append(
        {
            "category": "basic",
            "operation": "maintain",
            "college": "示例学院",
            "major": "计算机",
        }
    )
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
    basic = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成档案"},
        files={"file": ("synthetic.xlsx", workbook())},
    )
    assert basic.status_code == 200
    assert (
        client.post(
            f"/api/imports/{basic.json()['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    assert client.get("/api/awards").json()["distinct_outputs"] == 0
    spoof = client.post(
        "/api/awards/preview",
        headers=headers,
        data={"source_department": "合成科研处"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert spoof.status_code == 409


def test_conferences_complete_lifecycle(client):  # noqa: F811
    from io import BytesIO
    from uuid import uuid4

    from openpyxl import load_workbook

    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {
                    "category": "conferences",
                    "operation": op,
                    "college": "合成学院",
                    "major": "合成专业",
                }
                for op in ["maintain", "view", "identity", "void"]
            ],
        },
    )
    assert response.status_code == 200
    wb = load_workbook(BytesIO(client.get("/api/conferences/template").content))
    wb.active.append(
        [
            "10.1234/demo",
            "合成科研论文",
            "001",
            "合成人员",
            1,
            "第一作者",
            "合成学院",
            "合成专业",
            "口头报告",
            "2026-01-01",
        ]
    )
    stream = BytesIO()
    wb.save(stream)

    def preview():
        response = client.post(
            "/api/conferences/preview",
            headers=headers,
            data={"source_department": "合成科研处"},
            files={"file": ("synthetic.xlsx", stream.getvalue())},
        )
        assert response.status_code == 200, response.text
        return response.json()

    batch = preview()
    assert batch["items"][0]["status"] == "new"
    assert (
        client.post(
            f"/api/conferences/previews/{batch['id']}/confirm",
            headers=headers,
            json={"accept_changes": False},
        ).status_code
        == 200
    )
    result = client.get("/api/conferences").json()
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["participants"][0]["association"] == "pending"
    assert preview()["items"][0]["status"] == "duplicate"
    wb.active["B3"] = "合成科研论文更正"
    stream = BytesIO()
    wb.save(stream)
    change = preview()
    assert change["items"][0]["status"] == "change"
    url = f"/api/conferences/previews/{change['id']}/confirm"
    assert (
        client.post(url, headers=headers, json={"accept_changes": False}).status_code
        == 409
    )
    assert (
        client.post(url, headers=headers, json={"accept_changes": True}).status_code
        == 200
    )
    result = client.get("/api/conferences").json()
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["version"] == 2
    assert result["items"][0]["title"] == "合成科研论文更正"
    output_id = result["items"][0]["id"]
    void_url = f"/api/conferences/{output_id}/void"
    assert (
        client.post(
            void_url,
            headers=headers,
            json={"expected_version": 1, "reason": "重复登记"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            void_url,
            headers=headers,
            json={"expected_version": 2, "reason": "重复登记"},
        ).status_code
        == 200
    )
    assert client.get("/api/conferences").json()["distinct_outputs"] == 0
    history = client.get(f"/api/conferences/{output_id}/history").json()["items"]
    assert len(history) == 3
    assert history[-1]["payload"]["void_reason"] == "重复登记"
    assert history[0]["payload"]["title"] == "合成科研论文"
    archived = client.get("/api/conferences?voided=true").json()
    assert len(archived["items"]) == 1
    assert archived["distinct_outputs"] == 0
    retry = client.post(
        "/api/conferences/preview",
        headers=headers,
        data={"source_department": "合成科研处"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert retry.status_code == 409
    assert "作废历史" in retry.json()["detail"]
    # A newly linked student in another college immediately revokes visibility;
    # the submitted participant scope cannot override the live student archive.
    from test_students import workbook

    user = client.get("/api/me").json()["user"]
    grants = client.get("/api/access/grants").json()
    grants.append(
        {
            "category": "basic",
            "operation": "maintain",
            "college": "示例学院",
            "major": "计算机",
        }
    )
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
    basic = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成档案"},
        files={"file": ("synthetic.xlsx", workbook())},
    )
    assert basic.status_code == 200
    assert (
        client.post(
            f"/api/imports/{basic.json()['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    assert client.get("/api/conferences").json()["distinct_outputs"] == 0
    spoof = client.post(
        "/api/conferences/preview",
        headers=headers,
        data={"source_department": "合成科研处"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert spoof.status_code == 409
