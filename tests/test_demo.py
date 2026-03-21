import pytest

from quant_balance.demo import (
    BacktestDemoRequest,
    DemoValidationError,
    get_csv_template,
    get_demo_field_guide,
    get_demo_input_options,
    load_demo_bars,
    parse_csv_text_to_bars,
)


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
