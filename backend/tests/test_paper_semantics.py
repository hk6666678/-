# ruff: noqa: F811
from test_accounts import client  # noqa: F401
from test_papers import paper_setup, text_pdf, update_grants, upload_paper


def test_semantic_disabled_preserves_local_evidence(client, tmp_path):
    from aqp.paper_worker import run_once

    headers = paper_setup(client)
    paper = upload_paper(client, headers, text_pdf()).json()
    run_once(tmp_path / "accounts.sqlite3")
    response = client.post(f"/api/papers/{paper['id']}/semantic", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert (
        client.get(f"/api/papers/{paper['id']}/evidence").json()["result"]["page_count"]
        == 1
    )
    update_grants(client, headers, ["view"])
    assert client.get(f"/api/papers/{paper['id']}/semantic").status_code == 403
    assert (
        client.post(f"/api/papers/{paper['id']}/semantic", headers=headers).status_code
        == 403
    )


def test_semantic_exact_quotes_and_immutable_attempts(client, tmp_path, monkeypatch):
    import json

    from aqp import model_connection
    from aqp.paper_worker import run_once

    headers = paper_setup(client)
    paper = upload_paper(client, headers, text_pdf()).json()
    run_once(tmp_path / "accounts.sqlite3")
    assert (
        client.put(
            "/api/model/config",
            headers=headers,
            json={
                "enabled": True,
                "approved": True,
                "approval_reference": "Synthetic software test only",
                "endpoint": "http://127.0.0.1:9999/v1",
                "model": "synthetic-test-double",
                "allowed_purposes": ["papers"],
            },
        ).status_code
        == 200
    )

    def runner(config, text):
        assert "Synthetic text" in text
        return json.dumps(
            {
                "research_question": {
                    "text": "Synthetic text",
                    "page": 1,
                    "quote": "Synthetic text",
                },
                "method": {"text": "invented", "page": 2, "quote": "Synthetic text"},
            }
        )

    monkeypatch.setattr(model_connection, "default_runner", runner)
    url = f"/api/papers/{paper['id']}/semantic"
    result = client.post(url, headers=headers).json()
    assert result["status"] == "partial"
    assert result["features"]["research_question"]["status"] == "available"
    assert result["features"]["method"]["status"] == "failed"
    assert result["features"]["author_innovation_claim"]["status"] == "missing"
    assert result["model_config_version"] == 1
    assert result["version_id"] == paper["id"]

    def failed(config, text):
        raise TimeoutError("sensitive provider error")

    monkeypatch.setattr(model_connection, "default_runner", failed)
    assert client.post(url, headers=headers).json()["status"] == "failed"
    history = client.get(url).json()["items"]
    assert len(history) == 2
    assert history[1]["features"] == result["features"]
    assert "sensitive provider error" not in str(history)
    update_grants(client, headers, ["view", "maintain", "download"])
    assert client.post(url, headers=headers).status_code == 403
    assert client.get(url).status_code == 403
