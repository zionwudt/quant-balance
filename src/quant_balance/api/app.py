"""FastAPI 应用骨架。

当前阶段先提供基础健康检查、页面元信息和回测执行接口，
让未来前端可以直接消费 JSON，而不是继续依赖 Python 拼 HTML。
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import webbrowser

from quant_balance import __version__
from quant_balance.api.meta import build_backtest_meta
from quant_balance.api.presenters import build_backtest_response
from quant_balance.backtest_inputs import (
    DEFAULT_LONG_WINDOW,
    DEFAULT_SHORT_WINDOW,
    BacktestInputError,
    BacktestRequest,
)
from quant_balance.csv_loader import get_example_csv
from quant_balance.services.backtest_service import run_moving_average_backtest

DEFAULT_EXAMPLE_CSV_PATH = Path(__file__).resolve().parents[3] / "examples" / "demo_backtest.csv"
WEB_DEPENDENCY_HINT = "启动 API 模式需要先安装项目依赖：pip install -e ."


def create_api_app(
    *,
    developer_mode: bool = False,
    example_csv_path: Path = DEFAULT_EXAMPLE_CSV_PATH,
) -> Any:
    """创建 FastAPI 应用。"""

    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError(WEB_DEPENDENCY_HINT) from exc

    app = FastAPI(
        title="QuantBalance API",
        version=__version__,
        description="QuantBalance 回测与研究接口层。",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        """基础健康检查。"""

        return {"status": "ok"}

    @app.get("/api/meta")
    def api_meta() -> dict[str, object]:
        """返回表单和前端页面初始化所需的元信息。"""

        return asdict(
            build_backtest_meta(
                developer_mode=developer_mode,
                example_csv=_load_example_csv_text(example_csv_path),
            )
        )

    @app.post("/api/backtests/run")
    def run_backtest(payload: dict[str, object]) -> dict[str, object]:
        """执行一次回测，并返回 JSON 结果。"""

        try:
            request = _build_request_from_payload(payload, developer_mode=developer_mode)
            execution = run_moving_average_backtest(request, example_csv_path=example_csv_path)
            result_context = build_backtest_response(
                execution.report,
                run_context=execution.run_context,
                equity_curve_points=execution.equity_curve_points,
            )
        except BacktestInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return asdict(result_context)

    return app


def run_api_server(
    *,
    host: str,
    port: int,
    developer_mode: bool = False,
    open_browser: bool = False,
    example_csv_path: Path = DEFAULT_EXAMPLE_CSV_PATH,
) -> None:
    """启动 FastAPI 服务。"""

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(WEB_DEPENDENCY_HINT) from exc

    app = create_api_app(developer_mode=developer_mode, example_csv_path=example_csv_path)
    docs_url = f"http://{host}:{port}/docs"
    print(f"QuantBalance API is ready to start: http://{host}:{port}")
    print(f"接口文档地址：{docs_url}")
    if open_browser:
        opened = webbrowser.open(docs_url)
        status = "已尝试自动打开接口文档。" if opened else "未能自动打开浏览器，请手动访问上面的接口文档地址。"
        print(status)
    uvicorn.run(app, host=host, port=port)


def _load_example_csv_text(example_csv_path: Path) -> str:
    """优先读取磁盘上的示例 CSV，不存在时退回内联示例。"""

    if example_csv_path.exists():
        return example_csv_path.read_text(encoding="utf-8").strip()
    return get_example_csv()


def _build_request_from_payload(payload: dict[str, object] | None, *, developer_mode: bool) -> BacktestRequest:
    """把原始请求体规范化成服务层可直接消费的请求对象。"""

    payload = payload or {}
    quick_action = _payload_text(payload.get("quick_action"))
    input_mode = _payload_text(payload.get("input_mode"), default="example")
    if quick_action == "example-run":
        input_mode = "example"

    csv_text: str | None = None
    csv_path: str | None = None
    uploaded_csv_text = _payload_text(payload.get("csv_file_content"))
    if input_mode == "upload":
        csv_text = uploaded_csv_text or _payload_text(payload.get("csv_text"))
    elif input_mode == "path":
        csv_path = _payload_text(payload.get("csv_path"))

    return BacktestRequest(
        input_mode=input_mode,
        symbol=_payload_text(payload.get("symbol")),
        initial_cash=_payload_float(payload.get("initial_cash"), field_name="初始资金", default=100_000.0),
        short_window=_payload_int(payload.get("short_window"), field_name="短均线", default=DEFAULT_SHORT_WINDOW),
        long_window=_payload_int(payload.get("long_window"), field_name="长均线", default=DEFAULT_LONG_WINDOW),
        csv_text=csv_text,
        csv_path=csv_path,
        developer_mode=developer_mode,
    )


def _payload_text(value: object, *, default: str = "") -> str:
    """把请求体中的值规范化成字符串。"""

    if value is None:
        return default
    return str(value).strip()


def _payload_float(value: object, *, field_name: str, default: float) -> float:
    """把请求体中的值解析成浮点数。"""

    if value is None or str(value).strip() == "":
        return default
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise BacktestInputError(f"{field_name}必须是数字。") from exc


def _payload_int(value: object, *, field_name: str, default: int) -> int:
    """把请求体中的值解析成整数。"""

    if value is None or str(value).strip() == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise BacktestInputError(f"{field_name}必须是整数。") from exc
