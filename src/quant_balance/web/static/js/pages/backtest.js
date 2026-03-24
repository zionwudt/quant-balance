/**
 * 知衡 QuantBalance — 回测页面
 */

import { api, ApiError } from '../api.js';
import { toast } from '../components/toast.js';
import { renderEquityChart } from '../components/chart-equity.js';
import { renderTradesTable } from '../components/data-table.js';

let strategies = [];

export async function initBacktestPage(container) {
  // 加载策略列表
  try {
    const meta = await api.getMeta();
    strategies = meta.strategies || [];
  } catch {
    strategies = [
      'sma_cross',
      'ema_cross',
      'buy_and_hold',
      'macd',
      'rsi',
      'bollinger',
      'grid',
      'dca',
      'ma_rsi_filter',
    ];
  }

  container.innerHTML = buildHTML();
  bindEvents(container);
}

function buildHTML() {
  const today = new Date().toISOString().split('T')[0];
  const oneYearAgo = new Date(Date.now() - 365 * 86400000).toISOString().split('T')[0];

  const strategyOptions = strategies
    .map(s => `<option value="${s}">${s}</option>`)
    .join('');

  return `
    <div class="backtest-layout">
      <!-- 参数区 -->
      <div class="backtest-params">
        <div class="card">
          <div class="card-title">回测参数</div>

          <div class="form-group" style="margin-bottom: var(--space-3)">
            <label class="form-label">股票代码</label>
            <input class="input" id="bt-symbol" placeholder="如 600519.SH" value="600519.SH">
          </div>

          <div class="form-group" style="margin-bottom: var(--space-3)">
            <label class="form-label">时间范围</label>
            <div style="display:flex;gap:var(--space-2);align-items:center">
              <input class="input" id="bt-start" type="date" value="${oneYearAgo}">
              <span style="color:var(--text-muted)">→</span>
              <input class="input" id="bt-end" type="date" value="${today}">
            </div>
            <div class="quick-dates" style="margin-top:var(--space-1)">
              <button class="btn btn-ghost" data-range="365">近1年</button>
              <button class="btn btn-ghost" data-range="1095">近3年</button>
              <button class="btn btn-ghost" data-range="1825">近5年</button>
            </div>
          </div>

          <div class="form-group" style="margin-bottom: var(--space-3)">
            <label class="form-label">初始资金</label>
            <input class="input mono" id="bt-cash" type="number" value="100000" step="10000" min="1000">
          </div>

          <div class="form-group" style="margin-bottom: var(--space-3)">
            <label class="form-label">策略</label>
            <select class="input" id="bt-strategy">${strategyOptions}</select>
          </div>

          <div class="form-group" style="margin-bottom: var(--space-4)" id="bt-params-section">
            <!-- 策略参数会动态生成 -->
          </div>

          <button class="btn btn-primary btn-lg" id="bt-run" style="width:100%">
            ▶ 运行回测
          </button>
        </div>
      </div>

      <!-- 结果区 -->
      <div class="backtest-results" id="bt-results">
        <div class="empty-state" style="min-height:400px">
          <div class="empty-state-icon">⚖</div>
          <p>配置参数并运行回测，结果将在这里展示</p>
          <p class="text-muted" style="font-size:var(--text-xs)">快捷键 Ctrl+Enter 运行</p>
        </div>
      </div>
    </div>
  `;
}

function bindEvents(container) {
  const runBtn = container.querySelector('#bt-run');
  runBtn.onclick = () => runBacktest(container);

  // Ctrl+Enter 快捷键
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      runBacktest(container);
    }
  });

  // 快捷日期按钮
  container.querySelectorAll('[data-range]').forEach(btn => {
    btn.onclick = () => {
      const days = parseInt(btn.dataset.range);
      const end = new Date();
      const start = new Date(Date.now() - days * 86400000);
      container.querySelector('#bt-end').value = end.toISOString().split('T')[0];
      container.querySelector('#bt-start').value = start.toISOString().split('T')[0];
    };
  });

  // 策略切换 → 更新参数
  const strategySelect = container.querySelector('#bt-strategy');
  strategySelect.onchange = () => updateStrategyParams(container);
  updateStrategyParams(container);
}

