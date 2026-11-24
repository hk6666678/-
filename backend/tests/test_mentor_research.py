# ruff: noqa: F811
import json
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import Workbook
from test_accounts import client, login_admin  # noqa: F401
from test_attachments import pdf

SCOPE = {"college": "研究学院", "major": "研究专业"}
AS_OF = "2026-01-01"


ALL_CATEGORIES = ["basic", "mentor_groups", "courses", "topic", "midterm",
                  "research_papers", "patents", "awards", "conferences", "papers"]
ALL_OPERATIONS = ["maintain", "view", "identity", "analyze", "labels"]


def set_grants(client, headers, rows):
    """Grants are replaced as a whole, so every call sends the complete set."""
    user = client.get("/api/me").json()["user"]
    response = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": rows,
        },
    )
    assert response.status_code == 200, response.text


def rows_for(categories, operations):
    return [{"category": c, "operation": o, **SCOPE} for c in categories for o in operations]


def full_grants(client, headers, without=()):
    rows = rows_for(ALL_CATEGORIES, ALL_OPERATIONS)
    set_grants(client, headers, [r for r in rows if (r["category"], r["operation"]) not in without])


def import_students(client, headers, numbers):
    book = Workbook()
    sheet = book.active
    sheet.append(["AQP-PGS", "basic", "1"])
    sheet.append(["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份"])
    for number in numbers:
        sheet.append([number, f"学生{number}", SCOPE["college"], SCOPE["major"], "硕士", "2024"])
    out = BytesIO()
    book.save(out)
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("basic.xlsx", out.getvalue())},
    ).json()
    assert client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code == 200
    return {
        item["data"]["学号"]: item["id"]
        for item in client.get("/api/students?limit=200").json()["items"]
        if item["data"]["学号"] in numbers
    }


