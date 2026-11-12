"""Reproducible Chrome candidate UI check: uv run python backend/tests/browser_exports.py."""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).parent)]
import uvicorn
from aqp.app import create_app
from playwright.sync_api import sync_playwright
from test_accounts import client as client_fixture


def main():
    with tempfile.TemporaryDirectory(prefix="aqp-candidate-playwright-") as directory:
        root = Path(directory)
        client = client_fixture.__wrapped__(root)
        headers = __import__("test_accounts").login_admin(client)
        me = client.get("/api/me").json()["user"]
        original = client.get("/api/access/grants").json()
        grants = [
            {
                "category": "courses",
                "operation": op,
                "college": "合成导出学院",
                "major": "合成导出专业",
            }
            for op in ["view", "analyze", "export"]
        ]
        assert (
            client.put(
                f"/api/users/{me['id']}/grants",
                headers=headers,
                json={
                    "expected_version": me["version"],
                    "request_id": str(uuid4()),
                    "grants": grants,
                },
            ).status_code
            == 200
        )
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(root / "accounts.sqlite3"),
                host="127.0.0.1",
                port=int(os.environ.get("AQP_TEST_PORT", "8059")),
                log_level="warning",
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError("browser fixture server did not start")
                time.sleep(0.05)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.config.port}")
                page.get_by_label("用户名", exact=True).fill("trial-admin")
                page.get_by_label("密码", exact=True).fill("Synthetic-password-123!")
                page.get_by_role("button", name="登录平台 →").click()
                page.get_by_role(
                    "button", name="课程统计与通过规则", exact=True
                ).click()
                panel = page.locator("section").filter(
                    has=page.get_by_role(
                        "heading", name="课程分析与通过规则", exact=True
                    )
                )
                panel.get_by_label("学院", exact=True).fill("合成导出学院")
                panel.get_by_label("专业", exact=True).fill("合成导出专业")
                panel.get_by_role("button", name="生成新分析版本").click()
                link = panel.get_by_role("link", name="下载分析 Excel（须导出权限）")
                with page.expect_download() as event:
                    link.click()
                saved = root / "synthetic-report.xlsx"
                event.value.save_as(saved)
                from openpyxl import load_workbook

                wb = load_workbook(saved)
                values = [str(c.value) for sheet in wb for row in sheet for c in row]
                assert {
                    "generated_at",
                    "stale",
                    "data_version",
                    "rule_version",
                    "合成导出学院",
                } <= set(values)
                wb.close()
                current_user = client.get("/api/me").json()["user"]
                assert (
                    client.put(
                        f"/api/users/{me['id']}/grants",
                        headers=headers,
                        json={
                            "expected_version": current_user["version"],
                            "request_id": str(uuid4()),
                            "grants": [g for g in grants if g["operation"] != "export"],
                        },
                    ).status_code
                    == 200
                )
                assert (
                    page.request.get(
                        f"http://127.0.0.1:{server.config.port}"
                        + link.get_attribute("href")
                    ).status
                    == 403
                )
                browser.close()
                print(
                    "PASS Chrome 8059: synthetic Excel download, metadata, immediate export revocation"
                )
        finally:
            me = client.get("/api/me").json()["user"]
            response = client.put(
                f"/api/users/{me['id']}/grants",
                headers=headers,
                json={
                    "expected_version": me["version"],
                    "request_id": str(uuid4()),
                    "grants": original,
                },
            )
            assert response.status_code == 200
            assert client.get("/api/access/grants").json() == original
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
            print(
                "PASS finally restored original synthetic grants; temporary fixture cleaned"
            )


if __name__ == "__main__":
    main()
