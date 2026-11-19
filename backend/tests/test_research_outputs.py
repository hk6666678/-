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
    assert list(ws.values)[1][9:] == (
        "评价体系", "评价年度", "期刊分区", "影响因子"
    )
    patent_template = client.get("/api/patents/template")
    patent_sheet = load_workbook(BytesIO(patent_template.content)).active
    assert list(patent_sheet.values)[1][10:] == ("转化状态", "转化日期")


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
                for op in ["maintain", "view", "identity", "void", "analyze"]
            ]
            + [
                {
                    "category": "basic",
                    "operation": op,
                    "college": "合成学院",
                    "major": "合成专业",
                }
                for op in ["maintain", "view", "analyze"]
            ]
            + [
                {
                    "category": "topic",
                    "operation": op,
                    "college": "合成学院",
                    "major": "合成专业",
                }
                for op in ["maintain", "view", "analyze"]
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
    wb.active["I3"] = "20x5"
    stream = BytesIO()
    wb.save(stream)
    assert (
        client.post(
            "/api/research-outputs/preview",
            headers=headers,
            data={"source_department": "Synthetic"},
            files={"file": ("invalid.xlsx", stream.getvalue())},
        ).status_code
        == 422
    )
    wb.active["I3"] = 2025
    wb.active["J3"] = "合成期刊评价体系"
    wb.active["K3"] = 2024
    wb.active["L3"] = "Q2"
    wb.active["M3"] = 0
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
    assert result["items"][0]["details"] == {
        "发表年份": "2025",
        "评价体系": "合成期刊评价体系",
        "评价年度": "2024",
        "期刊分区": "Q2",
        "影响因子": "0",
    }
    wb.active.delete_cols(10, 4)
    stream = BytesIO()
    wb.save(stream)
    assert preview()["items"][0]["status"] == "duplicate"
    assert client.get("/api/research-outputs/statistics").json()["years"] == [
        {"year": "2025", "distinct_outputs": 1, "personal_participations": 1}
    ]
    assert result["items"][0]["title"] == "合成科研论文更正"
    assert client.get("/api/research-outputs/cohort").json() == {"items": []}
    from openpyxl import Workbook

    basic = Workbook()
    basic.active.append(["AQP-PGS", "basic", "1"])
    basic.active.append(["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"])
    basic.active.append(["001", "合成人员", "合成学院", "合成专业", "硕士", 2024])
    basic.active.append(["002", "合成同届", "合成学院", "合成专业", "硕士", 2024])
    basic_stream = BytesIO()
    basic.save(basic_stream)
    submitted = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("basic.xlsx", basic_stream.getvalue())},
    )
    assert submitted.status_code == 200, submitted.text
    assert (
        client.post(
            f"/api/imports/{submitted.json()['id']}/confirm", headers=headers
        ).status_code
        == 200
    )
    cohort = client.get("/api/research-outputs/cohort").json()["items"]
    assert len(cohort) == 2
    assert all(
        row["entry_year"] == 2024 and "student_number" not in row for row in cohort
    )
    assert sorted(len(row["outputs"]) for row in cohort) == [0, 1]
    output = next(row["outputs"][0] for row in cohort if row["outputs"])
    assert (output["date"], output["topic"], output["midterm"]) == (
        "2025",
        "无法比较",
        "无法比较",
    )
    topic = load_workbook(
        BytesIO(client.get("/api/templates/milestones/topic").content)
    )
    columns = [cell.value for cell in topic.active[2]]
    values = {
        "学号": "001",
        "姓名": "合成人员",
        "所属学院": "合成学院",
        "专业": "合成专业",
        "考核批次": "模拟选题",
        "选题标题": "合成题目",
        "评分制度": "百分制",
        "原始成绩": 85,
        "实际日期": "2025-04-01",
    }
    topic.active.append([values.get(column) for column in columns])
    topic_stream = BytesIO()
    topic.save(topic_stream)
    topic_preview = client.post(
        "/api/milestones/topic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("topic.xlsx", topic_stream.getvalue())},
    )
    assert topic_preview.status_code == 200, topic_preview.text
    assert (
        client.post(
            f"/api/milestone-imports/{topic_preview.json()['id']}/confirm",
            headers=headers,
        ).status_code
        == 200
    )
    rows = client.get("/api/research-outputs/cohort").json()["items"]
    assert (
        next(row["outputs"][0]["topic"] for row in rows if row["outputs"])
        == "同年（先后未知）"
    )
    correlation_url = "/api/analyses/topic-correlation"
    correlation_params = {
        "college": "合成学院",
        "major": "合成专业",
        "entry_year": 2024,
        "category": "research_papers",
    }
    correlation = client.get(correlation_url, params=correlation_params)
    assert correlation.status_code == 200, correlation.text
    correlation_result = correlation.json()
    assert correlation_result["cohort_count"] == 2
    assert correlation_result["excluded"] == {"缺少有效选题实际日期": 1}
    assert correlation_result["uncertain_participations"] == 1
    assert correlation_result["pearson_r"] is None
    assert len(correlation_result["points"]) == 1
    assert correlation_result["points"][0]["score"] == 85
    assert correlation_result["points"][0]["output_count"] == 0
    assert (
        client.get(
            correlation_url, params={**correlation_params, "category": "patents"}
        ).status_code
        == 403
    )
    output_id = result["items"][0]["id"]
    citation_template = client.get("/api/research-outputs/citations/template")
    assert citation_template.status_code == 200
    citation_wb = load_workbook(BytesIO(citation_template.content))
    citation_wb.active.append(["10.1234/demo", "2024-01-01", 2, "Synthetic source"])
    citation_stream = BytesIO()
    citation_wb.save(citation_stream)
    citation_preview = client.post(
        "/api/research-outputs/citations/preview",
        headers=headers,
        files={"file": ("citations.xlsx", citation_stream.getvalue())},
    )
    assert citation_preview.status_code == 200, citation_preview.text
    assert citation_preview.json()["errors"] == []
    batch_id = citation_preview.json()["id"]
    assert (
        client.post(
            f"/api/research-outputs/citations/previews/{batch_id}/confirm",
            headers=headers,
            json={"accept_changes": False},
        ).status_code
        == 200
    )
    citation_url = f"/api/research-outputs/{output_id}/citations"
    snapshot = {"date": "2025-01-02", "count": 7, "source_department": "科研处"}
    assert client.post(citation_url, headers=headers, json=snapshot).status_code == 200
    assert (
        client.post(citation_url, headers=headers, json=snapshot).json()["status"]
        == "duplicate"
    )
    assert (
        client.post(
            citation_url, headers=headers, json={**snapshot, "count": -1}
        ).status_code
        == 422
    )
    assert (
        client.post(
            citation_url, headers=headers, json={**snapshot, "count": 3}
        ).status_code
        == 409
    )
    for invalid in [
        {**snapshot, "date": "20260101"},
        {**snapshot, "date": "2026-02-30"},
        {**snapshot, "count": True},
        {**snapshot, "count": 1.5},
    ]:
        assert (
            client.post(citation_url, headers=headers, json=invalid).status_code == 422
        )
    correction = {
        **snapshot,
        "count": 3,
        "expected_version": 1,
        "confirmed": True,
        "reason": "来源更正",
    }
    assert (
        client.post(citation_url, headers=headers, json=correction).status_code == 200
    )
    history = client.get(citation_url).json()["items"]
    assert [(item["version"], item["count"]) for item in history] == [
        (1, 2),
        (1, 7),
        (2, 3),
    ]
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
    citation_url = "/api/research-outputs/1/citations"
    snapshot = {
        "date": "2025-01-01",
        "count": 4,
        "source_department": "Synthetic1 source",
    }
    assert client.post(citation_url, headers=headers, json=snapshot).status_code == 200
    assert client.get(citation_url).json()["data_version"] == 1
    # Correcting the student's name must not make the old revision unmaintainable.
    from io import BytesIO

    from openpyxl import load_workbook

    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("UPDATE students SET name='Corrected' WHERE id=1")
    wb = load_workbook(BytesIO(client.get("/api/research-outputs/template").content))
    for index, college, name in [(1, "A", "Corrected"), (2, "B", "Synthetic2")]:
        wb.active.append(
            [
                "shared",
                "Synthetic shared",
                str(index),
                name,
                index,
                "author",
                college,
                "Math",
            ]
        )
    stream = BytesIO()
    wb.save(stream)
    corrected = client.post(
        "/api/research-outputs/preview",
        headers=headers,
        data={"source_department": "Synthetic"},
        files={"file": ("synthetic.xlsx", stream.getvalue())},
    )
    assert corrected.status_code == 200
    assert corrected.json()["items"][0]["status"] == "change"
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("UPDATE students SET name='Synthetic1' WHERE id=1")
    assert (
        client.post(
            "/api/research-outputs/1/void",
            headers=headers,
            json={"expected_version": 1, "reason": "Synthetic"},
        ).status_code
        == 403
    )
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
    redacted = client.get(citation_url).json()["items"][0]
    assert "source_department" not in redacted
    assert "reason" not in redacted
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("DELETE FROM user_student_bindings WHERE user_id=?", (actor,))
    assert client.get("/api/research-outputs").json()["distinct_outputs"] == 0
    assert client.get(citation_url).status_code == 404
    assert client.post(citation_url, headers=headers, json=snapshot).status_code == 403


