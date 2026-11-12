# ruff: noqa: F811
from test_accounts import client  # noqa: F401


def test_external_assessment_requires_session(client):
    assert client.get("/api/external-assessments").status_code == 401


def test_external_assessment_authenticated_empty_list(client):
    from test_accounts import login_admin

    login_admin(client)
    response = client.get("/api/external-assessments")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["template"]["simulation"] is True

