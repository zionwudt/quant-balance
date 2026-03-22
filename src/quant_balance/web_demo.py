from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from quant_balance.backtest import BacktestEngine
from quant_balance.demo import BacktestDemoRequest, DemoValidationError, build_demo_page_context, build_demo_result_context, load_demo_bars
from quant_balance.models import AccountConfig
from quant_balance.strategy import MovingAverageCrossStrategy

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_EXAMPLE_CSV_PATH = Path(__file__).resolve().parents[2] / "examples" / "demo_backtest.csv"

WSGIApp = Callable[[dict[str, object], Callable[[str, list[tuple[str, str]]], None]], list[bytes]]


def create_app(*, developer_mode: bool = False, example_csv_path: Path = DEFAULT_EXAMPLE_CSV_PATH) -> WSGIApp:
    def app(environ: dict[str, object], start_response: Callable[[str, list[tuple[str, str]]], None]) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))

        if path == "/health":
            start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"ok"]

        if path not in {"/", "/demo"}:
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
            return ["Not Found".encode("utf-8")]

        form_data = _parse_form_data(environ) if method == "POST" else {}
        page_html = render_demo_page(
            form_data=form_data,
            developer_mode=developer_mode,
            example_csv_path=example_csv_path,
        )
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [page_html.encode("utf-8")]

    return app



def run_demo_web_server(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    developer_mode: bool = False,
    example_csv_path: Path = DEFAULT_EXAMPLE_CSV_PATH,
) -> None:
    app = create_app(developer_mode=developer_mode, example_csv_path=example_csv_path)
    with make_server(host, port, app) as server:
        print(f"QuantBalance Web Demo listening on http://{host}:{port}")
        server.serve_forever()



