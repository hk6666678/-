import json

import httpx
import pytest
from aqp import model_connection
from fastapi import HTTPException
from openai import RateLimitError


def test_large_input_is_rejected_before_client_or_credentials(monkeypatch):
    monkeypatch.delenv("AQP_MODEL_KEY_LOCAL", raising=False)
    config = model_connection.ModelConfig(max_input_chars=1000)
    with pytest.raises(HTTPException) as error:
        model_connection.default_runner(config, "模拟" * 501)
    assert error.value.status_code == 413


def test_openai_wire_limits_and_no_retry(monkeypatch):
    client_factory = httpx.Client
    requests = []
    options = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(429, json={"error": {"message": "Synthetic-secret"}})

    class Client(client_factory):
        def __init__(self, **kwargs):
            options.append(kwargs)
            super().__init__(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(model_connection.httpx, "Client", Client)
    monkeypatch.setenv("AQP_MODEL_KEY_LOCAL", "Synthetic-secret")
    config = model_connection.ModelConfig(
        endpoint="http://127.0.0.1:9999/v1", model="synthetic", max_output_tokens=512
    )
    # Exercise the actual LangChain client against a fake HTTP transport, no network.
    with pytest.raises(RateLimitError):
        model_connection.default_runner(config, "Synthetic materials only")
    assert len(requests) == 1
    payload = requests[0]
    assert payload.get("max_tokens", payload.get("max_completion_tokens")) == 512
    assert options[0] == {"follow_redirects": False, "trust_env": False, "timeout": 60}
