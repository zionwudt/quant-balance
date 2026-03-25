/**
 * 知衡 QuantBalance — 模拟盘 / 信号中心本地状态
 */

import { getAppSettings } from '../settings.js';

const PAPER_STATE_KEY = 'qb-paper-state';
const PAPER_EVENT = 'qb-paper-state-changed';

const WATCHLIST = [
  { symbol: '600519.SH', name: '贵州茅台', base_price: 1685, strategy: 'ma_rsi_filter', trigger_reason: '趋势延续 + RSI 再次站回 55' },
  { symbol: '000858.SZ', name: '五粮液', base_price: 136.2, strategy: 'sma_cross', trigger_reason: '5/20 日均线金叉，量能同步放大' },
  { symbol: '601318.SH', name: '中国平安', base_price: 45.4, strategy: 'macd', trigger_reason: 'MACD 零轴上方二次金叉' },
  { symbol: '600036.SH', name: '招商银行', base_price: 34.8, strategy: 'ema_cross', trigger_reason: 'EMA 快线重新站上慢线' },
  { symbol: '601899.SH', name: '紫金矿业', base_price: 18.7, strategy: 'bollinger', trigger_reason: '布林上轨突破，趋势加速' },
  { symbol: '600900.SH', name: '长江电力', base_price: 27.9, strategy: 'dca', trigger_reason: '回撤到长期均线附近，适合分批建仓' },
];

export function getPaperState() {
  return normalizeState(readState());
}

export function summarizePaperState(state = getPaperState()) {
  const holdings = (state.holdings || []).map(enrichHolding);
  const holdingsValue = holdings.reduce((sum, item) => sum + item.market_value, 0);
  const equity = roundMoney((state.cash || 0) + holdingsValue);
  const todayBase = getTodayBaseEquity(state.equity_curve || [], equity);
  const todayPnl = roundMoney(equity - todayBase);
  const exposurePct = equity > 0 ? +(holdingsValue / equity * 100).toFixed(2) : 0;

  return {
    status: state.status,
    equity,
    cash: roundMoney(state.cash || 0),
    holdings_value: roundMoney(holdingsValue),
    exposure_pct: exposurePct,
    today_pnl: todayPnl,
    holdings: holdings.sort((left, right) => right.market_value - left.market_value),
    trade_log: [...(state.trade_log || [])].sort((left, right) => String(right.timestamp).localeCompare(String(left.timestamp))),
    equity_curve: state.equity_curve || [],
    started_at: state.started_at,
    last_tick_at: state.last_tick_at,
  };
}

export function buildPaperReport(state = getPaperState()) {
  return {
    generated_at: toIsoString(new Date()),
    summary: summarizePaperState(state),
    holdings: (state.holdings || []).map(enrichHolding),
    trade_log: [...(state.trade_log || [])].sort((left, right) => String(right.timestamp).localeCompare(String(left.timestamp))),
    equity_curve: state.equity_curve || [],
    signal_history: state.signal_history || [],
  };
}

export function subscribePaperState(listener) {
  const handler = (event) => {
    listener(event.detail.state);
  };
  window.addEventListener(PAPER_EVENT, handler);
  return () => window.removeEventListener(PAPER_EVENT, handler);
}

export function tickPaperTrading() {
  return updatePaperState((state) => {
    if (state.status !== 'running') {
      return state;
    }

    const now = new Date();
    const next = deepClone(state);
    next.last_tick_at = toIsoString(now);
    next.holdings = (next.holdings || []).map((holding, index) => {
      const seed = hashSymbol(holding.symbol) + index * 17;
      const drift = Math.sin(now.getTime() / 900000 + seed) * 0.0032
        + Math.cos(now.getTime() / 3600000 + seed) * 0.0011;
      const floor = Number(holding.cost_price || holding.last_price || 1) * 0.72;
      const ceiling = Number(holding.cost_price || holding.last_price || 1) * 1.42;
      const lastPrice = clamp(
        Number(holding.last_price || holding.cost_price || 0) * (1 + drift),
        floor,
        ceiling,
      );
      return {
        ...holding,
        last_price: roundPrice(lastPrice),
        updated_at: next.last_tick_at,
      };
    });

    appendEquityPoint(next, now);
    return next;
  });
}

