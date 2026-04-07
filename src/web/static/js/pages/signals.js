/**
 * 知衡 QuantBalance — 信号中心页面
 */

import { api, ApiError } from '../api.js';
import { toast } from '../components/toast.js';
import { downloadBlob } from '../utils/download.js';

let pageState = createInitialState();

export async function initSignalsPage(container, routeContext = {}) {
  pageState = createInitialState(routeContext.navigateTo);
  container.innerHTML = buildHTML();
  bindEvents(container);
  await refreshSignals(container);
  pageState.refreshTimer = window.setInterval(() => {
    void refreshSignals(container, { silent: true });
  }, 30_000);

  return {
    exportCurrent() {
      void downloadSignalsExport(container, 'csv');
    },
    focusPrimary() {
      container.querySelector('#signals-date')?.focus();
    },
    dispose() {
      window.clearInterval(pageState.refreshTimer);
      pageState.refreshTimer = null;
    },
  };
}

function createInitialState(navigateTo = null) {
  return {
    navigateTo,
    todayPayload: { date: todayDateText(), total: 0, items: [] },
    recentPayload: { items: [] },
    historyPayload: { page: 1, page_size: 20, total: 0, has_more: false, items: [] },
    historyDays: 30,
    historyPage: 1,
    refreshTimer: null,
    loading: false,
  };
}

function buildHTML() {
  return `
    <div class="signals-layout">
      <div class="results-overview">
        <div>
          <div class="results-title">信号中心</div>
          <p class="results-subtitle">读取后端持久化信号，支持今日筛选、历史跟踪、状态流转与导出。</p>
        </div>
        <div class="results-tags">
          <span class="result-tag" id="signals-generated-tag">--</span>
          <input class="input mono input-sm" id="signals-date" type="date" value="${todayDateText()}">
          <button class="btn btn-secondary btn-sm" id="signals-refresh">刷新</button>
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
              <p class="card-subtitle">当日后端持久化买入候选，支持标记执行或忽略。</p>
            </div>
          </div>
          <div class="signal-card-grid" id="signals-buy"></div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">卖出信号</div>
              <p class="card-subtitle">当日后端持久化卖出候选，可直接联动到回测或模拟盘页。</p>
            </div>
          </div>
          <div class="signal-card-grid" id="signals-sell"></div>
        </div>
      </div>

      <div class="signals-secondary-grid">
        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">最近持久化信号</div>
              <p class="card-subtitle">最近 12 条信号快照，便于快速确认调度器是否有持续产出。</p>
            </div>
          </div>
          <div class="portfolio-table-wrapper" id="signals-recent"></div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">历史跟踪</div>
              <p class="card-subtitle">按天数窗口查看历史信号，并保留 1 / 5 / 10 / 20 日跟踪收益。</p>
            </div>
            <div class="signals-history-toolbar">
              <label class="advanced-field">
                <span class="form-label">窗口天数</span>
                <select class="input" id="signals-history-days">
                  <option value="7">7 天</option>
                  <option value="30" selected>30 天</option>
                  <option value="90">90 天</option>
                  <option value="365">365 天</option>
                </select>
              </label>
            </div>
          </div>
          <div class="portfolio-table-wrapper" id="signals-history"></div>
          <div class="history-pagination" id="signals-history-pagination"></div>
        </div>
      </div>
    </div>
  `;
}

function bindEvents(container) {
  container.querySelector('#signals-refresh')?.addEventListener('click', () => {
    void refreshSignals(container);
  });

  container.querySelector('#signals-date')?.addEventListener('change', () => {
    void refreshSignals(container);
  });

  container.querySelector('#signals-history-days')?.addEventListener('change', (event) => {
    pageState.historyDays = Number(event.target.value || 30);
    pageState.historyPage = 1;
    void refreshSignals(container);
  });

  container.querySelectorAll('[data-export-format]').forEach((button) => {
    button.addEventListener('click', () => {
      void downloadSignalsExport(container, button.dataset.exportFormat || 'csv');
    });
  });

  container.addEventListener('click', (event) => {
    const target = event.target.closest('[data-action]');
    if (!target) {
      return;
    }
    const action = target.dataset.action;
    if (action === 'history-page') {
      pageState.historyPage = Number(target.dataset.page || 1);
      void refreshSignals(container, { silent: true });
      return;
    }

    const signalId = Number(target.dataset.signalId || 0);
    const signal = findSignal(signalId);
    if (!signal) {
      toast.error('信号不存在或已失效，请刷新后重试');
      return;
    }

    if (action === 'view-kline') {
      pageState.navigateTo?.('backtest', { symbols: signal.symbol });
      return;
    }
    if (action === 'start-paper') {
      pageState.navigateTo?.('paper-trading', {
        symbols: signal.symbol,
        strategy: signal.strategy,
        asset_type: signal.asset_type || 'stock',
        start_date: String(signal.trade_date || signal.created_at || '').slice(0, 10),
      });
      return;
    }
    if (action === 'mark-status') {
      void mutateSignalStatus(container, signalId, target.dataset.status || 'pending');
    }
  });
}

