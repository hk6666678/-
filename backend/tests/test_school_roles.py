# ruff: noqa: F811
from uuid import uuid4

import pytest
from test_accounts import client, login_admin  # noqa: F401


@pytest.mark.parametrize("role", ["school_data_admin", "school_analyst"])
def test_school_roles_have_no_implicit_system_or_business_access(client, role):
    headers = login_admin(client)
    created = client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "synthetic-school",
            "password": "Synthetic-password-123!",
            "roles": [role],
            "request_id": str(uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    client.post("/api/logout", headers=headers)
    response = client.post(
        "/api/login",
        json={
            "username": "synthetic-school",
            "password": "Synthetic-password-123!",
        },
    )
    assert response.status_code == 200
    assert response.json()["user"]["roles"] == [role]
    assert client.get("/api/users").status_code == 403
    assert client.get("/api/students").status_code == 403
    assert client.get("/api/access/grants").json() == []