export function pausePaperTrading() {
  return updatePaperState((state) => ({
    ...state,
    status: 'paused',
    last_tick_at: toIsoString(new Date()),
  }));
}

export function resumePaperTrading() {
  return updatePaperState((state) => ({
    ...state,
    status: 'running',
    last_tick_at: toIsoString(new Date()),
  }));
}

export function stopPaperTrading() {
  return updatePaperState((state) => {
    const next = deepClone(state);
    next.status = 'stopped';
    next.last_tick_at = toIsoString(new Date());
    appendEquityPoint(next, new Date());
    return next;
  });
}

export function addSignalToPaperTrading(signal) {
  if (!signal?.symbol || !signal?.side) {
    throw new Error('信号数据不完整，无法加入模拟盘');
  }

  return updatePaperState((state) => {
    if (state.status === 'stopped') {
      throw new Error('模拟盘已停止，请刷新后重新开始新一轮跟踪');
    }

    const next = deepClone(state);
    const now = new Date();
    const price = roundPrice(Number(signal.price || 0));
    const quantity = normalizeQuantity(signal.side, signal.suggested_qty || 0);
    if (!(price > 0) || !(quantity > 0)) {
      throw new Error('信号价格或数量无效');
    }

    const tradeNotional = roundMoney(price * quantity);
    const positionIndex = next.holdings.findIndex((item) => item.symbol === signal.symbol);
    const existing = positionIndex >= 0 ? next.holdings[positionIndex] : null;

    if (signal.side === 'buy') {
      if (next.cash < tradeNotional) {
        throw new Error('可用现金不足，无法执行该买入信号');
      }

      next.cash = roundMoney(next.cash - tradeNotional);
      if (existing) {
        const totalQty = Number(existing.qty || 0) + quantity;
        const totalCost = Number(existing.cost_price || 0) * Number(existing.qty || 0) + tradeNotional;
        next.holdings[positionIndex] = {
          ...existing,
          qty: totalQty,
          cost_price: roundPrice(totalCost / totalQty),
          last_price: price,
          strategy: signal.strategy || existing.strategy,
          updated_at: toIsoString(now),
        };
      } else {
        next.holdings.push({
          symbol: signal.symbol,
          name: signal.name || signal.symbol,
          qty: quantity,
          cost_price: price,
          last_price: price,
          strategy: signal.strategy || 'manual_signal',
          opened_at: toIsoString(now),
          updated_at: toIsoString(now),
        });
      }
    } else {
      if (!existing || Number(existing.qty || 0) <= 0) {
        throw new Error('当前没有可卖出的持仓');
      }

      const sellQty = Math.min(quantity, Number(existing.qty || 0));
      next.cash = roundMoney(next.cash + price * sellQty);
      const remainingQty = Number(existing.qty || 0) - sellQty;
      if (remainingQty > 0) {
        next.holdings[positionIndex] = {
          ...existing,
          qty: remainingQty,
          last_price: price,
          updated_at: toIsoString(now),
        };
      } else {
        next.holdings.splice(positionIndex, 1);
      }
    }

    next.trade_log.unshift({
      id: buildId(signal.symbol, signal.side, now),
      timestamp: toIsoString(now),
      side: signal.side,
      symbol: signal.symbol,
      name: signal.name || signal.symbol,
      strategy: signal.strategy || 'manual_signal',
      reason: signal.trigger_reason || signal.reason || '来自信号中心',
      price,
      qty: quantity,
      notional: tradeNotional,
    });
    next.trade_log = next.trade_log.slice(0, 60);

    next.signal_history.unshift(buildSignalHistoryItem(signal, now));
    next.signal_history = next.signal_history.slice(0, 40);
    next.last_tick_at = toIsoString(now);
    appendEquityPoint(next, now);
    return next;
  });
}