async function refreshSignals(container, options = {}) {
  const { silent = false } = options;
  if (pageState.loading) {
    return;
  }
  pageState.loading = true;
  if (!silent) {
    container.querySelector('#signals-generated-tag').textContent = '加载中...';
  }

  const signalDate = container.querySelector('#signals-date')?.value || todayDateText();

  try {
    const [todayPayload, recentPayload, historyPayload] = await Promise.all([
      api.getSignalsToday(200, signalDate),
      api.getSignalsRecent(12, signalDate),
      api.getSignalsHistory(pageState.historyDays, pageState.historyPage, 20),
    ]);
    pageState.todayPayload = todayPayload;
    pageState.recentPayload = recentPayload;
    pageState.historyPayload = historyPayload;
    renderSignals(container);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : '信号读取失败';
    if (!silent) {
      toast.error(message);
    }
    renderErrorState(container, message);
  } finally {
    pageState.loading = false;
  }
}

function renderSignals(container) {
  const todayItems = pageState.todayPayload.items || [];
  const buySignals = todayItems.filter(item => item.side === 'BUY');
  const sellSignals = todayItems.filter(item => item.side === 'SELL');

  container.querySelector('#signals-generated-tag').textContent = `日期 ${pageState.todayPayload.date} · 共 ${pageState.todayPayload.total || 0} 条`;
  container.querySelector('#signals-buy').innerHTML = renderSignalCards(buySignals, 'buy');
  container.querySelector('#signals-sell').innerHTML = renderSignalCards(sellSignals, 'sell');
  container.querySelector('#signals-recent').innerHTML = renderRecentTable(pageState.recentPayload.items || []);
  container.querySelector('#signals-history').innerHTML = renderHistoryTable(pageState.historyPayload.items || []);
  container.querySelector('#signals-history-pagination').innerHTML = renderHistoryPagination(pageState.historyPayload);
  window.dispatchEvent(new CustomEvent('qb-status-message', {
    detail: {
      text: `信号中心 · 今日 ${pageState.todayPayload.total || 0} / 历史 ${pageState.historyPayload.total || 0}`,
    },
  }));
}

function renderErrorState(container, message) {
  container.querySelector('#signals-buy').innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠</div><p>${message}</p></div>`;
  container.querySelector('#signals-sell').innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠</div><p>${message}</p></div>`;
  container.querySelector('#signals-recent').innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div><p>暂无最近信号</p></div>';
  container.querySelector('#signals-history').innerHTML = '<div class="empty-state"><div class="empty-state-icon">📜</div><p>暂无历史信号</p></div>';
  container.querySelector('#signals-history-pagination').innerHTML = '';
}

