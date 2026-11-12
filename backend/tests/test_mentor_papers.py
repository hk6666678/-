import json

from aqp.store import connection
from test_accounts import client, login_admin  # noqa: F401
from test_attachments import pdf, setup_record


def test_mentor_attachment_binding_rechecked(client, tmp_path):  # noqa: F811
    headers = login_admin(client)
    record = setup_record(client, headers)
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "INSERT OR IGNORE INTO grants SELECT user_id, category, 'download', college, major FROM grants WHERE category='topic'"
        )
    result = client.post(
        f"/api/milestones/{record}/attachments",
        headers=headers,
        data={"expected_version": 0, "covered_student_ids": "[1]"},
        files={"file": ("synthetic.pdf", pdf())},
    )
    assert result.status_code == 200
    url = f"/api/attachments/{result.json()['id']}/download"
    assert client.get(url).status_code == 200
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "UPDATE users SET roles=?", (json.dumps(["platform_admin", "mentor"]),)
        )
    assert client.get(url).status_code == 403
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("INSERT INTO user_student_bindings VALUES (1,1)")
    assert client.get(url).status_code == 200
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("DELETE FROM user_student_bindings")
    assert client.get(url).status_code == 403


def test_mentor_original_mixed_rows_require_all_bindings(client, tmp_path):  # noqa: F811
    from io import BytesIO

    from openpyxl import load_workbook
    from test_students import workbook

    headers = login_admin(client)
    setup_record(client, headers)
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "INSERT OR IGNORE INTO grants SELECT user_id, category, 'download', college, major FROM grants WHERE category='basic'"
        )
        db.execute(
            "INSERT OR IGNORE INTO grants SELECT user_id, category, 'identity', college, major FROM grants WHERE category='basic'"
        )
    wb = load_workbook(BytesIO(workbook()))
    wb.active.cell(4, 2, "Synthetic second")
    output = BytesIO()
    wb.save(output)
    batch = client.post(
        "/api/imports/basic/preview",
        headers=headers,
        data={"source_department": "synthetic"},
        files={"file": ("synthetic.xlsx", output.getvalue())},
    ).json()
    assert (
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers).status_code
        == 200
    )
    url = f"/api/imports/{batch['id']}/download"
    assert client.get(url).status_code == 200
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute(
            "UPDATE users SET roles=?", (json.dumps(["platform_admin", "mentor"]),)
        )
        db.execute("INSERT INTO user_student_bindings VALUES (1,1)")
    assert client.get(url).status_code == 403
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("INSERT INTO user_student_bindings VALUES (1,2)")
    assert client.get(url).status_code == 200
    with connection(tmp_path / "accounts.sqlite3") as db:
        db.execute("DELETE FROM user_student_bindings WHERE student_id=2")
    assert client.get(url).status_code == 403
