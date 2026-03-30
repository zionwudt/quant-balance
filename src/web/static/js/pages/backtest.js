/**
 * 知衡 QuantBalance — 回测页面
 */

import { api, ApiError } from '../api.js';
import { toast } from '../components/toast.js';
import { renderEquityChart, disposeEquityChart } from '../components/chart-equity.js';
import { renderKlineChart, highlightKlineTrade, disposeKlineChart } from '../components/chart-kline.js';
import { renderMonthlyHeatmap, disposeMonthlyHeatmap } from '../components/chart-heatmap.js';
import { renderPortfolioAttributionCharts, disposePortfolioAttributionCharts } from '../components/chart-attribution.js';
import { renderTradesTable } from '../components/data-table.js';
import { createMultiStockSearch } from '../components/stock-search.js';
import { getAppSettings } from '../settings.js';
import { downloadJson } from '../utils/download.js';

const DEFAULT_STRATEGY_NAMES = [
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

const STRATEGY_PRESETS = {
  sma_cross: {
    label: 'SMA 双均线',
    summary: '用快慢均线金叉/死叉捕捉趋势切换。',
    params: [
      { key: 'fast_period', label: '快线窗口', defaultValue: 5, parser: 'int', min: 1, step: 1, unit: '日', hint: '更灵敏，但更容易被噪音触发。' },
      { key: 'slow_period', label: '慢线窗口', defaultValue: 20, parser: 'int', min: 2, step: 1, unit: '日', hint: '决定主要趋势过滤强度。' },
    ],
  },
  ema_cross: {
    label: 'EMA 双均线',
    summary: '比 SMA 更灵敏，适合更快的趋势切换。',
    params: [
      { key: 'fast_period', label: '快线窗口', defaultValue: 12, parser: 'int', min: 1, step: 1, unit: '日', hint: 'EMA 对近期价格更敏感。' },
      { key: 'slow_period', label: '慢线窗口', defaultValue: 26, parser: 'int', min: 2, step: 1, unit: '日', hint: '窗口越大，过滤越稳。' },
    ],
  },
  buy_and_hold: {
    label: '买入持有',
    summary: '只在开始时建仓，适合作为策略基准。',
    params: [],
  },
  macd: {
    label: 'MACD 趋势',
    summary: '利用快慢线与信号线交叉识别动量切换。',
    params: [
      { key: 'fast_period', label: '快线周期', defaultValue: 12, parser: 'int', min: 1, step: 1, unit: '日', hint: '决定 MACD 响应速度。' },
      { key: 'slow_period', label: '慢线周期', defaultValue: 26, parser: 'int', min: 2, step: 1, unit: '日', hint: '定义更长趋势。' },
      { key: 'signal_period', label: '信号周期', defaultValue: 9, parser: 'int', min: 1, step: 1, unit: '日', hint: '平滑 MACD 线，控制入场延迟。' },
    ],
  },
  rsi: {
    label: 'RSI 反转',
    summary: '超卖反弹入场，超买区域离场。',
    params: [
      { key: 'period', label: 'RSI 窗口', defaultValue: 14, parser: 'int', min: 2, step: 1, unit: '日', hint: '决定 RSI 反应周期。' },
      { key: 'oversold', label: '超卖线', defaultValue: 30, parser: 'float', min: 1, step: 1, unit: '', hint: '越低越保守。' },
      { key: 'overbought', label: '超买线', defaultValue: 70, parser: 'float', min: 1, step: 1, unit: '', hint: '越高越容易持有更久。' },
    ],
  },
  bollinger: {
    label: '布林突破',
    summary: '上轨突破入场，回落到中轨附近离场。',
    params: [
      { key: 'period', label: '窗口', defaultValue: 20, parser: 'int', min: 2, step: 1, unit: '日', hint: '决定布林带平滑程度。' },
      { key: 'num_std', label: '标准差倍数', defaultValue: 2, parser: 'float', min: 0.1, step: 0.1, unit: '倍', hint: '越大越不易触发。' },
    ],
  },
  grid: {
    label: '均线网格',
    summary: '围绕锚均线做低吸高抛的均值回归。',
    params: [
      { key: 'anchor_period', label: '锚均线', defaultValue: 20, parser: 'int', min: 2, step: 1, unit: '日', hint: '锚线决定网格中心。' },
      { key: 'grid_pct', label: '网格幅度', defaultValue: 0.05, parser: 'float', min: 0.01, step: 0.01, unit: '比例', hint: '幅度越大，交易更稀疏。' },
    ],
  },
  dca: {
    label: '定投',
    summary: '按固定间隔分批买入，适合摊平成本。',
    params: [
      { key: 'interval_days', label: '定投间隔', defaultValue: 20, parser: 'int', min: 1, step: 1, unit: '日', hint: '多久买一次。' },
      { key: 'trade_fraction', label: '单次仓位', defaultValue: 0.2, parser: 'float', min: 0.01, step: 0.05, unit: '比例', hint: '每次动用多少剩余资金。' },
    ],
  },
  ma_rsi_filter: {
    label: '均线 + RSI 过滤',
    summary: '先看趋势，再用 RSI 过滤弱势入场。',
    params: [
      { key: 'fast_period', label: '快均线', defaultValue: 10, parser: 'int', min: 1, step: 1, unit: '日', hint: '趋势方向更敏感。' },
      { key: 'slow_period', label: '慢均线', defaultValue: 30, parser: 'int', min: 2, step: 1, unit: '日', hint: '作为主趋势确认。' },
      { key: 'rsi_period', label: 'RSI 窗口', defaultValue: 14, parser: 'int', min: 2, step: 1, unit: '日', hint: '动量确认的观察长度。' },
      { key: 'rsi_threshold', label: '入场 RSI', defaultValue: 55, parser: 'float', min: 1, step: 1, unit: '', hint: '只有动量足够时才进场。' },
      { key: 'exit_rsi', label: '离场 RSI', defaultValue: 45, parser: 'float', min: 1, step: 1, unit: '', hint: '跌破后视为动量衰减。' },
    ],
  },
};

const BENCHMARK_OPTIONS = [
  { symbol: '', name: '不启用基准' },
  { symbol: '000300.SH', name: '沪深300' },
  { symbol: '000905.SH', name: '中证500' },
  { symbol: '000852.SH', name: '中证1000' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000001.SH', name: '上证指数' },
];

const REBALANCE_OPTIONS = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
  { value: 'quarterly', label: '每季度' },
];

let strategies = [];
let lastSingleResult = null;
let lastPortfolioResult = null;
let pageState = createInitialState();

export async function initBacktestPage(container, routeContext = {}) {
  disposeEquityChart();
  disposeKlineChart();
  disposeMonthlyHeatmap();
  disposePortfolioAttributionCharts();
  pageState = createInitialState(routeContext.params);

  try {
    const response = await api.getStrategies();
    strategies = buildStrategyDefinitions(response.strategies || []);
  } catch {
    strategies = buildStrategyDefinitions(
      DEFAULT_STRATEGY_NAMES.map(name => ({ name, doc: '' })),
    );
  }

  container.innerHTML = buildHTML();
  pageState.currentStrategy = strategies[0]?.name || 'sma_cross';
  pageState.symbolSearch = createMultiStockSearch(container.querySelector('#bt-symbol-search'), {
    initialSelection: pageState.initialSymbols,
    filterItem: item => item.kind !== 'benchmark',
    caption: '支持多选与标签删除；输入多只股票时将自动切换为等权组合回测。',
    onChange: () => {
      syncModeUI(container);
    },
  });

  bindEvents(container);
  syncStrategyCardSelection(container);
  updateStrategyParams(container);
  syncAdvancedInputs(container);
  syncModeUI(container);

  return {
    runPrimary() {
      void runBacktest(container);
    },
    exportCurrent() {
      exportCurrentResult();
    },
    focusPrimary() {
      pageState.symbolSearch?.focus();
    },
    dispose() {
      disposeEquityChart();
      disposeKlineChart();
      disposeMonthlyHeatmap();
      disposePortfolioAttributionCharts();
    },
  };
}

function createInitialState(params = {}) {
  const routeSymbols = parseSymbolsParam(params?.symbols);
  const tradingDefaults = getAppSettings().trading_defaults || {};
  return {
    currentStrategy: 'sma_cross',
    strategyValues: {},
    symbolSearch: null,
    tradingDefaults: {
      cash: Number(tradingDefaults.cash || 100000),
      commission: Number(tradingDefaults.commission || 0.001),
      rebalance_frequency: tradingDefaults.rebalance_frequency || 'monthly',
      stop_loss_pct: Number(tradingDefaults.stop_loss_pct || 0),
      take_profit_pct: Number(tradingDefaults.take_profit_pct || 0),
    },
    initialSymbols: routeSymbols.length
      ? routeSymbols.map(symbol => ({ symbol, name: '组合候选', market: '选股页带入' }))
      : [{ symbol: '600519.SH', name: '贵州茅台', market: '主板' }],
  };
}

function buildStrategyDefinitions(items) {
  const seen = new Set();
  const normalized = [];
  const source = items.length
    ? items
    : DEFAULT_STRATEGY_NAMES.map(name => ({ name, doc: '' }));

  source.forEach((item) => {
    const name = typeof item === 'string' ? item : item.name;
    if (!name || seen.has(name)) {
      return;
    }
    seen.add(name);
    const preset = STRATEGY_PRESETS[name] || {};
    normalized.push({
      name,
      label: preset.label || name,
      summary: preset.summary || (typeof item === 'string' ? '' : item.doc || ''),
      params: preset.params || [],
      doc: typeof item === 'string' ? '' : item.doc || '',
    });
  });

  return normalized.length
    ? normalized
    : DEFAULT_STRATEGY_NAMES.map(name => ({
      name,
      label: STRATEGY_PRESETS[name]?.label || name,
      summary: STRATEGY_PRESETS[name]?.summary || '',
      params: STRATEGY_PRESETS[name]?.params || [],
      doc: '',
    }));
}

function buildHTML() {
  const today = new Date();
  const oneYearAgo = new Date(today);
  oneYearAgo.setFullYear(today.getFullYear() - 1);
  const defaults = pageState.tradingDefaults || {};

  return `
    <div class="backtest-layout">
      <div class="backtest-params">
        <div class="card backtest-workbench">
          <div class="card-title">回测工作台</div>
          <div class="mode-banner" id="bt-mode-banner"></div>

          <div class="form-group" style="margin-bottom: var(--space-4)">
            <label class="form-label">股票代码</label>
            <div id="bt-symbol-search"></div>
          </div>

          <div class="portfolio-mode-panel hidden" id="bt-portfolio-panel">
            <div class="portfolio-mode-title">组合回测说明</div>
            <p class="portfolio-mode-note">当你选择 2 只及以上股票时，系统会自动切换为等权组合回测，并支持按日/周/月/季度再平衡。</p>
            <div class="portfolio-mode-list" id="bt-portfolio-list"></div>
          </div>

          <div class="form-group" style="margin-bottom: var(--space-4)">
            <label class="form-label">时间范围</label>
            <div class="date-range-row">
              <input class="input" id="bt-start" type="date" value="${formatDateInput(oneYearAgo)}">
              <span class="date-range-separator">→</span>
              <input class="input" id="bt-end" type="date" value="${formatDateInput(today)}">
            </div>
            <div class="quick-dates">
              <button class="btn btn-ghost" data-range="365">近1年</button>
              <button class="btn btn-ghost" data-range="1095">近3年</button>
              <button class="btn btn-ghost" data-range="1825">近5年</button>
            </div>
          </div>

          <div class="form-group" style="margin-bottom: var(--space-4)">
            <label class="form-label">初始资金</label>
            <input class="input mono" id="bt-cash" type="number" value="${defaults.cash || 100000}" step="10000" min="1000">
          </div>

          <div class="strategy-section" id="bt-strategy-section">
            <div class="section-heading">
              <div>
                <div class="form-label">策略切换</div>
                <p class="section-note">单股模式下可自由切换策略；组合模式使用等权再平衡，不再应用单标的择时策略。</p>
              </div>
            </div>
            <div class="strategy-radio-grid">
              ${strategies.map((strategy, index) => `
                <label class="strategy-card">
                  <input type="radio" name="bt-strategy" value="${strategy.name}" ${index === 0 ? 'checked' : ''}>
                  <span class="strategy-card-key mono">${strategy.name}</span>
                  <span class="strategy-card-title">${strategy.label}</span>
                  <span class="strategy-card-desc">${strategy.summary || strategy.doc || '暂无描述'}</span>
                </label>
              `).join('')}
            </div>
          </div>

          <div class="form-group strategy-params-section" id="bt-params-section"></div>

          <div class="advanced-panel" id="bt-advanced-panel">
            <button type="button" class="advanced-panel-toggle" id="bt-advanced-toggle" aria-expanded="false">
              <span>高级设置</span>
              <span class="advanced-panel-meta">滑点 / 风控 / 基准 / 再平衡</span>
              <span class="advanced-panel-caret">⌄</span>
            </button>
            <div class="advanced-panel-body">
              <div class="advanced-panel-inner">
                <div class="advanced-settings-grid">
                  <label class="advanced-field" id="bt-benchmark-field">
                    <span class="form-label">基准指数</span>
                    <select class="input" id="bt-benchmark-symbol">
                      ${BENCHMARK_OPTIONS.map(item => `<option value="${item.symbol}">${item.name}${item.symbol ? ` (${item.symbol})` : ''}</option>`).join('')}
                    </select>
                    <span class="field-help">用于在权益曲线和指标卡中观察超额收益。</span>
                  </label>

                  <label class="advanced-field">
                    <span class="form-label">手续费</span>
                    <input class="input mono" id="bt-commission" type="number" value="${defaults.commission || 0.001}" step="0.0005" min="0">
                    <span class="field-help">默认 0.001，即 0.1%。</span>
                  </label>

                  <label class="advanced-field hidden" id="bt-rebalance-field">
                    <span class="form-label">再平衡频率</span>
                    <select class="input" id="bt-rebalance-frequency">
                      ${REBALANCE_OPTIONS.map(item => `<option value="${item.value}"${item.value === defaults.rebalance_frequency ? ' selected' : ''}>${item.label}</option>`).join('')}
                    </select>
                    <span class="field-help">组合模式下使用等权重，再按该频率调仓。</span>
                  </label>

                  <label class="advanced-field" id="bt-slippage-mode-field">
                    <span class="form-label">滑点模式</span>
                    <select class="input" id="bt-slippage-mode">
                      <option value="off">关闭</option>
                      <option value="spread">点差</option>
                      <option value="commission">附加佣金</option>
                    </select>
                    <span class="field-help"><span class="mono">spread</span> 走价差，<span class="mono">commission</span> 叠加到手续费。</span>
                  </label>

                  <label class="advanced-field" id="bt-slippage-rate-field">
                    <span class="form-label">滑点比例</span>
                    <input class="input mono" id="bt-slippage-rate" type="number" value="0" step="0.0005" min="0">
                    <span class="field-help">与手续费同口径，例如 0.001 表示 0.1%。</span>
                  </label>

                  <label class="advanced-field toggle-field" id="bt-stop-loss-field">
                    <span class="form-label">止损</span>
                    <label class="toggle-row">
                      <input type="checkbox" id="bt-stop-loss-enabled" ${defaults.stop_loss_pct > 0 ? 'checked' : ''}>
                      <span>启用止损</span>
                    </label>
                    <input class="input mono" id="bt-stop-loss" type="number" value="${defaults.stop_loss_pct || 0.08}" step="0.01" min="0">
                    <span class="field-help">例如 0.08 代表回撤 8% 止损。</span>
                  </label>

                  <label class="advanced-field toggle-field" id="bt-take-profit-field">
                    <span class="form-label">止盈</span>
                    <label class="toggle-row">
                      <input type="checkbox" id="bt-take-profit-enabled" ${defaults.take_profit_pct > 0 ? 'checked' : ''}>
                      <span>启用止盈</span>
                    </label>
                    <input class="input mono" id="bt-take-profit" type="number" value="${defaults.take_profit_pct || 0.15}" step="0.01" min="0">
                    <span class="field-help">例如 0.15 代表盈利 15% 止盈。</span>
                  </label>

                  <label class="advanced-field" id="bt-max-position-field">
                    <span class="form-label">最大仓位</span>
                    <input class="input mono" id="bt-max-position" type="number" value="1" step="0.05" min="0.05" max="1">
                    <span class="field-help"><span class="mono">1</span> 表示满仓，<span class="mono">0.5</span> 表示单次最多 50% 仓位。</span>
                  </label>

                  <label class="advanced-field" id="bt-max-holdings-field">
                    <span class="form-label">最大持仓笔数</span>
                    <input class="input mono" id="bt-max-holdings" type="number" value="20" step="1" min="1">
                    <span class="field-help">对 <span class="mono">dca</span> 这类允许分批加仓的策略更有意义。</span>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <button class="btn btn-primary btn-lg" id="bt-run" style="width:100%">
            ▶ 运行回测
          </button>
        </div>
      </div>

      <div class="backtest-results" id="bt-results">
        <div class="empty-state backtest-empty">
          <div class="empty-state-icon">⚖</div>
          <p>单股模式支持 K 线、成交量、买卖点和交易区间联动。</p>
          <p>多股模式会切换为组合回测，并自动展示月度热力图与调仓记录。</p>
          <p class="text-muted" style="font-size:var(--text-xs)">支持 Ctrl+Enter 运行；从股票池页跳转后会自动带入选中的股票列表。</p>
        </div>
      </div>
    </div>
  `;
}

function bindEvents(container) {
  const runButton = container.querySelector('#bt-run');
  runButton.addEventListener('click', () => {
    void runBacktest(container);
  });

  container.querySelectorAll('[data-range]').forEach(button => {
    button.addEventListener('click', () => {
      const days = Number(button.dataset.range);
      const end = new Date();
      const start = new Date(end);
      start.setDate(end.getDate() - days);
      container.querySelector('#bt-start').value = formatDateInput(start);
      container.querySelector('#bt-end').value = formatDateInput(end);
    });
  });

  container.querySelectorAll('input[name="bt-strategy"]').forEach(input => {
    input.addEventListener('change', () => {
      syncStrategyCardSelection(container);
      updateStrategyParams(container);
    });
  });

  container.querySelector('#bt-advanced-toggle')?.addEventListener('click', () => {
    const panel = container.querySelector('#bt-advanced-panel');
    const isExpanded = panel.classList.toggle('expanded');
    container.querySelector('#bt-advanced-toggle')?.setAttribute('aria-expanded', String(isExpanded));
  });

  [
    '#bt-slippage-mode',
    '#bt-stop-loss-enabled',
    '#bt-take-profit-enabled',
  ].forEach((selector) => {
    container.querySelector(selector)?.addEventListener('change', () => syncAdvancedInputs(container));
  });
}

function syncModeUI(container) {
  const selectedSymbols = getSelectedSymbols();
  const isPortfolio = selectedSymbols.length > 1;

  container.querySelector('#bt-mode-banner').innerHTML = isPortfolio
    ? `<strong>组合模式</strong> · 已选 <span class="mono">${selectedSymbols.length}</span> 只股票，将按等权方式执行组合回测。`
    : `<strong>单股模式</strong> · 支持策略切换、K 线成交联动和可选 benchmark 对比。`;

  container.querySelector('#bt-strategy-section')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-params-section')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-benchmark-field')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-slippage-mode-field')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-slippage-rate-field')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-stop-loss-field')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-take-profit-field')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-max-position-field')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-max-holdings-field')?.classList.toggle('hidden', isPortfolio);
  container.querySelector('#bt-rebalance-field')?.classList.toggle('hidden', !isPortfolio);

  const portfolioPanel = container.querySelector('#bt-portfolio-panel');
  portfolioPanel?.classList.toggle('hidden', !isPortfolio);
  if (portfolioPanel) {
    const listEl = container.querySelector('#bt-portfolio-list');
    listEl.innerHTML = selectedSymbols.map(symbol => `<span class="result-tag mono">${symbol}</span>`).join('');
  }

  const runButton = container.querySelector('#bt-run');
  runButton.textContent = isPortfolio ? '▶ 运行组合回测' : '▶ 运行回测';
  syncAdvancedInputs(container);
}

