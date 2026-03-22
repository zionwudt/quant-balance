import pytest

from datetime import date

from quant_balance.demo import (
    BacktestDemoRequest,
    DemoValidationError,
    build_demo_acceptance_checklist,
    build_demo_page_context,
    build_demo_result_context,
    get_csv_template,
    get_demo_field_guide,
    get_demo_input_options,
    load_demo_bars,
    parse_csv_text_to_bars,
)
from quant_balance.report import generate_report


def test_demo_input_options_hide_path_mode_by_default() -> None:
    default_options = get_demo_input_options()
    developer_options = get_demo_input_options(developer_mode=True)

    assert [option["mode"] for option in default_options] == ["upload", "example"]
    assert [option["mode"] for option in developer_options] == ["upload", "example", "path"]


def test_demo_request_rejects_path_mode_without_developer_flag() -> None:
    request = BacktestDemoRequest(input_mode="path", symbol="600519.SH", csv_path="/tmp/a.csv")

    with pytest.raises(DemoValidationError, match="开发者模式"):
        request.validate()


def test_demo_request_rejects_invalid_ma_parameters() -> None:
    with pytest.raises(DemoValidationError, match="短均线必须小于长均线"):
        BacktestDemoRequest(input_mode="example", symbol="600519.SH", short_window=20, long_window=10).validate()

    with pytest.raises(DemoValidationError, match="不要超过 250"):
        BacktestDemoRequest(input_mode="example", symbol="600519.SH", short_window=5, long_window=300).validate()


def test_parse_csv_text_to_bars_rejects_missing_columns() -> None:
    csv_text = "date,open,high,low,close\n2026-01-05,10,11,9,10.5"

    with pytest.raises(DemoValidationError, match="缺少必要字段：volume"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_invalid_value_format() -> None:
    csv_text = "date,open,high,low,close,volume\n2026/01/05,10,11,9,10.5,1000"

    with pytest.raises(DemoValidationError, match="无法识别的数值或日期格式"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_accepts_headers_with_spaces() -> None:
    csv_text = "date, open,high, low,close, volume\n2026-01-05,10,11,9,10.5,1000"

    bars = parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")

    assert len(bars) == 1
    assert bars[0].date == date(2026, 1, 5)
    assert bars[0].open == 10.0
    assert bars[0].volume == 1000.0


def test_load_demo_bars_supports_example_mode() -> None:
    bars = load_demo_bars(BacktestDemoRequest(input_mode="example", symbol="600519.SH"))

    assert len(bars) == 4
    assert bars[0].symbol == "600519.SH"


def test_load_demo_bars_returns_friendly_file_not_found_message() -> None:
    request = BacktestDemoRequest(
        input_mode="path",
        symbol="600519.SH",
        csv_path="/no/such.csv",
        developer_mode=True,
    )

    with pytest.raises(DemoValidationError, match="找不到你提供的 CSV 文件"):
        load_demo_bars(request)


def test_csv_template_and_field_guide_expose_user_facing_boundary_hints() -> None:
    template = get_csv_template()
    guide = get_demo_field_guide()

    assert template.startswith("date,open,high,low,close,volume")
    assert guide.supported_frequency == "当前仅支持日线 CSV（daily bar）。"
    assert "印花税" in guide.notes[0]


def test_build_demo_page_context_aggregates_upload_and_hint_content() -> None:
    context = build_demo_page_context()

    assert [option["mode"] for option in context.input_options] == ["upload", "example"]
    assert context.csv_template.startswith("date,open,high,low,close,volume")
    assert context.example_csv.count("\n") >= 2
    assert "日线 CSV" in context.field_guide.supported_frequency


def test_build_demo_result_context_exposes_summary_trades_and_assumptions() -> None:
    report = generate_report(
        initial_equity=100_000.0,
        equity_curve=[100_000.0, 102_000.0, 101_000.0],
        equity_dates=[date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)],
        fills=[],
        benchmark_name="CSI300",
        benchmark_equity_curve=[100.0, 101.0, 100.5],
    )

    context = build_demo_result_context(report)

    assert context.chart_sections == ["summary", "trades", "equity_curve", "run_context", "export"]
    assert context.summary["benchmark_name"] == "CSI300"
    assert context.summary["max_drawdown_start"] == "2026-01-06"
    assert context.summary["max_drawdown_end"] == "2026-01-07"
    assert context.closed_trades == []
    assert any("滑点" in note for note in context.assumptions)
    assert context.export_json is not None
    assert context.run_context == {}
    assert context.equity_curve_points == []


def test_build_demo_acceptance_checklist_covers_core_browser_paths() -> None:
    checklist = build_demo_acceptance_checklist()
    contract_keys = {selector.key for selector in checklist.page_contract}
    scenario_ids = [scenario.scenario_id for scenario in checklist.scenarios]

    assert "page-root" in contract_keys
    assert "submit-button" in contract_keys
    assert "error-banner" in contract_keys
    assert scenario_ids == [
        "home-loads",
        "example-backtest",
        "upload-valid-csv",
        "upload-invalid-csv",
        "invalid-ma-params",
        "result-metrics-visible",
    ]
    assert any("data-testid" in note for note in checklist.notes)

    invalid_csv = next(s for s in checklist.scenarios if s.scenario_id == "upload-invalid-csv")
    assert "error-banner" in invalid_csv.selectors
    assert any("中文错误提示" in outcome for outcome in invalid_csv.expected_outcomes)


def test_demo_acceptance_checklist_to_dict_returns_serializable_payload() -> None:
    payload = build_demo_acceptance_checklist().to_dict()

    assert payload["page_contract"][0]["selector"].startswith("[data-testid='qb-")
    assert payload["scenarios"][0]["scenario_id"] == "home-loads"
    assert payload["scenarios"][1]["title"] == "使用示例数据完成一次回测"


def test_parse_csv_text_to_bars_rejects_unsorted_dates() -> None:
    csv_text = """date,open,high,low,close,volume
2026-01-06,10,11,9,10.5,1000
2026-01-05,10,11,9,10.5,1000"""

    with pytest.raises(DemoValidationError, match="日期顺序不正确"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_duplicate_dates() -> None:
    csv_text = """date,open,high,low,close,volume
2026-01-05,10,11,9,10.5,1000
2026-01-05,10.2,11.1,9.1,10.6,1100"""

    with pytest.raises(DemoValidationError, match="重复交易日"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_non_positive_prices() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,0,11,9,10.5,1000"

    with pytest.raises(DemoValidationError, match="价格必须全部大于 0"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_negative_volume() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,10,11,9,10.5,-1"

    with pytest.raises(DemoValidationError, match="成交量不能为负数"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_high_below_low() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,10,8,9,9.5,1000"

    with pytest.raises(DemoValidationError, match="high 不能小于 low"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_open_outside_price_range() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,12,11,9,10.5,1000"

    with pytest.raises(DemoValidationError, match="open 必须落在 low 和 high 之间"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")


def test_parse_csv_text_to_bars_rejects_close_outside_price_range() -> None:
    csv_text = "date,open,high,low,close,volume\n2026-01-05,10,11,9,12,1000"

    with pytest.raises(DemoValidationError, match="close 必须落在 low 和 high 之间"):
        parse_csv_text_to_bars(csv_text=csv_text, symbol="600519.SH")
