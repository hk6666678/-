# ruff: noqa: F811
import json
from uuid import uuid4

from test_accounts import client, login_admin  # noqa: F401


def seed_student(db, ident: int, number: str) -> None:
    db.execute(
        "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload)"
        " VALUES(?,?,?,?,'synthetic','synthetic','master',2025,'{}')",
        (ident, f"R{ident}", number, f"Synthetic{ident}"),
    )


def seed_patent(db, key: str, number: str, year_field: str) -> None:
    db.execute(
        "INSERT INTO patents_outputs(business_key,payload) VALUES(?,?)",
        (
            key,
            json.dumps(
                {
                    "title": f"Patent {key}",
                    "专利类型": "发明",
                    "申请日期": year_field,
                    "participants": [
                        {
                            "student_number": number,
                            "name": f"Synthetic{number[1:]}",
                            "college": "synthetic",
                            "major": "synthetic",
                        }
                    ],
                }
            ),
        ),
    )


def give_grants(client, headers, me, categories, operations) -> None:
    fresh = client.get("/api/me").json()["user"]
    assert me["id"] == fresh["id"]
    assert (
        client.put(
            f"/api/users/{me['id']}/grants",
            headers=headers,
            json={
                "expected_version": fresh["version"],
                "request_id": str(uuid4()),
                "grants": [
                    {
                        "category": category,
                        "operation": operation,
                        "college": "synthetic",
                        "major": "synthetic",
                    }
                    for category in categories
                    for operation in operations
                ],
            },
        ).status_code
        == 200
    )


def test_student_report_sections_missing_unauthorized_and_export(
    client, tmp_path
):
    from io import BytesIO

    from aqp.store import connection
    from openpyxl import load_workbook

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    dbpath = tmp_path / "accounts.sqlite3"
    with connection(dbpath) as db:
        seed_student(db, 1, "S1")
        seed_patent(db, "P1", "S1", "2026-01-01")
        db.commit()
    give_grants(
        client,
        headers,
        me,
        ["basic", "patents", "talent_evaluation", "topic", "midterm"],
        ["view", "identity", "analyze"],
    )
    report = client.get("/api/reports/students/1", headers=headers)
    assert report.status_code == 200
    data = report.json()
    assert data["level"] == "student"
    assert data["student"]["student_number"] == "S1"
    assert data["sections"]["patents"]["status"] == "ok"
    assert data["sections"]["patents"]["count"] == 1
    assert data["sections"]["patents"]["items"][0]["year"] == "2026"
    assert data["sections"]["courses"] == {
        "status": "unauthorized",
        "reason": "当前授权不足，该段未纳入",
    }
    assert data["sections"]["evaluation"]["status"] == "missing"
    assert data["sections"]["milestones"]["topic"]["status"] == "missing"
    # Export requires the export grant for every contributing category.
    export = client.get("/api/reports/students/1/export", headers=headers)
    assert export.status_code == 403
    give_grants(
        client,
        headers,
        me,
        ["basic", "patents"],
        ["view", "identity", "analyze", "export"],
    )
    export = client.get("/api/reports/students/1/export", headers=headers)
    assert export.status_code == 200
    workbook = load_workbook(BytesIO(export.content))
    cells = [
        cell.value
        for row in workbook.active.iter_rows()
        for cell in row
        if cell.value is not None
    ]
    workbook.close()
    assert any("当前授权不足" in str(cell) for cell in cells)
    assert any("Patent P1" in str(cell) for cell in cells)
    with connection(dbpath) as db:
        actions = {
            row[0]
            for row in db.execute(
                "SELECT action FROM audit WHERE action LIKE 'reports.%'"
            )
        }
        denials = db.execute(
            "SELECT COUNT(*) FROM audit WHERE action='reports.access' AND outcome='denied'"
        ).fetchone()[0]
    assert {"reports.read", "reports.export"} <= actions
    assert denials >= 1
    give_grants(client, headers, me, ["patents"], ["view", "identity", "analyze"])
    assert (
        client.get("/api/reports/students/1", headers=headers).status_code == 403
    )