function updateStrategyParams(container) {
  saveCurrentStrategyValues(container);
  const strategyName = getSelectedStrategyName(container);
  const strategy = strategies.find(item => item.name === strategyName) || strategies[0];
  const section = container.querySelector('#bt-params-section');
  pageState.currentStrategy = strategy.name;

  if (!strategy.params.length) {
    section.innerHTML = `
      <div class="params-summary">
        <label class="form-label">策略参数</label>
        <p class="section-note">${strategy.summary || strategy.doc || '该策略无需额外参数，可直接运行。'}</p>
      </div>
      <div class="strategy-param-empty">当前策略没有可调参数，更多风控选项在“高级设置”中配置。</div>
    `;
    return;
  }

  const values = pageState.strategyValues[strategy.name] || {};
  section.innerHTML = `
    <div class="params-summary">
      <label class="form-label">策略参数</label>
      <p class="section-note">${strategy.summary || strategy.doc || '根据当前策略调整参数。'}</p>
    </div>
    <div class="strategy-params-grid">
      ${strategy.params.map((param) => `
        <label class="param-card">
          <span class="param-card-title">${param.label}</span>
          <span class="param-card-desc">${param.hint || '暂无说明'}</span>
          <div class="param-card-input">
            <input
              class="input mono"
              data-param="${param.key}"
              data-param-parser="${param.parser || 'int'}"
              type="number"
              value="${values[param.key] ?? param.defaultValue ?? ''}"
              step="${param.step ?? 1}"
              min="${param.min ?? ''}"
              max="${param.max ?? ''}"
            >
            <span class="param-card-unit">${param.unit || ''}</span>
          </div>
        </label>
      `).join('')}
    </div>
  `;
}

