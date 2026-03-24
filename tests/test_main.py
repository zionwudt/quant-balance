from __future__ import annotations

from unittest.mock import patch

from quant_balance.main import check_config_or_guide, run_cli


def test_check_config_or_guide_prints_missing_config_message(capsys) -> None:
    with patch(
        "quant_balance.main.get_tushare_config_status",
        return_value={
            "config_exists": False,
            "config_path": "/tmp/config.toml",
            "token_configured": False,
        },
    ):
        result = check_config_or_guide()

    captured = capsys.readouterr()
    assert result == 1
    assert "首次使用" in captured.err
    assert "config/config.example.toml" in captured.err
    assert "/tmp/config.toml" in captured.err


def test_check_config_or_guide_prints_missing_token_message(capsys) -> None:
    with patch(
        "quant_balance.main.get_tushare_config_status",
        return_value={
            "config_exists": True,
            "config_path": "/tmp/config.toml",
            "token_configured": False,
        },
    ):
        result = check_config_or_guide()

    captured = capsys.readouterr()
    assert result == 1
    assert "[tushare] token 未设置" in captured.err


def test_run_cli_starts_server_after_config_check() -> None:
    with (
        patch(
            "quant_balance.main.get_tushare_config_status",
            return_value={
                "config_exists": True,
                "config_path": "/tmp/config.toml",
                "token_configured": True,
            },
        ),
        patch("quant_balance.main._load_server_config", return_value={"host": "0.0.0.0", "port": 9000}),
        patch("quant_balance.api.app.run_api_server") as mock_run_server,
    ):
        result = run_cli()

    assert result == 0
    mock_run_server.assert_called_once_with(host="0.0.0.0", port=9000)
