# -*- coding: utf-8 -*-
"""向演示库灌入真实课程风格的模拟数据：临时管理员走系统导入管线，完成后删除临时账号。"""
import io
import json
import os
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402

from aqp.app import create_app  # noqa: E402
from aqp.store import connection  # noqa: E402

DB = ROOT / "data" / "aqp.sqlite3"
TEMP_USER = "demo-refresh"
TEMP_PASSWORD = "Fresh-Demo-2026!"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

CS = ("电子与信息工程学院", "计算机科学与技术")
SE = ("软件学院", "软件工程")

STUDENTS = [
    # 学号, 姓名, (学院,专业), 入学年份, 前置院校, 入学方式, 学位类型, 学籍状态, 异动类型, 异动时间
    ("2450101", "陈思远", CS, "2024", "华中科技大学", "统一考试", "学术型学位", "正常", "", ""),
    ("2450102", "林雨桐", CS, "2024", "武汉大学", "推荐免试", "学术型学位", "硕博连读", "", ""),
    ("2450103", "赵启铭", CS, "2024", "湖南大学", "统一考试", "专业型学位", "正常", "转导师", "2025-09-15"),
    ("2450104", "孙嘉宁", CS, "2024", "东南大学", "推荐免试", "专业型学位", "正常", "", ""),
    ("2350105", "周子墨", CS, "2023", "哈尔滨工业大学", "统一考试", "学术型学位", "复学", "休学后复学", "2024-09-01"),
    ("2450201", "吴婧怡", SE, "2024", "同济大学", "统一考试", "专业型学位", "正常", "", ""),
    ("2450202", "郑博文", SE, "2024", "西安电子科技大学", "统一考试", "专业型学位", "正常", "", ""),
    ("2450203", "何晓萌", SE, "2024", "电子科技大学", "推荐免试", "专业型学位", "博转硕", "博转硕", "2024-12-20"),
]

COMMON = ("0001001", "中国特色社会主义理论与实践研究", 2)
ENGLISH = ("0001002", "学术英语写作", 2)
CS_COURSES = [
    ("CS51001", "矩阵论", "秋", 3),
    ("CS51002", "随机过程", "秋", 3),
    ("CS51003", "算法设计与分析", "秋", 3),
    ("CS52001", "机器学习", "春", 3),
    ("CS52002", "自然语言处理", "春", 3),
    ("CS52003", "计算机视觉", "春", 3),
]
SEC_COURSES = [
    ("SEC51001", "高级软件工程", "秋", 3),
    ("CS51001", "矩阵论", "秋", 3),
    ("SEC51002", "分布式系统", "春", 3),
    ("SEC52001", "大数据技术基础", "春", 3),
]

