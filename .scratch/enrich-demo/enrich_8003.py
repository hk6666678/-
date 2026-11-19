# -*- coding: utf-8 -*-
"""给 8003 演示库（data/linked-business-demo/demo.sqlite3）补模拟数据：
1) 全员成果核对起止学期（basic 内容变更修订）；2) 学院不一致演示学生；3) 引用增长历史；
4) 国际口头报告；5) 奖学金/人才项目。全部走系统正规导入管线，来源标注模拟演示数据。
运行前提：8003 服务在跑（脚本用独立连接短事务，不重启服务）。可重复运行（重复行会被跳过/更正）。"""
import json
import sqlite3
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402

from aqp.app import create_app  # noqa: E402
from aqp.store import connection  # noqa: E402

DB = ROOT / "data" / "linked-business-demo" / "demo.sqlite3"
TEMP_USER = "demo-enrich"
TEMP_PASSWORD = "Enrich-Demo-2026!"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SOURCE = "模拟演示数据（研究生院）"


def term_of(date_text: str, fall: bool) -> str:
    year = date_text[:4] if date_text[:4].isdigit() else "2024"
    return f"{year}{'秋' if fall else '春'}"


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

    def import_basic(rows: list[dict]) -> dict:
        template = client.get("/api/templates/basic").content
        preview = client.post(
            "/api/imports/basic/preview",
            data={"source_department": SOURCE},
            files={"file": ("enrich.xlsx", fill(template, rows), XLSX)},
            headers=headers,
        )
        assert preview.status_code == 200, preview.text
        batch = preview.json()
        confirmed = client.post(
            f"/api/imports/{batch['id']}/confirm", headers=headers
        )
        assert confirmed.status_code == 200, confirmed.text
        return confirmed.json()

    # ---------- 1) 全员成果核对起止学期（内容变更修订，保留其余字段原值） ----------
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as read:
        read.row_factory = sqlite3.Row
        students = read.execute(
            "SELECT payload FROM students WHERE active=1 ORDER BY id"
        ).fetchall()
    rows = []
    for student in students:
        payload = json.loads(student["payload"])
        end = term_of(payload.get("实际毕业日期") or "2026", fall=False)
        payload["成果核对起始学期"] = term_of(
            payload.get("入学日期") or f"{payload['入学年份']}-09-01", fall=True
        )
        payload["成果核对截止学期"] = end if end >= payload["成果核对起始学期"] else payload["成果核对起始学期"]
        rows.append(payload)
    result = import_basic(rows)
    print("basic revisions:", result)

    # ---------- 2) 学院不一致演示学生（课程记录学院≠档案学院 → 评分时排除） ----------
    scope_rows = []
    for index in range(1, 5):
        scope_rows.append(
            {
                "学号": f"DEMO-SCOPE-{index:02d}",
                "姓名": f"范围演示{index}",
                "所属学院": "软件学院",
                "专业": "软件工程",
                "培养层次": "硕士",
                "入学年份": "2024",
                "入学方式": "统一考试",
                "学习形式": "全日制",
                "学位类型": "专业型学位",
                "学籍状态": "转院系",
                "学籍异动类型": "转院系",
                "学籍异动时间": "2025-09-01",
                "成果核对起始学期": "2024秋",
                "成果核对截止学期": "2026春",
            }
        )
    result = import_basic(scope_rows)
    print("scope students:", result)

    course_book = Workbook()
    sheet = course_book.active
    assert sheet is not None
    sheet.append(["AQP-PGS", "courses", "1"])
    sheet.append(
        ["学号", "姓名", "所属学院", "专业", "培养层次", "入学年份", "课程编号",
         "课程名称", "修读学期", "考核次数", "评分制度", "原始成绩", "业务通过结果", "学分"]
    )
    for index in range(1, 5):
        for code, name, term, score in (
            ("SEC51001", "高级软件工程", "2024秋", 84),
            ("CS51001", "矩阵论", "2024秋", 78),
            ("SEC51002", "分布式系统", "2025春", 81),
        ):
            # 旧学院名：演示"档案更正学院后旧课程口径不一致"
            sheet.append(
                [f"DEMO-SCOPE-{index:02d}", f"范围演示{index}", "计算机学院", "软件工程",
                 "硕士", "2024", code, name, term, 1, "百分制", score, "通过" if score >= 60 else "不通过", 3]
            )
    stream = BytesIO()
    course_book.save(stream)
    preview = client.post(
        "/api/imports/courses/preview",
        data={"source_department": SOURCE},
        files={"file": ("scope-courses.xlsx", stream.getvalue(), XLSX)},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    batch = preview.json()
    confirmed = client.post(
        f"/api/imports/courses/{batch['id']}/confirm", headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    print("scope courses:", confirmed.json())

    # ---------- 3) 引用增长历史（给前 20 篇论文各补 2 个更早时间点） ----------
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as read:
        read.row_factory = sqlite3.Row
        outputs = read.execute(
            "SELECT c.output_id, c.count FROM research_citations c "
            "JOIN research_outputs o ON o.id=c.output_id AND o.active=1 "
            "WHERE c.snapshot_date=(SELECT MAX(d.snapshot_date) FROM research_citations d WHERE d.output_id=c.output_id) "
            "ORDER BY c.output_id LIMIT 20"
        ).fetchall()
    for row in outputs:
        latest = row["count"]
        for date, ratio in (("2025-07-01", 0.4), ("2026-01-01", 0.7)):
            body = {
                "date": date,
                "count": max(0, round(latest * ratio)),
                "source_department": "模拟演示数据（图书馆）",
                "expected_version": 0,
                "confirmed": True,
                "reason": "演示用引用增长历史",
            }
            created = client.post(
                f"/api/research-outputs/{row['output_id']}/citations",
                json=body,
                headers=headers,
            )
            assert created.status_code == 200, (row["output_id"], date, created.text)
    print("citation history added for", len(outputs), "papers")

    # ---------- 4) 国际口头报告 + 5) 奖学金/人才项目 ----------
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as read:
        read.row_factory = sqlite3.Row
        sample = read.execute(
            "SELECT id,student_number,name,college,major,entry_year FROM students WHERE active=1 ORDER BY id LIMIT 48"
        ).fetchall()
    conferences, awards = [], []
    for index, student in enumerate(sample, start=1):
        base = {
            "学号": student["student_number"],
            "姓名": student["name"],
            "所属学院": student["college"],
            "专业": student["major"],
        }
        if index <= 24:
            conferences.append(
                {
                    **base,
                    "作者次序": 1,
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
                    "作者次序": 1,
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
    awards.append(
        {
            **{
                key: sample[0][key] if key != "学号" else sample[0]["student_number"]
                for key in ("学号", "姓名")
            },
            "所属学院": sample[0]["college"],
            "专业": sample[0]["major"],
            "作者次序": 1,
            "参与角色": "获奖人",
            "业务编号": "AWD-DEMO-2025-TALENT-001",
            "获奖项目名称": "研究生拔尖创新人才培养项目",
            "获奖等级": "国家级",
            "获奖年份": "2025",
            "资源类型": "人才项目",
        }
    )
    for endpoint, rows_, template_path in (
        ("conferences", conferences, "/api/conferences/template"),
        ("awards", awards, "/api/awards/template"),
    ):
        template = client.get(template_path).content
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


if __name__ == "__main__":
    main()
