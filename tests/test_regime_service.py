"""测试市场状态识别服务。"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from quant_balance.services.regime_service import (
    resolve_market_regime_filter,
    run_market_regime_analysis,
)


def _make_bull_frame() -> pd.DataFrame:
    close = [100 + index * 2 for index in range(80)]
    df = pd.DataFrame(
        {
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": [1_000_000] * len(close),
        },
        index=pd.date_range("2024-01-01", periods=len(close), freq="B"),
    )
    df.attrs["data_provider"] = "tushare"
    return df


def test_run_market_regime_analysis_returns_latest_and_series() -> None:
    frame = _make_bull_frame()
    with patch("quant_balance.services.regime_service.load_dataframe", return_value=frame) as mock_load:
        payload = run_market_regime_analysis(
            symbol="000300.SH",
            start_date="2024-03-01",
            end_date="2024-03-29",
        )

    assert payload["symbol"] == "000300.SH"
    assert payload["latest"]["regime"] == "BULL"
    assert payload["series"][0]["date"] >= "2024-03-01"
    assert payload["run_context"]["data_provider"] == "tushare"
    mock_load.assert_called_once()
    assert mock_load.call_args.kwargs["adjust"] == "none"
    assert mock_load.call_args.kwargs["provider"] == "tushare"


def test_resolve_market_regime_filter_returns_match_result() -> None:
    frame = _make_bull_frame()
    with patch("quant_balance.services.regime_service.load_dataframe", return_value=frame):
        result = resolve_market_regime_filter(
            "BEAR",
            as_of_date="2024-03-29",
            symbol="000300.SH",
        )

    assert result["requested_regime"] == "BEAR"
    assert result["actual_regime"] == "BULL"
    assert result["matches"] is False
