"""Local interactive launcher: no key on disk or command line."""

import getpass
import os
import sys
import warnings
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if not sys.stdin.isatty():
        print("Run in a local interactive terminal; never pass a key as an argument.")
        return 2
    if os.environ.get("AQP_ATTACHMENTS"):
        print("Remove AQP_ATTACHMENTS before this isolated synthetic test.")
        return 2
    print("Bailian: qwen3.8-max-0902, synthetic fixtures ONLY.")
    print("Up to 6 requests, 16000 input characters / 1024 output tokens each.")
    print("Budget target CNY 5 is NOT a provider-enforced cap; no automatic retries.")
    print("Verify model pricing/account billing in the console before continuing.")
    try:
        confirmation = input("Type YES to confirm pricing reviewed and paid test: ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled; no model call made.")
        return 2
    if confirmation.strip() != "YES":
        return 2
    # Never fall back to echoed input if terminal password masking is unavailable.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            key = getpass.getpass("New, rotated Bailian API key (hidden): ").strip()
        except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
            print("Secure input cancelled or unavailable.")
            return 2
    if not key:
        return 2
    os.environ["AQP_MODEL_KEY_BAILIAN"] = key
    os.environ["AQP_LIVE_SYNTHETIC"] = "approved-bailian-5-cny"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.chdir(root)
    sys.path[:0] = [str(root / "backend"), str(root / "backend/tests")]
    try:
        import pytest

        return int(
            pytest.main(
                [
                    "backend/tests/live_bailian.py",
                    "-q",
                    "-s",
                    "--tb=no",
                    "--show-capture=no",
                    "-p",
                    "no:cacheprovider",
                ]
            )
        )
    finally:
        os.environ.pop("AQP_MODEL_KEY_BAILIAN", None)
        os.environ.pop("AQP_LIVE_SYNTHETIC", None)


if __name__ == "__main__":
    raise SystemExit(main())
