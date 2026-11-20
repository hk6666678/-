# -*- coding: utf-8 -*-
"""补引用快照并停用临时账号（主脚本已导入其余数据）。"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from aqp.app import create_app  # noqa: E402
from aqp.store import connection  # noqa: E402

DB = ROOT / "data" / "aqp.sqlite3"
TEMP_USER = "demo-refresh"
TEMP_PASSWORD = "Fresh-Demo-2026!"

CITATIONS = {
    "doi-10.1109/tkde.2024.4455661": 35,
    "acl-2025-long-234": 12,
    "cvpr-2025-1789": 21,
    "ruanjixb-2025-042": 8,
}


def main() -> None:
    from aqp.accounts import create_user

    with connection(DB) as db:
        row = db.execute("SELECT id FROM users WHERE username=?", (TEMP_USER,)).fetchone()
        if row is None:
            create_user(db, TEMP_USER, TEMP_PASSWORD, ["platform_admin"])
        db.execute(
            "UPDATE users SET active=1, school_view=1, school_full=1 WHERE username=?",
            (TEMP_USER,),
        )
        db.commit()

    client = TestClient(create_app(DB))
    login = client.post("/api/login", json={"username": TEMP_USER, "password": TEMP_PASSWORD})
    assert login.status_code == 200, login.text
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}

    outputs = client.get("/api/research-outputs").json()["items"]
    output_ids = {item["business_key"]: item["id"] for item in outputs}
    print("known keys:", sorted(output_ids))
    for business_key, count in CITATIONS.items():
        assert business_key in output_ids, (business_key, sorted(output_ids))
        created = client.post(
            f"/api/research-outputs/{output_ids[business_key]}/citations",
            json={
                "date": "2026-11-01",
                "count": count,
                "source_department": "模拟演示数据（图书馆）",
                "expected_version": 0,
                "confirmed": True,
                "reason": "演示用引用快照",
            },
            headers=headers,
        )
        assert created.status_code == 200, (business_key, created.text)
        print("citation:", business_key, count)
    client.post("/api/logout", headers=headers)

    with connection(DB) as db:
        db.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)", (TEMP_USER,))
        db.execute(
            "UPDATE users SET active=0, password_hash='refresh-demo-disabled' WHERE username=?",
            (TEMP_USER,),
        )
        db.commit()
    print("temp user deactivated")

    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
        for table in (
            "students", "course_records", "milestone_records",
            "research_outputs", "patents_outputs", "awards_outputs",
            "conferences_outputs", "mentor_directory", "research_groups",
            "mentor_relations", "output_citations",
        ):
            try:
                print(table, db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.OperationalError as e:
                print(table, "ERR", e)


if __name__ == "__main__":
    main()
