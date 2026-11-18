"""Explicit opt-in live test; not collected by ordinary pytest discovery."""

# ruff: noqa: F811
import logging
import os
from io import BytesIO

import pytest
from aqp import model_connection
from aqp.paper_worker import run_once
from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from test_accounts import client, login_admin  # noqa: F401
from test_agent import replace_grants, synthetic_student_and_analysis
from test_papers import paper_setup, text_pdf, update_grants, upload_paper


def synthetic_paper_pdf():
    writer = PdfWriter()
    page = writer.add_page(PdfReader(BytesIO(text_pdf())).pages[0])
    stream = DecodedStreamObject()
    lines = [
        "SYNTHETIC DEMONSTRATION ONLY",
        "Research question: Does synthetic method A improve learning?",
        "Method: We compare two synthetic teaching methods.",
        "Author claim: We propose a synthetic feedback framework.",
        "Outcome: Synthetic group A has a mean score of 80.",
    ]
    commands = " 0 -20 Td ".join(f"({line}) Tj" for line in lines)
    stream.set_data(f"BT /F1 10 Tf 10 250 Td {commands} ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.mark.skipif(
    os.environ.get("AQP_LIVE_SYNTHETIC") != "approved-bailian-5-cny",
    reason="Run only through the local credential launcher",
)
def test_live_synthetic_flow(client, tmp_path, monkeypatch, caplog):
    assert not os.environ.get("AQP_ATTACHMENTS"), "Remove inherited attachment override"
    headers = login_admin(client)
    assert client.post("/api/model/check", headers=headers).status_code == 503
    synthetic_student_and_analysis(client, headers)
    configured = client.put(
        "/api/model/config",
        headers=headers,
        json={
            "enabled": True,
            "approved": True,
            "external_authorized": True,
            "approval_reference": "User Q5-Q7: synthetic only; budget target CNY 5",
            "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen3.8-max-0902",
            "key_env": "AQP_MODEL_KEY_BAILIAN",
            "allowed_purposes": ["agent", "papers"],
            "max_input_chars": 16000,
            "max_output_tokens": 1024,
            "timeout_seconds": 60,
        },
    )
    assert configured.status_code == 200
    real_runner = model_connection.default_runner
    calls = []

    def limited(config, text):
        if len(calls) >= 6:
            raise HTTPException(429, "Live test request limit reached")
        calls.append(len(text))
        return real_runner(config, text)

    monkeypatch.setattr(model_connection, "default_runner", limited)
    caplog.set_level(logging.INFO, logger="aqp.model_connection")
    fixture_db = (tmp_path / "accounts.sqlite3").resolve()

    def post_fixture(url, **kwargs):
        # Only fixed requests constructed below reach this helper. The test
        # client has no listener and accepts no operator-supplied materials.
        token = model_connection.synthetic_fixture_db.set(fixture_db)
        try:
            return client.post(url, headers=headers, **kwargs)
        finally:
            model_connection.synthetic_fixture_db.reset(token)

    try:
        assert (
            client.post(
                "/api/agent/query",
                headers=headers,
                json={"question": "来源未经确认的输入"},
            ).status_code
            == 403
        )
        assert calls == []
        checked = post_fixture("/api/model/check")
        print(f"Connection HTTP status: {checked.status_code}")
        assert checked.status_code == 200
        result = post_fixture(
            "/api/agent/query",
            json={"question": "统计示例学院计算机专业学生人数，这是模拟数据测试。"},
        )
        print(f"Agent HTTP status: {result.status_code}")
        assert result.status_code == 200, "Agent request failed"
        data = result.json()
        assert data["plan"]["tool"] == "student_counts"
        assert data["tool_result"]["total"] == 1
        assert "系统依据" in data["answer"]

        # No grants: denied before any model call.
        replace_grants(client, headers, [])
        before = len(calls)
        assert (
            client.post(
                "/api/agent/query",
                headers=headers,
                json={"question": "查询001合成学生的档案"},
            ).status_code
            == 403
        )
        assert len(calls) == before

        headers = paper_setup(client)
        pdf = synthetic_paper_pdf()
        source = PdfReader(BytesIO(pdf)).pages[0].extract_text()
        paper = upload_paper(client, headers, pdf).json()
        assert run_once(tmp_path / "accounts.sqlite3")
        update_grants(
            client, headers, ["view", "maintain", "analyze", "identity", "download"]
        )
        response = post_fixture(f"/api/papers/{paper['id']}/semantic")
        assert response.status_code == 200
        features = response.json()
        print(f"Paper extraction status: {features['status']}")
        assert features["status"] in {"partial", "succeeded"}
        for key in ["research_question", "method"]:
            assert features["features"][key]["status"] == "available"
        for feature in features["features"].values():
            assert feature["status"] in {"available", "missing"}
            if feature["status"] == "available":
                assert feature["page"] == 1
                assert feature["quote"] in source
        before = len(calls)
        update_grants(client, headers, ["view"])
        assert (
            client.post(
                f"/api/papers/{paper['id']}/semantic", headers=headers
            ).status_code
            == 403
        )
        assert len(calls) == before
    finally:
        # No prompts, answers, credentials or provider exceptions in the summary.
        print(f"\nSynthetic live requests attempted: {len(calls)} / 6")
        for record in caplog.records:
            if record.name == "aqp.model_connection":
                print(record.getMessage())
        print("Actual billing: verify in Alibaba Cloud console; no hard CNY cap.")
