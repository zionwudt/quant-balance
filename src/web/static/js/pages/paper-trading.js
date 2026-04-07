/**
 * 知衡 QuantBalance — 模拟盘页面
 */

import { api, ApiError } from '../api.js';
import { toast } from '../components/toast.js';
import { renderEquityChart, disposeEquityChart } from '../components/chart-equity.js';
import { downloadJson } from '../utils/download.js';

let pageState = createInitialState();

export async function initPaperTradingPage(container, routeContext = {}) {
  pageState = createInitialState(routeContext.params);

  try {
    pageState.meta = await api.getMeta();
  } catch {
    pageState.meta = { strategies: ['macd', 'rsi', 'sma_cross'], defaults: { paper: {} } };
  }

  container.innerHTML = buildHTML();
  bindEvents(container);
  applyRouteDefaults(container);
  await refreshPaperStatus(container, { silent: true });

  return {
    exportCurrent() {
      exportPaperReport();
    },
    focusPrimary() {
      container.querySelector('#paper-symbols')?.focus();
    },
    dispose() {
      window.clearInterval(pageState.pollTimer);
      pageState.pollTimer = null;
      disposeEquityChart();
    },
  };
}

function createInitialState(params = {}) {
  return {
    meta: null,
    statusPayload: null,
    pollTimer: null,
    routeParams: params || {},
  };
}