def test_void_intersects_current_student_scope(client, tmp_path):  # noqa: F811
    import json

    from aqp.store import connection

    headers = login_admin(client)
    actor = client.get("/api/me").json()["user"]["id"]
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "INSERT INTO students(research_id,student_number,name,college,major,level,entry_year,payload) VALUES ('r','1','Synthetic','Current','Math','master',2025,'{}')"
        )
        payload = json.dumps(
            {
                "title": "Synthetic",
                "participants": [
                    {
                        "student_number": "1",
                        "name": "Synthetic",
                        "college": "Old",
                        "major": "Math",
                        "order": 1,
                        "role": "author",
                    }
                ],
            }
        )
        db.execute(
            "INSERT INTO research_outputs(id,business_key,payload) VALUES (1,'key',?)",
            (payload,),
        )
        db.execute(
            "INSERT INTO research_output_versions VALUES (1,1,?,'Synthetic',?)",
            (payload, actor),
        )
        for college, operation in [
            ("Old", "maintain"),
            ("Current", "maintain"),
            ("Old", "void"),
        ]:
            db.execute(
                "INSERT INTO grants VALUES (?,?,?,?,?)",
                (actor, "research_papers", operation, college, "Math"),
            )
    body = {"expected_version": 1, "reason": "Synthetic correction"}
    assert (
        client.post(
            "/api/research-outputs/1/void", headers=headers, json=body
        ).status_code
        == 403
    )
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "INSERT INTO grants VALUES (?,?,?,?,?)",
            (actor, "research_papers", "void", "Current", "Math"),
        )
    assert (
        client.post(
            "/api/research-outputs/1/void", headers=headers, json=body
        ).status_code
        == 200
    )


