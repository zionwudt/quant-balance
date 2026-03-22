from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_policy
from html import escape
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs
import webbrowser
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
    open_browser: bool = False,
    example_csv_path: Path = DEFAULT_EXAMPLE_CSV_PATH,
) -> None:
    app = create_app(developer_mode=developer_mode, example_csv_path=example_csv_path)
    with make_server(host, port, app) as server:
        demo_url = f"http://{host}:{port}/demo"
        print(f"QuantBalance Web Demo is ready: {demo_url}")
        print("首次使用建议：先保持默认参数，直接用“示例数据”完成一次回测。")
        print("三步即可体验：打开页面 → 点击运行回测 → 查看 summary / trades / 假设说明。")
        if open_browser:
            opened = webbrowser.open(demo_url)
            print("已尝试自动打开浏览器。" if opened else "未能自动打开浏览器，请手动访问上面的链接。")
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
    uploaded_filename = form_data.get("csv_filename", "")

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
            "</div>"
        )

    error_banner = f'<div class="error" data-testid="qb-demo-error">{escape(error_message)}</div>' if error_message else '<div data-testid="qb-demo-error" hidden></div>'
    upload_hint = f"已选择文件：{uploaded_filename}" if uploaded_filename else "选择本地 CSV 文件上传；若暂时没有文件，也可继续粘贴 CSV 文本做调试。"

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
    pre {{ background: #f3f4f6; border-radius: 8px; padding: 12px; overflow-x: auto; white-space: pre-wrap; }}
    ul {{ padding-left: 18px; }}
    .export-box {{ max-height: 260px; overflow: auto; }}
    .context-list dt {{ font-weight: 700; margin-top: 8px; }}
    .context-list dd {{ margin: 2px 0 8px 0; color: #374151; }}
  </style>
</head>
<body>
  <main data-testid=\"qb-demo-page\">
    <section class=\"card\" data-testid=\"qb-demo-header\">
      <h1>QuantBalance 本地 Web Demo</h1>
      <p>先把主人可直接点开的最小回测路径跑通：选择示例数据或上传 CSV，提交后直接看到 summary、trades 与关键假设说明。</p>
      <div class=\"success\" data-testid=\"first-run-guide\">
        <strong>第一次使用建议：</strong>先保持默认参数，直接用“示例数据”跑一遍。<br>
        <strong>三步完成：</strong>1) 打开页面 2) 点击“运行回测” 3) 查看 summary / trades / 假设说明。
      </div>
    </section>

    <section class=\"card\" data-testid=\"qb-demo-form\">
      <h2>回测表单</h2>
      {error_banner}
      {('<div class="success" data-testid="qb-demo-success">已完成一次回测，可继续调整参数后再次提交。</div>' if result_context else '')}
      <form method=\"post\" action=\"/demo\" enctype=\"multipart/form-data\">
        <div>
          <label>数据来源</label>
          <div class=\"radio-group\" data-testid=\"qb-input-mode\">
            {''.join(_render_mode_option(option['mode'], option['label'], selected_mode) for option in page_context.input_options)}
          </div>
        </div>
        <div class=\"grid\" style=\"margin-top: 16px;\">
          <div><label for=\"symbol\">股票代码</label><input id=\"symbol\" name=\"symbol\" value=\"{escape(symbol)}\" data-testid=\"qb-symbol-input\"></div>
          <div><label for=\"initial_cash\">初始资金</label><input id=\"initial_cash\" name=\"initial_cash\" value=\"{escape(initial_cash)}\" data-testid=\"qb-initial-cash-input\"></div>
          <div><label for=\"short_window\">短均线</label><input id=\"short_window\" name=\"short_window\" value=\"{escape(short_window)}\" data-testid=\"qb-short-window-input\"></div>
          <div><label for=\"long_window\">长均线</label><input id=\"long_window\" name=\"long_window\" value=\"{escape(long_window)}\" data-testid=\"qb-long-window-input\"></div>
        </div>
        <div style=\"margin-top: 16px;\">
          <label for=\"csv_file\">上传 CSV 文件</label>
          <input id=\"csv_file\" name=\"csv_file\" type=\"file\" accept=\".csv,text/csv\" data-testid=\"qb-upload-input\">
          <p class=\"hint\" data-testid=\"csv-upload-hint\">{escape(upload_hint)}</p>
        </div>
        <details style=\"margin-top: 16px;\">
          <summary>开发 / 调试辅助：直接粘贴 CSV 文本</summary>
          <textarea id=\"csv_text\" name=\"csv_text\" data-testid=\"csv-upload-textarea\">{escape(csv_text)}</textarea>
          <p class=\"hint\">上传文件会优先于文本粘贴路径；textarea 仅作为调试辅助保留。</p>
        </details>
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
      <ul>{''.join(f'<li>{escape(note)}</li>' for note in page_context.field_guide.notes)}</ul>
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


def run_demo_web_backtest(*, form_data: dict[str, str], developer_mode: bool = False, example_csv_path: Path = DEFAULT_EXAMPLE_CSV_PATH):
    input_mode = (form_data.get("input_mode") or "example").strip()
    symbol = (form_data.get("symbol") or "").strip()
    initial_cash = _parse_float(form_data.get("initial_cash"), field_name="初始资金")
    short_window = _parse_int(form_data.get("short_window"), field_name="短均线")
    long_window = _parse_int(form_data.get("long_window"), field_name="长均线")

    csv_text = None
    csv_path = None
    uploaded_csv_text = form_data.get("csv_file_content", "")
    if input_mode == "upload":
        csv_text = uploaded_csv_text or form_data.get("csv_text", "")
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
    result = BacktestEngine(config=config, strategy=strategy).run(bars)
    if result.report is None:
        raise RuntimeError("回测未生成 report")
    run_context = {
        "input_mode": input_mode,
        "symbol": symbol,
        "initial_cash": initial_cash,
        "short_window": short_window,
        "long_window": long_window,
        "bars_count": len(bars),
        "date_range_start": bars[0].date.isoformat() if bars else None,
        "date_range_end": bars[-1].date.isoformat() if bars else None,
    }
    equity_curve_points = [{"date": d.isoformat(), "equity": e} for d, e in zip(result.equity_dates, result.equity_curve)]
    return build_demo_result_context(result.report, run_context=run_context, equity_curve_points=equity_curve_points)


def render_result_section(result_context) -> str:
    if result_context is None:
        return ""
    summary_rows = ''.join(f'<tr><th>{escape(_summary_label(k))}</th><td>{escape(_format_value(v))}</td></tr>' for k, v in result_context.summary.items())
    trade_rows = ''.join(
        '<tr>'
        f'<td>{escape(str(t["symbol"]))}</td><td>{escape(str(t["entry_date"]))}</td><td>{escape(str(t["exit_date"]))}</td>'
        f'<td>{escape(str(t["quantity"]))}</td><td>{escape(_format_value(t["entry_price"]))}</td><td>{escape(_format_value(t["exit_price"]))}</td>'
        f'<td>{escape(_format_value(t["pnl"]))}</td><td>{escape(_format_value(t["pnl_ratio"]))}</td>'
        '</tr>' for t in result_context.closed_trades
    ) or '<tr><td colspan="8">当前这次回测没有形成 closed trades，但 summary 已可用于页面回归验证。</td></tr>'
    assumptions = ''.join(f'<li>{escape(note)}</li>' for note in result_context.assumptions)
    sample_size_warning = f'<div class="error" data-testid="qb-sample-size-warning">{escape(result_context.sample_size_warning)}</div>' if result_context.sample_size_warning else ''
    run_context = result_context.run_context or {}
    context_items = ''.join(f'<dt>{escape(str(k))}</dt><dd>{escape(_format_value(v))}</dd>' for k, v in run_context.items())
    export_json = escape(result_context.export_json or "")
    equity_svg = _render_equity_curve_svg(result_context.equity_curve_points or [])
    chart_sections = ', '.join(result_context.chart_sections)
    return f"""
    <section class=\"card\" data-testid=\"qb-result-panel\">
      <h2>回测结果</h2>
      <p class=\"hint\">稳定结果区锚点：summary / trades / assumptions / chart-sections</p>
      {sample_size_warning}
      <div class=\"grid\">
        <div><h3 data-testid=\"qb-summary-heading\">Summary</h3><table data-testid=\"qb-result-summary\">{summary_rows}</table></div>
        <div><h3 data-testid=\"qb-assumptions-heading\">关键假设说明</h3><ul data-testid=\"qb-result-assumptions\">{assumptions}</ul><p data-testid=\"qb-chart-sections\">预留图表区块：{escape(chart_sections)}</p></div>
      </div>
      <div class=\"grid\" style=\"margin-top: 16px;\">
        <div><h3 data-testid=\"qb-equity-curve-heading\">权益曲线（轻量 SVG）</h3><div data-testid=\"qb-equity-curve\">{equity_svg}</div></div>
        <div><h3 data-testid=\"qb-run-context-heading\">本次回测上下文</h3><dl class=\"context-list\" data-testid=\"qb-run-context\">{context_items}</dl></div>
      </div>
      <div style=\"margin-top: 16px;\"><h3 data-testid=\"qb-export-heading\">结果导出（JSON 快照）</h3><pre class=\"export-box\" data-testid=\"qb-export-json\">{export_json}</pre></div>
      <h3 data-testid=\"qb-trades-heading\">Closed Trades</h3>
      <table data-testid=\"qb-result-trades\"><thead><tr><th>Symbol</th><th>Entry</th><th>Exit</th><th>Qty</th><th>Entry Px</th><th>Exit Px</th><th>PnL</th><th>PnL %</th></tr></thead><tbody>{trade_rows}</tbody></table>
    </section>
    """


def _render_equity_curve_svg(points: list[dict[str, object]]) -> str:
    if not points:
        return "<p>暂无权益曲线数据。</p>"
    width, height, padding = 520, 180, 20
    equities = [float(point["equity"]) for point in points]
    min_equity, max_equity = min(equities), max(equities)
    span = max(max_equity - min_equity, 1.0)
    x_step = (width - padding * 2) / max(len(points) - 1, 1)
    coords = []
    for i, point in enumerate(points):
        x = padding + i * x_step
        y = height - padding - ((float(point["equity"]) - min_equity) / span) * (height - padding * 2)
        coords.append(f"{x:.1f},{y:.1f}")
    polyline = ' '.join(coords)
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="180" role="img" aria-label="equity curve">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f8fafc" rx="12"></rect>'
        f'<polyline fill="none" stroke="#2563eb" stroke-width="3" points="{polyline}"></polyline>'
        f'<text x="{padding}" y="18" fill="#475569" font-size="12">min {min_equity:.2f}</text>'
        f'<text x="{width - 120}" y="18" fill="#475569" font-size="12">max {max_equity:.2f}</text>'
        '</svg>'
    )


