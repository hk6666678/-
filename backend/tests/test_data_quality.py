# ruff: noqa: F811
import json

from test_accounts import client, login_admin  # noqa: F401
from test_mentor_research import (
    SCOPE,
    directory,
    full_grants,
    import_courses,
    import_students,
    import_topic_scores,
    relate,
)

CHECKS = "/api/consistency/checks"


def upload_thesis(client, headers, student_id, title, level="硕士", discipline=SCOPE["major"]):
    from test_attachments import pdf

    response = client.post(
        "/api/papers", headers=headers,
        data={"student_id": student_id, "title": title, "expected_version": 0,
              "covered_student_ids": json.dumps([student_id]),
              "level": level, "discipline": discipline, "year": "2026"},
        files={"file": ("synthetic.pdf", pdf())},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def run_checks(client, **params):
    response = client.get(
        CHECKS, params={"college": SCOPE["college"], "major": SCOPE["major"], **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


def by_code(body):
    return {item["code"]: item for item in body["items"]}


def archive(db_path, student_id, changes):
    from aqp.store import connection

    with connection(db_path) as db:
        row = db.execute("SELECT payload FROM students WHERE id=?", (student_id,)).fetchone()
        db.execute(
            "UPDATE students SET payload=? WHERE id=?",
            (json.dumps({**json.loads(row["payload"]), **changes}, ensure_ascii=False), student_id),
        )


def research_ids(client):
    return {item["id"]: item["research_id"] for item in client.get("/api/students?limit=200").json()["items"]}


def without_identity(client, headers):
    categories = ["basic", "courses", "topic", "midterm", "mentor_groups", "papers"]
    full_grants(
        client, headers,
        without=[(category, "identity") for category in categories],
    )


def test_consistency_checks_report_each_kind_of_mismatch(client, tmp_path):
    db_path = tmp_path / "accounts.sqlite3"
    headers = login_admin(client)
    full_grants(client, headers)
    students = import_students(client, headers, ["A", "B", "C", "D", "OK"])
    import_courses(client, headers, [("A", "C1", 80), ("OK", "C1", 80)])
    import_topic_scores(client, headers, {"A": 80, "OK": 80})
    upload_thesis(client, headers, students["D"], "层次不符的论文", level="博士")
    upload_thesis(client, headers, students["OK"], "正常论文")
    group = directory(client, headers, "groups", "QG-1", "核对课题组")
    mentor = directory(client, headers, "mentors", "QM-1", "王导师")
    relate(client, headers, students["A"], mentor, group, "2024-09-01")
    relate(client, headers, students["OK"], mentor, group, "2024-09-01")

    from aqp.store import connection

    pending = {"学号": "NOSUCH", "姓名": "无档案学生", "所属学院": SCOPE["college"], "专业": SCOPE["major"]}
    with connection(db_path) as db:
        # 课程与选题记录的来源学院、姓名与档案不一致：模拟档案更正后遗留的旧记录
        for table in ("course_records", "milestone_records"):
            row = db.execute(
                f"SELECT id,payload FROM {table} WHERE student_id=? ORDER BY id LIMIT 1",
                (students["A"],),
            ).fetchone()
            db.execute(
                f"UPDATE {table} SET payload=? WHERE id=?",
                (json.dumps({**json.loads(row["payload"]), "所属学院": "更正前学院", "姓名": "旧姓名"}, ensure_ascii=False), row["id"]),
            )
        # 一条尚未关联到正式档案的课程记录
        db.execute(
            "INSERT INTO import_batches(id,category,template_version,source_department,filename,file_hash,original_file,uploaded_by,created_at) VALUES(9000,'courses','1','合成来源','x','x',X'00',1,1)"
        )
        db.execute(
            "INSERT INTO import_rows(id,batch_id,sheet,row_number,raw_json,normalized_json,state) VALUES(9000,9000,'sheet',3,'{}',?,'pending')",
            (json.dumps(pending, ensure_ascii=False),),
        )
        db.execute(
            "INSERT INTO course_records(student_number,course_code,term,attempt,student_id,payload,state,source_row_id) VALUES('NOSUCH','C9','2024秋',1,NULL,?,'pending',9000)",
            (json.dumps(pending, ensure_ascii=False),),
        )
    archive(db_path, students["A"], {"导师姓名": "李导师"})  # 与有效关系里的王导师不符
    archive(db_path, students["B"], {"实际毕业日期": "2023-01-01"})  # 早于 2024 年入学
    archive(db_path, students["C"], {
        "盲审论文提交状态": "已提交", "盲审论文实际提交日期": "",
        "学籍异动类型": "转导师", "学籍异动时间": "",
    })
    archive(db_path, students["D"], {"导师姓名": "赵导师"})  # 登记了导师但没有指导关系
    archive(db_path, students["OK"], {"导师姓名": "王导师", "学籍异动类型": "休学后复学", "学籍异动时间": "2025-02-01"})

    result = by_code(run_checks(client))
    rid = research_ids(client)
    expected = {
        "course_scope": ["A"],
        "milestone_scope": ["A"],
        "record_name": ["A"],
        "thesis_scope": ["D"],
        "thesis_metadata_missing": [],
        "mentor_unlinked": ["D"],
        "mentor_name_mismatch": ["A"],
        "graduation_before_entry": ["B"],
        "blind_review_date": ["C"],
        "mobility_incomplete": ["C"],
    }
    for code, names in expected.items():
        assert [item["research_id"] for item in result[code]["items"]] == [rid[students[name]] for name in names], code
        assert result[code]["count"] == len(names), code
        assert result[code]["status"] == ("found" if names else "ok"), code
    # 同一学生的两条来源记录姓名不符，按学生计一条并写明记录数
    assert "2 条" in result["record_name"]["items"][0]["detail"]
    assert "更正前学院" in result["course_scope"]["items"][0]["detail"]
    assert result["pending_records"]["count"] == 1
    assert result["pending_records"]["courses"] == 1 and result["pending_records"]["topic"] == 0
    assert result["pending_records"]["status"] == "found" and result["pending_records"]["items"] == []
    assert result["pending_records"]["skipped_categories"] == []
    # 没有任何差异的学生不出现在任何检查项里
    assert rid[students["OK"]] not in json.dumps(result, ensure_ascii=False)
    # 明细只给研究编号：学生姓名、学号不出现在响应里
    body_text = json.dumps(result, ensure_ascii=False)
    assert "旧姓名" not in body_text and "无档案学生" not in body_text
    assert '"NOSUCH"' not in body_text


def test_consistency_checks_respect_scope_grants_and_hide_names(client, tmp_path):
    db_path = tmp_path / "accounts.sqlite3"
    headers = login_admin(client)
    full_grants(client, headers)
    students = import_students(client, headers, ["A", "OK"])
    import_courses(client, headers, [("A", "C1", 80), ("OK", "C1", 80)])
    from aqp.store import connection

    with connection(db_path) as db:
        row = db.execute(
            "SELECT id,payload FROM course_records WHERE student_id=?", (students["A"],)
        ).fetchone()
        db.execute(
            "UPDATE course_records SET payload=? WHERE id=?",
            (json.dumps({**json.loads(row["payload"]), "所属学院": "更正前学院", "姓名": "旧姓名"}, ensure_ascii=False), row["id"]),
        )
    archive(db_path, students["A"], {"导师姓名": "李导师"})
    rid = research_ids(client)

    params = {"college": SCOPE["college"], "major": SCOPE["major"]}
    # 与学院报告一致：需要该范围基础档案的查看和分析权限
    assert client.get(CHECKS, params={**params, "major": "别的专业"}).status_code == 403
    assert client.get(CHECKS, params={**params, "college": "别的学院"}).status_code == 403
    full_grants(client, headers, without=[("basic", "analyze")])
    assert client.get(CHECKS, params=params).status_code == 403
    full_grants(client, headers)

    # 撤掉课程查看权限：依赖它的检查标注未核对并说明原因，其余照常
    full_grants(client, headers, without=[("courses", "view")])
    result = by_code(run_checks(client))
    assert result["course_scope"]["status"] == "skipped" and "课程" in result["course_scope"]["reason"]
    assert result["course_scope"]["count"] is None and result["course_scope"]["items"] == []
    assert result["record_name"]["count"] == 0  # A 的课程记录不可见，其余记录姓名一致
    assert result["mentor_unlinked"]["count"] == 1
    assert [item["research_id"] for item in result["mentor_unlinked"]["items"]] == [rid[students["A"]]]
    pending = result["pending_records"]
    assert pending["status"] == "partial" and pending["courses"] is None
    assert pending["skipped_categories"] == ["courses"]

    # 撤掉身份权限：凡是需要比对姓名的检查都标注未核对
    full_grants(client, headers)
    without_identity(client, headers)
    result = by_code(run_checks(client))
    assert result["record_name"]["status"] == "skipped" and "身份" in result["record_name"]["reason"]
    assert result["mentor_name_mismatch"]["status"] == "skipped"
    assert result["course_scope"]["count"] == 1
    assert result["mentor_unlinked"]["count"] == 1

    # 撤掉论文查看权限：论文相关检查标注未核对
    full_grants(client, headers, without=[("papers", "view")])
    result = by_code(run_checks(client))
    assert result["thesis_scope"]["status"] == "skipped" and result["thesis_metadata_missing"]["status"] == "skipped"

    # 撤掉导师课题组查看权限：指导关系不可见时不报"登记了导师却没有关系"
    full_grants(client, headers, without=[("mentor_groups", "view")])
    result = by_code(run_checks(client))
    assert result["mentor_unlinked"]["status"] == "skipped"
    assert result["mentor_name_mismatch"]["status"] == "skipped"


def test_consistency_checks_cap_details_and_mark_truncation(client, tmp_path):
    headers = login_admin(client)
    full_grants(client, headers)
    numbers = [f"M{index}" for index in range(5)]
    students = import_students(client, headers, numbers)
    for number in numbers:
        archive(tmp_path / "accounts.sqlite3", students[number], {"学籍异动类型": "转导师"})
    body = run_checks(client, limit=2)
    item = by_code(body)["mobility_incomplete"]
    assert item["count"] == 5 and len(item["items"]) == 2 and item["truncated"] is True
    assert body["students"] == 5 and body["generated_at"] > 0
    assert "只报告差异" in body["basis"]
    assert client.get(CHECKS, params={"college": SCOPE["college"], "major": SCOPE["major"], "limit": 500}).status_code == 422
    assert client.get(CHECKS, params={"college": SCOPE["college"]}).status_code == 422


def test_data_classification_lists_three_levels_for_signed_in_users(client):
    assert client.get("/api/data-classification").status_code == 401
    login_admin(client)
    body = client.get("/api/data-classification").json()
    assert [level["level"] for level in body["levels"]] == ["公开", "内部", "敏感"]
    assert body["status"] == "建议映射，待业务确认"
    sensitive = {item["category"] for item in body["levels"][2]["items"]}
    assert {"basic", "papers", "blind_reviews", "mentor_groups", "research_papers"} <= sensitive
    internal = {item["category"] for item in body["levels"][1]["items"]}
    assert {"basic", "courses", "topic", "midterm", "research_papers", "talent_evaluation"} <= internal
    assert body["levels"][0]["items"] and "尚未接入" in body["levels"][0]["items"][0]["note"]
    assert "字段" in body["principle"]
    # 每一级都说明它是怎么被保护的
    assert all(level["protection"] for level in body["levels"])
    # 每个条目都有面向使用者的名称和说明
    assert all(item["name"] and item["note"] for level in body["levels"] for item in level["items"])
