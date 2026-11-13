"""Synthetic Chrome research-paper import acceptance."""

import sys
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).parent)]
import uvicorn
from aqp.app import create_app
from openpyxl import Workbook
from playwright.sync_api import expect, sync_playwright
from test_accounts import client as client_fixture
from test_accounts import login_admin


def main():
    with tempfile.TemporaryDirectory(prefix="aqp-research-browser-") as directory:
        root = Path(directory)
        client = client_fixture.__wrapped__(root)
        headers = login_admin(client)
        user = client.get("/api/me").json()["user"]
        assert (
            client.put(
                f"/api/users/{user['id']}/grants",
                headers=headers,
                json={
                    "expected_version": user["version"],
                    "request_id": str(uuid4()),
                    "grants": [
                        {
                            "category": "research_papers",
                            "operation": op,
                            "college": "合成学院",
                            "major": "合成专业",
                        }
                        for op in ["maintain", "view", "identity"]
                    ],
                },
            ).status_code
            == 200
        )
        wb = Workbook()
        wb.active.append(["AQP-PGS", "research_papers", "1"])
        wb.active.append(
            [
                "业务编号/DOI",
                "论文标题",
                "学号",
                "姓名",
                "作者次序",
                "参与角色",
                "所属学院",
                "专业",
            ]
        )
        wb.active.append(
            [
                "demo-001",
                "合成Chrome科研论文",
                "001",
                "合成人员",
                1,
                "第一作者",
                "合成学院",
                "合成专业",
            ]
        )
        filename = root / "synthetic.xlsx"
        wb.save(filename)
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(root / "accounts.sqlite3"),
                host="127.0.0.1",
                port=8052,
                log_level="warning",
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError("fixture server timeout")
                time.sleep(0.05)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page()
                page.goto("http://127.0.0.1:8052")
                page.get_by_label("用户名", exact=True).fill("trial-admin")
                page.get_by_label("密码", exact=True).fill("Synthetic-password-123!")
                page.get_by_role("button", name="登录平台 →").click()
                page.get_by_role("button", name="已发表科研论文", exact=True).click()
                page.get_by_label("来源部门", exact=True).fill("合成科研处")
                page.get_by_label("标准 Excel 文件", exact=True).set_input_files(
                    filename
                )
                page.get_by_role("button", name="预览导入", exact=True).click()
                expect(page.get_by_role("heading", name="导入预览")).to_be_visible()
                page.get_by_role("button", name="确认导入", exact=True).click()
                expect(
                    page.get_by_role("cell", name="合成Chrome科研论文", exact=True)
                ).to_be_visible()
                expect(
                    page.get_by_text(
                        "个人参与次数：1；范围内成果去重数：1。", exact=False
                    )
                ).to_be_visible()
                page.get_by_role("button", name="来源与历史", exact=True).click()
                expect(page.get_by_role("cell", name="合成科研处", exact=True)).to_be_visible()
                page.get_by_label("作废依据", exact=True).fill("合成重复登记核实")
                page.get_by_role("button", name="确认作废成果", exact=True).click()
                expect(page.get_by_text("该成果已作废，原始内容和历史继续保留。", exact=True)).to_be_visible()
                expect(page.get_by_text("个人参与次数：0；范围内成果去重数：0。", exact=False)).to_be_visible()
                page.screenshot(path=str(Path(__file__).resolve().parents[2] / ".scratch" / "research-void-history.png"), full_page=True)
                browser.close()
                print("Chrome research import and statistics passed")
        finally:
            server.should_exit = True
            thread.join(timeout=10)


if __name__ == "__main__":
    main()