export function getSignalCenterSnapshot() {
  const state = getPaperState();
  const settings = getAppSettings();
  const holdings = summarizePaperState(state).holdings;
  const heldSymbols = new Set(holdings.map((item) => item.symbol));
  const generatedAt = toIsoString(new Date());

  const buySignals = WATCHLIST
    .filter((item) => !heldSymbols.has(item.symbol))
    .slice(0, 4)
    .map((item, index) => buildBuySignal(item, settings, generatedAt, index));

  const sellSignals = holdings
    .slice(0, 4)
    .map((item, index) => buildSellSignal(item, generatedAt, index));

  return {
    generated_at: generatedAt,
    buy_signals: buySignals,
    sell_signals: sellSignals,
    history: (state.signal_history || []).map((item) => ({
      ...item,
      side_label: item.side === 'buy' ? '买入' : '卖出',
    })),
  };
}

function buildBuySignal(item, settings, generatedAt, index) {
  const allocation = 0.08 + index * 0.015;
  const cash = Number(settings.trading_defaults?.cash || 100000);
  const price = roundPrice(Number(item.base_price) * (1 + Math.sin(index + Date.now() / 7200000) * 0.01));
  const affordableQty = Math.max(1, Math.floor(cash * allocation / price));
  return {
    id: `buy-${item.symbol}`,
    side: 'buy',
    side_label: '买入',
    symbol: item.symbol,
    name: item.name,
    strategy: item.strategy,
    trigger_reason: item.trigger_reason,
    price,
    suggested_qty: normalizeQuantity('buy', affordableQty),
    confidence: `${72 + index * 5}%`,
    generated_at: generatedAt,
  };
}

function buildSellSignal(item, generatedAt, index) {
  const qty = normalizeQuantity('sell', Math.max(100, Math.floor(Number(item.qty || 0) * 0.5 / 100) * 100));
  const profitable = Number(item.pnl_pct || 0) >= 0;
  return {
    id: `sell-${item.symbol}`,
    side: 'sell',
    side_label: '卖出',
    symbol: item.symbol,
    name: item.name || item.symbol,
    strategy: item.strategy || 'position_monitor',
    trigger_reason: profitable
      ? '达到阶段目标位，建议锁定部分利润'
      : '跌破跟踪止损线，建议先减仓控制回撤',
    price: roundPrice(item.last_price || item.cost_price || 0),
    suggested_qty: Math.min(qty, Number(item.qty || 0)),
    confidence: `${68 + index * 4}%`,
    generated_at: generatedAt,
  };
}

function buildSignalHistoryItem(signal, now) {
  const seed = hashSymbol(signal.symbol) + now.getHours();
  const perf1 = +(Math.sin(seed) * 1.9).toFixed(2);
  const perf5 = +(perf1 + Math.cos(seed / 2) * 3.2).toFixed(2);
  const perf10 = +(perf5 + Math.sin(seed / 3) * 2.6).toFixed(2);
  return {
    id: buildId(signal.symbol, `${signal.side}-history`, now),
    generated_at: toIsoString(now),
    symbol: signal.symbol,
    name: signal.name || signal.symbol,
    side: signal.side,
    strategy: signal.strategy || 'manual_signal',
    trigger_reason: signal.trigger_reason || signal.reason || '来自信号中心',
    signal_price: roundPrice(signal.price || 0),
    suggested_qty: normalizeQuantity(signal.side, signal.suggested_qty || 0),
    performance_1d_pct: perf1,
    performance_5d_pct: perf5,
    performance_10d_pct: perf10,
    outcome_label: signal.side === 'buy' ? '已入模拟盘' : '已执行减仓',
  };
}

function updatePaperState(mutator) {
  const current = getPaperState();
  const next = normalizeState(mutator(deepClone(current)) || current);
  persistState(next);
  emitState(next);
  return next;
}

function normalizeState(raw) {
  const source = raw && typeof raw === 'object' ? raw : createDefaultState();
  const normalized = {
    status: ['running', 'paused', 'stopped'].includes(source.status) ? source.status : 'running',
    started_at: source.started_at || toIsoString(new Date()),
    last_tick_at: source.last_tick_at || toIsoString(new Date()),
    cash: roundMoney(Number(source.cash || 0)),
    holdings: Array.isArray(source.holdings) ? source.holdings.map(normalizeHolding) : [],
    trade_log: Array.isArray(source.trade_log) ? source.trade_log.slice(0, 60) : [],
    equity_curve: Array.isArray(source.equity_curve) ? source.equity_curve.slice(-160) : [],
    signal_history: Array.isArray(source.signal_history) ? source.signal_history.slice(0, 40) : [],
  };

  if (!normalized.equity_curve.length) {
    appendEquityPoint(normalized, new Date());
  }
  return normalized;
}

