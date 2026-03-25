/**
 * 知衡 QuantBalance — 信号中心页面
 */

import { api, ApiError } from '../api.js';
import { toast } from '../components/toast.js';
import { addSignalToPaperTrading, getSignalCenterSnapshot, subscribePaperState } from '../data/paper-store.js';
import { downloadBlob, downloadCsv } from '../utils/download.js';

let currentSnapshot = null;

export async function initSignalsPage(container, routeContext = {}) {
  container.innerHTML = buildHTML();
  bindEvents(container, routeContext.navigateTo);
  renderSignals(container);

  const unsubscribe = subscribePaperState(() => {
    renderSignals(container);
  });

  return {
    exportCurrent() {
      void downloadSignalsExport(container, 'csv');
    },
    focusPrimary() {
      container.querySelector('[data-action="view-kline"]')?.focus();
    },
    dispose() {
      unsubscribe();
    },
  };
}

function buildHTML() {
  return `
    <div class="signals-layout">
      <div class="results-overview">
        <div>
          <div class="results-title">信号中心</div>
          <p class="results-subtitle">把当天的买卖建议拆分为可执行卡片，并保留后续表现追踪，便于人工复核与加入模拟盘。</p>
        </div>
        <div class="results-tags">
          <span class="result-tag" id="signals-generated-tag">--</span>
          <input class="input mono input-sm" id="signals-export-date" type="date" value="${todayDateText()}">
          <button class="btn btn-secondary btn-sm" data-export-format="csv">导出 CSV</button>
          <button class="btn btn-secondary btn-sm" data-export-format="qmt">导出 QMT</button>
          <button class="btn btn-primary btn-sm" data-export-format="json">导出 JSON</button>
        </div>
      </div>

      <div class="signals-grid">
        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">买入信号</div>
              <p class="card-subtitle">更适合直接加入模拟盘的新开仓候选。</p>
            </div>
          </div>
          <div class="signal-card-grid" id="signals-buy"></div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">卖出信号</div>
              <p class="card-subtitle">针对已有持仓的减仓 / 止损 / 锁盈建议。</p>
            </div>
          </div>
          <div class="signal-card-grid" id="signals-sell"></div>
        </div>
      </div>

      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">历史跟踪</div>
            <p class="card-subtitle">保留近 40 条历史信号，并记录 1 / 5 / 10 日后表现，便于观察命中率与信号衰减速度。</p>
          </div>
        </div>
        <div class="portfolio-table-wrapper" id="signals-history"></div>
      </div>
    </div>
  `;
}

function bindEvents(container, navigateTo) {
  container.querySelectorAll('[data-export-format]').forEach((button) => {
    button.addEventListener('click', () => {
      void downloadSignalsExport(container, button.dataset.exportFormat || 'csv');
    });
  });

  container.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) {
      return;
    }
    const signalId = button.dataset.signalId;
    const signal = findSignal(signalId);
    if (!signal) {
      toast.error('信号已失效，请刷新后重试');
      return;
    }

    const action = button.dataset.action;
    if (action === 'view-kline') {
      navigateTo?.('backtest', { symbols: signal.symbol });
      return;
    }
    if (action === 'add-paper') {
      try {
        addSignalToPaperTrading(signal);
        toast.success(`${signal.name} 已加入模拟盘`);
      } catch (error) {
        toast.error(error.message || '加入模拟盘失败');
      }
      return;
    }
    if (action === 'export-signal') {
      exportSignals([signal]);
    }
  });
}

function renderSignals(container) {
  currentSnapshot = getSignalCenterSnapshot();
  container.querySelector('#signals-generated-tag').textContent = `生成于 ${formatDateTime(currentSnapshot.generated_at)}`;
  container.querySelector('#signals-buy').innerHTML = renderSignalCards(currentSnapshot.buy_signals, 'buy');
  container.querySelector('#signals-sell').innerHTML = renderSignalCards(currentSnapshot.sell_signals, 'sell');
  container.querySelector('#signals-history').innerHTML = renderHistoryTable(currentSnapshot.history);
  window.dispatchEvent(new CustomEvent('qb-status-message', {
    detail: { text: `信号中心 · 买入 ${currentSnapshot.buy_signals.length} / 卖出 ${currentSnapshot.sell_signals.length}` },
  }));
}