def courses_rows():
    """(学号,姓名,学院,专业) → 每人公共课2门+专业课；成绩定值可复现。"""
    scores = {
        "2450101": [86, 88, 91, 84, 92, 89, 90, 87],
        "2450102": [93, 90, 95, 92, 96, 94, 88, 91],
        "2450103": [78, 75, 81, 74, 62, 76, 80, 77],
        "2450104": [90, 85, 92, 88, 94, 89, 93, 91],
        "2350105": [82, 79, 85, 80, 84, "", 83, 81],
        "2450201": [88, 86, 90, 87, 91, 89],
        "2450202": [74, 71, 78, 73, 76, 75],
        "2450203": [83, 80, 86, 82, 85, 84],
    }
    rows = []
    for number, name, (college, major), year, *_ in STUDENTS:
        entry = int(year)
        plan = [
            (COMMON[0], COMMON[1], f"{entry}秋", COMMON[2]),
            (ENGLISH[0], ENGLISH[1], f"{entry}秋", ENGLISH[2]),
        ]
        if (college, major) == CS:
            plan += [
                (code, title, f"{entry if season == '秋' else entry + 1}{season}", credit)
                for code, title, season, credit in CS_COURSES
            ]
        else:
            plan += [
                (code, title, f"{entry if season == '秋' else entry + 1}{season}", credit)
                for code, title, season, credit in SEC_COURSES
            ]
        if number not in scores and entry == 2023:
            plan.extend(
                (code, title, term, 2)
                for code, title, term in (
                    ("RS61001", "科研方法专题", "2024秋"),
                    ("RS61002", "高级技术研讨", "2025春"),
                    ("RS62001", "学术前沿研讨", "2025秋"),
                    ("RS62002", "工程实践专题", "2026春"),
                )
            )
        for index, (code, title, term, credit) in enumerate(plan):
            raw = scores[number][index] if number in scores else 55 + (int(number[-4:]) * 7 + index * 11) % 45
            if number not in scores and int(number[-2:]) <= 5:
                raw = 78 + (int(number[-4:]) * 7 + index * 11) % 20
            if number not in scores and entry == 2023 and number.endswith("006") and term == "2026春":
                raw = 45
            if raw == "":
                result = ""
            elif int(raw) >= 60:
                result = "通过"
            else:
                result = "不通过"
            rows.append(
                {
                    "学号": number,
                    "姓名": name,
                    "所属学院": college,
                    "专业": major,
                    "培养层次": "硕士",
                    "入学年份": str(entry),
                    "课程编号": code,
                    "课程名称": title,
                    "修读学期": term,
                    "考核次数": 1,
                    "评分制度": "百分制",
                    "原始成绩": raw,
                    "业务通过结果": result,
                    "学分": credit,
                }
            )
    return rows

TOPIC_BATCH = "2025年春季学期选题"
MIDTERM_BATCH = "2026年春季学期中期"
TOPICS = {
    "2450101": ("基于大语言模型的代码缺陷自动修复方法研究", 82),
    "2450102": ("面向低资源场景的跨语言机器翻译关键技术研究", 88),
    "2450103": ("基于图神经网络的软件缺陷预测方法研究", 76),
    "2450104": ("多模态大模型在医学影像理解中的应用研究", 90),
    "2350105": ("隐私保护联邦学习中的梯度压缩方法研究", 79),
    "2450201": ("面向微服务架构的智能运维异常检测研究", 84),
    "2450202": ("基于知识图谱的推荐系统关键技术研究", 74),
    "2450203": ("边缘计算环境下分布式模型训练优化研究", 81),
}

MENTORS = [
    ("T-1024", "李文轩", CS),
    ("T-1088", "张慧敏", CS),
    ("T-2016", "周志强", SE),
]
GROUPS = [
    ("RG-01", "智能计算实验室", CS),
    ("RG-02", "数据科学与知识工程课题组", CS),
    ("RG-03", "软件工程与服务计算课题组", SE),
]
RELATIONS = [
    # 学号, 导师编号, 组编号, 开始, 结束(可空), 依据
    ("2450101", "T-1024", "RG-01", "2024-09-01", None, "入学建档"),
    ("2450102", "T-1024", "RG-01", "2024-09-01", None, "入学建档"),
    ("2450103", "T-1024", "RG-01", "2024-09-01", "2025-09-14", "入学建档（转导师前）"),
    ("2450103", "T-1088", "RG-02", "2025-09-15", None, "学籍异动：转导师后建档"),
    ("2450104", "T-1088", "RG-02", "2024-09-01", None, "入学建档"),
    ("2350105", "T-1024", "RG-01", "2023-09-01", None, "入学建档（复学后延续）"),
    ("2450201", "T-2016", "RG-03", "2024-09-01", None, "入学建档"),
    ("2450202", "T-2016", "RG-03", "2024-09-01", None, "入学建档"),
    ("2450203", "T-2016", "RG-03", "2024-09-01", None, "入学建档"),
]

