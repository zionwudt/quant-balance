"""信号导出：CSV / QMT / JSON。"""

from __future__ import annotations

from dataclasses import dataclass
import ast
import csv
import io
import json
from pathlib import Path
from typing import Literal

from quant_balance.core import signals as signal_store
from quant_balance.execution.adapters.qmt import QmtAdapter
from quant_balance.execution.models import ExecutionSignal

SignalExportFormat = Literal["csv", "qmt", "json"]
SUPPORTED_SIGNAL_EXPORT_FORMATS = frozenset({"csv", "qmt", "json"})


@dataclass(slots=True)
class SignalExportArtifact:
    """导出产物。"""

    filename: str
    media_type: str
    content: bytes
    format: SignalExportFormat
    trade_date: str
    total: int


def export_signals_for_date(
    *,
    format: str = "csv",
    date: str | None = None,
    db_path: Path | None = None,
) -> SignalExportArtifact:
    """导出指定日期的信号。"""

    export_format = _normalize_format(format)
    trade_date = signal_store.normalize_trade_date(date or signal_store.current_signal_date().isoformat())
    payload = signal_store.list_today_signals(as_of_date=trade_date, limit=500, db_path=db_path)
    items = list(payload.get("items") or [])

    if export_format == "csv":
        return _build_csv_artifact(items, trade_date=trade_date)
    if export_format == "qmt":
        return _build_qmt_artifact(items, trade_date=trade_date)
    return _build_json_artifact(items, trade_date=trade_date)


def _build_csv_artifact(items: list[dict[str, object]], *, trade_date: str) -> SignalExportArtifact:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["代码", "方向", "数量", "价格", "策略", "原因"])
    for item in items:
        writer.writerow([
            str(item.get("symbol") or "").upper(),
            str(item.get("side") or "BUY").upper(),
            int(item.get("suggested_qty") or 0),
            _format_price(item.get("signal_price")),
            str(item.get("strategy") or "").upper(),
            str(item.get("trigger_reason") or item.get("reason") or ""),
        ])

    content = buffer.getvalue().encode("gbk", errors="replace")
    return SignalExportArtifact(
        filename=f"signals-{trade_date}.csv",
        media_type="text/csv; charset=gbk",
        content=content,
        format="csv",
        trade_date=trade_date,
        total=len(items),
    )


def _build_json_artifact(items: list[dict[str, object]], *, trade_date: str) -> SignalExportArtifact:
    payload = {
        "date": trade_date,
        "total": len(items),
        "items": items,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return SignalExportArtifact(
        filename=f"signals-{trade_date}.json",
        media_type="application/json; charset=utf-8",
        content=content,
        format="json",
        trade_date=trade_date,
        total=len(items),
    )


def _build_qmt_artifact(items: list[dict[str, object]], *, trade_date: str) -> SignalExportArtifact:
    orders = [QmtAdapter.build_signal_payload(ExecutionSignal.from_signal_payload(item)) for item in items]
    script = f'''"""QuantBalance 自动生成的 miniQMT 交易指令。

交易日期: {trade_date}
信号数量: {len(items)}

使用方式:
1. 在 miniQMT 环境安装并确认 `xtquant` 可导入。
2. 按实际情况填写 `QMT_PATH`、`ACCOUNT_ID` 和 `ACCOUNT_TYPE`。
3. 直接运行本脚本即可按顺序下单。
"""

from __future__ import annotations

from xtquant import xtconstant, xttrader
from xtquant.xttype import StockAccount

QMT_PATH = r"C:\\miniQMT\\userdata_mini"
ACCOUNT_ID = "YOUR_ACCOUNT_ID"
ACCOUNT_TYPE = "STOCK"
SESSION_ID = "quant_balance_{trade_date.replace("-", "")}"

SIGNALS = {json.dumps(orders, ensure_ascii=False, indent=2)}


def resolve_order_type(side: str) -> int:
    return xtconstant.STOCK_BUY if side == "BUY" else xtconstant.STOCK_SELL


def resolve_price_type(price: float) -> int:
    return xtconstant.FIX_PRICE if price > 0 else xtconstant.LATEST_PRICE


def create_account() -> StockAccount:
    return StockAccount(ACCOUNT_ID, ACCOUNT_TYPE)


def place_orders() -> None:
    if ACCOUNT_ID == "YOUR_ACCOUNT_ID":
        raise SystemExit("请先把 ACCOUNT_ID 改成实际账户。")

    trader = xttrader.XtQuantTrader(QMT_PATH, SESSION_ID)
    trader.start()
    connect_result = trader.connect()
    if connect_result != 0:
        raise RuntimeError(f"XtQuantTrader.connect 失败: {{connect_result}}")

    account = create_account()
    subscribe_result = trader.subscribe(account)
    if subscribe_result != 0:
        raise RuntimeError(f"XtQuantTrader.subscribe 失败: {{subscribe_result}}")

    for signal in SIGNALS:
        order_remark = signal["remark"]
        order_id = trader.order_stock(
            account,
            signal["symbol"],
            resolve_order_type(signal["side"]),
            int(signal["quantity"]),
            resolve_price_type(float(signal["price"])),
            float(signal["price"]),
            signal["strategy_name"],
            order_remark,
        )
        print(
            f"submitted {{signal['symbol']}} {{signal['side']}} "
            f"qty={{signal['quantity']}} price={{signal['price']:.2f}} order_id={{order_id}}"
        )


if __name__ == "__main__":
    place_orders()
'''
    ast.parse(script)
    return SignalExportArtifact(
        filename=f"signals-{trade_date}-qmt.py",
        media_type="text/x-python; charset=utf-8",
        content=script.encode("utf-8"),
        format="qmt",
        trade_date=trade_date,
        total=len(items),
    )


def _format_price(value: object) -> str:
    price = float(value or 0.0)
    return f"{price:.2f}"


def _normalize_format(value: str) -> SignalExportFormat:
    normalized = str(value or "").strip().lower()
    if normalized not in SUPPORTED_SIGNAL_EXPORT_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_SIGNAL_EXPORT_FORMATS))
        raise ValueError(f"不支持的导出格式 {value!r}，当前支持: {supported}")
    return normalized  # type: ignore[return-value]


__all__ = [
    "SUPPORTED_SIGNAL_EXPORT_FORMATS",
    "SignalExportArtifact",
    "SignalExportFormat",
    "export_signals_for_date",
]