def test_group_report_current_relations_and_export(client, tmp_path):
    from io import BytesIO
    from time import strftime

    from aqp.store import connection
    from openpyxl import load_workbook

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    dbpath = tmp_path / "accounts.sqlite3"
    today = strftime("%Y-%m-%d")
    with connection(dbpath) as db:
        seed_student(db, 1, "S1")
        seed_patent(db, "P1", "S1", "2026-01-01")
        db.execute(
            "INSERT INTO mentor_directory(id,mentor_number,name,college,major) VALUES(1,'M1','Synthetic Mentor','synthetic','synthetic')"
        )
        db.execute(
            "INSERT INTO research_groups(id,group_number,name,college,major) VALUES(1,'G1','Synthetic Group','synthetic','synthetic')"
        )
        db.execute(
            "INSERT INTO mentor_group_relations(id,student_id,mentor_id,group_id,start_date,end_date,source_department) "
            "VALUES(1,1,1,1,'2020-01-01',NULL,'synthetic')"
        )
        db.commit()
    give_grants(
        client,
        headers,
        me,
        ["basic", "patents", "mentor_groups"],
        ["view", "identity", "analyze"],
    )
    report = client.get(
        f"/api/reports/mentor-groups?as_of={today}&mentor_id=1", headers=headers
    )
    assert report.status_code == 200
    data = report.json()
    assert data["level"] == "mentor_group"
    assert data["student_count"] == 1
    assert data["categories"]["patents"]["distinct_outputs"] == 1
    assert data["categories"]["patents"]["items"][0]["year"] == "2026"
    assert data["graduation"]["status"] == "missing"
    # A relation that has not started yet contributes nothing at this date.
    with connection(dbpath) as db:
        db.execute(
            "UPDATE mentor_group_relations SET start_date='2999-01-01' WHERE id=1"
        )
        db.commit()
    empty = client.get(
        f"/api/reports/mentor-groups?as_of={today}&mentor_id=1", headers=headers
    ).json()
    assert empty["student_count"] == 0
    with connection(dbpath) as db:
        db.execute(
            "UPDATE mentor_group_relations SET start_date='2020-01-01' WHERE id=1"
        )
        db.commit()
    export = client.get(
        f"/api/reports/mentor-groups/export?as_of={today}&mentor_id=1",
        headers=headers,
    )
    assert export.status_code == 403
    give_grants(
        client,
        headers,
        me,
        ["basic", "patents", "mentor_groups"],
        ["view", "identity", "analyze", "export"],
    )
    export = client.get(
        f"/api/reports/mentor-groups/export?as_of={today}&mentor_id=1",
        headers=headers,
    )
    assert export.status_code == 200
    workbook = load_workbook(BytesIO(export.content))
    cells = [
        cell.value
        for row in workbook.active.iter_rows()
        for cell in row
        if cell.value is not None
    ]
    workbook.close()
    assert any("Patent P1" in str(cell) for cell in cells)


def test_college_report_counts_and_partial_sections(client, tmp_path):
    from aqp.store import connection

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    dbpath = tmp_path / "accounts.sqlite3"
    with connection(dbpath) as db:
        seed_student(db, 1, "S1")
        seed_student(db, 2, "S2")
        seed_patent(db, "P1", "S1", "2026-01-01")
        seed_patent(db, "P2", "S2", "2025-02-02")
        db.commit()
    give_grants(
        client,
        headers,
        me,
        ["basic", "patents"],
        ["view", "identity", "analyze"],
    )
    data = client.get(
        "/api/reports/colleges?college=synthetic&major=synthetic", headers=headers
    ).json()
    assert data["level"] == "college"
    assert data["sections"]["students"]["count"] == 2
    assert data["sections"]["patents"]["distinct_outputs"] == 2
    assert data["sections"]["patents"]["personal_participations"] == 2
    assert data["sections"]["courses"]["status"] == "unauthorized"
    assert data["sections"]["mentor_groups"]["status"] == "unauthorized"
    assert (
        client.get(
            "/api/reports/colleges?college=elsewhere&major=elsewhere",
            headers=headers,
        ).status_code
        == 403
    )
    # Export demands export grants for contributing sections only; the
    # unauthorized ones stay labelled and never block or widen.
    export = client.get(
        "/api/reports/colleges/export?college=synthetic&major=synthetic",
        headers=headers,
    )
    assert export.status_code == 403
    give_grants(
        client,
        headers,
        me,
        ["basic", "patents"],
        ["view", "identity", "analyze", "export"],
    )
    export = client.get(
        "/api/reports/colleges/export?college=synthetic&major=synthetic",
        headers=headers,
    )
    assert export.status_code == 200
