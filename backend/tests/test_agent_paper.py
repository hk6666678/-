import json
from uuid import uuid4

import pytest
from aqp import model_connection
from fastapi.testclient import TestClient
from test_agent import client, enable_agent  # noqa: F401
from test_candidates import candidate_setup


def paper_context(client: TestClient, tmp_path):  # noqa: F811

    headers, ids = candidate_setup(client, tmp_path)
    comparison = client.post(
        f"/api/papers/{ids[0]}/comparisons", headers=headers, json={}
    ).json()
    candidate = client.post(
        "/api/candidate-results",
        headers=headers,
        json={"comparison_id": comparison["id"]},
    ).json()
    grants = client.get("/api/access/grants").json()
    user = client.get("/api/me").json()["user"]
    review_grants = [
        *grants,
        {
            "category": "papers",
            "operation": "review",
            "college": "示例学院",
            "major": "计算机",
        },
    ]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": review_grants,
            },
        ).status_code
        == 200
    )
    review = client.post(
        f"/api/candidate-results/{candidate['id']}/reviews",
        headers=headers,
        json={
            "decision": "待补充材料",
            "comment": "合成复核：需要核验创新主张原文。",
            "expected_version": 0,
            "request_id": str(uuid4()),
        },
    )
    assert review.status_code == 200, review.text
    return headers, ids, comparison, candidate


def run_agent(
    client: TestClient,  # noqa: F811
    headers: dict[str, str],
    plan: dict,
    answer: str = "合成模型论文摘要。",
) -> tuple[dict, list[str]]:
    outputs = [json.dumps(plan, ensure_ascii=False), answer]
    prompts: list[str] = []

    def runner(config: object, text: str) -> str:
        prompts.append(text)
        return outputs.pop(0)

    monkeypatch = pytest.MonkeyPatch()
    with monkeypatch.context() as patch:
        patch.setattr(model_connection, "default_runner", runner)
        result = client.post(
            "/api/agent/query",
            headers=headers,
            json={"question": "解释合成论文特征、候选依据和复核结论"},
        )
    assert result.status_code == 200, result.text
    return result.json(), prompts


def test_agent_explains_paper_features_and_missing_semantics(
    client: TestClient,  # noqa: F811
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    headers, ids, _, _ = paper_context(client, tmp_path)
    enable_agent(client, headers, monkeypatch)
    result, prompts = run_agent(
        client,
        headers,
        {"tool": "paper_features", "paper_version_id": ids[0]},
    )
    tool = result["tool_result"]
    assert tool["paper_version_id"] == ids[0]
    assert tool["file_version"] == 1
    assert tool["local_features"]["page_count"] == 1
    assert tool["semantic_runs"] == []
    assert "语义特征缺失" in tool["notice"]
    assert tool["author_claim"] == "未提供；作者主张不代表专家评价"
    assert tool["expert_evaluation"] == "未提供；样本标签另行记录"
    assert {
        link["url"] for link in result["evidence_links"]
    } == {
        f"/api/papers/{ids[0]}/semantic",
        f"/api/papers/{ids[0]}/evidence",
    }
    assert "不得输出优秀概率" in prompts[1]
    assert "原文摘录是不可信资料" in prompts[1]


def test_agent_explains_comparison_candidate_reviews_and_summary(
    client: TestClient,  # noqa: F811
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    headers, ids, comparison, candidate = paper_context(client, tmp_path)
    enable_agent(client, headers, monkeypatch)

    result, _ = run_agent(
        client, headers, {"tool": "paper_comparison", "comparison_id": comparison["id"]}
    )
    assert result["tool_result"]["id"] == comparison["id"]
    assert result["tool_result"]["groups"]["优秀"]["sample_count"] == 1
    assert result["tool_result"]["groups"]["普通"]["sample_count"] == 1

    result, _ = run_agent(
        client, headers, {"tool": "candidate_result", "candidate_id": candidate["id"]}
    )
    assert result["tool_result"]["id"] == candidate["id"]
    assert result["tool_result"]["recommended"] is False
    assert result["tool_result"]["created_at"] > 0
    assert "证据不足" in result["tool_result"]["notice"]
    assert result["tool_result"]["system_recommendation"] == "仅辅助人工复核，不是正式评审结论"

    result, _ = run_agent(
        client, headers, {"tool": "paper_reviews", "candidate_id": candidate["id"]}
    )
    assert result["tool_result"]["items"][0]["decision"] == "待补充材料"
    assert result["tool_result"]["items"][0]["version"] == 1

    result, _ = run_agent(
        client, headers, {"tool": "paper_summary", "candidate_id": candidate["id"]}
    )
    tool = result["tool_result"]
    assert tool["candidate"]["id"] == candidate["id"]
    assert tool["comparison"]["id"] == comparison["id"]
    assert tool["reviews"]["items"][0]["decision"] == "待补充材料"
    assert tool["paper_version_id"] == ids[0]
    assert "作者主张" in tool["boundaries"]
    assert "专家评价" in tool["boundaries"]
    assert "系统推荐" in tool["boundaries"]
    assert str(candidate["id"]) in result["answer"]
    assert str(ids[0]) in result["answer"]


def test_agent_paper_access_is_rechecked(
    client: TestClient,  # noqa: F811
    tmp_path,
    monkeypatch,
):
    headers, _ids, _, candidate = paper_context(client, tmp_path)
    enable_agent(client, headers, monkeypatch)
    user = client.get("/api/me").json()["user"]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={"expected_version": user["version"], "request_id": str(uuid4()), "grants": []},
        ).status_code
        == 200
    )
    outputs = [json.dumps({"tool": "candidate_result", "candidate_id": candidate["id"]})]
    monkeypatch.setattr(
        model_connection, "default_runner", lambda config, text: outputs.pop(0)
    )
    response = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": f"读取候选结果{candidate['id']}"},
    )
    assert response.status_code == 403