def render_demo_page(
    *,
    form_data: dict[str, str] | None = None,
    developer_mode: bool = False,
    example_csv_path: Path = DEFAULT_EXAMPLE_CSV_PATH,
) -> str:
    form_data = form_data or {}
    page_context = build_demo_page_context(developer_mode=developer_mode)
    selected_mode = form_data.get("input_mode", "example")
    symbol = form_data.get("symbol", "600519.SH")
    initial_cash = form_data.get("initial_cash", "100000")
    short_window = form_data.get("short_window", "5")
    long_window = form_data.get("long_window", "20")
    csv_text = form_data.get("csv_text", "")
    csv_path = form_data.get("csv_path", "")

    error_message = ""
    result_context = None
    if form_data:
        try:
            result_context = run_demo_web_backtest(
                form_data=form_data,
                developer_mode=developer_mode,
                example_csv_path=example_csv_path,
            )
        except DemoValidationError as exc:
            error_message = str(exc)

    developer_path_block = ""
    if developer_mode:
        developer_path_block = (
            f'<div style="margin-top: 16px;">'
            f'<label for="csv_path">本地 CSV 路径（开发者模式）</label>'
            f'<input id="csv_path" name="csv_path" value="{escape(csv_path)}" data-testid="csv-path-input">'
            '</div>'
        )

    error_banner = f'<div class="error" data-testid="qb-demo-error">{escape(error_message)}</div>' if error_message else '<div data-testid="qb-demo-error" hidden></div>'

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <title>QuantBalance Web Demo</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f6f8fb; color: #1f2937; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
    .card {{ background: #fff; border-radius: 14px; padding: 20px; box-shadow: 0 8px 30px rgba(15, 23, 42, 0.08); margin-bottom: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    label {{ display: block; font-weight: 600; margin-bottom: 6px; }}
    input, textarea, select {{ width: 100%; box-sizing: border-box; border: 1px solid #d0d7e2; border-radius: 10px; padding: 10px 12px; font: inherit; background: #fff; }}
    textarea {{ min-height: 160px; }}
    .hint {{ color: #4b5563; font-size: 14px; }}
    .error {{ background: #fff1f2; color: #be123c; border: 1px solid #fecdd3; border-radius: 10px; padding: 12px; margin-bottom: 16px; }}
    .success {{ background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; border-radius: 10px; padding: 12px; margin-bottom: 16px; }}
    .radio-group {{ display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; }}
    .radio-group label {{ font-weight: 500; display: inline-flex; align-items: center; gap: 6px; margin: 0; }}
    button {{ border: 0; border-radius: 10px; background: #2563eb; color: #fff; padding: 11px 18px; font: inherit; font-weight: 600; cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #e5e7eb; text-align: left; vertical-align: top; }}
    code, pre {{ background: #f3f4f6; border-radius: 8px; }}
    pre {{ padding: 12px; overflow-x: auto; white-space: pre-wrap; }}
    ul {{ padding-left: 18px; }}
  </style>
</head>
<body>
  <main data-testid=\"qb-demo-page\">
    <section class=\"card\" data-testid=\"qb-demo-header\">
      <h1>QuantBalance 本地 Web Demo</h1>
      <p>先把主人可直接点开的最小回测路径跑通：选择示例数据或粘贴 CSV，提交后直接看到 summary、trades 与关键假设说明。</p>
    </section>

    <section class=\"card\" data-testid=\"qb-demo-form\">
      <h2>回测表单</h2>
      {error_banner}
      {('<div class="success" data-testid="qb-demo-success">已完成一次回测，可继续调整参数后再次提交。</div>' if result_context else '')}
      <form method=\"post\" action=\"/demo\">
        <div>
          <label>数据来源</label>
          <div class=\"radio-group\" data-testid=\"qb-input-mode\">
            {''.join(_render_mode_option(option['mode'], option['label'], selected_mode) for option in page_context.input_options)}
          </div>
        </div>
        <div class=\"grid\" style=\"margin-top: 16px;\">
          <div>
            <label for=\"symbol\">股票代码</label>
            <input id=\"symbol\" name=\"symbol\" value=\"{escape(symbol)}\" data-testid=\"qb-symbol-input\">
          </div>
          <div>
            <label for=\"initial_cash\">初始资金</label>
            <input id=\"initial_cash\" name=\"initial_cash\" value=\"{escape(initial_cash)}\" data-testid=\"qb-initial-cash-input\">
          </div>
          <div>
            <label for=\"short_window\">短均线</label>
            <input id=\"short_window\" name=\"short_window\" value=\"{escape(short_window)}\" data-testid=\"qb-short-window-input\">
          </div>
          <div>
            <label for=\"long_window\">长均线</label>
            <input id=\"long_window\" name=\"long_window\" value=\"{escape(long_window)}\" data-testid=\"qb-long-window-input\">
          </div>
        </div>

        <div style=\"margin-top: 16px;\">
          <label for=\"csv_text\">上传 CSV 内容（先用文本粘贴模拟上传）</label>
          <textarea id=\"csv_text\" name=\"csv_text\" data-testid=\"qb-upload-input\">{escape(csv_text)}</textarea>
          <p class=\"hint\">当前 MVP 先用 textarea 作为浏览器上传入口占位，后续可无缝换成文件上传控件。</p>
        </div>

        {developer_path_block}

        <div style=\"margin-top: 18px; display: flex; gap: 12px; flex-wrap: wrap;\">
          <button type=\"submit\" data-testid=\"qb-submit-backtest\">运行回测</button>
        </div>
      </form>
    </section>

    <section class=\"card\" data-testid=\"demo-guide\">
      <h2>输入说明与稳定锚点</h2>
      <p>{escape(page_context.field_guide.supported_frequency)}</p>
      <p>{escape(page_context.field_guide.recommended_ma_range)}</p>
      <ul>
        {''.join(f'<li>{escape(note)}</li>' for note in page_context.field_guide.notes)}
      </ul>
      <h3>CSV 模板</h3>
      <pre data-testid=\"csv-template\">{escape(page_context.csv_template)}</pre>
      <h3>示例 CSV 预览</h3>
      <pre data-testid=\"example-csv-preview\">{escape(example_csv_path.read_text(encoding='utf-8').strip())}</pre>
    </section>

    {render_result_section(result_context) if result_context else ''}
  </main>
</body>
</html>
"""



def run_demo_web_backtest(
    *,
    form_data: dict[str, str],
    developer_mode: bool = False,
    example_csv_path: Path = DEFAULT_EXAMPLE_CSV_PATH,
):
    input_mode = (form_data.get("input_mode") or "example").strip()
    symbol = (form_data.get("symbol") or "").strip()
    initial_cash = _parse_float(form_data.get("initial_cash"), field_name="初始资金")
    short_window = _parse_int(form_data.get("short_window"), field_name="短均线")
    long_window = _parse_int(form_data.get("long_window"), field_name="长均线")

    csv_text = None
    csv_path = None
    if input_mode == "upload":
        csv_text = form_data.get("csv_text", "")
    elif input_mode == "example":
        csv_text = example_csv_path.read_text(encoding="utf-8")
    elif input_mode == "path":
        csv_path = form_data.get("csv_path", "")

    request = BacktestDemoRequest(
        input_mode=input_mode,
        symbol=symbol,
        initial_cash=initial_cash,
        short_window=short_window,
        long_window=long_window,
        csv_text=csv_text,
        csv_path=csv_path,
        developer_mode=developer_mode,
    )
    bars = load_demo_bars(request)
    strategy = MovingAverageCrossStrategy(short_window=short_window, long_window=long_window)
    config = AccountConfig(initial_cash=initial_cash, max_position_ratio=1.0, max_positions=1, max_drawdown_ratio=1.0)
    engine = BacktestEngine(config=config, strategy=strategy)
    result = engine.run(bars)
    if result.report is None:
        raise RuntimeError("回测未生成 report")
    return build_demo_result_context(result.report)



def render_result_section(result_context) -> str:
    if result_context is None:
        return ""

    summary_rows = ''.join(
        f'<tr><th>{escape(_summary_label(key))}</th><td>{escape(_format_value(value))}</td></tr>'
        for key, value in result_context.summary.items()
    )
    trade_rows = ''.join(
        '<tr>'
        f'<td>{escape(str(trade["symbol"]))}</td>'
        f'<td>{escape(str(trade["entry_date"]))}</td>'
        f'<td>{escape(str(trade["exit_date"]))}</td>'
        f'<td>{escape(str(trade["quantity"]))}</td>'
        f'<td>{escape(_format_value(trade["entry_price"]))}</td>'
        f'<td>{escape(_format_value(trade["exit_price"]))}</td>'
        f'<td>{escape(_format_value(trade["pnl"]))}</td>'
        f'<td>{escape(_format_value(trade["pnl_ratio"]))}</td>'
        '</tr>'
        for trade in result_context.closed_trades
    )
    if not trade_rows:
        trade_rows = '<tr><td colspan="8">当前这次回测没有形成 closed trades，但 summary 已可用于页面回归验证。</td></tr>'

    assumptions = ''.join(f'<li>{escape(note)}</li>' for note in result_context.assumptions)
    chart_sections = ', '.join(result_context.chart_sections)
    sample_size_warning = ""
    if result_context.sample_size_warning:
        sample_size_warning = (
            f'<div class="error" data-testid="qb-sample-size-warning">{escape(result_context.sample_size_warning)}</div>'
        )
    return f"""
    <section class=\"card\" data-testid=\"qb-result-panel\">
      <h2>回测结果</h2>
      <p class=\"hint\">稳定结果区锚点：summary / trades / assumptions / chart-sections</p>
      {sample_size_warning}
      <div class=\"grid\">
        <div>
          <h3 data-testid=\"qb-summary-heading\">Summary</h3>
          <table data-testid=\"qb-result-summary\">{summary_rows}</table>
        </div>
        <div>
          <h3 data-testid=\"qb-assumptions-heading\">关键假设说明</h3>
          <ul data-testid=\"qb-result-assumptions\">{assumptions}</ul>
          <p data-testid=\"qb-chart-sections\">预留图表区块：{escape(chart_sections)}</p>
        </div>
      </div>
      <h3 data-testid=\"qb-trades-heading\">Closed Trades</h3>
      <table data-testid=\"qb-result-trades\">
        <thead>
          <tr><th>Symbol</th><th>Entry</th><th>Exit</th><th>Qty</th><th>Entry Px</th><th>Exit Px</th><th>PnL</th><th>PnL %</th></tr>
        </thead>
        <tbody>{trade_rows}</tbody>
      </table>
    </section>
    """



def _parse_form_data(environ: dict[str, object]) -> dict[str, str]:
    content_length = int(str(environ.get("CONTENT_LENGTH") or 0) or 0)
    body = b""
    if content_length > 0:
        stream = environ.get("wsgi.input")
        if stream is not None:
            body = stream.read(content_length)
    if not body:
        return {}
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}



def _render_mode_option(mode: str, label: str, selected_mode: str) -> str:
    checked = "checked" if selected_mode == mode else ""
    extra_testid = ' data-testid="qb-use-example"' if mode == "example" else ""
    return f'<label{extra_testid}><input type="radio" name="input_mode" value="{escape(mode)}" {checked}> {escape(label)}</label>'



def _parse_float(value: str | None, *, field_name: str) -> float:
    try:
        return float((value or "").strip())
    except ValueError as exc:
        raise DemoValidationError(f"{field_name}必须是数字。") from exc



def _parse_int(value: str | None, *, field_name: str) -> int:
    try:
        return int((value or "").strip())
    except ValueError as exc:
        raise DemoValidationError(f"{field_name}必须是整数。") from exc



def _summary_label(key: str) -> str:
    labels = {
        "initial_equity": "初始资金",
        "final_equity": "期末权益",
        "total_return_pct": "总收益率(%)",
        "annualized_return_pct": "年化收益率(%)",
        "annualized_volatility_pct": "年化波动率(%)",
        "sharpe_ratio": "夏普比率",
        "sortino_ratio": "Sortino 比率",
        "max_drawdown_pct": "最大回撤(%)",
        "max_drawdown_start": "最大回撤开始",
        "max_drawdown_end": "最大回撤结束",
        "trades_count": "已闭合交易数",
        "win_rate_pct": "胜率(%)",
        "turnover_ratio": "换手率",
        "benchmark_name": "基准名称",
        "benchmark_return_pct": "基准收益率(%)",
        "excess_return_pct": "超额收益(%)",
    }
    return labels.get(key, key)



def _format_value(value: object) -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
