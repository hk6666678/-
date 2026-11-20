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


def error_workbook(template: bytes, category: str, error: str) -> bytes:
    """One isolated error per synthetic workbook, using real template headers."""
    if error == "unparseable":
        return b"synthetic invalid workbook"
    book = load_workbook(BytesIO(sample_workbook(template, category)))
    sheet = book.active
    columns = [cell.value for cell in sheet[2]]
    if error == "wrong-version":
        sheet.cell(1, 3, "999")
    elif error == "changed-key":
        field = {
            "basic": "入学年份",
            "courses": "原始成绩",
            "topic": "选题标题",
            "midterm": "业务通过结果",
        }[category]
        sheet.cell(
            3,
            columns.index(field) + 1,
            {"basic": "2024", "courses": 90, "topic": "变化选题", "midterm": "不通过"}[
                category
            ],
        )
    elif error == "missing-column":
        sheet.delete_cols(columns.index("学号") + 1)
    elif error == "bad-format":
        sheet.cell(
            3,
            columns.index("入学年份" if category == "basic" else "业务通过结果") + 1,
            "not-valid",
        )
    elif error == "duplicate":
        sheet.append([cell.value for cell in sheet[3]])
    elif error == "identity-conflict":
        sheet.cell(3, columns.index("姓名") + 1, "冲突姓名")
    else:
        raise ValueError(error)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def write_package(templates, output):
    """Keep small inputs and independent expectations beside the scale evidence."""
    import json

    output.mkdir(parents=True, exist_ok=False)
    for category in ["basic", "courses", "topic", "midterm"]:
        template = (templates / f"template-{category}.xlsx").read_bytes()
        (output / f"synthetic-{category}.xlsx").write_bytes(
            sample_workbook(template, category)
        )
        (output / f"errors-{category}.xlsx").write_bytes(
            sample_workbook(template, category, invalid=True)
        )
        for error in [
            "missing-column",
            "bad-format",
            "duplicate",
            "identity-conflict",
            "wrong-version",
            "unparseable",
            "changed-key",
        ]:
            (output / f"errors-{category}-{error}.xlsx").write_bytes(
                error_workbook(template, category, error)
            )
    (output / "expected.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "students": 1,
                "courses": 8,
                "topic": 1,
                "midterm": 1,
                "passed": 4,
                "failed": 2,
                "unknown": 2,
                "pass_rate": 66.67,
                "explanation": "4 / (4 + 2) * 100 = 66.67; unknown excluded",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Export synthetic small trial files")
    parser.add_argument("--templates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_package(args.templates, args.output)