function renderSignalCards(items, type) {
  if (!items.length) {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">${type === 'buy' ? '🛒' : '🛡'}</div>
        <p>${type === 'buy' ? '当前没有新的买入候选' : '当前没有需要处理的卖出信号'}</p>
      </div>
    `;
  }

  return items.map((item) => `
    <div class="signal-card signal-card-${item.side}">
      <div class="signal-card-head">
        <div>
          <div class="signal-card-title">${item.name}</div>
          <div class="signal-card-symbol mono">${item.symbol}</div>
        </div>
        <span class="result-tag">${item.side_label} · 置信度 ${item.confidence}</span>
      </div>
      <div class="signal-card-meta">
        <span>策略 <span class="mono">${item.strategy}</span></span>
        <span>价格 <span class="mono">${Number(item.price || 0).toFixed(3)}</span></span>
        <span>建议数量 <span class="mono">${item.suggested_qty}</span></span>
      </div>
      <p class="signal-card-reason">${item.trigger_reason}</p>
      <div class="signal-card-actions">
        <button class="btn btn-secondary btn-sm" data-action="view-kline" data-signal-id="${item.id}">查看 K 线</button>
        <button class="btn btn-primary btn-sm" data-action="add-paper" data-signal-id="${item.id}">加入模拟盘</button>
        <button class="btn btn-ghost btn-sm" data-action="export-signal" data-signal-id="${item.id}">导出 CSV</button>
      </div>
    </div>
  `).join('');
}

function renderHistoryTable(items) {
  if (!items.length) {
    return '<div class="empty-state"><div class="empty-state-icon">📜</div><p>暂无历史信号</p></div>';
  }

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>时间</th>
          <th>标的</th>
          <th>动作</th>
          <th>策略</th>
          <th data-align="right">信号价</th>
          <th data-align="right">1日</th>
          <th data-align="right">5日</th>
          <th data-align="right">10日</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        ${items.map((item) => `
          <tr data-pnl="${item.performance_5d_pct >= 0 ? 'profit' : 'loss'}">
            <td class="mono">${formatDateTime(item.generated_at)}</td>
            <td>${item.name} <span class="mono text-muted">${item.symbol}</span></td>
            <td>${item.side_label}</td>
            <td class="mono">${item.strategy}</td>
            <td data-align="right" class="mono">${Number(item.signal_price || 0).toFixed(3)}</td>
            <td data-align="right" class="mono ${item.performance_1d_pct >= 0 ? 'text-profit' : 'text-loss'}">${formatSignedPct(item.performance_1d_pct)}</td>
            <td data-align="right" class="mono ${item.performance_5d_pct >= 0 ? 'text-profit' : 'text-loss'}">${formatSignedPct(item.performance_5d_pct)}</td>
            <td data-align="right" class="mono ${item.performance_10d_pct >= 0 ? 'text-profit' : 'text-loss'}">${formatSignedPct(item.performance_10d_pct)}</td>
            <td>${item.outcome_label}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function findSignal(signalId) {
  if (!currentSnapshot) {
    return null;
  }
  return [...currentSnapshot.buy_signals, ...currentSnapshot.sell_signals].find((item) => item.id === signalId) || null;
}

function exportSignals(signals = null) {
  const rows = (signals || [...(currentSnapshot?.buy_signals || []), ...(currentSnapshot?.sell_signals || [])]).map((item) => ({
    generated_at: item.generated_at,
    side: item.side_label,
    symbol: item.symbol,
    name: item.name,
    strategy: item.strategy,
    trigger_reason: item.trigger_reason,
    price: Number(item.price || 0).toFixed(3),
    suggested_qty: item.suggested_qty,
    confidence: item.confidence,
  }));

  if (!rows.length) {
    toast.info('当前没有可导出的信号');
    return;
  }

  downloadCsv(`signals-${Date.now()}.csv`, rows, [
    'generated_at',
    'side',
    'symbol',
    'name',
    'strategy',
    'trigger_reason',
    'price',
    'suggested_qty',
    'confidence',
  ]);
  toast.success('信号 CSV 已导出');
}

async function downloadSignalsExport(container, format) {
  const normalizedFormat = String(format || 'csv').toLowerCase();
  const exportDate = container.querySelector('#signals-export-date')?.value || todayDateText();

  try {
    const result = await api.exportSignals(normalizedFormat, exportDate);
    const suffix = normalizedFormat === 'qmt' ? 'py' : normalizedFormat;
    downloadBlob(result.filename || `signals-${exportDate}.${suffix}`, result.blob);
    toast.success(`信号 ${normalizedFormat.toUpperCase()} 已导出`);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : '信号导出失败';
    toast.error(message);
  }
}

function formatSignedPct(value) {
  const number = Number(value || 0);
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}%`;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '-';
  }
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function todayDateText() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
