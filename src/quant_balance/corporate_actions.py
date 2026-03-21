from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from quant_balance.models import MarketBar, Portfolio


@dataclass(frozen=True, slots=True)
class CorporateAction:
    symbol: str
    ex_date: date
    cash_dividend_per_share: float = 0.0
    share_ratio: float = 0.0

    def validate(self) -> None:
        if self.cash_dividend_per_share < 0:
            raise ValueError("cash_dividend_per_share 不能为负数")
        if self.share_ratio < 0:
            raise ValueError("share_ratio 不能为负数")


class CorporateActionBook:
    def __init__(self, actions: Iterable[CorporateAction] | None = None) -> None:
        self._actions_by_key: dict[tuple[str, date], list[CorporateAction]] = defaultdict(list)
        for action in actions or []:
            action.validate()
            self._actions_by_key[(action.symbol, action.ex_date)].append(action)

    def actions_for(self, symbol: str, ex_date: date) -> Sequence[CorporateAction]:
        return tuple(self._actions_by_key.get((symbol, ex_date), ()))

    def apply_to_portfolio(self, *, symbol: str, ex_date: date, portfolio: Portfolio) -> None:
        actions = self.actions_for(symbol, ex_date)
        if not actions:
            return

        position = portfolio.positions.get(symbol)
        if position is None or position.quantity <= 0:
            return

        for action in actions:
            if action.cash_dividend_per_share > 0:
                portfolio.cash += position.quantity * action.cash_dividend_per_share

            if action.share_ratio > 0:
                old_quantity = position.quantity
                new_quantity = int(round(old_quantity * (1 + action.share_ratio)))
                if old_quantity > 0:
                    position.avg_price = position.avg_price / (1 + action.share_ratio)
                position.quantity = new_quantity

    def apply_forward_adjustments(self, bars: Sequence[MarketBar]) -> list[MarketBar]:
        adjusted_bars = [
            MarketBar(
                symbol=bar.symbol,
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in bars
        ]

        bars_by_symbol: dict[str, list[int]] = defaultdict(list)
        for index, bar in enumerate(adjusted_bars):
            bars_by_symbol[bar.symbol].append(index)

        for symbol, indices in bars_by_symbol.items():
            symbol_bars = [adjusted_bars[index] for index in indices]
            symbol_bars.sort(key=lambda item: item.date)
            cumulative_factor = 1.0

            for idx in range(len(symbol_bars) - 1, -1, -1):
                current_bar = symbol_bars[idx]
                for price_field in ("open", "high", "low", "close"):
                    setattr(current_bar, price_field, getattr(current_bar, price_field) * cumulative_factor)

                actions = self.actions_for(symbol, current_bar.date)
                if not actions or idx == 0:
                    continue

                previous_close = symbol_bars[idx - 1].close
                event_factor = 1.0
                for action in actions:
                    event_factor *= _forward_adjustment_factor(previous_close, action)
                cumulative_factor *= event_factor

        return adjusted_bars


def _forward_adjustment_factor(previous_close: float, action: CorporateAction) -> float:
    if previous_close <= 0:
        raise ValueError("前一交易日收盘价必须大于 0，才能计算前复权因子")

    numerator = previous_close - action.cash_dividend_per_share
    denominator = previous_close * (1 + action.share_ratio)
    if numerator <= 0 or denominator <= 0:
        raise ValueError("公司行为导致前复权因子非法，请检查现金分红或送转参数")
    return numerator / denominator
