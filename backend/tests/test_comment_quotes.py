# ruff: noqa: F811
from test_accounts import client  # noqa: F401


def quoted_reviews(client):
    """Two blind reviews on one synthetic paper; caller decides the grants."""
    from uuid import uuid4

    from test_accounts import login_admin
    from test_attachments import pdf, setup_record

    headers = login_admin(client)
    setup_record(client, headers)
    user = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {"category": "papers", "operation": op, "college": "示例学院", "major": "计算机"}
                for op in ["maintain", "view", "identity"]
            ]
            + [
                {"category": "blind_reviews", "operation": op, "college": "示例学院", "major": "计算机"}
                for op in ["maintain", "view", "download"]
            ],
        },
    )
    assert response.status_code == 200, response.text
    paper = client.post(
        "/api/papers",
        headers=headers,
        data={
            "student_id": 1,
            "title": "合成论文",
            "expected_version": 0,
            "covered_student_ids": "[1]",
        },
        files={"file": ("synthetic.pdf", pdf())},
    )
    assert paper.status_code == 200, paper.text
    ids = []
    for code, comment in (
        ("R01", "论文创新性较强。写作规范有待改进。参考文献偏少。"),
        ("R02", "研究方法存在不足。\n建议补充对比实验。"),
    ):
        created = client.post(
            "/api/external-assessments",
            headers=headers,
            json={
                "category": "blind_reviews",
                "paper_version_id": paper.json()["id"],
                "batch": "模拟2026",
                "anonymous_code": code,
                "scores": {"quality": 85},
                "comment": comment,
                "source": "模拟来源",
            },
        )
        assert created.status_code == 200, created.text
        ids.append(created.json()["id"])
    return headers, paper.json()["id"], ids


def regrant(client, headers, operations):
    from uuid import uuid4

    user = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {"category": "papers", "operation": op, "college": "示例学院", "major": "计算机"}
                for op in ["maintain", "view", "identity"]
            ]
            + [
                {"category": "blind_reviews", "operation": op, "college": "示例学院", "major": "计算机"}
                for op in operations
            ],
        },
    )
    assert response.status_code == 200, response.text


def test_keyword_quotes_return_matching_sentences_with_review_references(client):
    _, paper_id, ids = quoted_reviews(client)
    response = client.get(
        "/api/external-assessments/keywords",
        params={"terms": "创新,不足,未出现的词", "quotes": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {"创新": 1, "不足": 1, "未出现的词": 0}
    assert body["scanned"] == 2 and body["skipped"] == 0
    assert body["quotes"] == [
        {"word": "创新", "review_id": ids[0], "paper_version_id": paper_id, "quote": "论文创新性较强。"},
        {"word": "不足", "review_id": ids[1], "paper_version_id": paper_id, "quote": "研究方法存在不足。"},
    ]
    # 没有命中的句子和未命中的词都不出现
    assert "写作规范" not in response.text and "对比实验" not in response.text


def test_keyword_quotes_off_by_default_and_count_one_sentence_per_word(client):
    _, _, ids = quoted_reviews(client)
    plain = client.get("/api/external-assessments/keywords", params={"terms": "创新"}).json()
    assert "quotes" not in plain
    both = client.get(
        "/api/external-assessments/keywords", params={"terms": "创新,较强", "quotes": True}
    ).json()
    # 同一句命中两个词时按词各返回一条
    assert [item["word"] for item in both["quotes"]] == ["创新", "较强"]
    assert {item["quote"] for item in both["quotes"]} == {"论文创新性较强。"}
    assert {item["review_id"] for item in both["quotes"]} == {ids[0]}


def test_keyword_quotes_need_download_grant_and_never_leak_text(client):
    headers, _, _ = quoted_reviews(client)
    regrant(client, headers, ["maintain", "view"])
    response = client.get(
        "/api/external-assessments/keywords", params={"terms": "创新,不足", "quotes": True}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["quotes"] == []
    assert body["scanned"] == 0 and body["skipped"] == 2
    assert body["counts"] == {"创新": 0, "不足": 0}
    assert "创新性较强" not in response.text and "建议补充" not in response.text


def test_keyword_quotes_truncate_long_sentences(client):
    from uuid import uuid4

    from test_accounts import login_admin
    from test_attachments import pdf, setup_record

    headers = login_admin(client)
    setup_record(client, headers)
    user = client.get("/api/me").json()["user"]
    assert client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {"category": "papers", "operation": op, "college": "示例学院", "major": "计算机"}
                for op in ["maintain", "view", "identity"]
            ]
            + [
                {"category": "blind_reviews", "operation": op, "college": "示例学院", "major": "计算机"}
                for op in ["maintain", "view", "download"]
            ],
        },
    ).status_code == 200
    paper = client.post(
        "/api/papers",
        headers=headers,
        data={"student_id": 1, "title": "合成论文", "expected_version": 0, "covered_student_ids": "[1]"},
        files={"file": ("synthetic.pdf", pdf())},
    ).json()
    for index in range(3):
        created = client.post(
            "/api/external-assessments",
            headers=headers,
            json={
                "category": "blind_reviews",
                "paper_version_id": paper["id"],
                "batch": "模拟2026",
                "anonymous_code": f"L{index}",
                "scores": {"quality": 85},
                "comment": "命中" + "长" * 700 + "。后面这句不含关键词。",
                "source": "模拟来源",
            },
        )
        assert created.status_code == 200, created.text
    body = client.get(
        "/api/external-assessments/keywords", params={"terms": "命中", "quotes": True}
    ).json()
    # 每条评语每个词只返回首个命中句；过长的句子截断到 500 字
    assert len(body["quotes"]) == 3
    assert all(len(item["quote"]) == 500 and item["quote"].startswith("命中长长") for item in body["quotes"])


def test_keyword_quote_list_is_capped(client, monkeypatch):
    from aqp import external_assessments

    quoted_reviews(client)
    monkeypatch.setattr(external_assessments, "QUOTE_LIMIT", 1)
    body = client.get(
        "/api/external-assessments/keywords", params={"terms": "创新,不足", "quotes": True}
    ).json()
    assert len(body["quotes"]) == 1
    assert body["quotes_truncated"] is True
    assert body["counts"] == {"创新": 1, "不足": 1}, "上限只限制原句列表，不影响计数"


def test_keyword_quotes_follow_paper_scope_filter(client):
    _, paper_id, _ = quoted_reviews(client)
    body = client.get(
        "/api/external-assessments/keywords",
        params={"terms": "创新,不足", "quotes": True, "paper_version_id": paper_id},
    ).json()
    assert {item["review_id"] for item in body["quotes"]} and body["quotes"]
    elsewhere = client.get(
        "/api/external-assessments/keywords",
        params={"terms": "创新,不足", "quotes": True, "paper_version_id": -1},
    ).json()
    assert elsewhere["quotes"] == []