def directory(client, headers, kind, number, name):
    response = client.post(
        f"/api/mentor-groups/directory/{kind}",
        headers=headers,
        json={"number": number, "name": name, **SCOPE},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def relate(client, headers, student_id, mentor_id, group_id, start, end=None):
    body = {
        "student_id": student_id, "mentor_id": mentor_id, "group_id": group_id,
        "start_date": start, "source_department": "合成来源", "reason": "合成关系",
    }
    if end:
        body["end_date"] = end
    response = client.post("/api/mentor-groups/relations", headers=headers, json=body)
    assert response.status_code == 200, response.text


def seed_outputs(db_path, output_counts, oral_reports=()):
    """One research output per count for each student number; optional oral talks."""
    from aqp.store import connection

    with connection(db_path) as db:
        for number, count in output_counts.items():
            participant = {
                "student_number": number, "name": f"学生{number}",
                "college": SCOPE["college"], "major": SCOPE["major"],
            }
            for index in range(count):
                db.execute(
                    "INSERT INTO research_outputs(business_key,payload) VALUES(?,?)",
                    (f"P-{number}-{index}", json.dumps({"title": "合成论文", "participants": [participant]}, ensure_ascii=False)),
                )
        for number in oral_reports:
            db.execute(
                "INSERT INTO conferences_outputs(business_key,payload) VALUES(?,?)",
                (f"C-{number}", json.dumps({
                    "title": "合成国际会议",
                    "participants": [{"student_number": number, "name": f"学生{number}",
                                      "college": SCOPE["college"], "major": SCOPE["major"]}],
                    "details": {"报告类型": "口头报告", "会议范围": "国际", "会议日期": "2025-05-01"},
                }, ensure_ascii=False)),
            )


def labeled_paper(client, headers, student_id, number, label):
    paper = client.post(
        "/api/papers", headers=headers,
        data={"student_id": student_id, "title": f"合成学位论文{number}",
              "expected_version": 0, "covered_student_ids": json.dumps([student_id])},
        files={"file": ("synthetic.pdf", pdf())},
    )
    assert paper.status_code == 200, paper.text
    marked = client.post(
        f"/api/papers/{paper.json()['id']}/labels", headers=headers,
        json={"label": label, "confirmed_by": "合成专家", "basis": "合成书面确认", "expected_version": 0},
    )
    assert marked.status_code == 200, marked.text
    return paper.json()["id"]


def import_topic_scores(client, headers, scores):
    book = Workbook()
    sheet = book.active
    sheet.append(["AQP-PGS", "topic", "1"])
    sheet.append(["学号", "姓名", "考核批次", "评分制度", "原始成绩", "所属学院", "专业", "选题标题"])
    for number, score in scores.items():
        sheet.append([number, f"学生{number}", "合成选题批次", "百分制", score,
                      SCOPE["college"], SCOPE["major"], "合成选题"])
    out = BytesIO()
    book.save(out)
    batch = client.post(
        "/api/milestones/topic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("topic.xlsx", out.getvalue())},
    ).json()
    assert client.post(f"/api/milestone-imports/{batch['id']}/confirm", headers=headers).status_code == 200


def test_scale_output_relates_group_size_to_outputs_per_student(client, tmp_path):
    headers = login_admin(client)
    full_grants(client, headers)
    numbers = [f"RES-{index}" for index in range(1, 8)]
    students = import_students(client, headers, numbers)
    group = directory(client, headers, "groups", "RG-1", "合成课题组")
    # 规模 1、1、2、3 的四位导师；人均成果 1、2、3、4
    plan = {0: [1], 1: [2], 2: [3, 4], 3: [5, 6, 7]}
    for index, members in plan.items():
        mentor = directory(client, headers, "mentors", f"RES-M{index}", f"合成导师{index}")
        for member in members:
            relate(client, headers, students[f"RES-{member}"], mentor, group, "2024-09-01")
    seed_outputs(tmp_path / "accounts.sqlite3", {"RES-1": 1, "RES-2": 2, "RES-3": 3, "RES-4": 3, "RES-5": 4, "RES-6": 4, "RES-7": 4})

    body = client.get("/api/mentor-groups/scale-output", params={"as_of": AS_OF, "kind": "mentor"}).json()
    assert body["kind"] == "mentor_id"
    assert [(unit["students"], unit["outputs_per_student"]) for unit in body["units"]] == [(1, 1.0), (1, 2.0), (2, 3.0), (3, 4.0)]
    # 手算：x=[1,1,2,3]，y=[1,2,3,4]，r = 3.5 / sqrt(2.75 * 5)
    assert body["correlation"]["count"] == 4
    assert body["correlation"]["r"] == pytest.approx(0.944, abs=0.001)
    assert body["excluded_units"] == 0
    assert [unit["name"] for unit in body["units"]] == [f"合成导师{index}" for index in range(4)]

    # 单位名称沿用目录的身份授权：撤掉身份权限后不再返回
    full_grants(client, headers, without=[("mentor_groups", "identity")])
    anonymous = client.get("/api/mentor-groups/scale-output", params={"as_of": AS_OF, "kind": "mentor"}).json()
    assert all(unit["name"] is None for unit in anonymous["units"])
    assert [(unit["students"], unit["outputs_per_student"]) for unit in anonymous["units"]] == [(1, 1.0), (1, 2.0), (2, 3.0), (3, 4.0)]
    full_grants(client, headers)

    grouped = client.get("/api/mentor-groups/scale-output", params={"as_of": AS_OF, "kind": "group"}).json()
    assert grouped["kind"] == "group_id"
    # 只有一个课题组且不足三个单位，不计算相关系数
    assert [(unit["students"], unit["outputs_per_student"]) for unit in grouped["units"]] == [(7, 21 / 7)]
    assert grouped["correlation"] == {"r": None, "count": 1}


def test_scale_output_excludes_units_with_incomplete_output_access(client, tmp_path):
    headers = login_admin(client)
    full_grants(client, headers)
    students = import_students(client, headers, ["RES-1", "RES-2", "RES-3"])
    group = directory(client, headers, "groups", "RG-1", "合成课题组")
    seed_outputs(tmp_path / "accounts.sqlite3", {"RES-1": 1, "RES-2": 2, "RES-3": 3})
    for index in range(3):
        mentor = directory(client, headers, "mentors", f"RES-M{index}", f"合成导师{index}")
        relate(client, headers, students[f"RES-{index + 1}"], mentor, group, "2024-09-01")
    assert client.get("/api/mentor-groups/scale-output", params={"as_of": AS_OF}).json()["correlation"]["count"] == 3

    # 撤掉一类成果的分析权限后，人均产出无法完整计算，单位不纳入
    full_grants(client, headers, without=[("awards", "analyze")])
    body = client.get("/api/mentor-groups/scale-output", params={"as_of": AS_OF}).json()
    assert body["units"] == [] and body["excluded_units"] == 3
    assert body["correlation"] == {"r": None, "count": 0}

    # 与事实统计一致：需要导师课题组的查看和分析权限
    full_grants(client, headers, without=[("mentor_groups", "analyze")])
    assert client.get("/api/mentor-groups/scale-output", params={"as_of": AS_OF}).status_code == 403


def test_growth_path_compares_excellent_and_ordinary_labeled_students(client, tmp_path):
    headers = login_admin(client)
    full_grants(client, headers)
    numbers = ["E1", "E2", "O1", "O2", "P1"]
    students = import_students(client, headers, numbers)
    mentor = directory(client, headers, "mentors", "RES-M", "合成导师")
    group = directory(client, headers, "groups", "RG-1", "合成课题组")
    for number in numbers:
        # E2 的指导关系已结束：历届学生仍纳入
        relate(client, headers, students[number], mentor, group, "2023-09-01", "2025-06-30" if number == "E2" else None)
    for number, label in [("E1", "优秀"), ("E2", "优秀"), ("O1", "普通"), ("O2", "普通"), ("P1", "待评")]:
        labeled_paper(client, headers, students[number], number, label)
    import_topic_scores(client, headers, {"E1": 90, "E2": 90, "O1": 70, "O2": 70, "P1": 80})
    seed_outputs(tmp_path / "accounts.sqlite3", {"E1": 2, "E2": 2, "O1": 1}, oral_reports=["E1"])

    body = client.get(
        "/api/mentor-groups/growth-path", params={"as_of": AS_OF, "mentor_id": mentor}
    ).json()
    assert body["students"] == 5
    assert body["excellent"]["count"] == 2 and body["ordinary"]["count"] == 2
    assert body["excluded"] == {"unlabeled": 1, "unauthorized": 0}
    assert body["excellent"]["metrics"]["topic_score"] == {"count": 2, "mean": 90.0}
    assert body["ordinary"]["metrics"]["topic_score"] == {"count": 2, "mean": 70.0}
    # 成果参与人次包含会议：E1 两篇论文加一场国际口头报告，E2 两篇论文
    assert body["excellent"]["metrics"]["outputs_per_student"] == {"count": 2, "mean": 2.5}
    assert body["ordinary"]["metrics"]["outputs_per_student"] == {"count": 2, "mean": 0.5}
    assert body["excellent"]["metrics"]["oral_reports"] == {"count": 2, "mean": 0.5}
    assert body["excellent"]["metrics"]["course_pass_ratio"] == {"count": 0, "mean": None}
    assert body["differences"]["topic_score"] == pytest.approx(20.0)
    assert body["differences"]["outputs_per_student"] == pytest.approx(2.0)
    assert body["differences"]["oral_reports"] == pytest.approx(0.5)
    assert body["differences"]["course_pass_ratio"] is None
    assert body["notice"] is None
    assert body["unit_name"] == "合成导师"

    full_grants(client, headers, without=[("mentor_groups", "identity")])
    anonymous = client.get("/api/mentor-groups/growth-path", params={"as_of": AS_OF, "mentor_id": mentor}).json()
    assert anonymous["unit_name"] is None
    assert anonymous["differences"]["topic_score"] == pytest.approx(20.0)


def test_growth_path_requires_labels_and_paper_access(client):
    headers = login_admin(client)
    full_grants(client, headers)
    students = import_students(client, headers, ["E1", "E2", "O1"])
    mentor = directory(client, headers, "mentors", "RES-M", "合成导师")
    group = directory(client, headers, "groups", "RG-1", "合成课题组")
    for number in students:
        relate(client, headers, students[number], mentor, group, "2024-09-01")

    empty = client.get("/api/mentor-groups/growth-path", params={"as_of": AS_OF, "mentor_id": mentor}).json()
    assert empty["excluded"] == {"unlabeled": 3, "unauthorized": 0}
    assert empty["differences"] is None and "标签" in empty["notice"]

    for number, label in [("E1", "优秀"), ("E2", "优秀"), ("O1", "普通")]:
        labeled_paper(client, headers, students[number], number, label)
    # 对照组只有 1 人，不给出均值差
    few = client.get("/api/mentor-groups/growth-path", params={"as_of": AS_OF, "mentor_id": mentor}).json()
    assert few["ordinary"]["count"] == 1 and few["differences"] is None
    assert "不足" in few["notice"]

    # 撤掉论文身份权限后读不到专家标签，任何一组都不下结论
    full_grants(client, headers, without=[("papers", "identity")])
    blind = client.get("/api/mentor-groups/growth-path", params={"as_of": AS_OF, "mentor_id": mentor}).json()
    assert blind["excluded"] == {"unlabeled": 0, "unauthorized": 3}
    assert blind["excellent"]["count"] == 0 and blind["ordinary"]["count"] == 0
    assert "标签" in blind["notice"]
    assert "合成学位论文" not in json.dumps(blind, ensure_ascii=False)

    assert client.get("/api/mentor-groups/growth-path", params={"as_of": AS_OF}).status_code == 422
    assert client.get(
        "/api/mentor-groups/growth-path",
        params={"as_of": AS_OF, "mentor_id": mentor, "group_id": group},
    ).status_code == 422
    missing = client.get("/api/mentor-groups/growth-path", params={"as_of": AS_OF, "mentor_id": 9999})
    assert missing.status_code == 404


def import_courses(client, headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.append(["AQP-PGS", "courses", "1"])
    sheet.append(["学号", "姓名", "课程编号", "课程名称", "修读学期", "考核次数", "评分制度", "原始成绩", "业务通过结果", "学分"])
    for number, code, score in rows:
        passed = "" if score == "" else ("通过" if score >= 60 else "不通过")
        sheet.append([number, f"学生{number}", code, f"合成课程{code}", "2024秋", 1, "百分制", score, passed, 3])
    out = BytesIO()
    book.save(out)
    batch = client.post(
        "/api/imports/courses/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("courses.xlsx", out.getvalue())},
    ).json()
    assert client.post(f"/api/imports/courses/{batch['id']}/confirm", headers=headers).status_code == 200


def test_growth_path_course_ratio_skips_unknown_and_out_of_scope_records(client, tmp_path):
    from aqp.store import connection

    headers = login_admin(client)
    full_grants(client, headers)
    students = import_students(client, headers, ["E1", "E2", "O1", "O2"])
    mentor = directory(client, headers, "mentors", "RES-M", "合成导师")
    group = directory(client, headers, "groups", "RG-1", "合成课题组")
    for number in students:
        relate(client, headers, students[number], mentor, group, "2024-09-01")
    for number, label in [("E1", "优秀"), ("E2", "优秀"), ("O1", "普通"), ("O2", "普通")]:
        labeled_paper(client, headers, students[number], number, label)
    # E1 一门不通过（随后变成旧学院记录）、一门通过；E2 一门通过、一门不通过；
    # O1 一门通过；O2 一门通过、一门缺成绩（通过状态未知）
    import_courses(client, headers, [
        ("E1", "C1", 50), ("E1", "C2", 90),
        ("E2", "C1", 80), ("E2", "C2", 50),
        ("O1", "C1", 80),
        ("O2", "C1", 80), ("O2", "C2", ""),
    ])
    with connection(tmp_path / "accounts.sqlite3") as db:
        # 模拟档案更正学院后遗留的旧课程记录：口径与档案不一致。
        # 这条恰为不通过，若未被排除，E1 的比例会是 0.5 而不是 1.0。
        stale = db.execute(
            "SELECT id,payload FROM course_records WHERE student_id=? AND course_code='C1'",
            (students["E1"],),
        ).fetchone()
        db.execute(
            "UPDATE course_records SET payload=? WHERE id=?",
            (json.dumps({**json.loads(stale["payload"]), "所属学院": "更正前学院"}, ensure_ascii=False), stale["id"]),
        )

    body = client.get("/api/mentor-groups/growth-path", params={"as_of": AS_OF, "mentor_id": mentor}).json()
    # E1 只剩一门可计（1.0），E2 为 0.5；O1 为 1.0，O2 存在未知状态不给出比例
    assert body["excellent"]["metrics"]["course_pass_ratio"] == {"count": 2, "mean": 0.75}
    assert body["ordinary"]["metrics"]["course_pass_ratio"] == {"count": 1, "mean": 1.0}
    assert body["differences"]["course_pass_ratio"] == pytest.approx(-0.25)

    # 撤掉课程分析权限后该维度对两组都不可用
    full_grants(client, headers, without=[("courses", "analyze")])
    blind = client.get("/api/mentor-groups/growth-path", params={"as_of": AS_OF, "mentor_id": mentor}).json()
    assert blind["excellent"]["metrics"]["course_pass_ratio"] == {"count": 0, "mean": None}
    assert blind["differences"]["course_pass_ratio"] is None
