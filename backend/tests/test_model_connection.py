# ruff: noqa: F811
import pytest
from aqp import model_connection
from fastapi.testclient import TestClient
from test_accounts import client, login_admin  # noqa: F401


def test_model_disabled_by_default(client: TestClient) -> None:  # noqa: F811
    headers = login_admin(client)
    response = client.get("/api/model/config")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert client.post("/api/model/check", headers=headers).status_code == 503


def test_approved_connection_and_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = login_admin(client)
    config = {
        "expected_version": 0,
        "enabled": True,
        "approved": True,
        "approval_reference": "Synthetic test approval",
        "endpoint": "http://127.0.0.1:9999/v1",
        "model": "synthetic",
        "allowed_purposes": ["agent"],
        "key_env": "AQP_MODEL_KEY_TEST",
    }
    monkeypatch.setenv("AQP_MODEL_KEY_TEST", "Synthetic-secret")
    assert (
        client.put("/api/model/config", headers=headers, json=config).status_code == 200
    )
    assert "Synthetic-secret" not in client.get("/api/model/config").text
    sent = []

    def fake(config: model_connection.ModelConfig, text: str) -> str:
        sent.append(text)
        return "OK"

    monkeypatch.setattr(model_connection, "default_runner", fake)
    assert client.post("/api/model/check", headers=headers).json()["connected"] is True
    assert sent == ["Synthetic connection check. Reply OK. No business data."]

    def failed(config: model_connection.ModelConfig, text: str) -> str:
        raise RuntimeError("Synthetic-secret")

    monkeypatch.setattr(model_connection, "default_runner", failed)
    response = client.post("/api/model/check", headers=headers)
    assert response.status_code == 502 and "Synthetic-secret" not in response.text
    assert "Synthetic-secret" not in client.get("/api/account-audit").text
    assert (
        client.put("/api/model/config", headers=headers, json=config).status_code == 409
    )
    config.update(expected_version=1, enabled=False)
    assert (
        client.put("/api/model/config", headers=headers, json=config).status_code == 200
    )
    assert client.post("/api/model/check", headers=headers).status_code == 503


def test_external_endpoint_needs_approval(client: TestClient) -> None:  # noqa: F811
    headers = login_admin(client)
    assert (
        client.put(
            "/api/model/config",
            headers=headers,
            json={"endpoint": "https://models.example.invalid/v1"},
        ).status_code
        == 422
    )