function normalizeHolding(holding) {
  return {
    symbol: String(holding.symbol || '').toUpperCase(),
    name: String(holding.name || holding.symbol || ''),
    qty: Math.max(0, Math.round(Number(holding.qty || 0))),
    cost_price: roundPrice(Number(holding.cost_price || 0)),
    last_price: roundPrice(Number(holding.last_price || holding.cost_price || 0)),
    strategy: String(holding.strategy || 'manual_signal'),
    opened_at: holding.opened_at || toIsoString(new Date()),
    updated_at: holding.updated_at || toIsoString(new Date()),
  };
}

function enrichHolding(holding) {
  const qty = Number(holding.qty || 0);
  const costPrice = Number(holding.cost_price || 0);
  const lastPrice = Number(holding.last_price || costPrice);
  const marketValue = roundMoney(qty * lastPrice);
  const costValue = roundMoney(qty * costPrice);
  const pnl = roundMoney(marketValue - costValue);
  const pnlPct = costValue > 0 ? +(pnl / costValue * 100).toFixed(2) : 0;

  return {
    ...holding,
    market_value: marketValue,
    cost_value: costValue,
    pnl,
    pnl_pct: pnlPct,
  };
}

function createDefaultState() {
  const settings = getAppSettings();
  const defaultCash = Number(settings.trading_defaults?.cash || 100000);
  const now = new Date();
  const holdings = [
    {
      symbol: '600036.SH',
      name: '招商银行',
      qty: 1200,
      cost_price: 34.2,
      last_price: 35.78,
      strategy: 'sma_cross',
      opened_at: toIsoString(addHours(now, -30)),
      updated_at: toIsoString(now),
    },
    {
      symbol: '601318.SH',
      name: '中国平安',
      qty: 800,
      cost_price: 46.1,
      last_price: 45.36,
      strategy: 'macd',
      opened_at: toIsoString(addHours(now, -22)),
      updated_at: toIsoString(now),
    },
  ];

  const holdingsCost = holdings.reduce((sum, item) => sum + Number(item.cost_price) * Number(item.qty), 0);
  const cash = roundMoney(Math.max(defaultCash - holdingsCost, defaultCash * 0.18));
  const tempState = {
    status: 'running',
    started_at: toIsoString(addHours(now, -36)),
    last_tick_at: toIsoString(now),
    cash,
    holdings,
    trade_log: [
      {
        id: buildId('600036.SH', 'buy', addHours(now, -30)),
        timestamp: toIsoString(addHours(now, -30)),
        side: 'buy',
        symbol: '600036.SH',
        name: '招商银行',
        strategy: 'sma_cross',
        reason: '均线金叉，放量确认',
        price: 34.2,
        qty: 1200,
        notional: roundMoney(34.2 * 1200),
      },
      {
        id: buildId('601318.SH', 'buy', addHours(now, -22)),
        timestamp: toIsoString(addHours(now, -22)),
        side: 'buy',
        symbol: '601318.SH',
        name: '中国平安',
        strategy: 'macd',
        reason: 'MACD 零轴上方金叉',
        price: 46.1,
        qty: 800,
        notional: roundMoney(46.1 * 800),
      },
    ],
    equity_curve: [],
    signal_history: buildDefaultSignalHistory(now),
  };

  const summary = summarizePaperState(tempState);
  tempState.equity_curve = buildInitialEquityCurve(now, summary.equity, cash, summary.holdings_value);
  return tempState;
}