def test_citation_batch_revoked_second_row_rolls_back(client, tmp_path):  # noqa: F811
    import json
    from io import BytesIO

    from aqp.store import connection
    from openpyxl import load_workbook

    headers = login_admin(client)
    actor = client.get("/api/me").json()["user"]["id"]
    with connection(tmp_path / "accounts.sqlite3") as db:
        for index, college in [(1, "A"), (2, "B")]:
            for op in ["maintain", "view"]:
                db.execute(
                    "INSERT INTO grants VALUES (?,?,?,?,?)",
                    (actor, "research_papers", op, college, "Math"),
                )
            payload = json.dumps(
                {
                    "title": "Synthetic",
                    "participants": [
                        {
                            "student_number": str(index),
                            "name": "Synthetic",
                            "college": college,
                            "major": "Math",
                            "order": 1,
                            "role": "author",
                        }
                    ],
                }
            )
            db.execute(
                "INSERT INTO research_outputs(id,business_key,payload) VALUES (?,?,?)",
                (index, str(index), payload),
            )
    wb = load_workbook(
        BytesIO(client.get("/api/research-outputs/citations/template").content)
    )
    for index in [1, 2]:
        wb.active.append([str(index), "2025-01-01", 3, "Synthetic source"])
    stream = BytesIO()
    wb.save(stream)
    batch = client.post(
        "/api/research-outputs/citations/preview",
        headers=headers,
        files={"file": ("c.xlsx", stream.getvalue())},
    ).json()
    assert batch["errors"] == []
    assert client.get("/api/research-outputs/1/citations").json()["items"] == []
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "DELETE FROM grants WHERE user_id=? AND category='research_papers' AND operation='maintain' AND college='B'",
            (actor,),
        )
    response = client.post(
        f"/api/research-outputs/citations/previews/{batch['id']}/confirm",
        headers=headers,
        json={"accept_changes": False},
    )
    assert response.status_code == 403
    for index in [1, 2]:
        assert (
            client.get(f"/api/research-outputs/{index}/citations").json()["items"] == []
        )
    stats = client.get("/api/research-outputs/statistics").json()
    assert stats["years"] == [
        {"year": "年份缺失", "distinct_outputs": 2, "personal_participations": 2}
    ]
    assert stats["missing_citations"] == 2
    assert client.get("/api/patents/citations/template").status_code == 404
