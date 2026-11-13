# ruff: noqa: F811
import importlib.util
import json
from pathlib import Path

from aqp.store import connection
from test_accounts import client  # noqa: F401


def test_enable_config_is_audited_and_contains_no_credential(client, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "bailian_launcher",
        Path(__file__).resolve().parents[2] / "tools/start_bailian.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    database = tmp_path / "accounts.sqlite3"
    assert module.enable_config(database) == 1
    assert module.enable_config(database) == 2
    with connection(database) as db:
        config = json.loads(
            db.execute("SELECT payload FROM model_configs WHERE version=2").fetchone()[
                0
            ]
        )
        assert config["enabled"] and config["external_authorized"]
        assert config["allowed_purposes"] == ["agent", "papers"]
        assert config["key_env"] == "AQP_MODEL_KEY_BAILIAN"
        assert "api_key" not in config
        assert (
            db.execute(
                "SELECT COUNT(*) FROM audit WHERE action='model.configure'"
            ).fetchone()[0]
            == 2
        )