function buildDefaultSignalHistory(now) {
  const entries = [
    ['600519.SH', '贵州茅台', 'buy', 'ma_rsi_filter', '趋势回踩后重新上拐', 1678.2, 300, 1.8, 4.6, 6.1, '观察完成'],
    ['601899.SH', '紫金矿业', 'buy', 'bollinger', '布林上轨突破', 18.15, 1500, -0.6, 2.4, 5.3, '观察完成'],
    ['600036.SH', '招商银行', 'sell', 'sma_cross', '跌破跟踪止损线', 35.1, 600, -1.2, -0.4, 0.8, '已触发减仓'],
    ['600900.SH', '长江电力', 'buy', 'dca', '回撤至长期成本区', 27.48, 1200, 0.9, 1.7, 2.6, '观察完成'],
  ];

  return entries.map((item, index) => ({
    id: `history-${index + 1}`,
    generated_at: toIsoString(addHours(now, -(index + 1) * 9)),
    symbol: item[0],
    name: item[1],
    side: item[2],
    strategy: item[3],
    trigger_reason: item[4],
    signal_price: item[5],
    suggested_qty: item[6],
    performance_1d_pct: item[7],
    performance_5d_pct: item[8],
    performance_10d_pct: item[9],
    outcome_label: item[10],
  }));
}

function buildInitialEquityCurve(now, currentEquity, cash, holdingsValue) {
  const points = [];
  for (let index = 0; index < 24; index += 1) {
    const pointTime = addHours(now, -(23 - index) * 0.35);
    const progress = index / 23;
    const drift = (0.992 + progress * 0.008 + Math.sin(index / 3) * 0.0015);
    const equity = roundMoney(currentEquity * drift);
    points.push({
      date: toIsoString(pointTime),
      equity,
      cash: roundMoney(cash),
      holdings_value: roundMoney(Math.max(equity - cash, 0)),
      exposure_pct: equity > 0 ? +((Math.max(equity - cash, 0) / equity) * 100).toFixed(2) : 0,
    });
  }

  points[points.length - 1] = {
    date: toIsoString(now),
    equity: roundMoney(currentEquity),
    cash: roundMoney(cash),
    holdings_value: roundMoney(holdingsValue),
    exposure_pct: currentEquity > 0 ? +(holdingsValue / currentEquity * 100).toFixed(2) : 0,
  };
  return points;
}

function appendEquityPoint(state, now) {
  const summary = summarizePaperState(state);
  state.equity_curve = Array.isArray(state.equity_curve) ? state.equity_curve : [];
  const lastPoint = state.equity_curve[state.equity_curve.length - 1];
  if (lastPoint && lastPoint.date === toIsoString(now)) {
    lastPoint.equity = summary.equity;
    lastPoint.cash = summary.cash;
    lastPoint.holdings_value = summary.holdings_value;
    lastPoint.exposure_pct = summary.exposure_pct;
    return;
  }

  state.equity_curve.push({
    date: toIsoString(now),
    equity: summary.equity,
    cash: summary.cash,
    holdings_value: summary.holdings_value,
    exposure_pct: summary.exposure_pct,
  });
  state.equity_curve = state.equity_curve.slice(-160);
}

function readState() {
  try {
    const text = localStorage.getItem(PAPER_STATE_KEY);
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

function persistState(state) {
  localStorage.setItem(PAPER_STATE_KEY, JSON.stringify(state));
}

function emitState(state) {
  window.dispatchEvent(new CustomEvent(PAPER_EVENT, {
    detail: { state },
  }));
}

function getTodayBaseEquity(points, fallback) {
  const today = toDateKey(new Date());
  const point = points.find((item) => {
    const date = new Date(item.date);
    return !Number.isNaN(date.getTime()) && toDateKey(date) === today;
  });
  return Number(point?.equity || fallback || 0);
}

function normalizeQuantity(side, rawValue) {
  const value = Math.max(0, Math.floor(Number(rawValue || 0)));
  if (value <= 0) {
    return 0;
  }
  if (side === 'sell') {
    return value;
  }
  if (value >= 100) {
    return Math.floor(value / 100) * 100;
  }
  return value;
}

function deepClone(value) {
  if (typeof structuredClone === 'function') {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function hashSymbol(symbol) {
  return String(symbol || '').split('').reduce((sum, char) => sum + char.charCodeAt(0), 0);
}

function buildId(symbol, action, date) {
  return `${symbol}-${action}-${date.getTime()}`;
}

function addHours(date, hours) {
  return new Date(date.getTime() + hours * 3600000);
}

function toIsoString(date) {
  return date.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function toDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function roundMoney(value) {
  return +Number(value || 0).toFixed(2);
}

function roundPrice(value) {
  return +Number(value || 0).toFixed(3);
}
