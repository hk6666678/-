# -*- coding: utf-8 -*-
"""第三阶段：按隔夜先例直接落库（与正规 confirm 同形）：
1) 240 名学生 payload 补成果核对起止学期 + student_revisions 版本链 + import_rows 置 imported；
2) 12 条旧学院课程置 linked 并关联 SCOPE 学生（档案=软件学院 vs 课程=计算机学院 → 评分排除演示）；
3) 审计两行；4) 端到端验证：对 DEMO-SCOPE-01 生成模拟评分快照，断言排除证据出现。"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

DB = ROOT / "data" / "linked-business-demo" / "demo.sqlite3"
TEMP_USER = "demo-enrich"
TEMP_PASSWORD = "Enrich-Demo-2026!"


def term_of(date_text: str, fall: bool) -> str:
    year = date_text[:4] if date_text[:4].isdigit() else "2024"
    return f"{year}{'秋' if fall else '春'}"


def main() -> None:
    from aqp.accounts import PASSWORDS, create_user
    from aqp.store import connection

    with connection(DB) as db:
        row = db.execute("SELECT id FROM users WHERE username=?", (TEMP_USER,)).fetchone()
        if row is None:
            create_user(db, TEMP_USER, TEMP_PASSWORD, ["platform_admin"])
        else:
            db.execute(
                "UPDATE users SET password_hash=? WHERE username=?",
                (PASSWORDS.hash(TEMP_PASSWORD), TEMP_USER),
            )
        db.execute(
            "UPDATE users SET active=1, school_view=1, school_full=1 WHERE username=?",
            (TEMP_USER,),
        )
        db.commit()
        actor_id = db.execute(
            "SELECT id FROM users WHERE username=?", (TEMP_USER,)
        ).fetchone()["id"]

    now = int(time.time())
    with connection(DB) as db:
        db.execute("BEGIN IMMEDIATE")

        # 1) basic 批次 7 的 240 个 conflict 行 → 应用为学生档案修订
        applied = 0
        for r in db.execute(
            "SELECT id,normalized_json FROM import_rows WHERE batch_id=7 AND state='conflict'"
        ).fetchall():
            payload = json.loads(r["normalized_json"])
            student = db.execute(
                "SELECT id,version FROM students WHERE student_number=? AND active=1",
                (payload["学号"],),
            ).fetchone()
            if student is None:
                continue
            db.execute(
                "UPDATE students SET payload=? WHERE id=?",
                (r["normalized_json"], student["id"]),
            )
            db.execute(
                "INSERT INTO student_revisions(student_id,version,payload,source_row_id,created_at,actor_id) VALUES (?,?,?,?,?,?)",
                (student["id"], student["version"] + 1, r["normalized_json"], r["id"], now, actor_id),
            )
            db.execute(
                "UPDATE import_rows SET state='imported', error='', student_id=? WHERE id=?",
                (student["id"], r["id"]),
            )
            applied += 1
        print("basic revisions applied:", applied)

        # 2) courses 批次 9 的 conflict 行 → 落 course_records 并关联 SCOPE 学生
        linked = 0
        for r in db.execute(
            "SELECT id,normalized_json FROM import_rows WHERE batch_id=9 AND state IN ('conflict','linked')"
        ).fetchall():
            payload = json.loads(r["normalized_json"])
            student = db.execute(
                "SELECT id FROM students WHERE student_number=? AND active=1",
                (payload["学号"],),
            ).fetchone()
            if student is None:
                continue
            exists = db.execute(
                "SELECT id FROM course_records WHERE source_row_id=?", (r["id"],)
            ).fetchone()
            if exists is None:
                db.execute(
                    "INSERT INTO course_records(student_number,course_code,term,attempt,student_id,payload,state,source_row_id) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        payload["学号"],
                        payload["课程编号"],
                        payload["修读学期"],
                        int(payload["考核次数"]),
                        student["id"],
                        r["normalized_json"],
                        "linked",
                        r["id"],
                    ),
                )
            else:
                db.execute(
                    "UPDATE course_records SET student_id=?, state='linked', active=1 WHERE id=?",
                    (student["id"], exists["id"]),
                )
            db.execute(
                "UPDATE import_rows SET state='linked', error='', student_id=? WHERE id=?",
                (student["id"], r["id"]),
            )
            linked += 1
        print("scope courses linked:", linked)

        db.execute(
            "INSERT INTO audit(actor_id,action,target,outcome,created_at,details) VALUES (?,?,?,?,?,?)",
            (actor_id, "demo.enrich", "basic+courses", "success", now,
             json.dumps({"revisions": applied, "linked": linked}, ensure_ascii=False)),
        )
        db.commit()

    # 3) 端到端验证：SCOPE-01 生成模拟评分，课程应出现“范围不一致已排除”
    from fastapi.testclient import TestClient

    from aqp.app import create_app

    client = TestClient(create_app(DB))
    login = client.post(
        "/api/login", json={"username": TEMP_USER, "password": TEMP_PASSWORD}
    )
    assert login.status_code == 200, login.text
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}
    roster = client.get("/api/students?limit=200&major=软件工程").json()["items"]
    target = next(
        item for item in roster if item["data"]["学号"] == "DEMO-SCOPE-01"
    )
    snapshot = client.post(
        "/api/evaluation-snapshots", headers=headers, json={"student_id": target["id"]}
    )
    assert snapshot.status_code == 200, snapshot.text
    body = snapshot.json()
    ratio = next(i for i in body["inputs"] if i["feature"] == "course_pass_ratio")
    excluded = [e for e in ratio["evidence"] if e["status"] == "范围不一致已排除"]
    counted = [e for e in ratio["evidence"] if e["status"] != "范围不一致已排除"]
    print("scope demo snapshot: total=", body.get("total"),
          "| counted:", len(counted), "| excluded:", len(excluded))
    assert len(excluded) == 3 and len(counted) == 0, (counted, excluded)
    client.post("/api/logout", headers=headers)

    with connection(DB) as db:
        db.execute(
            "DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)",
            (TEMP_USER,),
        )
        db.execute("UPDATE users SET active=0 WHERE username=?", (TEMP_USER,))
        db.commit()
    print("temp user deactivated")


if __name__ == "__main__":
    main()