def _parse_form_data(environ: dict[str, object]) -> dict[str, str]:
    content_type = str(environ.get("CONTENT_TYPE") or "")
    if content_type.startswith("multipart/form-data"):
        return _parse_multipart_form_data(environ)
    content_length = int(str(environ.get("CONTENT_LENGTH") or 0) or 0)
    stream = environ.get("wsgi.input")
    body = stream.read(content_length) if stream is not None and content_length > 0 else b""
    if not body:
        return {}
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {k: v[-1] if v else "" for k, v in parsed.items()}


def _parse_multipart_form_data(environ: dict[str, object]) -> dict[str, str]:
    content_type = str(environ.get("CONTENT_TYPE") or "")
    content_length = int(str(environ.get("CONTENT_LENGTH") or 0) or 0)
    stream = environ.get("wsgi.input")
    body = stream.read(content_length) if stream is not None and content_length > 0 else b""
    if not body:
        return {}
    message = BytesParser(policy=email_policy).parsebytes(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body)
    form_data: dict[str, str] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if filename:
            form_data[f"{name}_content"] = text
            form_data[f"{name}_filename"] = filename
        else:
            form_data[name] = text
    if "csv_file_filename" in form_data:
        form_data["csv_filename"] = form_data["csv_file_filename"]
    return form_data


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
    return {
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
    }.get(key, key)


def _format_value(value: object) -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _print_module_entry_hint() -> int:
    import sys
    print("quant_balance.web_demo 不是独立 CLI 入口。\n请改用：python -m quant_balance web-demo --help\n或：quant-balance web-demo --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_print_module_entry_hint())