function saveCurrentStrategyValues(container) {
  const strategyName = pageState.currentStrategy;
  if (!strategyName) {
    return;
  }
  const values = {};
  container.querySelectorAll('#bt-params-section [data-param]').forEach((input) => {
    if (input.value !== '') {
      values[input.dataset.param] = parseValue(input.value, input.dataset.paramParser || 'int');
    }
  });
  pageState.strategyValues[strategyName] = values;
}

function syncAdvancedInputs(container) {
  const slippageMode = container.querySelector('#bt-slippage-mode')?.value || 'off';
  const slippageInput = container.querySelector('#bt-slippage-rate');
  const stopLossEnabled = container.querySelector('#bt-stop-loss-enabled')?.checked;
  const takeProfitEnabled = container.querySelector('#bt-take-profit-enabled')?.checked;
  const stopLossInput = container.querySelector('#bt-stop-loss');
  const takeProfitInput = container.querySelector('#bt-take-profit');
  const isPortfolio = getSelectedSymbols().length > 1;

  if (slippageInput) {
    slippageInput.disabled = slippageMode === 'off' || isPortfolio;
    slippageInput.closest('.advanced-field')?.classList.toggle('is-disabled', slippageMode === 'off' || isPortfolio);
  }
  if (stopLossInput) {
    stopLossInput.disabled = !stopLossEnabled || isPortfolio;
    stopLossInput.closest('.advanced-field')?.classList.toggle('is-disabled', !stopLossEnabled || isPortfolio);
  }
  if (takeProfitInput) {
    takeProfitInput.disabled = !takeProfitEnabled || isPortfolio;
    takeProfitInput.closest('.advanced-field')?.classList.toggle('is-disabled', !takeProfitEnabled || isPortfolio);
  }
}

