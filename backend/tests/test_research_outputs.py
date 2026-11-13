from test_accounts import client, login_admin  # noqa: F401


def test_research_outputs_require_explicit_access(client):  # noqa: F811
    login_admin(client)
    response = client.get("/api/research-outputs")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "personal_participations": 0,
        "distinct_outputs": 0,
    }


def test_research_template_available_to_authenticated_user(client):  # noqa: F811
    login_admin(client)
    response = client.get("/api/research-outputs/template")
    assert response.status_code == 200
    from io import BytesIO

    from openpyxl import load_workbook

    ws = load_workbook(BytesIO(response.content)).active
    assert next(iter(ws.values))[:3] == ("AQP-PGS", "research_papers", "1")


def test_shared_output_preview_confirm_pending_and_duplicate(client):  # noqa: F811
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
                    "category": "research_papers",
                    "operation": op,
                    "college": "合成学院",
                    "major": "合成专业",
                }
                for op in ["maintain", "view", "identity"]
            ],
        },
    )
    assert response.status_code == 200
    wb = load_workbook(BytesIO(client.get("/api/research-outputs/template").content))
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
        ]
    )
    stream = BytesIO()
    wb.save(stream)

    def preview():
        response = client.post(
            "/api/research-outputs/preview",
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
            f"/api/research-outputs/previews/{batch['id']}/confirm",
            headers=headers,
            json={"accept_changes": False},
        ).status_code
        == 200
    )
    result = client.get("/api/research-outputs").json()
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["participants"][0]["association"] == "pending"
    assert preview()["items"][0]["status"] == "duplicate"
    wb.active["B3"] = "合成科研论文更正"
    stream = BytesIO()
    wb.save(stream)
    change = preview()
    assert change["items"][0]["status"] == "change"
    url = f"/api/research-outputs/previews/{change['id']}/confirm"
    assert (
        client.post(url, headers=headers, json={"accept_changes": False}).status_code
        == 409
    )
    assert (
        client.post(url, headers=headers, json={"accept_changes": True}).status_code
        == 200
    )
    result = client.get("/api/research-outputs").json()
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["version"] == 2
    assert result["items"][0]["title"] == "合成科研论文更正"
    output_id = result["items"][0]["id"]
    void_url = f"/api/research-outputs/{output_id}/void"
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
    assert client.get("/api/research-outputs").json()["distinct_outputs"] == 0
    history = client.get(f"/api/research-outputs/{output_id}/history").json()["items"]
    assert len(history) == 3
    assert history[-1]["payload"]["void_reason"] == "重复登记"
    assert history[0]["payload"]["title"] == "合成科研论文"
    archived = client.get("/api/research-outputs?voided=true").json()
    assert len(archived["items"]) == 1
    assert archived["distinct_outputs"] == 0
    retry = client.post(
        "/api/research-outputs/preview",
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
    assert client.get("/api/research-outputs").json()["distinct_outputs"] == 0
    spoof = client.post(
        "/api/research-outputs/preview",
        headers=headers,
        data={"source_department": "合成科研处"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert spoof.status_code == 409


def test_change_cannot_remove_out_of_scope_existing_participant(client, tmp_path):  # noqa: F811
    import json
    from io import BytesIO

    from aqp.store import connection
    from openpyxl import load_workbook

    headers = login_admin(client)
    with connection(tmp_path / "accounts.sqlite3") as db:
        actor = db.execute("SELECT id FROM users").fetchone()[0]
        db.execute(
            "INSERT INTO grants VALUES (?,?,?,?,?)",
            (actor, "research_papers", "maintain", "Allowed", "Math"),
        )
        db.execute(
            "INSERT INTO research_outputs(business_key,payload) VALUES (?,?)",
            (
                "shared",
                json.dumps(
                    {
                        "title": "Shared",
                        "participants": [
                            {
                                "student_number": "hidden",
                                "name": "Hidden",
                                "order": 1,
                                "role": "author",
                                "college": "Hidden",
                                "major": "Math",
                            }
                        ],
                    }
                ),
            ),
        )
    wb = load_workbook(BytesIO(client.get("/api/research-outputs/template").content))
    wb.active.append(
        ["shared", "Shared", "allowed", "Allowed", 1, "author", "Allowed", "Math"]
    )
    stream = BytesIO()
    wb.save(stream)
    result = client.post(
        "/api/research-outputs/preview",
        headers=headers,
        data={"source_department": "Synthetic"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert result.status_code == 403


def test_shared_research_mentor_and_scope_matrix(client, tmp_path):  # noqa: F811
    import json

    from aqp.store import connection

    headers = login_admin(client)
    actor = client.get("/api/me").json()["user"]["id"]
    with connection(tmp_path / "accounts.sqlite3") as db:
        participants = []
        for index, college in [(1, "A"), (2, "B")]:
            db.execute(
                "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    index,
                    str(index),
                    str(index),
                    f"Synthetic{index}",
                    college,
                    "Math",
                    "master",
                    2025,
                    "{}",
                ),
            )
            participants.append(
                {
                    "student_number": str(index),
                    "name": f"Synthetic{index}",
                    "college": college,
                    "major": "Math",
                    "order": index,
                    "role": "author",
                }
            )
            for operation in ["view", "identity", "maintain"]:
                db.execute(
                    "INSERT INTO grants VALUES (?,?,?,?,?)",
                    (actor, "research_papers", operation, college, "Math"),
                )
        payload = json.dumps(
            {"title": "Synthetic shared", "participants": participants}
        )
        db.execute(
            "INSERT INTO research_outputs(id,business_key,payload) VALUES (1,'shared',?)",
            (payload,),
        )
        db.execute(
            "INSERT INTO research_output_versions VALUES (1,1,?,?,?)",
            (payload, "Synthetic source", actor),
        )
        db.execute(
            "UPDATE users SET roles=? WHERE id=?",
            (json.dumps(["platform_admin", "mentor"]), actor),
        )
    assert client.get("/api/research-outputs").json()["distinct_outputs"] == 0
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("INSERT INTO user_student_bindings VALUES (?,1)", (actor,))
    result = client.get("/api/research-outputs").json()
    assert result["personal_participations"] == 1
    assert result["distinct_outputs"] == 1
    assert result["items"][0]["participants"][0]["name"] == "Synthetic1"
    assert client.get("/api/research-outputs/1/history").status_code == 403
    assert (
        client.post(
            "/api/research-outputs/1/void",
            headers=headers,
            json={"expected_version": 1, "reason": "Synthetic"},
        ).status_code
        == 403
    )
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("INSERT INTO user_student_bindings VALUES (?,2)", (actor,))
    assert client.get("/api/research-outputs").json()["personal_participations"] == 2
    assert client.get("/api/research-outputs/1/history").status_code == 200
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "DELETE FROM grants WHERE user_id=? AND category='research_papers' AND operation='identity' AND college='B'",
            (actor,),
        )
    assert (
        "name"
        not in client.get("/api/research-outputs").json()["items"][0]["participants"][1]
    )
    assert client.get("/api/research-outputs/1/history").status_code == 403
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("DELETE FROM user_student_bindings WHERE user_id=?", (actor,))
    assert client.get("/api/research-outputs").json()["distinct_outputs"] == 0
