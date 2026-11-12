from test_accounts import client, login_admin  # noqa: F401


def test_research_outputs_require_explicit_access(client):  # noqa: F811
    login_admin(client)
    response = client.get("/api/research-outputs")
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "personal_participations": 0,
        "distinct_outputs": 0,
    }