function syncStrategyCardSelection(container) {
  container.querySelectorAll('.strategy-card').forEach((card) => {
    const input = card.querySelector('input[name="bt-strategy"]');
    card.classList.toggle('is-active', Boolean(input?.checked));
  });
}

async function runBacktest(container) {
  const selectedSymbols = getSelectedSymbols();
  const runButton = container.querySelector('#bt-run');
  const resultsEl = container.querySelector('#bt-results');
  const isPortfolio = selectedSymbols.length > 1;
  const startDate = container.querySelector('#bt-start').value;
  const endDate = container.querySelector('#bt-end').value;
  const cash = Number(container.querySelector('#bt-cash').value);
  const commission = Number(container.querySelector('#bt-commission').value);

  if (!selectedSymbols.length) {
    toast.error('请输入或选择至少 1 只股票');
    return;
  }
  if (!startDate || !endDate) {
    toast.error('请选择时间范围');
    return;
  }
  if (startDate > endDate) {
    toast.error('起始日期不能晚于结束日期');
    return;
  }
  if (!Number.isFinite(cash) || cash <= 0) {
    toast.error('初始资金必须大于 0');
    return;
  }
  if (!Number.isFinite(commission) || commission < 0) {
    toast.error('手续费不能为负数');
    return;
  }

  saveCurrentStrategyValues(container);
  const params = isPortfolio ? null : collectStrategyParams(container);
  if (!isPortfolio && !params) {
    return;
  }

  runButton.disabled = true;
  runButton.classList.add('btn-loading');
  runButton.textContent = isPortfolio ? '⏳ 组合回测中...' : '⏳ 回测中...';
  resultsEl.innerHTML = buildSkeleton(isPortfolio ? 4 : 5);
  document.querySelector('.progress-bar')?.classList.add('active');

  try {
    if (isPortfolio) {
      const result = await api.runPortfolio({
        symbols: selectedSymbols,
        start_date: startDate,
        end_date: endDate,
        allocation: 'equal',
        rebalance_frequency: container.querySelector('#bt-rebalance-frequency').value,
        cash,
        commission,
      });
      lastPortfolioResult = result;
      renderPortfolioResults(resultsEl, result);
    } else {
      const slippageMode = container.querySelector('#bt-slippage-mode').value;
      const slippageRate = Number(container.querySelector('#bt-slippage-rate').value || 0);
      const benchmarkSymbol = container.querySelector('#bt-benchmark-symbol').value;
      const payload = {
        symbol: selectedSymbols[0],
        start_date: startDate,
        end_date: endDate,
        strategy: getSelectedStrategyName(container),
        cash,
        commission,
        params,
      };
      if (benchmarkSymbol) {
        payload.benchmark_symbol = benchmarkSymbol;
      }
      if (slippageMode !== 'off') {
        payload.slippage_mode = slippageMode;
      }
      if (slippageRate > 0) {
        payload.slippage_rate = slippageRate;
      }

      const result = await api.runBacktest(payload);
      lastSingleResult = result;
      renderSingleResults(resultsEl, result);
    }

    runButton.textContent = '✓ 完成';
    runButton.style.background = 'var(--profit)';
    window.setTimeout(() => {
      runButton.textContent = isPortfolio ? '▶ 运行组合回测' : '▶ 运行回测';
      runButton.style.background = '';
    }, 1500);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : '回测失败，请检查参数和行情配置';
    toast.error(message);
    if (isPortfolio && lastPortfolioResult) {
      renderPortfolioResults(resultsEl, lastPortfolioResult);
    } else if (!isPortfolio && lastSingleResult) {
      renderSingleResults(resultsEl, lastSingleResult);
    } else {
      resultsEl.innerHTML = `
        <div class="empty-state backtest-empty">
          <div class="empty-state-icon">⚠</div>
          <p>${message}</p>
          <p class="text-muted" style="font-size:var(--text-xs)">表单内容已保留，修正后可直接重试。</p>
        </div>
      `;
    }
  } finally {
    runButton.disabled = false;
    runButton.classList.remove('btn-loading');
    document.querySelector('.progress-bar')?.classList.remove('active');
    window.dispatchEvent(new CustomEvent('qb-status-message', {
      detail: {
        text: isPortfolio ? '回测中心 · 组合结果已更新' : '回测中心 · 单股结果已更新',
      },
    }));
  }
}