function updateStrategyParams(container) {
  const strategy = container.querySelector('#bt-strategy').value;
  const section = container.querySelector('#bt-params-section');

  const paramDefs = {
    sma_cross: [
      { key: 'fast_period', label: '短均线', value: 5, unit: '日', parser: 'int', step: 1, min: 1 },
      { key: 'slow_period', label: '长均线', value: 20, unit: '日', parser: 'int', step: 1, min: 2 },
    ],
    ema_cross: [
      { key: 'fast_period', label: '短均线', value: 12, unit: '日', parser: 'int', step: 1, min: 1 },
      { key: 'slow_period', label: '长均线', value: 26, unit: '日', parser: 'int', step: 1, min: 2 },
    ],
    buy_and_hold: [],
    macd: [
      { key: 'fast_period', label: '快线', value: 12, unit: '日', parser: 'int', step: 1, min: 1 },
      { key: 'slow_period', label: '慢线', value: 26, unit: '日', parser: 'int', step: 1, min: 2 },
      { key: 'signal_period', label: '信号线', value: 9, unit: '日', parser: 'int', step: 1, min: 1 },
    ],
    rsi: [
      { key: 'period', label: 'RSI 窗口', value: 14, unit: '日', parser: 'int', step: 1, min: 2 },
      { key: 'oversold', label: '超卖线', value: 30, unit: '', parser: 'float', step: 1, min: 1 },
      { key: 'overbought', label: '超买线', value: 70, unit: '', parser: 'float', step: 1, min: 1 },
    ],
    bollinger: [
      { key: 'period', label: '窗口', value: 20, unit: '日', parser: 'int', step: 1, min: 2 },
      { key: 'num_std', label: '标准差', value: 2.0, unit: '倍', parser: 'float', step: 0.1, min: 0.1 },
    ],
    grid: [
      { key: 'anchor_period', label: '锚均线', value: 20, unit: '日', parser: 'int', step: 1, min: 2 },
      { key: 'grid_pct', label: '网格幅度', value: 0.05, unit: '比例', parser: 'float', step: 0.01, min: 0.01 },
    ],
    dca: [
      { key: 'interval_days', label: '定投间隔', value: 20, unit: '日', parser: 'int', step: 1, min: 1 },
      { key: 'trade_fraction', label: '每次仓位', value: 0.2, unit: '比例', parser: 'float', step: 0.05, min: 0.01 },
    ],
    ma_rsi_filter: [
      { key: 'fast_period', label: '短均线', value: 10, unit: '日', parser: 'int', step: 1, min: 1 },
      { key: 'slow_period', label: '长均线', value: 30, unit: '日', parser: 'int', step: 1, min: 2 },
      { key: 'rsi_period', label: 'RSI 窗口', value: 14, unit: '日', parser: 'int', step: 1, min: 2 },
      { key: 'rsi_threshold', label: '入场 RSI', value: 55, unit: '', parser: 'float', step: 1, min: 1 },
      { key: 'exit_rsi', label: '离场 RSI', value: 45, unit: '', parser: 'float', step: 1, min: 1 },
    ],
  };

  const params = paramDefs[strategy] || [];
  if (params.length === 0) {
    section.innerHTML = '';
    return;
  }

  section.innerHTML = `
    <label class="form-label">策略参数</label>
    ${params.map(p => `
      <div style="display:flex;align-items:center;gap:var(--space-2);margin-top:var(--space-1)">
        <span style="font-size:var(--text-sm);color:var(--text-secondary);width:60px">${p.label}</span>
        <input
          class="input mono"
          data-param="${p.key}"
          data-param-parser="${p.parser || 'int'}"
          type="number"
          value="${p.value}"
          step="${p.step ?? 1}"
          min="${p.min ?? ''}"
          style="width:100px"
        >
        <span style="font-size:var(--text-xs);color:var(--text-muted)">${p.unit}</span>
      </div>
    `).join('')}
  `;
}

