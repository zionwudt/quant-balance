from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quant_balance.core.data_adapter import load_multi_dataframes
from quant_balance.data.common import DataLoadError


def test_load_multi_dataframes_raises_for_invalid_provider() -> None:
    with pytest.raises(DataLoadError, match="不支持的数据源"):
        load_multi_dataframes(
            ["600519.SH"],
            "2026-01-01",
            "2026-01-31",
            data_provider="unknown",
        )


def test_load_multi_dataframes_skips_symbol_level_data_load_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample_df = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [10.2],
            "Low": [9.9],
            "Close": [10.1],
            "Volume": [1000.0],
        },
        index=pd.to_datetime(["2026-01-05"]),
    )

    def fake_load_dataframe(
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        asset_type: str = "stock",
        timeframe: str = "1d",
        adjust: str = "qfq",
        provider: str | None = None,
        db_path: Path | None = None,
    ) -> pd.DataFrame:
        if symbol == "AAA":
            raise DataLoadError("missing data")
        return sample_df

    monkeypatch.setattr("quant_balance.core.data_adapter.load_dataframe", fake_load_dataframe)

    result = load_multi_dataframes(
        ["AAA", "BBB"],
        "2026-01-01",
        "2026-01-31",
    )

    assert list(result) == ["BBB"]
    assert result["BBB"].equals(sample_df)