function renderSignalCards(items, type) {
  if (!items.length) {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">${type === 'buy' ? '🛒' : '🛡'}</div>
        <p>${type === 'buy' ? '当前没有新的买入候选' : '当前没有新的卖出候选'}</p>
      </div>
    `;
  }

  return items.map((item) => `
    <div class="signal-card signal-card-${type}">
      <div class="signal-card-head">
        <div>
          <div class="signal-card-title">${escapeHtml(item.name || item.symbol)}</div>
          <div class="signal-card-symbol mono">${item.symbol}</div>
        </div>
        <div class="signal-status-stack">
          <span class="result-tag">${item.side_label} · ${item.status_label}</span>
          <span class="result-tag mono">${formatDateTime(item.created_at)}</span>
        </div>
      </div>
      <div class="signal-card-meta">
        <span>策略 <span class="mono">${escapeHtml(item.strategy || '-')}</span></span>
        <span>价格 <span class="mono">${formatPrice(item.price)}</span></span>
        <span>数量 <span class="mono">${item.suggested_qty || 0}</span></span>
        <span>20 日 <span class="mono ${pctClass(item.performance_20d_pct)}">${formatSignedPct(item.performance_20d_pct)}</span></span>
      </div>
      <p class="signal-card-reason">${escapeHtml(item.trigger_reason || item.reason || '-')}</p>
      <div class="signal-card-actions">
        <button class="btn btn-secondary btn-sm" data-action="view-kline" data-signal-id="${item.id}">查看 K 线</button>
        <button class="btn btn-secondary btn-sm" data-action="start-paper" data-signal-id="${item.id}">去模拟盘</button>
        ${buildStatusButtons(item)}
      </div>
    </div>
  `).join('');
}

function renderRecentTable(items) {
  if (!items.length) {
    return '<div class="empty-state"><div class="empty-state-icon">📭</div><p>最近没有可显示的信号</p></div>';
  }

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>时间</th>
          <th>标的</th>
          <th>动作</th>
          <th>状态</th>
          <th data-align="right">价格</th>
        </tr>
      </thead>
      <tbody>
        ${items.map((item) => `
          <tr data-pnl="${rowPnlType(item.performance_5d_pct)}">
            <td class="mono">${formatDateTime(item.created_at)}</td>
            <td>${escapeHtml(item.name || item.symbol)} <span class="mono text-muted">${item.symbol}</span></td>
            <td>${item.side_label}</td>
            <td>${item.status_label}</td>
            <td data-align="right" class="mono">${formatPrice(item.price)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderHistoryTable(items) {
  if (!items.length) {
    return '<div class="empty-state"><div class="empty-state-icon">📜</div><p>当前窗口内没有历史信号</p></div>';
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
          <th data-align="right">1 日</th>
          <th data-align="right">5 日</th>
          <th data-align="right">10 日</th>
          <th data-align="right">20 日</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        ${items.map((item) => `
          <tr data-pnl="${rowPnlType(item.performance_5d_pct)}">
            <td class="mono">${formatDateTime(item.created_at)}</td>
            <td>${escapeHtml(item.name || item.symbol)} <span class="mono text-muted">${item.symbol}</span></td>
            <td>${item.side_label}</td>
            <td class="mono">${escapeHtml(item.strategy || '-')}</td>
            <td data-align="right" class="mono">${formatPrice(item.signal_price)}</td>
            <td data-align="right" class="mono ${pctClass(item.performance_1d_pct)}">${formatSignedPct(item.performance_1d_pct)}</td>
            <td data-align="right" class="mono ${pctClass(item.performance_5d_pct)}">${formatSignedPct(item.performance_5d_pct)}</td>
            <td data-align="right" class="mono ${pctClass(item.performance_10d_pct)}">${formatSignedPct(item.performance_10d_pct)}</td>
            <td data-align="right" class="mono ${pctClass(item.performance_20d_pct)}">${formatSignedPct(item.performance_20d_pct)}</td>
            <td>
              <div class="signals-history-status">
                <span>${item.status_label}</span>
                <div class="signals-inline-actions">
                  ${buildStatusButtons(item)}
                </div>
              </div>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderHistoryPagination(payload) {
  const total = Number(payload.total || 0);
  const page = Number(payload.page || 1);
  const pageSize = Number(payload.page_size || 20);
  if (!total) {
    return '';
  }
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return `
    <span class="text-muted">第 ${page} / ${totalPages} 页，共 ${total} 条</span>
    <div class="signals-inline-actions">
      <button class="btn btn-ghost btn-sm" data-action="history-page" data-page="${Math.max(1, page - 1)}"${page <= 1 ? ' disabled' : ''}>上一页</button>
      <button class="btn btn-ghost btn-sm" data-action="history-page" data-page="${Math.min(totalPages, page + 1)}"${page >= totalPages ? ' disabled' : ''}>下一页</button>
    </div>
  `;
}

function buildStatusButtons(item) {
  const status = String(item.status || 'pending');
  return `
    <button class="btn btn-ghost btn-sm" data-action="mark-status" data-signal-id="${item.id}" data-status="pending"${status === 'pending' ? ' disabled' : ''}>待处理</button>
    <button class="btn btn-primary btn-sm" data-action="mark-status" data-signal-id="${item.id}" data-status="executed"${status === 'executed' ? ' disabled' : ''}>已执行</button>
    <button class="btn btn-secondary btn-sm" data-action="mark-status" data-signal-id="${item.id}" data-status="ignored"${status === 'ignored' ? ' disabled' : ''}>忽略</button>
  `;
}

async function mutateSignalStatus(container, signalId, status) {
  try {
    await api.updateSignalStatus(signalId, status);
    toast.success(`信号已更新为${statusLabel(status)}`);
    await refreshSignals(container, { silent: true });
  } catch (error) {
    const message = error instanceof ApiError ? error.message : '信号状态更新失败';
    toast.error(message);
  }
}

async function downloadSignalsExport(container, format) {
  const normalizedFormat = String(format || 'csv').toLowerCase();
  const exportDate = container.querySelector('#signals-date')?.value || todayDateText();

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

function findSignal(signalId) {
  const buckets = [
    ...(pageState.todayPayload.items || []),
    ...(pageState.recentPayload.items || []),
    ...(pageState.historyPayload.items || []),
  ];
  return buckets.find(item => Number(item.id) === Number(signalId)) || null;
}

function rowPnlType(value) {
  if (value == null) {
    return 'profit';
  }
  return Number(value) >= 0 ? 'profit' : 'loss';
}

function pctClass(value) {
  if (value == null) {
    return '';
  }
  return Number(value) >= 0 ? 'text-profit' : 'text-loss';
}

function formatSignedPct(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return '-';
  }
  const number = Number(value);
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}%`;
}

function formatPrice(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return '-';
  }
  return Number(value).toFixed(3);
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

function statusLabel(status) {
  return {
    pending: '待处理',
    executed: '已执行',
    ignored: '已忽略',
    expired: '已过期',
  }[status] || status;
}

function todayDateText() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