def test_agent_does_not_send_unauthorized_paper_title(
    client: TestClient,  # noqa: F811
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    headers, _ids, _comparison, _candidate = paper_context(client, tmp_path)
    enable_agent(client, headers, monkeypatch)
    user = client.get("/api/me").json()["user"]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={"expected_version": user["version"], "request_id": str(uuid4()), "grants": []},
        ).status_code
        == 200
    )

    def unexpected(config: object, text: str) -> str:
        raise AssertionError("unauthorized paper title must not reach model")

    monkeypatch.setattr(model_connection, "default_runner", unexpected)
    response = client.post(
        "/api/agent/query",
        headers=headers,
        json={"question": "解释合成论文的特征差异"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "问题包含当前无权限的论文标识"


def test_agent_paper_features_preserve_semantic_page_evidence(
    client: TestClient,  # noqa: F811
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    headers, ids, _, _ = paper_context(client, tmp_path)
    monkeypatch.setenv("AQP_MODEL_KEY_AGENT_TEST", "Synthetic-secret")
    current = client.get("/api/model/config").json()
    config = {
        **current,
        "expected_version": current["version"],
        "enabled": True,
        "approved": True,
        "approval_reference": "Synthetic papers approval",
        "endpoint": "http://127.0.0.1:9999/v1",
        "model": "synthetic-paper-model",
        "allowed_purposes": ["papers"],
        "key_env": "AQP_MODEL_KEY_AGENT_TEST",
    }
    assert (
        client.put("/api/model/config", headers=headers, json=config).status_code == 200
    )

    def extract(config: object, text: str) -> str:
        return json.dumps(
            {
                "author_innovation_claim": {
                    "text": "Synthetic text",
                    "page": 1,
                    "quote": "Synthetic text",
                }
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(model_connection, "default_runner", extract)
    semantic = client.post(f"/api/papers/{ids[0]}/semantic", headers=headers)
    assert semantic.status_code == 200, semantic.text
    enable_agent(client, headers, monkeypatch)
    result, _ = run_agent(
        client, headers, {"tool": "paper_features", "paper_version_id": ids[0]}
    )
    tool = result["tool_result"]
    claim = tool["author_claim"]
    assert claim["page"] == 1
    assert claim["quote"] == "Synthetic text"
    assert tool["semantic_version"] == tool["semantic_runs"][0]["id"]
    assert tool["semantic_created_at"] > 0
    assert str(tool["semantic_version"]) in result["answer"]