function exportCurrentResult() {
  const payload = lastSingleResult || lastPortfolioResult;
  if (!payload) {
    toast.info('当前还没有可导出的回测结果');
    return;
  }

  const suffix = lastSingleResult ? 'backtest' : 'portfolio';
  downloadJson(`quant-balance-${suffix}-${Date.now()}.json`, payload);
  toast.success('回测结果已导出');
}

function collectStrategyParams(container) {
  const params = {};
  container.querySelectorAll('#bt-params-section [data-param]').forEach((input) => {
    if (!input.value) {
      return;
    }
    params[input.dataset.param] = parseValue(input.value, input.dataset.paramParser || 'int');
  });

  const stopLossEnabled = container.querySelector('#bt-stop-loss-enabled').checked;
  const takeProfitEnabled = container.querySelector('#bt-take-profit-enabled').checked;
  const stopLossValue = Number(container.querySelector('#bt-stop-loss').value);
  const takeProfitValue = Number(container.querySelector('#bt-take-profit').value);
  const maxPositionValue = Number(container.querySelector('#bt-max-position').value);
  const maxHoldingsValue = Number(container.querySelector('#bt-max-holdings').value);

  if (stopLossEnabled) {
    if (!Number.isFinite(stopLossValue) || stopLossValue < 0) {
      toast.error('止损比例必须是非负数');
      return null;
    }
    params.stop_loss_pct = stopLossValue;
  }
  if (takeProfitEnabled) {
    if (!Number.isFinite(takeProfitValue) || takeProfitValue < 0) {
      toast.error('止盈比例必须是非负数');
      return null;
    }
    params.take_profit_pct = takeProfitValue;
  }
  if (!Number.isFinite(maxPositionValue) || maxPositionValue <= 0 || maxPositionValue > 1) {
    toast.error('最大仓位必须位于 (0, 1] 区间');
    return null;
  }
  if (!Number.isFinite(maxHoldingsValue) || maxHoldingsValue < 1) {
    toast.error('最大持仓笔数必须 >= 1');
    return null;
  }

  params.max_position_pct = maxPositionValue;
  params.max_holdings = Math.trunc(maxHoldingsValue);
  return params;
}

