"""Synthetic small inputs; expected outcomes are specified in test_trial_samples."""

from io import BytesIO

from openpyxl import load_workbook


def sample_workbook(template: bytes, category: str, invalid: bool = False) -> bytes:
    book = load_workbook(BytesIO(template))
    sheet = book.active
    assert sheet is not None
    columns = [cell.value for cell in sheet[2]]
    if sheet.max_row > 2:
        sheet.delete_rows(3, sheet.max_row - 2)
    statuses = (
        ["通过"] * 4 + ["不通过"] * 2 + ["", ""] if category == "courses" else ["通过"]
    )
    for index, status in enumerate(statuses):
        row = {
            "学号": "SYN-TRIAL-001",
            "姓名": "合成学生",
            "所属学院": "合成试用学院",
            "专业": "合成专业",
            "培养层次": "硕士",
            "入学年份": "2025",
            "课程编号": "SYN-C1",
            "课程名称": "合成课程",
            "修读学期": "2025秋",
            "考核次数": index + 1,
            "评分制度": "百分制",
            "原始成绩": 80 if status else "",
            "业务通过结果": status,
            "考核批次": "合成批次",
            "选题标题": "合成选题",
            "学分": 2,
        }
        if invalid:
            row["学号"] = ""
        sheet.append([row.get(column, "") for column in columns])
    output = BytesIO()
    book.save(output)
    return output.getvalue()
