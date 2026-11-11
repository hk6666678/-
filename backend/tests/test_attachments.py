# ruff: noqa: F811
from io import BytesIO

from pypdf import PdfWriter
from test_accounts import (
    client,  # noqa: F401
    login_admin,
)
from test_milestones import grant, sheet
from test_students import workbook


def setup_record(client, headers, linked=True):
    grant(client, headers)
    if linked:
        batch = client.post(
            "/api/imports/basic/preview",
            headers=headers,
            data={"source_department": "合成来源"},
            files={"file": ("basic.xlsx", workbook())},
        ).json()
        client.post(f"/api/imports/{batch['id']}/confirm", headers=headers)
    batch = client.post(
        "/api/milestones/topic/preview",
        headers=headers,
        data={"source_department": "合成来源"},
        files={"file": ("sample.xlsx", sheet())},
    ).json()
    client.post(f"/api/milestone-imports/{batch['id']}/confirm", headers=headers)
    return client.get("/api/milestones").json()["items"][0]["id"]


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def test_synthetic_pdf_versions_and_independent_download_permission(client):
    headers = login_admin(client)
    record = setup_record(client, headers)
    url = f"/api/milestones/{record}/attachments"
    result = client.post(
        url,
        headers=headers,
        data={"expected_version": 0, "covered_student_ids": "[1]"},
        files={"file": ("synthetic.pdf", pdf())},
    )
    assert result.status_code == 200, result.text
    item = result.json()
    assert item["version"] == 1
    assert client.get(f"/api/attachments/{item['id']}/download").status_code == 403
    assert client.get(f"/api/attachments/{item['id']}/preview").status_code == 403
    assert len(client.get(url).json()["items"]) == 1
    assert (
        client.post(
            url,
            headers=headers,
            data={"expected_version": 0, "covered_student_ids": "[1]"},
            files={"file": ("synthetic.pdf", pdf())},
        ).status_code
        == 409
    )


def test_pending_identity_cannot_upload(client):
    headers = login_admin(client)
    record = setup_record(client, headers, False)
    assert (
        client.post(
            f"/api/milestones/{record}/attachments",
            headers=headers,
            data={"expected_version": 0, "covered_student_ids": "[1]"},
            files={"file": ("synthetic.pdf", pdf())},
        ).status_code
        == 409
    )


def permissions(client, headers, operations, college="示例学院"):
    from uuid import uuid4

    user = client.get("/api/me").json()["user"]
    result = client.put(
        f"/api/users/{user['id']}/grants",
        headers=headers,
        json={
            "expected_version": user["version"],
            "request_id": str(uuid4()),
            "grants": [
                {
                    "category": "topic",
                    "operation": op,
                    "college": college,
                    "major": "计算机",
                }
                for op in operations
            ],
        },
    )
    assert result.status_code == 200


def docx():
    from zipfile import ZipFile

    out = BytesIO()
    with ZipFile(out, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic document &lt;script&gt;never execute&lt;/script&gt;</w:t></w:r></w:p></w:body></w:document>',
        )
    return out.getvalue()


def test_synthetic_docx_history_and_live_revocation(client):
    headers = login_admin(client)
    record = setup_record(client, headers)
    url = f"/api/milestones/{record}/attachments"
    permissions(client, headers, ["maintain", "identity", "view", "download"])
    first = client.post(
        url,
        headers=headers,
        data={"expected_version": 0, "covered_student_ids": "[1]"},
        files={"file": ("../synthetic.pdf", pdf())},
    ).json()
    raw = docx()
    second = client.post(
        url,
        headers=headers,
        data={"expected_version": 1, "covered_student_ids": "[1]"},
        files={"file": ("synthetic.docx", raw)},
    )
    assert second.status_code == 200, second.text
    second = second.json()
    assert [v["version"] for v in client.get(url).json()["items"]] == [2, 1]
    assert client.get(f"/api/attachments/{first['id']}/download").content == pdf()
    downloaded = client.get(f"/api/attachments/{second['id']}/download")
    assert (
        downloaded.content == raw
        and "attachment;" in downloaded.headers["content-disposition"]
    )
    preview = client.get(f"/api/attachments/{second['id']}/preview")
    assert preview.status_code == 200 and preview.headers["content-type"].startswith(
        "text/plain"
    )
    assert "<script>never execute</script>" in preview.text
    assert client.get("/attachments/synthetic.docx").status_code == 404
    permissions(client, headers, ["view", "download", "maintain"])
    assert client.get(url).json()["items"][0]["original_filename"] == "名称已脱敏"
    for action in ["download", "preview"]:
        assert client.get(f"/api/attachments/{first['id']}/{action}").status_code == 403
    permissions(client, headers, ["identity", "view", "download"], "其他学院")
    assert client.get(url).status_code == 403


def test_invalid_file_and_unverified_coverage_rejected(client):
    headers = login_admin(client)
    record = setup_record(client, headers)
    url = f"/api/milestones/{record}/attachments"
    for content, ids, status in [
        (b"fake", "[1]", 422),
        (pdf(), "[999]", 422),
        (pdf(), "[1,999]", 403),
    ]:
        assert (
            client.post(
                url,
                headers=headers,
                data={"expected_version": 0, "covered_student_ids": ids},
                files={"file": ("synthetic.pdf", content)},
            ).status_code
            == status
        )
    assert client.get(url).json()["items"] == []