PAPERS = [
    ("DOI-10.1109/TKDE.2024.4455661", "基于大语言模型的代码缺陷自动修复方法研究", 2025,
     [("2450101", "陈思远", 1, "第一作者"), ("2450102", "林雨桐", 2, "参与作者")]),
    ("ACL-2025-LONG-234", "面向低资源场景的跨语言机器翻译关键技术研究", 2025,
     [("2450102", "林雨桐", 1, "第一作者")]),
    ("CVPR-2025-1789", "多模态大模型在医学影像理解中的应用研究", 2025,
     [("2450104", "孙嘉宁", 1, "第一作者")]),
    ("RUANJIXB-2025-042", "基于知识图谱的推荐系统关键技术研究", 2025,
     [("2450202", "郑博文", 1, "第一作者")]),
    ("JSJXB-2024-311", "隐私保护联邦学习中的梯度压缩方法研究", 2024,
     [("2350105", "周子墨", 1, "第一作者")]),
    ("ICSE-2026-TECH-105", "面向微服务架构的智能运维异常检测研究", 2026,
     [("2450201", "吴婧怡", 1, "第一作者")]),
]
PATENTS = [
    ("CN202411023456.7", "一种基于图神经网络的软件缺陷预测方法及系统", "发明", "2024-11-01",
     [("2450103", "赵启铭", 1, "第一作者"), ("2450104", "孙嘉宁", 2, "参与作者")]),
    ("CN202520345678.8", "一种微服务运行时异常检测装置", "实用新型", "2025-03-15",
     [("2450201", "吴婧怡", 1, "第一作者")]),
]
AWARDS = [
    ("AWD-2025-GJSXJ-001", "研究生国家奖学金", "国家级", "2025",
     [("2450102", "林雨桐", 1, "获奖人")]),
    ("AWD-2024-MCM-TEAM17", "全国研究生数学建模竞赛一等奖", "国家级", "2024",
     [("2450101", "陈思远", 1, "队长"), ("2450103", "赵启铭", 2, "队员")]),
]
CONFERENCES = [
    ("CONF-ACL-2025-234", "Annual Meeting of the Association for Computational Linguistics (ACL 2025)",
     "口头报告", "2025-07-27", [("2450102", "林雨桐", 1, "报告人")]),
    ("CONF-ICCV-2025-881", "IEEE/CVF International Conference on Computer Vision (ICCV 2025)",
     "海报报告", "2025-10-19", [("2450104", "孙嘉宁", 1, "报告人")]),
]
CITATIONS = {
    "DOI-10.1109/TKDE.2024.4455661": 35,
    "ACL-2025-LONG-234": 12,
    "CVPR-2025-1789": 21,
    "RUANJIXB-2025-042": 8,
}