function buildHTML() {
  const defaults = pageState.meta?.defaults?.paper || {};
  const strategies = pageState.meta?.strategies || ['macd', 'rsi', 'sma_cross'];

  return `
    <div class="paper-layout">
      <div class="results-overview">
        <div>
          <div class="results-title">模拟盘</div>
          <p class="results-subtitle">直接连接后端模拟盘会话，支持新建会话、查看持仓快照、暂停和停止。</p>
        </div>
        <div class="results-tags">
          <span class="result-tag" id="paper-status-tag">未连接</span>
          <span class="result-tag mono" id="paper-session-tag">session --</span>
          <input class="input mono input-sm" id="paper-as-of-date" type="date" value="${todayDateText()}">
          <button class="btn btn-secondary btn-sm" id="paper-refresh">刷新</button>
        </div>
      </div>

      <div class="paper-control-grid">
        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">启动新会话</div>
              <p class="card-subtitle">填写股票池与策略后，新建后端 SQLite 持久化模拟盘会话。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <label class="advanced-field">
              <span class="form-label">策略</span>
              <select class="input" id="paper-strategy">
                ${strategies.map((item) => `<option value="${item}"${item === (defaults.strategy || 'macd') ? ' selected' : ''}>${item}</option>`).join('')}
              </select>
            </label>

            <label class="advanced-field">
              <span class="form-label">资产类型</span>
              <select class="input" id="paper-asset-type">
                <option value="stock"${(defaults.asset_type || 'stock') === 'stock' ? ' selected' : ''}>股票</option>
                <option value="convertible_bond"${defaults.asset_type === 'convertible_bond' ? ' selected' : ''}>可转债</option>
              </select>
            </label>

            <label class="advanced-field">
              <span class="form-label">初始资金</span>
              <input class="input mono" id="paper-initial-cash" type="number" min="1000" step="10000" value="${defaults.initial_cash || 100000}">
            </label>

            <label class="advanced-field">
              <span class="form-label">起始日期</span>
              <input class="input" id="paper-start-date" type="date" value="${defaults.start_date || todayDateText()}">
            </label>
          </div>

          <label class="advanced-field">
            <span class="form-label">跟踪标的</span>
            <textarea class="paper-textarea" id="paper-symbols" placeholder="支持逗号、空格或换行分隔，例如：600519.SH, 000858.SZ"></textarea>
            <span class="field-help">会话启动后将以这组股票池为基础，按后端交易日回放真实信号。</span>
          </label>

          <label class="advanced-field">
            <span class="form-label">策略参数 JSON</span>
            <textarea class="paper-textarea mono" id="paper-strategy-params" placeholder='例如 {"fast_period":12,"slow_period":26}'>{}</textarea>
            <span class="field-help">留空或 <span class="mono">{}</span> 表示使用策略默认参数。</span>
          </label>

          <div class="settings-actions">
            <button class="btn btn-primary" id="paper-start">启动模拟盘</button>
          </div>
          <div class="settings-inline-status" id="paper-start-status"></div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">会话摘要</div>
              <p class="card-subtitle">查看当前或最近会话的状态、结束日期和策略配置。</p>
            </div>
          </div>
          <div class="paper-session-summary" id="paper-session-summary"></div>
        </div>
      </div>

      <div class="card paper-account-bar" id="paper-account-bar"></div>

      <div class="paper-toolbar">
        <button class="btn btn-secondary" id="paper-pause">暂停会话</button>
        <button class="btn btn-danger" id="paper-stop">停止并结算</button>
        <button class="btn btn-primary" id="paper-report">导出报告</button>
      </div>

      <div class="paper-grid">
        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">当前持仓</div>
              <p class="card-subtitle">显示后端按结算日计算的最新持仓和浮盈浮亏。</p>
            </div>
          </div>
          <div class="paper-holdings-list" id="paper-holdings"></div>
        </div>

        <div class="paper-main-column">
          <div class="card">
            <div class="results-card-head">
              <div>
                <div class="card-title">权益曲线</div>
                <p class="card-subtitle">跟随后端返回的日度权益快照，可切换结算日期重新回放。</p>
              </div>
            </div>
            <div class="chart-container" id="paper-equity-chart"></div>
          </div>

          <div class="card">
            <div class="results-card-head">
              <div>
                <div class="card-title">最近成交</div>
                <p class="card-subtitle">展示当前会话已执行的模拟盘成交记录。</p>
              </div>
            </div>
            <div class="portfolio-table-wrapper" id="paper-trade-log"></div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function bindEvents(container) {
  container.querySelector('#paper-refresh')?.addEventListener('click', () => {
    void refreshPaperStatus(container);
  });

  container.querySelector('#paper-as-of-date')?.addEventListener('change', () => {
    void refreshPaperStatus(container, { silent: true });
  });

  container.querySelector('#paper-start')?.addEventListener('click', () => {
    void startPaperSession(container);
  });

  container.querySelector('#paper-pause')?.addEventListener('click', () => {
    void pausePaperSession(container);
  });

  container.querySelector('#paper-stop')?.addEventListener('click', () => {
    void stopPaperSession(container);
  });

  container.querySelector('#paper-report')?.addEventListener('click', () => {
    exportPaperReport();
  });
}

function applyRouteDefaults(container) {
  const params = pageState.routeParams || {};
  const symbols = parseSymbolsParam(params.symbols);
  if (symbols.length) {
    container.querySelector('#paper-symbols').value = symbols.join(', ');
  }
  if (params.strategy) {
    container.querySelector('#paper-strategy').value = params.strategy;
  }
  if (params.asset_type) {
    container.querySelector('#paper-asset-type').value = params.asset_type;
  }
  if (params.start_date) {
    container.querySelector('#paper-start-date').value = params.start_date;
  }
}

async function refreshPaperStatus(container, options = {}) {
  const { silent = false } = options;
  const asOfDate = container.querySelector('#paper-as-of-date')?.value || null;

  try {
    const payload = await api.getPaperStatus(null, asOfDate);
    pageState.statusPayload = payload;
    renderPaperState(container, payload);
    syncPolling(container, payload);
  } catch (error) {
    pageState.statusPayload = null;
    syncPolling(container, null);
    renderPaperState(container, null);
    if (!silent) {
      const message = error instanceof ApiError ? error.message : '模拟盘状态读取失败';
      toast.error(message);
    }
  }
}

function syncPolling(container, payload) {
  window.clearInterval(pageState.pollTimer);
  pageState.pollTimer = null;
  if (payload?.has_session && payload.status === 'running') {
    pageState.pollTimer = window.setInterval(() => {
      void refreshPaperStatus(container, { silent: true });
    }, 20_000);
  }
}

function renderPaperState(container, payload) {
  if (!payload?.has_session) {
    container.querySelector('#paper-status-tag').textContent = '无活跃会话';
    container.querySelector('#paper-session-tag').textContent = 'session --';
    container.querySelector('#paper-session-summary').innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">💼</div>
        <p>当前没有可读取的模拟盘会话。</p>
      </div>
    `;
    container.querySelector('#paper-account-bar').innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📦</div>
        <p>启动模拟盘后，这里会显示账户权益和现金快照。</p>
      </div>
    `;
    container.querySelector('#paper-holdings').innerHTML = '<div class="empty-state"><div class="empty-state-icon">📦</div><p>暂无持仓</p></div>';
    container.querySelector('#paper-trade-log').innerHTML = '<div class="empty-state"><div class="empty-state-icon">🧾</div><p>暂无成交</p></div>';
    renderEquityChart(container.querySelector('#paper-equity-chart'), [], null);
    container.querySelector('#paper-pause').disabled = true;
    container.querySelector('#paper-stop').disabled = true;
    container.querySelector('#paper-report').disabled = true;
    window.dispatchEvent(new CustomEvent('qb-status-message', {
      detail: { text: '模拟盘 · 无会话' },
    }));
    return;
  }

  const summary = payload.summary || {};
  container.querySelector('#paper-status-tag').textContent = statusText(payload.status);
  container.querySelector('#paper-session-tag').textContent = `session ${String(payload.session_id || '--').slice(0, 12)}`;
  container.querySelector('#paper-session-summary').innerHTML = `
    <div class="paper-session-grid">
      <div><span class="text-muted">会话 ID</span><div class="mono">${payload.session_id || '--'}</div></div>
      <div><span class="text-muted">策略</span><div class="mono">${payload.strategy || '--'}</div></div>
      <div><span class="text-muted">状态</span><div>${statusText(payload.status)}</div></div>
      <div><span class="text-muted">结算到</span><div>${payload.as_of_date || '--'}</div></div>
      <div><span class="text-muted">起始日期</span><div>${payload.report?.run_context?.start_date || '--'}</div></div>
      <div><span class="text-muted">标的数</span><div>${(payload.symbols || []).length}</div></div>
    </div>
    <div class="paper-session-symbols">
      ${(payload.symbols || []).map((symbol) => `<span class="result-tag mono">${symbol}</span>`).join('')}
    </div>
  `;

  container.querySelector('#paper-account-bar').innerHTML = `
    <div class="paper-account-item">
      <span class="paper-account-label">账户权益</span>
      <span class="paper-account-value mono">${formatMoney(summary.equity)}</span>
    </div>
    <div class="paper-account-item">
      <span class="paper-account-label">今日盈亏</span>
      <span class="paper-account-value mono ${moneyClass(summary.today_pnl)}">${formatSignedMoney(summary.today_pnl)}</span>
    </div>
    <div class="paper-account-item">
      <span class="paper-account-label">可用现金</span>
      <span class="paper-account-value mono">${formatMoney(summary.cash)}</span>
    </div>
    <div class="paper-account-item">
      <span class="paper-account-label">持仓数</span>
      <span class="paper-account-value mono">${summary.positions_count ?? 0}</span>
    </div>
  `;

  renderHoldings(container.querySelector('#paper-holdings'), payload.holdings || []);
  container.querySelector('#paper-trade-log').innerHTML = renderTradeTable(payload.trades || []);
  renderEquityChart(
    container.querySelector('#paper-equity-chart'),
    (payload.equity_curve || []).map((item) => ({
      date: item.date,
      label: item.date,
      equity: item.equity,
    })),
    payload.equity_curve?.[0]?.equity || summary.equity,
  );

  container.querySelector('#paper-pause').disabled = payload.status !== 'running';
  container.querySelector('#paper-stop').disabled = payload.status === 'stopped';
  container.querySelector('#paper-report').disabled = false;
  window.dispatchEvent(new CustomEvent('qb-status-message', {
    detail: { text: `模拟盘 · ${statusText(payload.status)}` },
  }));
}

function renderHoldings(container, holdings) {
  if (!holdings.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📦</div><p>当前没有持仓</p></div>';
    return;
  }

  container.innerHTML = holdings.map((item) => `
    <div class="paper-holding-card">
      <div class="paper-holding-head">
        <div>
          <div class="paper-holding-title">${escapeHtml(item.name || item.symbol)}</div>
          <div class="paper-holding-meta mono">${item.symbol} · ${escapeHtml(item.strategy || '-')}</div>
        </div>
        <span class="result-tag mono">${item.qty} 股</span>
      </div>
      <div class="paper-holding-grid">
        <div>
          <div class="paper-holding-label">市值</div>
          <div class="mono">${formatMoney(item.market_value)}</div>
        </div>
        <div>
          <div class="paper-holding-label">最新价</div>
          <div class="mono">${formatPrice(item.last_price)}</div>
        </div>
        <div>
          <div class="paper-holding-label">成本价</div>
          <div class="mono">${formatPrice(item.cost_price)}</div>
        </div>
        <div>
          <div class="paper-holding-label">浮动盈亏</div>
          <div class="mono ${moneyClass(item.pnl)}">${formatSignedMoney(item.pnl)} / ${formatSignedPct(item.pnl_pct)}</div>
        </div>
      </div>
    </div>
  `).join('');
}

function renderTradeTable(trades) {
  if (!trades.length) {
    return '<div class="empty-state"><div class="empty-state-icon">🧾</div><p>当前没有成交记录</p></div>';
  }

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>日期</th>
          <th>动作</th>
          <th>标的</th>
          <th data-align="right">价格</th>
          <th data-align="right">数量</th>
          <th>原因</th>
        </tr>
      </thead>
      <tbody>
        ${trades.slice(0, 20).map((trade) => `
          <tr data-pnl="${String(trade.side || '').toUpperCase() === 'BUY' ? 'profit' : 'loss'}">
            <td class="mono">${trade.trade_date || '-'}</td>
            <td>${trade.side_label || trade.side || '-'}</td>
            <td>${escapeHtml(trade.name || trade.symbol)} <span class="mono text-muted">${trade.symbol || '-'}</span></td>
            <td data-align="right" class="mono">${formatPrice(trade.price)}</td>
            <td data-align="right" class="mono">${trade.quantity ?? trade.qty ?? '-'}</td>
            <td>${escapeHtml(trade.reason || '-')}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

async function startPaperSession(container) {
  const statusEl = container.querySelector('#paper-start-status');
  try {
    const symbols = parseSymbolsParam(container.querySelector('#paper-symbols').value);
    if (!symbols.length) {
      toast.error('请至少输入 1 个标的');
      return;
    }
    const payload = {
      strategy: container.querySelector('#paper-strategy').value,
      strategy_params: parseJsonInput(container.querySelector('#paper-strategy-params').value, '策略参数'),
      symbols,
      initial_cash: Number(container.querySelector('#paper-initial-cash').value || 0),
      asset_type: container.querySelector('#paper-asset-type').value,
      start_date: container.querySelector('#paper-start-date').value || null,
    };
    const statusText = '正在启动模拟盘会话...';
    statusEl.textContent = statusText;
    const result = await api.startPaper(payload);
    pageState.statusPayload = result;
    statusEl.innerHTML = '<span class="text-profit">模拟盘会话已启动。</span>';
    toast.success('模拟盘已启动');
    renderPaperState(container, result);
    syncPolling(container, result);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : error.message || '模拟盘启动失败';
    container.querySelector('#paper-start-status').innerHTML = `<span class="text-loss">${escapeHtml(message)}</span>`;
    toast.error(message);
  }
}

async function pausePaperSession(container) {
  const sessionId = pageState.statusPayload?.session_id || null;
  if (!sessionId) {
    toast.error('当前没有可暂停的会话');
    return;
  }
  try {
    const payload = await api.pausePaper(sessionId);
    pageState.statusPayload = payload;
    renderPaperState(container, payload);
    syncPolling(container, payload);
    toast.success('模拟盘已暂停');
  } catch (error) {
    const message = error instanceof ApiError ? error.message : '暂停模拟盘失败';
    toast.error(message);
  }
}

async function stopPaperSession(container) {
  const sessionId = pageState.statusPayload?.session_id || null;
  if (!sessionId) {
    toast.error('当前没有可停止的会话');
    return;
  }
  const asOfDate = container.querySelector('#paper-as-of-date')?.value || null;
  try {
    const payload = await api.stopPaper(sessionId, asOfDate);
    pageState.statusPayload = payload;
    renderPaperState(container, payload);
    syncPolling(container, payload);
    toast.success('模拟盘已停止并完成结算');
  } catch (error) {
    const message = error instanceof ApiError ? error.message : '停止模拟盘失败';
    toast.error(message);
  }
}

function exportPaperReport() {
  const report = pageState.statusPayload?.report;
  if (!report) {
    toast.info('当前没有可导出的模拟盘报告');
    return;
  }
  downloadJson(`paper-trading-report-${Date.now()}.json`, report);
  toast.success('模拟盘报告已导出');
}

function parseSymbolsParam(value) {
  return String(value || '')
    .split(/[\s,]+/)
    .map(item => item.trim().toUpperCase())
    .filter(Boolean);
}

function parseJsonInput(value, label) {
  const text = String(value || '').trim();
  if (!text) {
    return {};
  }
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(`${label}必须是 JSON 对象`);
    }
    return parsed;
  } catch (error) {
    throw new Error(`${label} JSON 无效`);
  }
}

function statusText(status) {
  if (status === 'paused') {
    return '已暂停';
  }
  if (status === 'stopped') {
    return '已停止';
  }
  if (status === 'running') {
    return '运行中';
  }
  return '未连接';
}

function moneyClass(value) {
  if (!Number.isFinite(Number(value))) {
    return '';
  }
  return Number(value) >= 0 ? 'text-profit' : 'text-loss';
}

function formatMoney(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return '-';
  }
  return `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatSignedMoney(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return '-';
  }
  const number = Number(value);
  return `${number >= 0 ? '+' : '-'}${formatMoney(Math.abs(number))}`;
}

function formatPrice(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return '-';
  }
  return Number(value).toFixed(3);
}

function formatSignedPct(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return '-';
  }
  const number = Number(value);
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}%`;
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