function renderSingleResults(container, result) {
  disposeMonthlyHeatmap();
  disposePortfolioAttributionCharts();
  const summary = result.summary || {};
  const trades = (result.trades || []).map((trade, index) => ({
    ...trade,
    trade_index: trade.trade_index ?? index + 1,
  }));
  const equityCurve = result.equity_curve || [];
  const priceBars = result.price_bars || [];
  const chartOverlays = result.chart_overlays || {};
  const context = result.run_context || {};
  const strategyDef = strategies.find(item => item.name === context.strategy);

  container.innerHTML = `
    <div class="results-overview">
      <div>
        <div class="results-title">${context.symbol || '回测结果'}</div>
        <p class="results-subtitle">
          ${strategyDef?.label || context.strategy || '策略'} · ${context.start_date || '-'} ~ ${context.end_date || '-'}
          ${context.benchmark_symbol ? ` · 基准 ${context.benchmark_symbol}` : ''}
        </p>
      </div>
      <div class="results-tags">
        <span class="result-tag mono">${context.asset_type || 'stock'}</span>
        <span class="result-tag mono">${context.data_provider || 'auto'}</span>
        <span class="result-tag mono">${context.bars_count || 0} bars</span>
      </div>
    </div>

    <div class="metrics-grid" id="bt-metrics"></div>

    <div class="card">
      <div class="results-card-head">
        <div>
          <div class="card-title">K 线与成交</div>
          <p class="card-subtitle">OHLC、成交量、策略线、买卖点已叠加。点击下方交易行可高亮区间。</p>
        </div>
      </div>
      <div class="chart-container chart-container-xl" id="bt-kline-chart"></div>
      <div class="trade-focus" id="bt-trade-focus">未选中交易，点击成交明细中的某一行可高亮对应区间。</div>
    </div>

    <div class="card">
      <div class="results-card-head">
        <div>
          <div class="card-title">权益曲线</div>
          <p class="card-subtitle">策略净值、回撤和可选 benchmark 会在同一视图里对照展示。</p>
        </div>
      </div>
      <div class="chart-container" id="bt-equity-chart"></div>
    </div>

    <div class="card">
      <div class="results-card-head">
        <div>
          <div class="card-title">月度收益热力图</div>
          <p class="card-subtitle">悬浮可查看精确月收益，颜色从深绿到深红映射收益强弱。</p>
        </div>
      </div>
      <div class="chart-container chart-container-heatmap" id="bt-heatmap-chart"></div>
    </div>

    <div class="card">
      <div class="results-card-head">
        <div>
          <div class="card-title">成交明细 <span class="text-secondary" style="font-size:var(--text-sm);font-weight:400">(${trades.length} 笔交易)</span></div>
          <p class="card-subtitle">支持排序；点击任意一行，会同步高亮 K 线上的入场到离场区间。</p>
        </div>
      </div>
      <div id="bt-trades-table"></div>
    </div>
  `;

  renderMetrics(container.querySelector('#bt-metrics'), summary, equityCurve);
  renderKlineChart(
    container.querySelector('#bt-kline-chart'),
    priceBars,
    chartOverlays,
    null,
  );
  renderEquityChart(
    container.querySelector('#bt-equity-chart'),
    equityCurve,
    summary.initial_equity,
  );
  renderMonthlyHeatmap(
    container.querySelector('#bt-heatmap-chart'),
    summary.monthly_returns || [],
  );
  renderTradesTable(container.querySelector('#bt-trades-table'), trades, {
    onRowSelect: (trade) => {
      highlightKlineTrade(trade);
      renderTradeFocus(container.querySelector('#bt-trade-focus'), trade);
    },
  });
}

function renderPortfolioResults(container, result) {
  disposeKlineChart();
  disposeMonthlyHeatmap();
  disposePortfolioAttributionCharts();
  const summary = result.summary || {};
  const equityCurve = result.equity_curve || [];
  const weights = result.weights || [];
  const rebalances = result.rebalances || [];
  const attribution = result.attribution || {};
  const stockContributions = attribution.stock_contributions || [];
  const sectorSummary = attribution.sector_summary || [];
  const benchmark = attribution.benchmark || {};
  const costBreakdown = attribution.cost_breakdown || {};
  const context = result.run_context || {};
  const loadedSymbols = context.loaded_symbols || context.symbols || [];
  const latestWeights = weights[weights.length - 1]?.weights || {};

  container.innerHTML = `
    <div class="results-overview">
      <div>
        <div class="results-title">组合回测 · ${loadedSymbols.length} 只股票</div>
        <p class="results-subtitle">
          ${context.start_date || '-'} ~ ${context.end_date || '-'} · ${context.allocation === 'custom' ? '自定义权重' : '等权配置'} · ${formatRebalanceLabel(summary.rebalance_frequency || context.rebalance_frequency)}
        </p>
      </div>
      <div class="results-tags">
        ${loadedSymbols.slice(0, 6).map(symbol => `<span class="result-tag mono">${symbol}</span>`).join('')}
        ${loadedSymbols.length > 6 ? `<span class="result-tag mono">+${loadedSymbols.length - 6}</span>` : ''}
      </div>
    </div>

    <div class="metrics-grid" id="bt-metrics"></div>

    <div class="card">
      <div class="results-card-head">
        <div>
          <div class="card-title">月度收益热力图</div>
          <p class="card-subtitle">年 x 月矩阵视图，便于识别收益分布、回撤月份和风格切换。</p>
        </div>
      </div>
      <div class="chart-container chart-container-heatmap" id="bt-heatmap-chart"></div>
    </div>

    <div class="card">
      <div class="results-card-head">
        <div>
          <div class="card-title">组合权益曲线</div>
          <p class="card-subtitle">组合净值与回撤同步展示，可快速判断再平衡后的净值平滑度。</p>
        </div>
      </div>
      <div class="chart-container" id="bt-equity-chart"></div>
    </div>

    <div class="portfolio-results-grid">
      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">个股贡献拆解</div>
            <p class="card-subtitle">饼图按贡献绝对值分配扇区，悬浮可查看正负贡献、PnL 和期末权重。</p>
          </div>
        </div>
        <div class="chart-container chart-container-attribution" id="bt-stock-attribution-chart"></div>
      </div>

      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">Brinson 行业归因</div>
            <p class="card-subtitle">相对 ${benchmark.label || '内置基准'} 的配置、选股与交互效应；三项合计等于超额收益。</p>
          </div>
        </div>
        <div class="chart-container chart-container-attribution" id="bt-sector-attribution-chart"></div>
      </div>
    </div>

    <div class="portfolio-results-grid">
      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">最新持仓权重</div>
            <p class="card-subtitle">展示最后一个有效调仓节点的目标权重。</p>
          </div>
        </div>
        <div class="portfolio-table-wrapper">
          ${renderWeightsSnapshot(latestWeights)}
        </div>
      </div>

      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">调仓记录</div>
            <p class="card-subtitle">按时间列出每次再平衡的换手率和目标股票数。</p>
          </div>
        </div>
        <div class="portfolio-table-wrapper">
          ${renderRebalanceRows(rebalances)}
        </div>
      </div>
    </div>

    <div class="portfolio-results-grid portfolio-results-grid-wide">
      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">个股贡献明细</div>
            <p class="card-subtitle">按股票展开 PnL、收益贡献与贡献占比，快速定位主要来源与拖累项。</p>
          </div>
        </div>
        <div class="portfolio-table-wrapper">
          ${renderStockContributionRows(stockContributions)}
        </div>
      </div>

      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">成本与超额摘要</div>
            <p class="card-subtitle">同步展示内置基准表现、总成本、换手率和成本效率。</p>
          </div>
        </div>
        ${renderPortfolioAttributionSummary(benchmark, costBreakdown)}
      </div>
    </div>
  `;

  renderMetrics(container.querySelector('#bt-metrics'), summary, equityCurve);
  renderEquityChart(
    container.querySelector('#bt-equity-chart'),
    equityCurve,
    summary.initial_equity,
  );
  renderMonthlyHeatmap(
    container.querySelector('#bt-heatmap-chart'),
    summary.monthly_returns || [],
  );
  renderPortfolioAttributionCharts(
    container.querySelector('#bt-stock-attribution-chart'),
    stockContributions,
    container.querySelector('#bt-sector-attribution-chart'),
    sectorSummary,
  );
}

