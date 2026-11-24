# ruff: noqa: F811
from io import BytesIO

import pytest
from test_accounts import client, login_admin  # noqa: F401

PDF = "application/pdf"
WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def seed(client, tmp_path, operations=("view", "analyze", "export")):
    from test_reports import give_grants, seed_patent, seed_student

    headers = login_admin(client)
    me = client.get("/api/me").json()["user"]
    give_grants(client, headers, me, ["basic", "patents"], list(operations))
    from aqp.store import connection

    with connection(tmp_path / "accounts.sqlite3") as db:
        # seed_patent derives the participant name from the number, so keep them in step
        seed_student(db, 1, "S1")
        seed_patent(db, "P1", "S1", "2025-03-01")
    return headers


def pdf_text(body: bytes) -> str:
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(body)).pages)


def word_text(body: bytes) -> str:
    from docx import Document

    document = Document(BytesIO(body))
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        parts.extend(cell.text for row in table.rows for cell in row.cells)
    return "\n".join(parts)


def text_of(response) -> str:
    assert response.status_code == 200, response.text[:300]
    if response.headers["content-type"].startswith(PDF):
        assert response.content.startswith(b"%PDF")
        return pdf_text(response.content)
    assert response.headers["content-type"].startswith(WORD)
    return word_text(response.content)


CASES = [
    ("/api/reports/students/1/export", {}, "report-student-1", "学生发展报告"),
    ("/api/reports/mentor-groups/export", {"as_of": "2026-01-01"}, "report-group-all", "导师课题组培养报告"),
    ("/api/reports/colleges/export", {"college": "synthetic", "major": "synthetic"}, "report-college", "学院学科质量报告"),
]


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
@pytest.mark.parametrize("path, params, filename, title", CASES)
def test_reports_render_as_pdf_and_word_with_the_same_grants(client, tmp_path, fmt, path, params, filename, title):
    seed(client, tmp_path)
    assert client.get(path, params=params).status_code == 200
    response = client.get(path, params={**params, "format": fmt})
    text = text_of(response)
    assert response.headers["content-disposition"] == f'attachment; filename="{filename}.{fmt}"'
    assert response.headers["cache-control"] == "no-store"
    assert title in text
    # 没有身份授权时，学生报告只出现研究编号
    assert "Synthetic1" not in text and "S1" not in text
    # 口径说明随文档一起输出
    assert "当前权限" in text
    from aqp.store import connection

    with connection(tmp_path / "accounts.sqlite3") as db:
        targets = [row[0] for row in db.execute("SELECT target FROM audit WHERE action='reports.export' ORDER BY id")]
    # Excel 与排版文档各导出一次，留痕里带上格式
    assert len(targets) == 2 and targets[-1].endswith(f":{fmt}")


def test_student_report_documents_carry_identity_only_when_authorized(client, tmp_path):
    seed(client, tmp_path, ("view", "analyze", "export", "identity"))
    for fmt in ("pdf", "docx"):
        text = text_of(client.get("/api/reports/students/1/export", params={"format": fmt}))
        assert "S1" in text and "Synthetic1" in text, fmt
        # 纳入的成果段落列出标题和年份，未纳入的段落写明原因而不是留空
        assert "Patent P1" in text and "2025" in text, fmt
        assert "未纳入" in text and "授权不足" in text, fmt
        assert "含学生身份信息" in text, fmt


def test_report_documents_keep_the_export_boundary(client, tmp_path):
    seed(client, tmp_path, ("view", "analyze"))
    for fmt in ("pdf", "docx"):
        denied = client.get("/api/reports/students/1/export", params={"format": fmt})
        assert denied.status_code == 403, fmt
        assert "报告导出授权不足" in denied.json()["detail"]
        assert client.get("/api/reports/colleges/export", params={"format": fmt, "college": "synthetic", "major": "synthetic"}).status_code == 403
    denied_events = client.get("/api/audit", params={"action": "reports.access"}).json()["items"]
    assert denied_events and all(event["outcome"] == "denied" for event in denied_events)
    assert client.get("/api/reports/students/1/export", params={"format": "html"}).status_code == 422


def test_pdf_export_explains_a_missing_chinese_font(client, tmp_path, monkeypatch):
    from aqp import report_documents
    from fastapi import HTTPException

    seed(client, tmp_path)

    def no_font() -> str:
        raise HTTPException(503, "服务器缺少中文字体，无法生成 PDF；请改用 Word 或 Excel 导出")

    monkeypatch.setattr(report_documents, "register_font", no_font)
    denied = client.get("/api/reports/students/1/export", params={"format": "pdf"})
    assert denied.status_code == 503
    assert "Word" in denied.json()["detail"]
    # 同一次授权下 Word 不依赖字体，照常生成
    assert client.get("/api/reports/students/1/export", params={"format": "docx"}).status_code == 200


def test_font_registration_finds_an_installed_chinese_font():
    from aqp.report_documents import FONT_CANDIDATES, register_font

    assert register_font() in {candidate[0] for candidate in FONT_CANDIDATES}


def test_report_documents_state_missing_and_unauthorized_sections(client, tmp_path):
    seed(client, tmp_path)
    text = text_of(client.get("/api/reports/colleges/export", params={"format": "docx", "college": "synthetic", "major": "synthetic"}))
    assert "缺失" in text
    assert "未纳入" in text
    assert "在册学生 1 人" in text
    group = text_of(client.get("/api/reports/mentor-groups/export", params={"format": "docx", "as_of": "2026-01-01"}))
    assert "统计日期 2026-01-01" in group
