# -*- coding: utf-8 -*-
"""补数第二阶段：确认冲突行（240 基础修订 + 12 旧学院课程）、补国际口头报告与奖学金/人才项目、验证。"""
import json
import sqlite3
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from aqp.app import create_app  # noqa: E402
from aqp.store import connection  # noqa: E402

DB = ROOT / "data" / "linked-business-demo" / "demo.sqlite3"
TEMP_USER = "demo-enrich"
TEMP_PASSWORD = "Enrich-Demo-2026!"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def main() -> None:
    from aqp.accounts import PASSWORDS, create_user

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

    client = TestClient(create_app(DB))
    login = client.post(
        "/api/login", json={"username": TEMP_USER, "password": TEMP_PASSWORD}
    )
    assert login.status_code == 200, login.text
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}

    # ---------- 1) 确认冲突行：basic 批次与 courses 批次 ----------
    for batch_id, evidence in (
        (7, "模拟演示：补充成果核对起止学期（人工确认内容变更）"),
        (9, "模拟演示：人工确认转院系学生旧学院课程归属"),
    ):
        view = client.get(f"/api/resolutions/{batch_id}")
        if view.status_code != 200:
            print("batch", batch_id, "skip:", view.text[:120])
            continue
        rows = view.json()["rows"]
        done = 0
        for row in rows:
            if row["state"] not in ("conflict", "pending", "ready"):
                continue
            validated = client.post(
                f"/api/resolutions/rows/{row['id']}/validate",
                headers=headers,
                json={"data": row["data"], "evidence": evidence, "version": 0},
            )
            if validated.status_code != 200:
                print("validate fail", row["id"], validated.text[:160])
                continue
            version = validated.json()["rows"][0]["revisions"][-1]["version"]
            confirmed = client.post(
                f"/api/resolutions/rows/{row['id']}/confirm",
                headers=headers,
                json={"version": version},
            )
            if confirmed.status_code != 200:
                print("confirm fail", row["id"], confirmed.text[:160])
                continue
            done += 1
        print(f"batch {batch_id}: confirmed {done} rows")

    # ---------- 2) 国际口头报告 + 奖学金/人才项目 ----------
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as read:
        read.row_factory = sqlite3.Row
        sample = read.execute(
            "SELECT student_number,name,college,major FROM students WHERE active=1 ORDER BY id LIMIT 48"
        ).fetchall()

    def fill(template: bytes, rows: list[dict]) -> bytes:
        book = load_workbook(BytesIO(template))
        sheet = book.active
        assert sheet is not None
        columns = [cell.value for cell in sheet[2]]
        for data in rows:
            sheet.append([data.get(column, "") for column in columns])
        out = BytesIO()
        book.save(out)
        return out.getvalue()

    conferences, awards = [], []
    for index, student in enumerate(sample, start=1):
        base = {
            "学号": student["student_number"],
            "姓名": student["name"],
            "所属学院": student["college"],
            "专业": student["major"],
            "作者次序": 1,
        }
        if index <= 24:
            conferences.append(
                {
                    **base,
                    "参与角色": "报告人",
                    "业务编号": f"CONF-DEMO-2025-{index:03d}",
                    "会议名称": "International Conference on Demo Research (ICDR 2025)",
                    "报告类型": "口头报告",
                    "会议日期": f"2025-{(index % 12) + 1:02d}-15",
                    "会议范围": "国际",
                }
            )
        else:
            awards.append(
                {
                    **base,
                    "参与角色": "获奖人",
                    "业务编号": f"AWD-DEMO-2025-{index:03d}",
                    "获奖项目名称": (
                        "研究生国家奖学金" if index % 2 == 0 else "研究生学业奖学金"
                    ),
                    "获奖等级": "国家级" if index % 2 == 0 else "校级",
                    "获奖年份": "2025",
                    "资源类型": "奖学金",
                }
            )
    first = sample[0]
    awards.append(
        {
            "学号": first["student_number"],
            "姓名": first["name"],
            "所属学院": first["college"],
            "专业": first["major"],
            "作者次序": 1,
            "参与角色": "获奖人",
            "业务编号": "AWD-DEMO-2025-TALENT-001",
            "获奖项目名称": "研究生拔尖创新人才培养项目",
            "获奖等级": "国家级",
            "获奖年份": "2025",
            "资源类型": "人才项目",
        }
    )
    for endpoint, rows_ in (("conferences", conferences), ("awards", awards)):
        template = client.get(f"/api/{endpoint}/template").content
        preview = client.post(
            f"/api/{endpoint}/preview",
            data={"source_department": "模拟演示数据（学生处）"},
            files={"file": ("enrich.xlsx", fill(template, rows_), XLSX)},
            headers=headers,
        )
        assert preview.status_code == 200, (endpoint, preview.text)
        batch = preview.json()
        confirmed = client.post(
            f"/api/{endpoint}/previews/{batch['id']}/confirm",
            json={"accept_changes": True},
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        print(endpoint, "imported:", len(rows_), "rows")

    client.post("/api/logout", headers=headers)
    with connection(DB) as db:
        db.execute(
            "DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)",
            (TEMP_USER,),
        )
        db.execute("UPDATE users SET active=0 WHERE username=?", (TEMP_USER,))
        db.commit()
    print("temp user deactivated")

    # ---------- 3) 只读验证 ----------
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        with_term = db.execute(
            "SELECT COUNT(*) FROM students WHERE active=1 AND payload LIKE '%成果核对起始学期%'"
        ).fetchone()[0]
        print("students with 核对学期:", with_term)
        mismatch = 0
        for s in db.execute("SELECT id,college,major FROM students WHERE student_number LIKE 'DEMO-SCOPE-%'"):
            for r in db.execute(
                "SELECT payload FROM course_records WHERE student_id=? AND state='linked' AND active=1",
                (s["id"],),
            ):
                p = json.loads(r["payload"])
                if p.get("所属学院") != s["college"]:
                    mismatch += 1
        print("scope-mismatch linked courses:", mismatch)
        multi = db.execute(
            "SELECT COUNT(*) FROM (SELECT output_id FROM research_citations GROUP BY output_id HAVING COUNT(*) >= 3)"
        ).fetchone()[0]
        print("papers with >=3 citation points:", multi)
        oral = db.execute(
            "SELECT COUNT(*) FROM conferences_outputs WHERE active=1 AND payload LIKE '%口头报告%'"
        ).fetchone()[0]
        talent = db.execute(
            "SELECT COUNT(*) FROM awards_outputs WHERE active=1 AND payload LIKE '%人才项目%'"
        ).fetchone()[0]
        scholarship = db.execute(
            "SELECT COUNT(*) FROM awards_outputs WHERE active=1 AND payload LIKE '%奖学金%'"
        ).fetchone()[0]
        print("oral reports:", oral, "| talent projects:", talent, "| scholarship rows:", scholarship)


if __name__ == "__main__":
    main()