def fill(template: bytes, rows: list[dict]) -> bytes:
    book = load_workbook(io.BytesIO(template))
    sheet = book.active
    assert sheet is not None
    columns = [cell.value for cell in sheet[2]]
    for row in rows:
        sheet.append([row.get(column, "") for column in columns])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def main(extended: bool = False) -> None:
    from aqp.accounts import create_user

    with connection(DB) as db:
        row = db.execute(
            "SELECT id FROM users WHERE username=?", (TEMP_USER,)
        ).fetchone()
        if row is None:
            create_user(db, TEMP_USER, TEMP_PASSWORD, ["platform_admin"])
        db.execute(
            "UPDATE users SET active=1, school_view=1, school_full=1 WHERE username=?",
            (TEMP_USER,),
        )
        db.commit()
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
    csrf = login.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    source = "模拟演示数据（研究生院）"
    if extended:
        for (college, major), credits in ((CS, 20), (SE, 16)):
            response = client.post(
                "/api/training-requirements",
                json={"college": college, "major": major, "required_credits": credits,
                      "repeat_policy": "max_passed_credits", "confirmed": True, "reason": "合成演示口径"},
                headers=headers,
            )
            assert response.status_code == 200, response.text

    def import_basic(rows, url_preview, url_confirm, extra=None):
        template = client.get(template_url).content
        data = fill(template, rows)
        preview = client.post(
            url_preview,
            data={"source_department": source, **(extra or {})},
            files={"file": ("fresh-demo.xlsx", data, XLSX)},
            headers=headers,
        )
        assert preview.status_code == 200, preview.text
        batch = preview.json()
        confirmed = client.post(url_confirm.format(id=batch["id"]), headers=headers)
        assert confirmed.status_code == 200, confirmed.text
        return confirmed.json()

    # 1) 基础档案
    basic_rows = [
        {
            "学号": number,
            "姓名": name,
            "所属学院": college,
            "专业": major,
            "培养层次": "硕士",
            "入学年份": year,
            "前置院校": prior,
            "学制": "2.5年",
            "入学方式": entry,
            "学习形式": "全日制",
            "学位类型": degree,
            "学籍状态": status,
            "学籍异动类型": mobility or "",
            "学籍异动时间": mobility_date or "",
            **({
                "盲审送审批次": f"{int(year) + 2}年模拟送审",
                "盲审论文应交日期": f"{int(year) + 2}-04-10",
                "盲审论文实际提交日期": f"{int(year) + 2}-04-09" if int(number[-2:]) % 12 else "",
                "盲审论文提交状态": "已提交" if int(number[-2:]) % 12 else "未提交",
                "预计毕业日期": f"{int(year) + 2}-06-30",
                "实际毕业日期": f"{int(year) + 2}-{'07-15' if int(number[-2:]) % 3 == 0 else '06-25'}"
                    if int(year) <= 2024 and int(number[-2:]) % 12 else "",
                "毕业去向": ("工业界", "学术界", "创业")[int(number[-2:]) % 3],
                "成果核对起始学期": f"{year}秋",
                "成果核对截止学期": f"{int(year) + 2}春",
                "研究方向": ("智能计算" if college == CS[0] else "软件质量工程")
                    if int(number[-2:]) <= 12 else
                    ("数据科学" if college == CS[0] else "服务计算"),
            } if extended else {}),
        }
        for number, name, (college, major), year, prior, entry, degree, status, mobility, mobility_date in STUDENTS
    ]
    template_url = "/api/templates/basic"
    result = import_basic(basic_rows, "/api/imports/basic/preview", "/api/imports/{id}/confirm")
    print("basic:", result.get("counts") if isinstance(result, dict) else result)

    # 2) 课程
    template_url = "/api/templates/courses"
    result = import_basic(
        courses_rows(),
        "/api/imports/courses/preview",
        "/api/imports/courses/{id}/confirm",
    )
    print("courses:", result.get("counts") if isinstance(result, dict) else result)

    # 3) 选题与中期
    by_number = {number: (name, (college, major)) for number, name, (college, major), *_ in STUDENTS}
    for category, batch_name in (("topic", TOPIC_BATCH), ("midterm", MIDTERM_BATCH)):
        rows = []
        for number, (title, score) in TOPICS.items():
            name, (college, major) = by_number[number]
            year = 2000 + int(number[:2]) if extended else 2023 if number.startswith("235") else 2024
            if extended and category == "midterm":
                score = max(60, min(99, score + (int(number[-2:]) * 11 % 17) - 8))
            term = f"{year + 1}春"
            if category == "midterm" and number.startswith("235"):
                term = "2025春"
            rows.append(
                {
                    "学号": number,
                    "姓名": name,
                    "考核批次": batch_name,
                    "评分制度": "百分制",
                    "原始成绩": score,
                    "业务通过结果": "通过",
                    "完成状态": "通过",
                    "选题标题": title if category == "topic" else "",
                    "实际日期": f"{year + (1 if category == 'topic' else 2)}-04-15" if extended else (
                        "2025-04-15" if category == "topic" else ("2025-04-18" if number.startswith("235") else "2026-04-20")
                    ),
                    "计划日期": f"{year + (1 if category == 'topic' else 2)}-04-{'10' if score < 70 else '20'}" if extended else "",
                    "所属学院": college,
                    "专业": major,
                }
            )
        template_url = f"/api/templates/milestones/{category}"
        result = import_basic(
            rows,
            f"/api/milestones/{category}/preview",
            "/api/milestone-imports/{id}/confirm",
        )
        print(f"{category}:", result.get("counts") if isinstance(result, dict) else result)

    # 4) 四类成果
    for category, key, title, extras, entries in (
        ("research_papers", "业务编号/DOI", "论文标题", ("发表年份",), PAPERS),
        ("patents", "申请号", "专利名称", ("专利类型", "申请日期"), PATENTS),
        ("awards", "业务编号", "获奖项目名称", ("获奖等级", "获奖年份"), AWARDS),
        ("conferences", "业务编号", "会议名称", ("报告类型", "会议日期"), CONFERENCES),
    ):
        endpoint = "research-outputs" if category == "research_papers" else category
        rows = []
        for entry in entries:
            business_key, item_title = entry[0], entry[1]
            extra_values = entry[2:-1]
            participants = entry[-1]
            for pnumber, pname, order, role in participants:
                _, (college, major) = by_number[pnumber]
                row = {
                    key: business_key,
                    title: item_title,
                    "学号": pnumber,
                    "姓名": pname,
                    "作者次序": order,
                    "参与角色": role,
                    "所属学院": college,
                    "专业": major,
                }
                for label, value in zip(extras, extra_values):
                    row[label] = value
                if extended and category == "research_papers":
                    row.update({"评价体系": "模拟期刊评价", "评价年度": entry[2], "期刊分区": "Q2", "影响因子": 2.5})
                    row["发表日期"] = f"{entry[2]}-{'04' if business_key.endswith('01') else '09'}-15"
                if extended and category == "awards":
                    row["获奖日期"] = f"{entry[3]}-11-01"
                    row["资源类型"] = "奖学金" if business_key.endswith("-02") else "竞赛获奖"
                if extended and category == "conferences":
                    row["会议范围"] = "国际" if business_key.endswith("-02") else "国内"
                if extended and category == "patents":
                    row.update({"转化状态": "未转化"})
                rows.append(row)
        template = client.get(f"/api/{endpoint}/template").content
        preview = client.post(
            f"/api/{endpoint}/preview",
            data={"source_department": "模拟演示数据（图书馆）"},
            files={"file": ("fresh-demo.xlsx", fill(template, rows), XLSX)},
            headers=headers,
        )
        assert preview.status_code == 200, preview.text
        batch = preview.json()
        confirmed = client.post(
            f"/api/{endpoint}/previews/{batch['id']}/confirm",
            json={"accept_changes": True},
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        print(f"{category}: imported")

    # 5) 导师课题组目录与关系
    mentors = {}
    for number, name, (college, major) in MENTORS:
        created = client.post(
            "/api/mentor-groups/directory/mentors",
            json={"number": number, "name": name, "college": college, "major": major},
            headers=headers,
        )
        assert created.status_code == 200, created.text
        mentors[number] = created.json()["id"]
        if extended:
            profile = client.post(
                f"/api/mentor-groups/directory/mentors/{mentors[number]}/profile",
                json=demo_mentor_profile(number, college),
                headers=headers,
            )
            assert profile.status_code == 200, profile.text
    groups = {}
    for number, name, (college, major) in GROUPS:
        created = client.post(
            "/api/mentor-groups/directory/groups",
            json={"number": number, "name": name, "college": college, "major": major},
            headers=headers,
        )
        assert created.status_code == 200, created.text
        groups[number] = created.json()["id"]
    roster = []
    for offset in range(0, len(STUDENTS), 200):
        page = client.get("/api/students", params={"limit": 200, "offset": offset})
        assert page.status_code == 200, page.text
        roster.extend(page.json()["items"])
    student_ids = {item["data"]["学号"]: item["id"] for item in roster}
    assert set(by_number) <= student_ids.keys()
    for pnumber, mnumber, gnumber, start, end, reason in RELATIONS:
        body = {
            "student_id": student_ids[pnumber],
            "mentor_id": mentors[mnumber],
            "group_id": groups[gnumber],
            "start_date": start,
            "source_department": "模拟演示数据（学院培养办）",
            "reason": reason,
        }
        if end:
            body["end_date"] = end
        created = client.post("/api/mentor-groups/relations", json=body, headers=headers)
        assert created.status_code == 200, (pnumber, created.text)
    print("directory+relations: imported")

    # 6) 引用快照（仅科研论文）
    outputs = client.get("/api/research-outputs").json()["items"]
    output_ids = {item["business_key"]: item["id"] for item in outputs}
    for business_key, count in CITATIONS.items():
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
        if extended:
            earlier = client.post(
                f"/api/research-outputs/{output_ids[business_key]}/citations",
                json={"date": "2026-07-01", "count": max(0, count - 4), "source_department": "模拟演示数据（图书馆）",
                      "expected_version": 0, "confirmed": True, "reason": "合成引用起点"},
                headers=headers,
            )
            assert earlier.status_code == 200, earlier.text
    print("citations: imported")

    if extended:
        seed_evaluation_and_papers(client, headers, student_ids)

    client.post("/api/logout", headers=headers)

    with connection(DB) as db:
        db.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)", (TEMP_USER,))
        # 审计外键要求保留用户行；停用并改写密码使其无法登录
        db.execute(
            "UPDATE users SET active=0, password_hash=? WHERE username=?",
            ("refresh-demo-disabled", TEMP_USER),
        )
        db.commit()
    print("temp user deactivated")

    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
        for table in ("students", "course_records", "milestone_records", "research_outputs", "mentor_directory"):
            print(table, db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        if extended:
            for table in ("course_records", "milestone_records", "mentor_group_relations", "evaluation_snapshots"):
                linked = db.execute(
                    f"SELECT count(DISTINCT student_id) FROM {table}"
                ).fetchone()[0]
                assert linked == len(STUDENTS), (table, linked)
            for table in ("research_outputs", "patents_outputs", "awards_outputs", "conferences_outputs"):
                linked = db.execute(
                    f"""SELECT count(DISTINCT s.id) FROM {table} o
                        JOIN json_each(o.payload, '$.participants') p
                        JOIN students s ON s.student_number=json_extract(p.value, '$.student_number')"""
                ).fetchone()[0]
                assert linked >= 200, (table, linked)
            paired = db.execute(
                """SELECT count(*) FROM (
                   SELECT p.student_id FROM paper_versions p JOIN external_assessments a
                   ON a.paper_version_id=p.id GROUP BY p.student_id
                   HAVING count(DISTINCT a.category)=2)"""
            ).fetchone()[0]
            assert paired >= 200, paired
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
            print(f"verified: {len(STUDENTS)} linked student histories, {paired} PDF/assessment pairs")


def seed_evaluation_and_papers(client, headers, student_ids):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    from aqp.paper_worker import run_once

    totals = 0
    for number, student_id in student_ids.items():
        response = client.post(
            "/api/evaluation-snapshots", headers=headers,
            json={"student_id": student_id},
        )
        assert response.status_code == 200, response.text
        total = response.json()["total"]
        assert (total is None) == (int(number[-2:]) % 12 == 0), response.json()
        totals += total is not None
    print(f"evaluation: {totals} complete, {len(student_ids) - totals} intentional gaps")

    for number, student_id in student_ids.items():
        if int(number[-2:]) % 12 == 0:
            continue
        writer = PdfWriter()
        page = writer.add_blank_page(595, 842)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): DictionaryObject({
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }),
            }),
        })
        stream = DecodedStreamObject()
        stream.set_data(
            b"BT /F1 12 Tf 40 780 Td (Synthetic Thesis - Demonstration Only) Tj "
            b"0 -24 Td (1 Introduction) Tj 0 -24 Td (2 Experimental Method) Tj "
            b"0 -24 Td (3 Conclusion) Tj 0 -24 Td (References) Tj ET"
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
        pdf = io.BytesIO()
        writer.write(pdf)
        response = client.post(
            "/api/papers", headers=headers,
            data={"title": TOPICS[number][0], "student_id": student_id,
                  "expected_version": 0, "covered_student_ids": json.dumps([student_id])},
            files={"file": (f"{number}.pdf", pdf.getvalue(), "application/pdf")},
        )
        assert response.status_code == 200, response.text
        assert run_once(DB)
        with connection(DB) as db:
            paper_version = db.execute("SELECT MAX(id) FROM paper_versions").fetchone()[0]
        for category, base in (("blind_reviews", 78), ("defenses", 82)):
            response = client.post(
                "/api/external-assessments", headers=headers,
                json={"category": category, "paper_version_id": paper_version,
                      "batch": "模拟评分批次", "anonymous_code": f"{number}-{category}",
                      "scores": {"quality": base + int(number[-2:]) * 7 % 17},
                      "comment": "模拟评语：方法清晰，有创新点，参考文献可补充。",
                      "source": "模拟演示数据（学位办）"},
            )
            assert response.status_code == 200, response.text


def demo_mentor_profile(number: str, college: str) -> dict[str, str]:
    group = int(number[4:])
    base = "智能计算" if college == CS[0] else "软件质量工程"
    return {
        "direction": (base, f"{base}与系统", f"{base}应用")[((group - 1) // 4)],
        "title": "教授" if group in (9, 10, 11) else "副教授" if group != 12 else "讲师",
        "effective_on": "2020-01-01",
    }


def prepare_extended_demo():
    STUDENTS.clear()
    TOPICS.clear()
    MENTORS.clear()
    GROUPS.clear()
    RELATIONS.clear()
    PAPERS.clear()
    PATENTS.clear()
    AWARDS.clear()
    CONFERENCES.clear()
    CITATIONS.clear()
    surnames = "陈林赵孙周吴郑何许高朱梁沈冯宋蒋韩罗谢唐邓叶姜徐"
    given_names = ("思远", "雨桐", "启铭", "嘉宁", "子墨", "婧怡", "博文", "晓萌",
                   "亦航", "书瑶", "明澈", "若岚", "一帆", "清越", "景行", "知夏",
                   "昱辰", "安然", "昕妍", "宇谦", "泽言", "舒宁", "晨曦", "子谦")
    subjects = (
        ("联邦学习的非独立同分布优化", "低资源跨语言信息检索", "医学影像的弱监督分割",
         "图神经网络的被动异常检测", "视觉问答中的跨模态对齐", "边缘设备上的模型量化",
         "多视角点云配准", "知识图谱的实体对齐", "时序数据的自监督表示",
         "低照度图像增强", "稀疏注意力的长文本建模", "面向科学文献的信息抽取"),
        ("微服务调用链的故障定位", "大规模软件仓库中的缺陷预测", "分布式日志的异常检测",
         "面向持续交付的测试用例选择", "云原生应用的弹性调度", "基于语义的代码检索",
         "需求变更的影响分析", "开源依赖库的版本演化", "软件架构的自动化违例检测",
         "移动应用界面的可访问性测试", "服务负载的在线性能诊断", "持续集成流水线的资源优化"),
    )
    schools = ("南京大学", "浙江大学", "厦门大学", "西安交通大学", "东南大学", "四川大学")
    for scope_index, (college, major) in enumerate((CS, SE), 1):
        mentor_names = (
            ("梁文博", "沈静怡", "贺明宇", "秦雅楠", "杜志远", "赵秋宁", "罗彦博", "韩思敏", "许明川", "曹昕然", "周弘毅", "陈嘉平"),
            ("许嘉明", "周雨薇", "田子恒", "薛晓琳", "宋文清", "陆静怡", "吴博涵", "程佳琪", "邓志宏", "严晓峰", "顾书宁", "蒋怡君"),
        )
        group_names = (
            ("智能计算与感知", "数据科学与知识工程", "计算成像", "自然语言处理", "视觉计算", "知识推理", "边缘智能", "智能系统", "学习理论", "模式识别", "计算优化", "科学计算"),
            ("软件质量工程", "服务计算与系统", "程序分析", "可信软件", "云原生系统", "软件测试", "数据工程", "系统架构", "服务治理", "工程自动化", "软件演化", "人机交互"),
        )
        for group in range(1, 13):
            mentor = f"T10{scope_index}{group}"
            team = f"RG{scope_index}0{group}"
            MENTORS.append((mentor, mentor_names[scope_index - 1][group - 1], (college, major)))
            GROUPS.append((team, group_names[scope_index - 1][group - 1], (college, major)))
        for year in range(2020, 2025):
            for index in range(1, 25):
                number = f"{year % 100}50{scope_index}{index:03}"
                name_index = (scope_index - 1) * 12 + index - 1
                name = surnames[name_index % 24] + given_names[(name_index + scope_index * 3 + (year - 2020) * 4) % 24]
                group = (index - 1) // 2 + 1
                STUDENTS.append((number, name, (college, major), str(year), schools[(index + year) % len(schools)],
                                 "统一考试", "学术型学位", "正常", "转导师" if index == 5 else "",
                                 f"{year + 1}-09-01" if index == 5 else ""))
                title = f"{subjects[scope_index - 1][(index + year - 2024) % 12]}研究"
                TOPICS[number] = (title, 61 + (index * 7) % 37)
                RELATIONS.append((number, f"T10{scope_index}{group}", f"RG{scope_index}0{group}",
                                  f"{year}-09-01", "", "合成指导关系"))
                people = [(number, name, 1, "第一参与人")]
                papers = 3 if index <= 5 else 1 + index % 3
                for paper in range(papers):
                    key = f"rp-{number}-{paper + 1:02}"
                    PAPERS.append((key, f"{title}：{('方法设计', '实验分析', '应用评估')[paper]}", year + 1, people))
                    CITATIONS[key] = (10 if index <= 5 else 0) + paper * 4 + index
                if index % 12:
                    PATENTS.append((f"P-{number}", f"一种用于{title.removesuffix('研究')}的方法及系统", "发明", f"{year + 1}-08-01", people))
                AWARDS.append((f"A-{number}", "研究生创新实践竞赛", "校级", year + 1, people))
                CONFERENCES.append((f"C-{number}", "研究生学术论坛", "口头报告", f"{year + 1}-09-01", people))
                if index <= 5:
                    PATENTS.append((f"P-{number}-02", f"一种{title.removesuffix('研究')}实现装置", "发明", f"{year + 1}-10-01", people))
                    AWARDS.append((f"A-{number}-02", "研究生学术成果奖", "校级", year + 1, people))
                    CONFERENCES.append((f"C-{number}-02", "青年学者学术交流会", "口头报告", f"{year + 1}-11-01", people))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--isolated-demo", type=Path, required=True, help="新的独立演示目录")
    args = parser.parse_args()
    demo_dir = args.isolated_demo.resolve()
    demo_dir.mkdir(parents=True, exist_ok=False)
    DB = demo_dir / "demo.sqlite3"
    os.environ["AQP_ATTACHMENTS"] = str(demo_dir / "attachments")
    TEMP_PASSWORD = secrets.token_urlsafe(24)
    create_app(DB)
    prepare_extended_demo()
    main(extended=True)
    from aqp.accounts import create_user

    password = secrets.token_urlsafe(18)
    with connection(DB) as db:
        create_user(db, "demo-admin", password, ["platform_admin"])
        db.execute("UPDATE users SET school_view=1,school_full=1 WHERE username='demo-admin'")
    (demo_dir / "login.txt").write_text(f"账号 demo-admin\n密码 {password}\n", encoding="utf-8")
