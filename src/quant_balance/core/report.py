"""回测报告 — 汇总回测结果的关键指标与交易明细。"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
import math

from .models import Fill

# A 股年化指标默认按 252 个交易日折算。
TRADING_DAYS_PER_YEAR = 252
# 样本太短时，年化与风险指标波动很大，因此显式降级为提示信息。
MIN_PERIODS_FOR_ANNUALIZED_METRICS = 60
SHORT_SAMPLE_WARNING = "当前样本较短，年化收益、波动率、夏普与 Sortino 仅供演示参考。"


@dataclass(slots=True)
class ClosedTrade:
    """由多笔成交回报聚合出的已闭合交易。"""

    symbol: str
    entry_date: date
    exit_date: date
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_ratio: float
    holding_days: int


@dataclass(slots=True)
class BacktestReport:
    """回测结果面向展示层的汇总快照。"""

    initial_equity: float
    final_equity: float
    total_return_pct: float
    annualized_return_pct: float | None
    annualized_volatility_pct: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown_pct: float
    max_drawdown_amount: float
    max_drawdown_start: date | None
    max_drawdown_end: date | None
    trades_count: int
    fills_count: int
    win_rate_pct: float
    profit_loss_ratio: float | None
    average_holding_days: float
    turnover_ratio: float
    benchmark_name: str | None = None
    benchmark_return_pct: float | None = None
    excess_return_pct: float | None = None
    sample_size_warning: str | None = None
    closed_trades: list[ClosedTrade] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """转换成适合 JSON 序列化的字典结构。"""

        payload = asdict(self)
        payload["max_drawdown_start"] = self.max_drawdown_start.isoformat() if self.max_drawdown_start else None
        payload["max_drawdown_end"] = self.max_drawdown_end.isoformat() if self.max_drawdown_end else None
        payload["closed_trades"] = [
            {
                **asdict(trade),
                "entry_date": trade.entry_date.isoformat(),
                "exit_date": trade.exit_date.isoformat(),
            }
            for trade in self.closed_trades
        ]
        return payload


def generate_report(
    *,
    initial_equity: float,
    equity_curve: Sequence[float],
    equity_dates: Sequence[date],
    fills: Sequence[Fill],
    benchmark_name: str | None = None,
    benchmark_equity_curve: Sequence[float] | None = None,
) -> BacktestReport:
    """根据权益曲线和成交记录生成所有衍生指标。"""

    if len(equity_curve) != len(equity_dates):
        raise ValueError("equity_curve and equity_dates must have the same length")

    final_equity = equity_curve[-1] if equity_curve else initial_equity
    total_return_pct = _safe_pct_change(initial_equity, final_equity)
    daily_returns = _daily_returns(equity_curve)
    sample_size_warning = None
    if len(equity_curve) < MIN_PERIODS_FOR_ANNUALIZED_METRICS:
        # 样本过短时保留总收益和回撤，但不输出容易误导的年化类指标。
        annualized_return_pct = None
        annualized_volatility_pct = None
        sharpe_ratio = None
        sortino_ratio = None
        sample_size_warning = SHORT_SAMPLE_WARNING
    else:
        annualized_return_pct = _annualized_return_pct(initial_equity, final_equity, len(equity_curve))
        annualized_volatility_pct = _annualized_volatility_pct(daily_returns)
        sharpe_ratio = _sharpe_ratio(daily_returns)
        sortino_ratio = _sortino_ratio(daily_returns)

    # 回撤和交易统计都直接从原始曲线/成交序列衍生，避免依赖策略内部状态。
    drawdown_amount, drawdown_pct, drawdown_start, drawdown_end = _max_drawdown(equity_curve, equity_dates)
    closed_trades = _closed_trades(fills)
    trades_count = len(closed_trades)
    win_rate_pct = _win_rate_pct(closed_trades)
    profit_loss_ratio = _profit_loss_ratio(closed_trades)
    average_holding_days = _average_holding_days(closed_trades)
    turnover_ratio = _turnover_ratio(fills, initial_equity)
    benchmark_return_pct = None
    excess_return_pct = None
    if benchmark_equity_curve:
        if len(benchmark_equity_curve) != len(equity_curve):
            raise ValueError("benchmark_equity_curve must match equity_curve length")
        # 基准曲线默认假设与策略曲线拥有相同采样点，因此这里只比较起止收益。
        benchmark_return_pct = _safe_pct_change(benchmark_equity_curve[0], benchmark_equity_curve[-1])
        excess_return_pct = total_return_pct - benchmark_return_pct

    return BacktestReport(
        initial_equity=initial_equity,
        final_equity=final_equity,
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized_return_pct,
        annualized_volatility_pct=annualized_volatility_pct,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        max_drawdown_pct=drawdown_pct,
        max_drawdown_amount=drawdown_amount,
        max_drawdown_start=drawdown_start,
        max_drawdown_end=drawdown_end,
        trades_count=trades_count,
        fills_count=len(fills),
        win_rate_pct=win_rate_pct,
        profit_loss_ratio=profit_loss_ratio,
        average_holding_days=average_holding_days,
        turnover_ratio=turnover_ratio,
        benchmark_name=benchmark_name,
        benchmark_return_pct=benchmark_return_pct,
        excess_return_pct=excess_return_pct,
        sample_size_warning=sample_size_warning,
        closed_trades=closed_trades,
    )


def _daily_returns(equity_curve: Sequence[float]) -> list[float]:
    """把权益曲线转换成逐日简单收益率。"""

    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        if previous <= 0:
            returns.append(0.0)
        else:
            returns.append((current / previous) - 1.0)
    return returns


def _annualized_return_pct(initial_equity: float, final_equity: float, periods: int) -> float:
    """把观察期内的总收益折算成年化收益率。"""

    if initial_equity <= 0 or final_equity <= 0 or periods <= 1:
        return 0.0
    years = periods / TRADING_DAYS_PER_YEAR
    return ((final_equity / initial_equity) ** (1 / years) - 1.0) * 100


def _annualized_volatility_pct(daily_returns: Sequence[float]) -> float:
    """根据日收益率计算年化样本波动率。"""

    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((value - mean) ** 2 for value in daily_returns) / (len(daily_returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100


def _sharpe_ratio(daily_returns: Sequence[float]) -> float:
    """计算无风险利率为 0 时的夏普比率。"""

    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    volatility = _annualized_volatility_pct(daily_returns) / 100
    if volatility == 0:
        return 0.0
    return (mean * TRADING_DAYS_PER_YEAR) / volatility


def _sortino_ratio(daily_returns: Sequence[float]) -> float:
    """仅使用下行波动计算 Sortino 比率。"""

    if len(daily_returns) < 2:
        return 0.0
    downside = [min(value, 0.0) for value in daily_returns]
    downside_variance = sum(value**2 for value in downside) / len(daily_returns)
    downside_deviation = math.sqrt(downside_variance) * math.sqrt(TRADING_DAYS_PER_YEAR)
    if downside_deviation == 0:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    return (mean * TRADING_DAYS_PER_YEAR) / downside_deviation


def _max_drawdown(equity_curve: Sequence[float], equity_dates: Sequence[date]) -> tuple[float, float, date | None, date | None]:
    """找出权益曲线中最差的一段峰值到谷值回撤。"""

    if not equity_curve:
        return 0.0, 0.0, None, None
    peak_value = equity_curve[0]
    peak_date = equity_dates[0]
    worst_amount = 0.0
    worst_pct = 0.0
    worst_start = peak_date
    worst_end = peak_date
    for current_date, equity in zip(equity_dates, equity_curve):
        if equity > peak_value:
            peak_value = equity
            peak_date = current_date
        # 这里持续拿当前权益和历史峰值比较，记录最差的一次回撤区间。
        drawdown_amount = peak_value - equity
        drawdown_pct = drawdown_amount / peak_value if peak_value > 0 else 0.0
        if drawdown_pct > worst_pct:
            worst_amount = drawdown_amount
            worst_pct = drawdown_pct
            worst_start = peak_date
            worst_end = current_date
    return worst_amount, worst_pct * 100, worst_start, worst_end


def _closed_trades(fills: Sequence[Fill]) -> list[ClosedTrade]:
    """按 FIFO 规则把买卖成交配对成已闭合交易。"""

    open_lots: dict[str, deque[tuple[date, int, float]]] = {}
    trades: list[ClosedTrade] = []
    for fill in fills:
        lots = open_lots.setdefault(fill.symbol, deque())
        if fill.side == "BUY":
            # 买入成交先进入待平仓队列，后续卖出按 FIFO 与之配对。
            lots.append((fill.date, fill.quantity, fill.price))
            continue
        quantity_to_close = fill.quantity
        while quantity_to_close > 0 and lots:
            entry_date, lot_quantity, entry_price = lots[0]
            matched_quantity = min(quantity_to_close, lot_quantity)
            pnl = (fill.price - entry_price) * matched_quantity
            pnl_ratio = ((fill.price / entry_price) - 1.0) * 100 if entry_price > 0 else 0.0
            trades.append(
                ClosedTrade(
                    symbol=fill.symbol,
                    entry_date=entry_date,
                    exit_date=fill.date,
                    quantity=matched_quantity,
                    entry_price=entry_price,
                    exit_price=fill.price,
                    pnl=pnl,
                    pnl_ratio=pnl_ratio,
                    holding_days=(fill.date - entry_date).days,
                )
            )
            quantity_to_close -= matched_quantity
            if matched_quantity == lot_quantity:
                lots.popleft()
            else:
                # 若只平掉部分仓位，则保留剩余 lot 继续等待后续卖出。
                lots[0] = (entry_date, lot_quantity - matched_quantity, entry_price)
    return trades


def _win_rate_pct(trades: Sequence[ClosedTrade]) -> float:
    """返回已闭合交易中盈利交易的占比。"""

    if not trades:
        return 0.0
    wins = sum(1 for trade in trades if trade.pnl > 0)
    return wins / len(trades) * 100


def _profit_loss_ratio(trades: Sequence[ClosedTrade]) -> float | None:
    """在盈亏两侧都存在时，返回平均盈利与平均亏损的比值。"""

    profits = [trade.pnl for trade in trades if trade.pnl > 0]
    losses = [-trade.pnl for trade in trades if trade.pnl < 0]
    if not profits:
        return 0.0 if losses else None
    if not losses:
        return None
    avg_profit = sum(profits) / len(profits)
    avg_loss = sum(losses) / len(losses)
    if avg_loss == 0:
        return None
    return avg_profit / avg_loss


def _average_holding_days(trades: Sequence[ClosedTrade]) -> float:
    """返回已闭合交易的平均持有天数。"""

    if not trades:
        return 0.0
    return sum(trade.holding_days for trade in trades) / len(trades)


def _turnover_ratio(fills: Sequence[Fill], initial_equity: float) -> float:
    """用成交总额除以初始权益，近似计算换手率。"""

    if initial_equity <= 0:
        return 0.0
    turnover = sum(fill.quantity * fill.price for fill in fills)
    return turnover / initial_equity


def _safe_pct_change(start: float, end: float) -> float:
    """一个带保护的涨跌幅计算函数，供报表层统一复用。"""

    if start <= 0:
        return 0.0
    return (end / start - 1.0) * 100
