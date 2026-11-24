"""Readable PDF and Word renditions of the three-level reports.

The Excel export flattens every field path; these renditions are meant to be
read by people, so each section becomes a short statement or a small table.
They carry exactly what the report computed: a section labelled missing or
unauthorized stays labelled here instead of quietly disappearing."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from fastapi import HTTPException, Response
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.enums import TA_LEFT  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFError, TTFont  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from aqp.exports import excel_report

Block = tuple[Any, ...]
ReportFormat = Literal["xlsx", "pdf", "docx"]

OUTPUT_NAMES = {
    "research_papers": "科研论文",
    "patents": "专利",
    "awards": "获奖项目",
    "conferences": "会议",
}
MILESTONE_NAMES = {"topic": "选题", "midterm": "中期"}
COMPLETENESS_NAMES = {
    "courses": "课程",
    "topic": "选题",
    "midterm": "中期",
    "research_papers": "科研论文",
    "patents": "专利",
    "awards": "获奖",
    "conferences": "会议",
    "papers": "学位论文",
    "blind_reviews": "盲审",
    "defenses": "答辩",
}
CLOSING = (
    "本报告按读取时的当前权限生成，只包含当前授权范围内的数据；"
    "无授权或缺失的段落已如实标注，未填零。"
    "各项数值的记录与版本依据见平台对应页面及 Excel 导出。"
)
INTERNAL_LABEL = "内部资料"
SENSITIVE_LABEL = "敏感：含学生身份信息"
LISTING_LIMIT = 200
BEIJING = timezone(timedelta(hours=8))

# (family, regular file, bold file). PDF embedding needs an actual font file
# on the server; Word documents use whatever the reader has installed.
FONT_CANDIDATES = (
    ("MicrosoftYaHei", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"),
    ("SimHei", "C:/Windows/Fonts/simhei.ttf", None),
    ("SimSun", "C:/Windows/Fonts/simsun.ttc", None),
    ("DengXian", "C:/Windows/Fonts/Deng.ttf", "C:/Windows/Fonts/Dengb.ttf"),
    (
        "NotoSansCJK",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        None,
    ),
    ("WenQuanYiZenHei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", None),
    ("PingFangSC", "/System/Library/Fonts/PingFang.ttc", None),
)
_registered_font: str | None = None


def load_font(family: str, regular: str, bold: str | None) -> bool:
    """Register one family with an optional bold face; False if it fails."""
    try:
        pdfmetrics.registerFont(TTFont(family, regular, subfontIndex=0))
        if bold is not None and Path(bold).is_file():
            pdfmetrics.registerFont(TTFont(f"{family}-Bold", bold, subfontIndex=0))
            pdfmetrics.registerFontFamily(
                family,
                normal=family,
                bold=f"{family}-Bold",
                italic=family,
                boldItalic=f"{family}-Bold",
            )
    except (TTFError, OSError):
        # A font that exists but cannot be read is as unusable as none.
        return False
    return True


def register_font() -> str:
    """Register the first installed Chinese font and return its family name."""
    global _registered_font
    if _registered_font:
        return _registered_font
    for family, regular, bold in FONT_CANDIDATES:
        if Path(regular).is_file() and load_font(family, regular, bold):
            _registered_font = family
            return family
    raise HTTPException(503, "服务器缺少中文字体，无法生成 PDF；请改用 Word 或 Excel 导出")


def section_state(section: dict[str, Any]) -> str | None:
    """Wording for a section that contributes nothing; None when it has data."""
    status = section.get("status")
    if status == "unauthorized":
        return "未纳入：当前授权不足，不计数"
    if status == "missing":
        return f"缺失：{section.get('reason') or '暂无数据'}，不填零"
    return None


def generated_time(report: dict[str, Any]) -> str:
    return datetime.fromtimestamp(report["generated_at"], BEIJING).strftime("%Y-%m-%d %H:%M")


def student_blocks(report: dict[str, Any]) -> tuple[str, list[Block], bool]:
    student = report["student"]
    sections = report["sections"]
    masked = bool(student.get("identity_masked"))
    blocks: list[Block] = []
    if masked:
        blocks.append(
            ("para", f"研究对象：研究编号 {student['research_id']}（身份未授权，姓名与学号不显示）")
        )
    else:
        blocks.append(
            ("para", f"研究对象：{student['name']}　学号 {student['student_number']}")
        )
    blocks.append(
        (
            "para",
            (
                f"{student['college']}／{student['major']} · {student['level']} · "
                f"{student['entry_year']} 级"
            ),
        )
    )

    blocks.append(("heading", "课程学习"))
    courses = sections["courses"]
    state = section_state(courses)
    if state is not None:
        blocks.append(("para", state))
    else:
        blocks.append(
            (
                "para",
                (
                    f"共 {courses['total']} 门课程：通过 {courses['passed']} 门，"
                    f"不通过 {courses['failed']} 门，通过状态未知 {courses['unknown']} 门。"
                ),
            )
        )
        ratio = courses["pass_ratio"]
        blocks.append(
            (
                "para",
                f"通过比例 {ratio:.1%}。"
                if ratio is not None
                else "存在通过状态未知的课程，不计算通过比例。",
            )
        )
        if courses.get("pass_rule_version"):
            blocks.append(("note", f"通过规则版本 {courses['pass_rule_version']}。"))

    blocks.append(("heading", "选题与中期"))
    rows: list[list[str]] = []
    for key, name in MILESTONE_NAMES.items():
        section = sections["milestones"][key]
        state = section_state(section)
        if state is not None:
            rows.append([name, state])
            continue
        results = [str(item["result"]) for item in section["items"]]
        summary = "、".join(
            f"{result} {results.count(result)} 条" for result in dict.fromkeys(results)
        )
        rows.append([name, f"{section['count']} 条记录：{summary}"])
    blocks.append(("table", ["环节", "情况"], rows))

    blocks.append(("heading", "科研成果"))
    counts: list[list[str]] = []
    listing: list[list[str]] = []
    for key, name in OUTPUT_NAMES.items():
        section = sections[key]
        state = section_state(section)
        if state is not None:
            counts.append([name, "—", state])
            continue
        counts.append([name, str(section["count"]), ""])
        listing.extend(
            [name, str(item.get("year") or "年份缺失"), str(item.get("title") or "（无标题）")]
            for item in section["items"]
        )
    blocks.append(("table", ["类别", "数量", "说明"], counts))
    if listing:
        blocks.append(("table", ["类别", "年份", "成果标题"], listing[:LISTING_LIMIT]))
    if len(listing) > LISTING_LIMIT:
        blocks.append(
            ("note", f"成果较多，仅列出前 {LISTING_LIMIT} 项；完整清单见 Excel 导出。")
        )

    blocks.append(("heading", "人才评价快照"))
    evaluation = sections["evaluation"]
    state = section_state(evaluation)
    if state is not None:
        blocks.append(("para", state))
    else:
        total = evaluation.get("total")
        score = f"总分 {total:.2f}／100" if total is not None else "数据不完整，未形成总分"
        blocks.append(
            (
                "para",
                (
                    f"最新快照 #{evaluation['snapshot_id']}：{score}；"
                    f"规则版本 {evaluation['rule_version']}。"
                ),
            )
        )
        if evaluation.get("notice"):
            blocks.append(("note", str(evaluation["notice"])))
    return "学生发展报告", blocks, not masked


def group_blocks(report: dict[str, Any]) -> tuple[str, list[Block], bool]:
    blocks: list[Block] = [
        ("para", f"统计日期 {report['as_of']}"),
        (
            "para",
            (
                f"当前有效指导关系 {len(report['relation_ids'])} 条，"
                f"涉及学生 {report['student_count']} 人。"
            ),
        ),
    ]
    rows = []
    for key, name in OUTPUT_NAMES.items():
        values = report["categories"][key]
        per_student = values.get("participations_per_student")
        rows.append(
            [
                name,
                str(values["student_count"]),
                str(values["distinct_outputs"]),
                f"{per_student:.2f}"
                if per_student is not None
                else "部分成果类别未授权，不计算",
            ]
        )
    blocks.append(("heading", "学生与成果"))
    blocks.append(
        ("table", ["成果类别", "参与学生（人）", "成果去重数", "人均参与人次"], rows)
    )

    blocks.append(("heading", "毕业与按期情况"))
    graduation, delay = report["graduation"], report["delay"]
    if graduation["status"] != "descriptive":
        blocks.append(
            ("para", f"毕业情况无法统计：{graduation['reason'] or '缺少可核查的预计毕业日期'}。")
        )
    else:
        blocks.append(
            (
                "para",
                (
                    f"已到预计毕业日期 {graduation['due']} 人，其中已毕业 "
                    f"{graduation['completed']} 人。"
                ),
            )
        )
        destinations = sorted(
            (graduation.get("destinations") or {}).items(), key=lambda pair: -pair[1]
        )
        if destinations:
            blocks.append(
                ("para", "毕业去向：" + "、".join(f"{name} {count} 人" for name, count in destinations) + "。")
            )
    if delay["status"] != "descriptive":
        blocks.append(
            ("para", f"延期情况无法统计：{delay['reason'] or '缺少可核查的预计毕业日期'}。")
        )
    else:
        verified = delay["late"] + delay["on_time"]
        blocks.append(
            (
                "para",
                (
                    f"可判断按期与否 {verified} 人：按期 {delay['on_time']} 人，"
                    f"延期 {delay['late']} 人；另有 {delay['unknown']} 人缺少实际毕业日期，无法判断。"
                ),
            )
        )
    return "导师课题组培养报告", blocks, False


def college_blocks(report: dict[str, Any]) -> tuple[str, list[Block], bool]:
    scope, sections = report["scope"], report["sections"]
    blocks: list[Block] = [("para", f"范围：{scope['college']}／{scope['major']}")]
    students = sections["students"]
    state = section_state(students)
    blocks.append(
        ("para", state if state is not None else f"在册学生 {students['count']} 人。")
    )
    rows = []
    for key, name in OUTPUT_NAMES.items():
        section = sections[key]
        state = section_state(section)
        rows.append(
            [
                f"{name}成果",
                state
                or (
                    f"成果去重 {section['distinct_outputs']} 项，"
                    f"个人参与 {section['personal_participations']} 人次"
                ),
            ]
        )
    courses = sections["courses"]
    state = section_state(courses)
    if state is not None:
        rows.append(["课程学习", state])
    else:
        ratio = courses["pass_ratio"]
        text = (
            f"考核记录 {courses['records']} 条：通过 {courses['passed']} 条，"
            f"状态未知 {courses['unknown']} 条"
        )
        text += (
            f"，通过比例 {ratio:.1%}"
            if ratio is not None
            else "；存在状态未知的记录，不计算通过比例"
        )
        if courses.get("pass_rule_version"):
            text += f"；通过规则版本 {courses['pass_rule_version']}"
        rows.append(["课程学习", text])
    mentors = sections["mentor_groups"]
    state = section_state(mentors)
    rows.append(
        ["导师课题组", state or f"当前有效指导关系 {mentors['active_relations']} 条"]
    )
    blocks.append(("heading", "培养概况"))
    blocks.append(("table", ["方面", "情况"], rows))

    completeness = report.get("completeness")
    if completeness:
        blocks.append(("heading", f"{completeness['entry_year']} 级数据完整性"))
        rows = [
            [
                COMPLETENESS_NAMES.get(key, key),
                section_state(item)
                or f"缺失 {item['missing_count']} 人（{item['missing_rate']:.1%}）",
            ]
            for key, item in completeness["items"].items()
        ]
        blocks.append(
            ("table", ["数据类别", f"{completeness['student_count']} 名学生中的缺失情况"], rows)
        )
    return "学院学科质量报告", blocks, False


def report_blocks(report: dict[str, Any]) -> tuple[str, list[Block], bool]:
    """Title, readable blocks and whether the document carries identity data."""
    level = report["level"]
    title, blocks, sensitive = (
        student_blocks(report)
        if level == "student"
        else group_blocks(report)
        if level == "mentor_group"
        else college_blocks(report)
    )
    label = SENSITIVE_LABEL if sensitive else INTERNAL_LABEL
    return title, [("meta", f"{label} · 生成时间 {generated_time(report)}（北京时间）"), *blocks], sensitive


def attachment(filename: str, media_type: str, body: bytes) -> Response:
    """Build the response in one step so the length header matches the body."""
    return Response(
        body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def column_widths(count: int, available: float) -> list[float]:
    if count == 2:
        return [available * 0.25, available * 0.75]
    return [available / count] * count


def pdf_document(
    title: str, blocks: list[Block], sensitive: bool, filename: str
) -> Response:
    font = register_font()
    ink, secondary = colors.HexColor("#1d1d1f"), colors.HexColor("#6e6e73")
    base = {"fontName": font, "alignment": TA_LEFT, "textColor": ink}
    styles = {
        "title": ParagraphStyle("title", fontSize=20, leading=28, spaceAfter=4, **base),
        "heading": ParagraphStyle("heading", fontSize=13, leading=20, spaceBefore=14, spaceAfter=6, **base),
        "para": ParagraphStyle("para", fontSize=10.5, leading=17, spaceAfter=4, **base),
        "note": ParagraphStyle("note", fontSize=9, leading=14, spaceAfter=4, **{**base, "textColor": secondary}),
        "th": ParagraphStyle("th", fontSize=9.5, leading=14, **{**base, "textColor": secondary}),
        "td": ParagraphStyle("td", fontSize=9.5, leading=14, **base),
    }
    label = SENSITIVE_LABEL if sensitive else INTERNAL_LABEL
    margin = 20 * mm
    available = A4[0] - 2 * margin

    def line(text: str) -> Paragraph:
        return Paragraph(escape(text).replace("\n", "<br/>"), styles["para"])

    def decorate(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont(font, 8.5)
        canvas.setFillColor(secondary)
        canvas.drawString(margin, A4[1] - 13 * mm, "AQP-PGS 研究生培养质量研究平台")
        canvas.drawRightString(A4[0] - margin, A4[1] - 13 * mm, label)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=24 * mm,
        bottomMargin=22 * mm,
        title=title,
        author="AQP-PGS",
        subject=label,
    )
    story: list[Any] = [Paragraph(escape(title), styles["title"])]
    for block in blocks:
        kind = block[0]
        if kind == "heading":
            story.append(Paragraph(escape(str(block[1])), styles["heading"]))
        elif kind in {"note", "meta"}:
            story.append(Paragraph(escape(str(block[1])), styles["note"]))
            if kind == "meta":
                story.append(Spacer(1, 6 * mm))
        elif kind == "table":
            headers, rows = block[1], block[2]
            data = [
                [Paragraph(escape(str(cell)), styles["th"]) for cell in headers]
            ] + [
                [Paragraph(escape(str(cell)), styles["td"]) for cell in row] for row in rows
            ]
            table = Table(
                data, colWidths=column_widths(len(headers), available), repeatRows=1
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f7")),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#d2d2d7")),
                        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e8e8ed")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.extend([table, Spacer(1, 3 * mm)])
        else:
            story.append(line(str(block[1])))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(escape(CLOSING), styles["note"]))
    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return attachment(filename, "application/pdf", output.getvalue())


def docx_document(
    title: str, blocks: list[Block], sensitive: bool, filename: str
) -> Response:
    label = SENSITIVE_LABEL if sensitive else INTERNAL_LABEL
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal.font.size = Pt(10.5)
    fonts = normal.element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn("w:eastAsia"), "微软雅黑")
    fonts.set(qn("w:ascii"), "Microsoft YaHei")
    fonts.set(qn("w:hAnsi"), "Microsoft YaHei")
    heading = document.sections[0].header.paragraphs[0]
    heading.text = f"AQP-PGS 研究生培养质量研究平台 · {label}"
    heading.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    title_run = document.add_paragraph().add_run(title)
    title_run.bold = True
    title_run.font.size = Pt(22)
    title_run.font.color.rgb = RGBColor(0x1D, 0x1D, 0x1F)

    for block in blocks:
        kind = block[0]
        if kind == "heading":
            run = document.add_heading(str(block[1]), level=1).runs[0]
            run.font.color.rgb = RGBColor(0x1D, 0x1D, 0x1F)
            run.font.size = Pt(14)
        elif kind in {"note", "meta"}:
            run = document.add_paragraph(str(block[1])).runs[0]
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(0x6E, 0x6E, 0x73)
        elif kind == "table":
            headers, rows = block[1], block[2]
            table = document.add_table(rows=1, cols=len(headers))
            table.style = "Table Grid"
            for cell, text in zip(table.rows[0].cells, headers, strict=True):
                cell.text = ""
                run = cell.paragraphs[0].add_run(str(text))
                run.bold = True
                run.font.size = Pt(9.5)
            for values in rows:
                cells = table.add_row().cells
                for cell, text in zip(cells, values, strict=True):
                    cell.text = ""
                    cell.paragraphs[0].add_run(str(text)).font.size = Pt(9.5)
            document.add_paragraph()
        else:
            document.add_paragraph(str(block[1]))
    closing = document.add_paragraph(CLOSING).runs[0]
    closing.font.size = Pt(9)
    closing.font.color.rgb = RGBColor(0x6E, 0x6E, 0x73)
    output = BytesIO()
    document.save(output)
    return attachment(
        filename,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        output.getvalue(),
    )


def export_report(
    report: dict[str, Any], filename: str, fmt: str
) -> Response:
    if fmt == "xlsx":
        return excel_report(report, filename)
    title, blocks, sensitive = report_blocks(report)
    if fmt == "pdf":
        return pdf_document(title, blocks, sensitive, f"{filename}.pdf")
    return docx_document(title, blocks, sensitive, f"{filename}.docx")
