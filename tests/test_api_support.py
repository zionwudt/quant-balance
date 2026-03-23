from datetime import date

import pytest

from quant_balance.api.meta import (
    build_backtest_meta,
    get_backtest_field_guide,
    get_backtest_input_options,
)
from quant_balance.api.presenters import build_backtest_response
from quant_balance.backtest_inputs import BacktestInputError, BacktestRequest
from quant_balance.csv_loader import get_csv_template, load_bars, parse_csv_text_to_bars
from quant_balance.core.report import generate_report


def test_backtest_input_options_hide_path_mode_by_default() -> None:
    default_options = get_backtest_input_options()
    developer_options = get_backtest_input_options(developer_mode=True)

    assert [option["mode"] for option in default_options] == ["upload", "example"]
    assert [option["mode"] for option in developer_options] == ["upload", "example", "path"]


def test_backtest_request_rejects_path_mode_without_developer_flag() -> None:
    request = BacktestRequest(input_mode="path", symbol="600519.SH", csv_path="/tmp/a.csv")

    with pytest.raises(BacktestInputError, match="开发者模式"):
        request.validate()


def test_backtest_request_rejects_invalid_ma_parameters() -> None:
    with pytest.raises(BacktestInputError, match="短均线必须小于长均线"):
        BacktestRequest(input_mode="example", symbol="600519.SH", short_window=20, long_window=10).validate()

    with pytest.raises(BacktestInputError, match="不要超过 250"):
        BacktestRequest(input_mode="example", symbol="600519.SH", short_window=5, long_window=300).validate()


def test_parse_csv_text_to_bars_rejects_missing_columns() -> None:
    csv_text = "date,open,high,low,close\n2026-01-05,10,11,9,10.5"

    with pytest.raises(BacktestInputError, match="缺少必要字段：volume"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_invalid_value_format() -> None:
    csv_text = "date,open,high,low,close,volume\n2026/01/05,10,11,9,10.5,1000"

    with pytest.raises(BacktestInputError, match="无法识别的数值或日期格式"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_accepts_headers_with_spaces() -> None:
    csv_text = "date, open,high, low,close, volume\n2026-01-05,10,11,9,10.5,1000"

    bars = parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")

    assert len(bars) == 1
    assert bars[0].date == date(2026, 1, 5)
    assert bars[0].open == 10.0
    assert bars[0].volume == 1000.0


def test_load_bars_supports_example_mode() -> None:
    bars = load_bars(BacktestRequest(input_mode="example", symbol="600519.SH"))

    assert len(bars) == 4
    assert bars[0].symbol == "600519.SH"


def test_load_bars_returns_friendly_file_not_found_message() -> None:
    request = BacktestRequest(
        input_mode="path",
        symbol="600519.SH",
        csv_path="/no/such.csv",
        developer_mode=True,
    )

    with pytest.raises(BacktestInputError, match="找不到你提供的 CSV 文件"):
        load_bars(request)


def test_csv_template_and_field_guide_expose_user_facing_boundary_hints() -> None:
    template = get_csv_template()
    guide = get_backtest_field_guide()

    assert template.startswith("date,open,high,low,close,volume")
    assert guide.supported_frequency == "当前仅支持日线 CSV（daily bar）。"
    assert "印花税" in guide.notes[0]


def test_build_backtest_meta_aggregates_upload_and_hint_content() -> None:
    meta = build_backtest_meta(developer_mode=False, example_csv="date,open,high,low,close,volume\n2026-01-05,10,11,9,10.5,1000")

    assert [option["mode"] for option in meta.input_options] == ["upload", "example"]
    assert meta.csv_template.startswith("date,open,high,low,close,volume")
    assert meta.example_csv.count("\n") >= 1
    assert "日线 CSV" in meta.field_guide.supported_frequency
    assert meta.server_mode == "api"
    assert meta.developer_mode is False


def test_build_backtest_response_exposes_summary_trades_and_assumptions() -> None:
    report = generate_report(
        initial_equity=100_000.0,
        equity_curve=[100_000.0, 102_000.0, 101_000.0],
        equity_dates=[date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)],
        fills=[],
        benchmark_name="CSI300",
        benchmark_equity_curve=[100.0, 101.0, 100.5],
    )

    response = build_backtest_response(report)

    assert response.chart_sections == ["summary", "trades", "equity_curve", "run_context", "export"]
    assert response.summary["benchmark_name"] == "CSI300"
    assert response.summary["max_drawdown_start"] == "2026-01-06"
    assert response.summary["max_drawdown_end"] == "2026-01-07"
    assert response.closed_trades == []
    assert any("滑点" in note for note in response.assumptions)
    assert response.export_json is not None
    assert response.run_context == {}
    assert response.equity_curve_points == []


def test_parse_csv_text_to_bars_rejects_unsorted_dates() -> None:
    csv_text = """date,open,high,low,close,volume
2026-01-06,10,11,9,10.5,1000
2026-01-05,10,11,9,10.5,1000"""

    with pytest.raises(BacktestInputError, match="日期顺序不正确"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_duplicate_dates() -> None:
    csv_text = """date,open,high,low,close,volume
2026-01-05,10,11,9,10.5,1000
2026-01-05,10.2,11.1,9.1,10.6,1100"""

    with pytest.raises(BacktestInputError, match="重复交易日"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_non_positive_prices() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,0,11,9,10.5,1000"

    with pytest.raises(BacktestInputError, match="价格必须全部大于 0"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_negative_volume() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,10,11,9,10.5,-1"

    with pytest.raises(BacktestInputError, match="成交量不能为负数"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_high_below_low() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,10,8,9,9.5,1000"

    with pytest.raises(BacktestInputError, match="high 不能小于 low"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_open_outside_price_range() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,12,11,9,10.5,1000"

    with pytest.raises(BacktestInputError, match="open 必须落在 low 和 high 之间"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_close_outside_price_range() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,10,11,9,12,1000"

    with pytest.raises(BacktestInputError, match="close 必须落在 low 和 high 之间"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")