async function runBacktest(container) {
  const runBtn = container.querySelector('#bt-run');
  const resultsEl = container.querySelector('#bt-results');

  const symbol = container.querySelector('#bt-symbol').value.trim();
  const startDate = container.querySelector('#bt-start').value;
  const endDate = container.querySelector('#bt-end').value;
  const strategy = container.querySelector('#bt-strategy').value;
  const cash = parseFloat(container.querySelector('#bt-cash').value);

  if (!symbol) {
    toast.error('请输入股票代码');
    return;
  }
  if (!startDate || !endDate) {
    toast.error('请选择时间范围');
    return;
  }

  // 收集策略参数
  const params = {};
  container.querySelectorAll('[data-param]').forEach(el => {
    if (!el.value) {
      return;
    }
    const parser = el.dataset.paramParser || 'int';
    params[el.dataset.param] = parser === 'float'
      ? parseFloat(el.value)
      : parseInt(el.value, 10);
  });

  // 运行中状态
  runBtn.disabled = true;
  runBtn.classList.add('btn-loading');
  runBtn.textContent = '⏳ 回测中...';

  // 显示 skeleton
  resultsEl.innerHTML = buildSkeleton();

  // 进度条
  document.querySelector('.progress-bar')?.classList.add('active');

  try {
    const result = await api.runBacktest({
      symbol,
      start_date: startDate,
      end_date: endDate,
      strategy,
      cash,
      params,
    });

    // 完成动画
    runBtn.textContent = '✓ 完成';
    runBtn.style.background = 'var(--profit)';
    setTimeout(() => {
      runBtn.textContent = '▶ 运行回测';
      runBtn.style.background = '';
    }, 1500);

    renderResults(resultsEl, result);
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : '回测失败，请检查参数';
    toast.error(msg);
    resultsEl.innerHTML = `
      <div class="empty-state" style="min-height:400px">
        <div class="empty-state-icon">⚠</div>
        <p>${msg}</p>
        <button class="btn btn-ghost" onclick="this.closest('.backtest-results').innerHTML=''">清除</button>
      </div>
    `;
  } finally {
    runBtn.disabled = false;
    runBtn.classList.remove('btn-loading');
    document.querySelector('.progress-bar')?.classList.remove('active');
  }
}

function renderResults(container, result) {
  const summary = result.summary || {};
  const trades = result.trades || [];
  const equityCurve = result.equity_curve || [];

  container.innerHTML = `
    <div class="metrics-grid" id="bt-metrics"></div>
    <div class="card">
      <div class="card-title">权益曲线</div>
      <div class="chart-container" id="bt-equity-chart"></div>
    </div>
    <div class="card">
      <div class="card-title">成交明细 <span class="text-secondary" style="font-size:var(--text-sm);font-weight:400">(${trades.length} 笔交易)</span></div>
      <div id="bt-trades-table"></div>
    </div>
  `;

  renderMetrics(container.querySelector('#bt-metrics'), summary);
  renderEquityChart(
    container.querySelector('#bt-equity-chart'),
    equityCurve,
    summary.initial_equity
  );
  renderTradesTable(container.querySelector('#bt-trades-table'), trades);
}

function renderMetrics(container, s) {
  const metrics = [
    { label: '总收益', value: formatPct(s.total_return_pct), color: pctColor(s.total_return_pct) },
    { label: '年化收益', value: formatPct(s.annualized_return_pct), color: pctColor(s.annualized_return_pct) },
    { label: '最大回撤', value: `-${formatPctAbs(s.max_drawdown_pct)}`, color: 'var(--loss)' },
    { label: 'Sharpe', value: formatNum(s.sharpe_ratio), color: sharpeColor(s.sharpe_ratio) },
    { label: '胜率', value: formatPctAbs(s.win_rate_pct), color: winRateColor(s.win_rate_pct) },
    { label: '交易次数', value: s.trades_count ?? '-', color: 'var(--text-primary)' },
  ];

  container.innerHTML = metrics.map(m => `
    <div class="metric-card">
      <span class="metric-label">${m.label}</span>
      <span class="metric-value" style="color:${m.color}">${m.value}</span>
    </div>
  `).join('');
}

function buildSkeleton() {
  return `
    <div class="metrics-grid">
      ${Array(6).fill('<div class="metric-card"><div class="skeleton" style="height:16px;width:60px;margin-bottom:8px"></div><div class="skeleton" style="height:32px;width:100px"></div></div>').join('')}
    </div>
    <div class="card">
      <div class="skeleton" style="height:350px"></div>
    </div>
    <div class="card">
      ${Array(5).fill('<div class="skeleton" style="height:20px;margin-bottom:8px"></div>').join('')}
    </div>
  `;
}

function formatPct(n) {
  if (n == null) return '-';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${Number(n).toFixed(2)}%`;
}

function formatPctAbs(n) {
  if (n == null) return '-';
  return `${Number(n).toFixed(2)}%`;
}

function formatNum(n) {
  if (n == null) return '-';
  return Number(n).toFixed(2);
}

function pctColor(n) {
  if (n == null) return 'var(--text-primary)';
  return n >= 0 ? 'var(--profit)' : 'var(--loss)';
}

function sharpeColor(n) {
  if (n == null) return 'var(--text-primary)';
  return n >= 1 ? 'var(--profit)' : n >= 0 ? 'var(--text-primary)' : 'var(--loss)';
}

function winRateColor(n) {
  if (n == null) return 'var(--text-primary)';
  return n >= 50 ? 'var(--profit)' : 'var(--loss)';
}
