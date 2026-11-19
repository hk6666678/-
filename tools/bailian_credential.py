"""Save a Bailian credential locally and start AQP without printing it."""

import argparse
import os
import sys
from pathlib import Path

SERVICE = "AQP-PGS 百炼 Agent"
ACCOUNT = "AQP_MODEL_KEY_BAILIAN"


def vault():
    from keyring.backends.Windows import WinVaultKeyring

    return WinVaultKeyring()


def configure_agent(force: bool) -> None:
    secret = os.environ.get(ACCOUNT)
    if sys.platform == "win32" and not secret:
        secret = vault().get_password(SERVICE, ACCOUNT)
    if secret:
        os.environ[ACCOUNT] = secret
    if secret or force:
        os.environ["AQP_BAILIAN_AGENT_DB"] = str(
            Path(os.environ.get("AQP_DB", "data/aqp.sqlite3")).resolve()
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--enable-agent", action="store_true")
    args = parser.parse_args()
    if args.save:
        if sys.platform != "win32":
            sys.exit("保存凭证需要 Windows。")
        secret = os.environ.get(ACCOUNT, "").strip()
        if not secret:
            sys.exit("已取消，原凭证保持不变。")
        vault().set_password(SERVICE, ACCOUNT, secret)
        print("已保存到当前 Windows 用户的凭据管理器。")
        return

    import uvicorn

    configure_agent(args.enable_agent)
    uvicorn.run("aqp.app:create_app", factory=True, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
