"""Validate isolated live-test setup using a test double, never an external call."""

# ruff: noqa: F811
import json

from aqp import model_connection
from live_bailian import test_live_synthetic_flow as run_flow
from test_accounts import client  # noqa: F401


def test_live_harness_offline(client, tmp_path, monkeypatch, caplog):
    answers = iter(
        [
            "OK",
            json.dumps(
                {"tool": "student_counts", "college": "示例学院", "major": "计算机"}
            ),
            "模拟数据当前范围共1名学生。",
            json.dumps(
                {
                    "research_question": {
                        "text": "Synthetic question",
                        "page": 1,
                        "quote": "Does synthetic method A improve learning?",
                    },
                    "method": {
                        "text": "Synthetic comparison",
                        "page": 2,
                        "quote": "We compare two synthetic teaching methods.",
                    },
                    "author_innovation_claim": None,
                    "outcome_description": None,
                }
            ),
        ]
    )
    calls = []

    def fake(config, text):
        calls.append(text)
        return next(answers)

    monkeypatch.setenv("AQP_MODEL_KEY_BAILIAN", "Synthetic-secret")
    monkeypatch.delenv("AQP_ATTACHMENTS", raising=False)
    monkeypatch.setattr(model_connection, "default_runner", fake)
    run_flow(client, tmp_path, monkeypatch, caplog)
    assert len(calls) == 4
    pages = json.loads(calls[-1].split("SOURCE JSON: ", 1)[1])
    assert [page["page"] for page in pages] == [1, 2]
    assert "Does synthetic method A improve learning?" in pages[0]["text"]
    assert "We compare two synthetic teaching methods." in pages[1]["text"]
