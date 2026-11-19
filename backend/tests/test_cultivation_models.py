import json
from uuid import uuid4

import pytest
from aqp.cultivation_models import fit_factors
from aqp.store import connection
from test_accounts import client, login_admin  # noqa: F401


def test_factor_regression_recovers_independent_effects():
    rows = [(60, 67), (80, 61), (64, 90), (66, 65), (92, 90), (71, 85)]
    result = fit_factors([(x, y, 0.2 * x + 0.3 * y + 10) for x, y in rows])
    assert [row["coefficient"] for row in result["factors"]] == pytest.approx(
        [0.2, 0.3]
    )
    assert "notice" in fit_factors([(x, x, y) for x, y in rows])
    assert "notice" in fit_factors([(x, y, 30) for x, y in rows])
    assert "notice" in fit_factors([])
    noisy = fit_factors(
        [
            (x, y, 0.2 * x + 0.3 * y + noise)
            for (x, y), noise in zip(rows, [2, 0, 1, 3, 0, 2], strict=True)
        ]
    )
    assert all(
        row["interval"][0] < row["coefficient"] < row["interval"][1]
        for row in noisy["factors"]
    )
    assert all(0 <= row["p_value"] <= 1 for row in noisy["factors"])


def test_factor_routes_require_current_scope(client):  # noqa: F811
    login_admin(client)
    assert (
        client.get(
            "/api/cultivation/factors?college=S&major=M&entry_year=2024"
        ).status_code
        == 403
    )
    assert client.get("/api/cultivation/students/1/signals").status_code == 403


def test_personal_signals_compare_authorized_peers_without_revealing_their_records(
    client, tmp_path  # noqa: F811
):
    headers = login_admin(client)
    user = client.get("/api/me").json()["user"]
    grants = [
        {
            "category": category,
            "operation": op,
            "college": "合成学院",
            "major": "合成专业",
        }
        for category in ("basic", "research_papers", "patents", "awards", "conferences")
        for op in ("view", "analyze")
    ]
    assert (
        client.put(
            f"/api/users/{user['id']}/grants",
            headers=headers,
            json={
                "expected_version": user["version"],
                "request_id": str(uuid4()),
                "grants": grants,
            },
        ).status_code
        == 200
    )
    with connection(tmp_path / "accounts.sqlite3") as db:
        for ident in range(1, 6):
            payload = {"学号": f"S{ident}", "所属学院": "合成学院", "专业": "合成专业"}
            if ident == 1:
                payload.update({"学籍异动类型": "转导师", "学籍异动时间": "2025-06-01"})
            db.execute(
                "INSERT INTO students(id,research_id,student_number,name,college,major,level,entry_year,payload) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    f"R{ident}",
                    f"S{ident}",
                    f"N{ident}",
                    "合成学院",
                    "合成专业",
                    "master",
                    2023 if ident == 5 else 2024,
                    json.dumps(payload),
                ),
            )
            if ident != 1:
                db.execute(
                    "INSERT INTO research_outputs(business_key,payload) VALUES(?,?)",
                    (
                        f"P{ident}",
                        json.dumps(
                            {
                                "participants": [
                                    {
                                        "student_number": f"S{ident}",
                                        "name": f"N{ident}",
                                        "college": "合成学院",
                                        "major": "合成专业",
                                    }
                                ],
                            }
                        ),
                    ),
                )
    response = client.get("/api/cultivation/students/1/signals")
    assert response.status_code == 200
    assert response.json() == {
        "mobility": {"type": "转导师", "date": "2025-06-01"},
        "peer_outputs": {
            "count": 0,
            "peer_median": 1,
            "peer_count": 3,
            "below": True,
            "sources": [],
        },
        "output_trend": {"observations": [], "signal": "登记覆盖未确认"},
    }
