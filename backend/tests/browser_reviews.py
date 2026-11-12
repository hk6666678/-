"""Reproducible Chrome candidate UI check: uv run python backend/tests/browser_candidates.py."""

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
from playwright.sync_api import expect, sync_playwright
from test_accounts import client as client_fixture
from test_candidates import candidate_setup


def main():
    with tempfile.TemporaryDirectory(prefix="aqp-review-playwright-") as directory:
        root = Path(directory)
        client = client_fixture.__wrapped__(root)
        headers, _ = candidate_setup(client, root)
        me = client.get("/api/me").json()["user"]
        original = client.get("/api/access/grants").json()
        assert (
            client.put(
                f"/api/users/{me['id']}/grants",
                headers=headers,
                json={
                    "expected_version": me["version"],
                    "request_id": str(uuid4()),
                    "grants": [
                        *original,
                        {
                            "category": "papers",
                            "operation": "review",
                            "college": "示例学院",
                            "major": "计算机",
                        },
                    ],
                },
            ).status_code
            == 200
        )
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(root / "accounts.sqlite3"),
                host="127.0.0.1",
                port=int(os.environ.get("AQP_TEST_PORT", "8046")),
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
                page.get_by_role("button", name="论文上传与解析", exact=True).click()
                page.get_by_label("规则名称", exact=True).fill(
                    "合成浏览器规则（非业务标准）"
                )
                page.get_by_label("适用学院", exact=True).fill("示例学院")
                page.get_by_label("适用专业／学科", exact=True).fill("计算机")
                page.get_by_label("培养层次", exact=True).last.fill("硕士")
                page.get_by_label("合成验证规则", exact=True).check()
                page.get_by_role("button", name="保存候选规则草稿", exact=True).click()
                expect(
                    page.get_by_role(
                        "heading", name="合成浏览器规则（非业务标准） · ID 1 / v1"
                    )
                ).to_be_visible()
                page.get_by_label("专家确认人", exact=True).fill("合成专家")
                page.get_by_label("书面确认来源", exact=True).fill("仅软件合成验证")
                page.get_by_role(
                    "button", name="确认启用此规则版本", exact=True
                ).click()
                expect(
                    page.get_by_text(
                        "确认人：合成专家；依据：仅软件合成验证", exact=True
                    )
                ).to_be_visible()
                page.get_by_label("比较论文版本ID", exact=True).fill("1")
                page.get_by_role("button", name="生成同类比较", exact=True).click()
                expect(
                    page.get_by_role("button", name="检查历史比较是否过时")
                ).to_be_visible()
                page.get_by_label("当前比较快照ID", exact=True).fill("1")
                page.get_by_role(
                    "button", name="生成候选结果新版本", exact=True
                ).click()
                expect(
                    page.get_by_role("heading", name="候选结果 1：辅助候选推荐")
                ).to_be_visible()
                expect(
                    page.get_by_role("cell", name="命中", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="读取原页证据（重新检查权限）").click()
                expect(
                    page.locator("pre").filter(has_text="Synthetic text").last
                ).to_be_visible()
                page.get_by_label("历史候选结果ID", exact=True).fill("1")
                page.get_by_role(
                    "button", name="读取并检查历史结果", exact=True
                ).click()
                expect(
                    page.get_by_role("heading", name="候选结果 1：辅助候选推荐")
                ).to_be_visible()
                page.get_by_role("button", name="读取复核历史", exact=True).click()
                expect(
                    page.get_by_text("复核版本 0 · 当前候选版本", exact=True)
                ).to_be_visible()
                page.get_by_label("复核意见", exact=True).fill("合成浏览器复核意见")
                page.get_by_role("button", name="提交复核新版本", exact=True).click()
                expect(
                    page.get_by_text("复核版本 1 · 当前候选版本", exact=True)
                ).to_be_visible()
                page.get_by_label("复核结论", exact=True).select_option(
                    label="待补充材料"
                )
                page.get_by_label("复核意见", exact=True).fill("合成浏览器修订")
                page.get_by_role("button", name="提交复核新版本", exact=True).click()
                expect(
                    page.get_by_text("复核版本 2 · 当前候选版本", exact=True)
                ).to_be_visible()
                expect(page.get_by_label("复核历史", exact=True)).to_contain_text(
                    "合成浏览器复核意见"
                )
                expect(page.get_by_label("复核历史", exact=True)).to_contain_text(
                    "合成浏览器修订"
                )
                browser.close()
                print(
                    "PASS Chrome 8046: draft, expert activation, comparison, candidate hit, original page, history"
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