function renderWeightsSnapshot(weights) {
  const entries = Object.entries(weights || {}).sort((left, right) => right[1] - left[1]);
  if (!entries.length) {
    return '<div class="empty-state"><div class="empty-state-icon">📦</div><p>暂无权重快照</p></div>';
  }

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>股票</th>
          <th data-align="right">权重</th>
        </tr>
      </thead>
      <tbody>
        ${entries.map(([symbol, weight]) => `
          <tr>
            <td class="mono">${symbol}</td>
            <td data-align="right" class="mono">${formatPctAbs(Number(weight) * 100)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderRebalanceRows(rebalances) {
  if (!rebalances.length) {
    return '<div class="empty-state"><div class="empty-state-icon">🔁</div><p>暂无调仓记录</p></div>';
  }

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>日期</th>
          <th data-align="right">换手率</th>
          <th data-align="right">持仓数</th>
        </tr>
      </thead>
      <tbody>
        ${rebalances.map(item => `
          <tr>
            <td>${formatDate(item.date)}</td>
            <td data-align="right" class="mono">${formatPctAbs(item.turnover_pct)}</td>
            <td data-align="right" class="mono">${Object.values(item.weights || {}).filter(value => Number(value) > 0).length}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderStockContributionRows(stockContributions) {
  if (!stockContributions.length) {
    return '<div class="empty-state"><div class="empty-state-icon">🧩</div><p>暂无个股贡献数据</p></div>';
  }

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>股票</th>
          <th>行业</th>
          <th data-align="right">PnL</th>
          <th data-align="right">贡献</th>
          <th data-align="right">贡献占比</th>
          <th data-align="right">期末权重</th>
        </tr>
      </thead>
      <tbody>
        ${stockContributions.map(item => `
          <tr>
            <td>
              <div class="table-primary">${item.name || item.symbol}</div>
              <div class="table-secondary mono">${item.symbol}</div>
            </td>
            <td>${item.sector || '未分类'}</td>
            <td data-align="right" class="mono ${Number(item.pnl) >= 0 ? 'text-profit' : 'text-loss'}">${formatMoney(item.pnl)}</td>
            <td data-align="right" class="mono ${Number(item.contribution_pct) >= 0 ? 'text-profit' : 'text-loss'}">${formatPct(item.contribution_pct)}</td>
            <td data-align="right" class="mono">${formatPct(item.contribution_share_pct)}</td>
            <td data-align="right" class="mono">${formatPctAbs(item.final_weight_pct)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderPortfolioAttributionSummary(benchmark, costBreakdown) {
  const totalCost = Number(costBreakdown.total_cost);
  const excessReturn = Number(benchmark.excess_return_pct);
  return `
    <div class="cost-breakdown-grid">
      <div class="metric-card">
        <span class="metric-label">组合总收益</span>
        <span class="metric-value" style="color:${pctColor(benchmark.portfolio_total_return_pct)}">${formatPct(benchmark.portfolio_total_return_pct)}</span>
      </div>
      <div class="metric-card">
        <span class="metric-label">基准收益</span>
        <span class="metric-value">${formatPct(benchmark.benchmark_total_return_pct)}</span>
      </div>
      <div class="metric-card">
        <span class="metric-label">超额收益</span>
        <span class="metric-value" style="color:${pctColor(excessReturn)}">${formatPct(excessReturn)}</span>
      </div>
      <div class="metric-card">
        <span class="metric-label">总交易成本</span>
        <span class="metric-value" style="color:${totalCost > 0 ? 'var(--loss)' : 'var(--text-primary)'}">${formatMoney(totalCost)}</span>
      </div>
    </div>

    <div class="attribution-summary">
      <div class="attribution-summary-block">
        <div class="attribution-summary-title">成本拆解</div>
        <div class="attribution-summary-row"><span>佣金</span><span class="mono">${formatMoney(costBreakdown.commission)} (${formatPctAbs(costBreakdown.commission_share_pct)})</span></div>
        <div class="attribution-summary-row"><span>印花税</span><span class="mono">${formatMoney(costBreakdown.stamp_tax)} (${formatPctAbs(costBreakdown.stamp_tax_share_pct)})</span></div>
        <div class="attribution-summary-row"><span>滑点</span><span class="mono">${formatMoney(costBreakdown.slippage)} (${formatPctAbs(costBreakdown.slippage_share_pct)})</span></div>
        <div class="attribution-summary-row"><span>成本率</span><span class="mono">${formatPctAbs(costBreakdown.cost_rate_pct)}</span></div>
      </div>

      <div class="attribution-summary-block">
        <div class="attribution-summary-title">换手关系</div>
        <div class="attribution-summary-row"><span>成交额</span><span class="mono">${formatMoney(costBreakdown.traded_notional)}</span></div>
        <div class="attribution-summary-row"><span>累计换手</span><span class="mono">${formatPctAbs(costBreakdown.turnover_pct)}</span></div>
        <div class="attribution-summary-row"><span>成本 / 换手</span><span class="mono">${formatNum(costBreakdown.cost_to_turnover_bps)} bps</span></div>
        <div class="attribution-summary-row"><span>订单数</span><span class="mono">${costBreakdown.orders_count ?? '-'}</span></div>
      </div>

      <div class="attribution-summary-block attribution-summary-note">
        <div class="attribution-summary-title">基准说明</div>
        <p>${benchmark.methodology || '以同股票池内置基准做简化 Brinson 归因。'}</p>
      </div>
    </div>
  `;
}

function renderTradeFocus(container, trade) {
  if (!container) {
    return;
  }
  if (!trade) {
    container.textContent = '未选中交易，点击成交明细中的某一行可高亮对应区间。';
    return;
  }
  container.innerHTML = `
    已高亮交易 <span class="mono">#${trade.trade_index}</span>：
    ${formatDate(trade.entry_time)} → ${formatDate(trade.exit_time)}，
    入场 ${formatMoney(trade.entry_price)}，
    出场 ${formatMoney(trade.exit_price)}，
    盈亏 <span class="${trade.return_pct >= 0 ? 'text-profit' : 'text-loss'} mono">${formatPct(trade.return_pct)}</span>
  `;
}

function renderMetrics(container, summary, equityCurve) {
  const annualizedVolatilityPct = computeAnnualizedVolatilityPct(equityCurve);
  const metrics = [
    { label: '总收益', value: formatPct(summary.total_return_pct), color: pctColor(summary.total_return_pct) },
    { label: '最大回撤', value: summary.max_drawdown_pct == null ? '-' : `-${formatPctAbs(summary.max_drawdown_pct)}`, color: 'var(--loss)' },
    { label: 'Sharpe', value: formatNum(summary.sharpe_ratio), color: sharpeColor(summary.sharpe_ratio) },
    { label: '胜率', value: formatPctAbs(summary.win_rate_pct), color: winRateColor(summary.win_rate_pct) },
    { label: '交易次数', value: summary.trades_count ?? summary.total_trades ?? '-', color: 'var(--text-primary)' },
    { label: '年化波动', value: formatPctAbs(annualizedVolatilityPct), color: volatilityColor(annualizedVolatilityPct) },
  ];

  container.innerHTML = metrics.map(metric => `
    <div class="metric-card">
      <span class="metric-label">${metric.label}</span>
      <span class="metric-value" style="color:${metric.color}">${metric.value}</span>
    </div>
  `).join('');
}

function buildSkeleton(cardCount) {
  return `
    <div class="metrics-grid">
      ${Array(6).fill('<div class="metric-card"><div class="skeleton" style="height:16px;width:60px;margin-bottom:8px"></div><div class="skeleton" style="height:32px;width:100px"></div></div>').join('')}
    </div>
    ${Array(cardCount).fill('<div class="card"><div class="skeleton" style="height:280px"></div></div>').join('')}
  `;
}

function getSelectedStrategyName(container) {
  return container.querySelector('input[name="bt-strategy"]:checked')?.value || strategies[0]?.name || 'sma_cross';
}

function getSelectedSymbols() {
  return pageState.symbolSearch?.getValues().map(symbol => String(symbol).toUpperCase()) || [];
}

function parseValue(value, parser) {
  return parser === 'float' ? Number(value) : parseInt(value, 10);
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatDate(value) {
  if (!value) {
    return '-';
  }
  return String(value).split(' ')[0];
}

function formatPct(value) {
  if (value == null || !Number.isFinite(Number(value))) return '-';
  const sign = Number(value) >= 0 ? '+' : '';
  return `${sign}${Number(value).toFixed(2)}%`;
}

function formatPctAbs(value) {
  if (value == null || !Number.isFinite(Number(value))) return '-';
  return `${Number(value).toFixed(2)}%`;
}

function formatNum(value) {
  if (value == null || !Number.isFinite(Number(value))) return '-';
  return Number(value).toFixed(2);
}

function formatMoney(value) {
  if (value == null || !Number.isFinite(Number(value))) return '-';
  return Number(value).toFixed(2);
}

function formatRebalanceLabel(value) {
  return REBALANCE_OPTIONS.find(item => item.value === value)?.label || value || '-';
}

function pctColor(value) {
  if (value == null) return 'var(--text-primary)';
  return Number(value) >= 0 ? 'var(--profit)' : 'var(--loss)';
}

function sharpeColor(value) {
  if (value == null) return 'var(--text-primary)';
  if (Number(value) >= 1) return 'var(--profit)';
  if (Number(value) >= 0) return 'var(--text-primary)';
  return 'var(--loss)';
}

function winRateColor(value) {
  if (value == null) return 'var(--text-primary)';
  return Number(value) >= 50 ? 'var(--profit)' : 'var(--loss)';
}

function volatilityColor(value) {
  if (value == null) return 'var(--text-primary)';
  if (Number(value) >= 35) return 'var(--loss)';
  if (Number(value) >= 20) return 'var(--warning)';
  return 'var(--profit)';
}

function computeAnnualizedVolatilityPct(equityCurve) {
  if (!equityCurve || equityCurve.length < 3) return null;

  const returns = [];
  for (let index = 1; index < equityCurve.length; index += 1) {
    const prev = Number(equityCurve[index - 1].equity);
    const current = Number(equityCurve[index].equity);
    if (!Number.isFinite(prev) || !Number.isFinite(current) || prev <= 0) {
      continue;
    }
    returns.push(current / prev - 1);
  }

  if (returns.length < 2) return null;
  const mean = returns.reduce((sum, item) => sum + item, 0) / returns.length;
  const variance = returns.reduce((sum, item) => sum + ((item - mean) ** 2), 0) / returns.length;
  return Math.sqrt(variance) * Math.sqrt(252) * 100;
}

function parseSymbolsParam(value) {
  return String(value || '')
    .split(',')
    .map(item => item.trim().toUpperCase())
    .filter(Boolean);
}
