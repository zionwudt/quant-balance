from __future__ import annotations

from pathlib import Path

from quant_balance.data import common


def test_save_tushare_token_creates_config_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(common, "_CONFIG_PATH", config_path)

    saved_path = common.save_tushare_token("test-token")

    assert saved_path == config_path
    assert config_path.exists()
    assert 'token = "test-token"' in config_path.read_text(encoding="utf-8")

    status = common.get_tushare_config_status(check_connection=False)
    assert status["config_exists"] is True
    assert status["token_configured"] is True
    assert status["connection_ok"] is None


def test_save_tushare_token_preserves_other_config_sections(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join([
            "[data]",
            'daily_providers = ["akshare", "tushare"]',
            "",
            "[server]",
            'host = "0.0.0.0"',
            "port = 9000",
            "",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(common, "_CONFIG_PATH", config_path)

    common.save_tushare_token("saved-token")
    config = common.load_app_config()

    assert config["tushare"]["token"] == "saved-token"
    assert config["data"]["daily_providers"] == ["akshare", "tushare"]
    assert config["server"]["port"] == 9000
