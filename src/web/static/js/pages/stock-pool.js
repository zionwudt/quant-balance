/**
 * 知衡 QuantBalance — 股票池研究页
 */

import { api, ApiError } from '../api.js';
import { toast } from '../components/toast.js';
import { downloadCsv } from '../utils/download.js';

let pageState = createInitialState();

export async function initStockPoolPage(container, routeContext = {}) {
  pageState = createInitialState(routeContext);

  try {
    pageState.meta = await api.getMeta();
  } catch {
    pageState.meta = buildFallbackMeta();
  }

  container.innerHTML = buildHTML(pageState.meta, routeContext.params);
  renderFactorCards(container, pageState.meta);
  bindEvents(container);
  updateFactorDisplays(container);
  await ensureIndustryOptions(container, getPoolDate(container));
  await refreshStockPool(container);

  return {
    exportCurrent() {
      exportRankings();
    },
    focusPrimary() {
      container.querySelector('#sp-pool-date')?.focus();
    },
    dispose() {
      clearTimeout(pageState.refreshTimer);
      pageState.refreshTimer = null;
    },
  };
}

function createInitialState(routeContext = {}) {
  return {
    meta: null,
    navigateTo: routeContext.navigateTo || null,
    rankings: [],
    selectedSymbols: new Set(),
    filteredCount: 0,
    sortKey: 'rank',
    sortAsc: true,
    refreshTimer: null,
    requestSerial: 0,
    industryOptions: [],
    industryOptionsDate: '',
  };
}

function buildFallbackMeta() {
  return {
    factors: [
      { name: 'roe', description: 'ROE（越高越好）', default_direction: 'higher_better' },
      { name: 'pe', description: '市盈率（越低越好）', default_direction: 'lower_better' },
      { name: 'pb', description: '市净率（越低越好）', default_direction: 'lower_better' },
      { name: 'dv_ratio', description: '股息率（越高越好）', default_direction: 'higher_better' },
    ],
    defaults: {
      stock_pool: {
        filters: {
          industries: [],
          exclude_st: false,
          min_listing_days: null,
          min_market_cap: null,
          max_market_cap: null,
          min_pe: null,
          max_pe: null,
        },
      },
      factors_rank: {
        factors: [
          { name: 'roe', weight: 0.4 },
          { name: 'pe', weight: 0.25 },
          { name: 'pb', weight: 0.2 },
          { name: 'dv_ratio', weight: 0.15 },
        ],
        top_n: 50,
      },
    },
  };
}

function buildHTML(meta, params = {}) {
  const defaults = meta.defaults || {};
  const stockPoolDefaults = defaults.stock_pool?.filters || {};
  const factorDefaults = defaults.factors_rank || {};
  const today = params?.pool_date || formatDateInput(new Date());

  return `
    <div class="stock-pool-layout">
      <div class="results-overview">
        <div>
          <div class="results-title">股票池研究</div>
          <p class="results-subtitle">先做历史股票池过滤，再按因子权重实时打分，最后把候选股一键带入组合回测。</p>
        </div>
        <div class="results-tags" id="sp-stats"></div>
      </div>

      <div class="card stock-pool-toolbar expanded">
        <button type="button" class="advanced-panel-toggle" id="sp-filter-toggle" aria-expanded="true">
          <span>筛选器</span>
          <span class="advanced-panel-meta">股票池日期 / 行业 / 市值 / PE / 次新过滤</span>
          <span class="advanced-panel-caret">⌄</span>
        </button>
        <div class="advanced-panel-body stock-pool-filter-body" style="grid-template-rows:1fr">
          <div class="advanced-panel-inner">
            <div class="stock-pool-filter-grid">
              <label class="advanced-field">
                <span class="form-label">股票池日期</span>
                <input class="input" id="sp-pool-date" type="date" value="${today}">
                <span class="field-help">按照该日期的历史股票池和财务快照做筛选。</span>
              </label>

              <label class="advanced-field">
                <span class="form-label">返回前 N 名</span>
                <input class="input mono" id="sp-top-n" type="number" min="5" step="5" value="${factorDefaults.top_n || 50}">
                <span class="field-help">最终排名表默认展示前 50 名。</span>
              </label>

              <label class="advanced-field">
                <span class="form-label">排除 ST</span>
                <label class="toggle-row">
                  <input type="checkbox" id="sp-exclude-st" ${stockPoolDefaults.exclude_st ? 'checked' : ''}>
                  <span>自动过滤 ST / *ST</span>
                </label>
                <span class="field-help">减少极端风险标的干扰。</span>
              </label>

              <label class="advanced-field">
                <span class="form-label">排除近上市天数</span>
                <input class="input mono" id="sp-min-listing-days" type="number" min="0" step="30" value="${stockPoolDefaults.min_listing_days ?? 365}">
                <span class="field-help">例如 365 表示排除上市不足 1 年的次新股。</span>
              </label>

              <label class="advanced-field">
                <span class="form-label">最小市值</span>
                <input class="input mono" id="sp-min-market-cap" type="number" min="0" step="1000" value="${stockPoolDefaults.min_market_cap ?? ''}">
                <span class="field-help">沿用 <span class="mono">daily_basic.total_mv</span> 口径。</span>
              </label>

              <label class="advanced-field">
                <span class="form-label">最大市值</span>
                <input class="input mono" id="sp-max-market-cap" type="number" min="0" step="1000" value="${stockPoolDefaults.max_market_cap ?? ''}">
                <span class="field-help">留空表示不设上限。</span>
              </label>

              <label class="advanced-field">
                <span class="form-label">最小 PE</span>
                <input class="input mono" id="sp-min-pe" type="number" step="1" value="${stockPoolDefaults.min_pe ?? ''}">
                <span class="field-help">用于过滤极低估值异常样本。</span>
              </label>

              <label class="advanced-field">
                <span class="form-label">最大 PE</span>
                <input class="input mono" id="sp-max-pe" type="number" step="1" value="${stockPoolDefaults.max_pe ?? ''}">
                <span class="field-help">用于过滤高估值样本。</span>
              </label>

              <label class="advanced-field stock-pool-industry-field">
                <span class="form-label">行业多选</span>
                <select class="input stock-pool-industry-select" id="sp-industries" multiple size="7"></select>
                <span class="field-help">按住 <span class="mono">Ctrl / Cmd</span> 可多选，空选表示不过滤行业。</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">因子权重</div>
            <p class="card-subtitle">拖动滑杆会实时调整归一化占比；点击方向按钮可反转因子偏好。</p>
          </div>
        </div>
        <div class="factor-grid" id="sp-factors-grid"></div>
      </div>

      <div class="card">
        <div class="results-card-head">
          <div>
            <div class="card-title">排名结果</div>
            <p class="card-subtitle">可排序，可勾选股票进入组合回测；默认会自动勾选前 5 名。</p>
          </div>
        </div>
        <div id="sp-table"></div>
      </div>

      <div class="stock-pool-actions">
        <div class="stock-pool-selection-hint" id="sp-selection-hint"></div>
        <button class="btn btn-primary btn-lg" id="sp-launch">一键发起组合回测</button>
      </div>
    </div>
  `;
}

function renderFactorCards(container, meta) {
  const definitions = new Map((meta.factors || []).map(item => [item.name, item]));
  const factors = meta.defaults?.factors_rank?.factors || [];
  const grid = container.querySelector('#sp-factors-grid');

  grid.innerHTML = factors.map((spec) => {
    const definition = definitions.get(spec.name) || {
      name: spec.name,
      description: spec.name,
      default_direction: 'higher_better',
    };
    const rawWeight = Math.round(Number(spec.weight || 0.1) * 100);
    return `
      <div class="factor-card" data-factor-name="${spec.name}" data-default-direction="${definition.default_direction}">
        <div class="factor-card-head">
          <div>
            <div class="factor-card-title mono">${spec.name}</div>
            <p class="factor-card-desc">${definition.description}</p>
          </div>
          <button type="button" class="btn btn-ghost btn-sm factor-direction-toggle" data-direction="${definition.default_direction}">
            ${directionLabel(definition.default_direction, definition.default_direction)}
          </button>
        </div>
        <div class="factor-slider-row">
          <input class="factor-slider" type="range" min="1" max="100" value="${Math.max(rawWeight, 1)}">
          <div class="factor-slider-meta">
            <span class="factor-slider-raw mono">${Math.max(rawWeight, 1)}</span>
            <span class="factor-slider-share mono">0%</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function bindEvents(container) {
  container.querySelector('#sp-filter-toggle')?.addEventListener('click', () => {
    const button = container.querySelector('#sp-filter-toggle');
    const body = container.querySelector('.stock-pool-filter-body');
    const expanded = button.getAttribute('aria-expanded') !== 'false';
    button.setAttribute('aria-expanded', String(!expanded));
    button.closest('.stock-pool-toolbar')?.classList.toggle('expanded', !expanded);
    body.style.gridTemplateRows = expanded ? '0fr' : '1fr';
  });

  [
    '#sp-pool-date',
    '#sp-top-n',
    '#sp-exclude-st',
    '#sp-min-listing-days',
    '#sp-min-market-cap',
    '#sp-max-market-cap',
    '#sp-min-pe',
    '#sp-max-pe',
    '#sp-industries',
  ].forEach((selector) => {
    container.querySelector(selector)?.addEventListener('change', () => {
      void scheduleRefresh(container);
    });
  });

  container.querySelectorAll('.factor-slider').forEach((slider) => {
    slider.addEventListener('input', () => {
      updateFactorDisplays(container);
      void scheduleRefresh(container);
    });
  });

  container.querySelectorAll('.factor-direction-toggle').forEach((button) => {
    button.addEventListener('click', () => {
      const card = button.closest('.factor-card');
      const defaultDirection = card.dataset.defaultDirection;
      const currentDirection = button.dataset.direction;
      const nextDirection = currentDirection === 'higher_better' ? 'lower_better' : 'higher_better';
      button.dataset.direction = nextDirection;
      button.textContent = directionLabel(defaultDirection, nextDirection);
      void scheduleRefresh(container);
    });
  });

  container.querySelector('#sp-launch')?.addEventListener('click', () => {
    launchPortfolioBacktest();
  });
}

async function scheduleRefresh(container) {
  clearTimeout(pageState.refreshTimer);
  pageState.refreshTimer = setTimeout(() => {
    void refreshStockPool(container);
  }, 180);
}

async function refreshStockPool(container) {
  const table = container.querySelector('#sp-table');
  const stats = container.querySelector('#sp-stats');
  const requestId = pageState.requestSerial + 1;
  pageState.requestSerial = requestId;

  table.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⏳</div><p>正在更新股票池与因子排名...</p></div>';
  stats.innerHTML = '<span class="result-tag">刷新中</span>';

  try {
    const poolDate = getPoolDate(container);
    await ensureIndustryOptions(container, poolDate);
    const filters = collectFilters(container);
    const factors = collectFactorSpecs(container);
    const topN = Number(container.querySelector('#sp-top-n').value || 50);

    const [poolPayload, rankingPayload] = await Promise.all([
      api.filterStockPool({
        pool_date: poolDate,
        filters,
      }),
      api.runFactorRanking({
        pool_date: poolDate,
        pool_filters: filters,
        factors,
        top_n: topN,
      }),
    ]);

    if (requestId !== pageState.requestSerial) {
      return;
    }

    pageState.filteredCount = poolPayload.total_count || 0;
    pageState.rankings = rankingPayload.rankings || [];
    reconcileSelection();
    renderStats(container, rankingPayload);
    renderRankingsTable(container);
    syncSelectionStatus(container);
    window.dispatchEvent(new CustomEvent('qb-status-message', {
      detail: { text: `股票池研究 · 候选 ${pageState.filteredCount} / 已选 ${pageState.selectedSymbols.size}` },
    }));
  } catch (error) {
    const message = error instanceof ApiError ? error.message : '股票池刷新失败';
    toast.error(message);
    table.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠</div><p>${message}</p></div>`;
    stats.innerHTML = '<span class="result-tag">刷新失败</span>';
  }
}

async function ensureIndustryOptions(container, poolDate) {
  if (pageState.industryOptionsDate === poolDate && pageState.industryOptions.length) {
    return;
  }

  try {
    const payload = await api.filterStockPool({ pool_date: poolDate });
    pageState.industryOptionsDate = poolDate;
    pageState.industryOptions = [...new Set(
      (payload.items || [])
        .map(item => String(item.industry || '').trim())
        .filter(Boolean),
    )].sort((left, right) => left.localeCompare(right, 'zh-CN'));
    renderIndustryOptions(container);
  } catch {
    pageState.industryOptions = [];
    renderIndustryOptions(container);
  }
}

function renderIndustryOptions(container) {
  const select = container.querySelector('#sp-industries');
  const current = Array.from(select.selectedOptions).map(option => option.value);
  const selected = new Set(current);

  select.innerHTML = pageState.industryOptions.map(industry => `
    <option value="${industry}"${selected.has(industry) ? ' selected' : ''}>${industry}</option>
  `).join('');
}

function updateFactorDisplays(container) {
  const cards = container.querySelectorAll('.factor-card');
  const rawWeights = Array.from(cards).map(card => Number(card.querySelector('.factor-slider').value || 1));
  const total = rawWeights.reduce((sum, value) => sum + value, 0) || 1;

  cards.forEach((card, index) => {
    const raw = rawWeights[index];
    const share = raw / total * 100;
    card.querySelector('.factor-slider-raw').textContent = String(raw);
    card.querySelector('.factor-slider-share').textContent = `${share.toFixed(1)}%`;
  });
}

function collectFilters(container) {
  return {
    industries: getSelectedValues(container.querySelector('#sp-industries')),
    exclude_st: container.querySelector('#sp-exclude-st').checked,
    min_listing_days: optionalNumber(container.querySelector('#sp-min-listing-days').value),
    min_market_cap: optionalNumber(container.querySelector('#sp-min-market-cap').value),
    max_market_cap: optionalNumber(container.querySelector('#sp-max-market-cap').value),
    min_pe: optionalNumber(container.querySelector('#sp-min-pe').value),
    max_pe: optionalNumber(container.querySelector('#sp-max-pe').value),
  };
}

function collectFactorSpecs(container) {
  return Array.from(container.querySelectorAll('.factor-card')).map((card) => ({
    name: card.dataset.factorName,
    weight: Number(card.querySelector('.factor-slider').value || 1),
    direction: card.querySelector('.factor-direction-toggle').dataset.direction,
  }));
}

function renderStats(container, rankingPayload) {
  const runContext = rankingPayload.run_context || {};
  container.querySelector('#sp-stats').innerHTML = `
    <span class="result-tag">候选池 ${pageState.filteredCount}</span>
    <span class="result-tag">可评分 ${runContext.scored_count ?? pageState.rankings.length}</span>
    <span class="result-tag">已选 ${pageState.selectedSymbols.size}</span>
    <span class="result-tag">跳过财报 ${runContext.skipped_symbols_no_financial?.length || 0}</span>
  `;
}

function reconcileSelection() {
  const available = new Set(pageState.rankings.map(item => item.symbol));
  const next = new Set([...pageState.selectedSymbols].filter(symbol => available.has(symbol)));
  if (!next.size) {
    pageState.rankings.slice(0, 5).forEach(item => next.add(item.symbol));
  }
  pageState.selectedSymbols = next;
}

function renderRankingsTable(container) {
  const host = container.querySelector('#sp-table');
  const rows = getSortedRankings();
  if (!rows.length) {
    host.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔍</div><p>当前过滤条件下没有可显示的股票</p></div>';
    return;
  }

  host.innerHTML = `
    <div class="portfolio-table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th></th>
            <th data-sort="rank">排名</th>
            <th data-sort="symbol">代码</th>
            <th data-sort="name">名称</th>
            <th data-sort="industry">行业</th>
            <th data-sort="listing_days" data-align="right">上市天数</th>
            <th data-sort="total_score" data-align="right">总分</th>
            <th>因子摘要</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(item => `
            <tr data-symbol="${item.symbol}">
              <td><input type="checkbox" class="stock-pool-checkbox" data-symbol="${item.symbol}"${pageState.selectedSymbols.has(item.symbol) ? ' checked' : ''}></td>
              <td class="mono">${item.rank}</td>
              <td class="mono">${item.symbol}</td>
              <td>${item.name || '-'}</td>
              <td>${item.industry || '-'}</td>
              <td data-align="right" class="mono">${item.listing_days ?? '-'}</td>
              <td data-align="right" class="mono">${Number(item.total_score || 0).toFixed(2)}</td>
              <td>${renderFactorSummary(item.factors || {})}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;

  host.querySelectorAll('th[data-sort]').forEach((header) => {
    header.addEventListener('click', () => {
      const key = header.dataset.sort;
      if (pageState.sortKey === key) {
        pageState.sortAsc = !pageState.sortAsc;
      } else {
        pageState.sortKey = key;
        pageState.sortAsc = key !== 'total_score';
      }
      renderRankingsTable(container);
    });
  });

  host.querySelectorAll('.stock-pool-checkbox').forEach((checkbox) => {
    checkbox.addEventListener('change', () => {
      const symbol = checkbox.dataset.symbol;
      if (checkbox.checked) {
        pageState.selectedSymbols.add(symbol);
      } else {
        pageState.selectedSymbols.delete(symbol);
      }
      syncSelectionStatus(container);
    });
  });
}

function renderFactorSummary(factors) {
  const items = Object.entries(factors).slice(0, 4);
  return `
    <div class="factor-summary-list">
      ${items.map(([name, payload]) => `
        <span class="factor-summary-chip">
          <span class="mono">${name}</span>
          <span>${payload.raw_value == null ? '-' : Number(payload.raw_value).toFixed(2)}</span>
        </span>
      `).join('')}
    </div>
  `;
}

function getSortedRankings() {
  const items = [...pageState.rankings];
  const direction = pageState.sortAsc ? 1 : -1;
  return items.sort((left, right) => compareValue(left[pageState.sortKey], right[pageState.sortKey], direction));
}

function compareValue(left, right, direction) {
  const leftValue = left ?? '';
  const rightValue = right ?? '';
  const leftNumber = Number(leftValue);
  const rightNumber = Number(rightValue);
  const isNumber = Number.isFinite(leftNumber) && Number.isFinite(rightNumber);

  let result = 0;
  if (isNumber) {
    result = leftNumber === rightNumber ? 0 : (leftNumber > rightNumber ? 1 : -1);
  } else {
    result = String(leftValue).localeCompare(String(rightValue), 'zh-CN');
  }
  return result * direction;
}

function syncSelectionStatus(container) {
  const selected = [...pageState.selectedSymbols];
  container.querySelector('#sp-selection-hint').textContent = selected.length
    ? `已选择 ${selected.length} 只股票：${selected.slice(0, 6).join('、')}${selected.length > 6 ? '…' : ''}`
    : '尚未选择股票，请先勾选至少 1 只股票。';
  container.querySelector('#sp-launch').disabled = selected.length === 0;
}

function launchPortfolioBacktest() {
  const symbols = [...pageState.selectedSymbols];
  if (!symbols.length) {
    toast.error('请先在表格中选择股票');
    return;
  }
  const params = { symbols: symbols.join(',') };
  if (pageState.navigateTo) {
    void pageState.navigateTo('backtest', params);
    return;
  }
  window.location.hash = `#/backtest?symbols=${encodeURIComponent(params.symbols)}`;
}

function exportRankings() {
  if (!pageState.rankings.length) {
    toast.info('当前没有可导出的股票池结果');
    return;
  }

  const rows = getSortedRankings().map((item) => ({
    rank: item.rank,
    symbol: item.symbol,
    name: item.name,
    industry: item.industry,
    listing_days: item.listing_days,
    total_score: Number(item.total_score || 0).toFixed(2),
    factors: Object.entries(item.factors || {})
      .map(([name, payload]) => `${name}:${Number(payload.raw_value || 0).toFixed(2)}`)
      .join(' | '),
  }));
  downloadCsv(`stock-pool-${Date.now()}.csv`, rows, [
    'rank',
    'symbol',
    'name',
    'industry',
    'listing_days',
    'total_score',
    'factors',
  ]);
  toast.success('股票池结果已导出');
}

function getPoolDate(container) {
  return container.querySelector('#sp-pool-date').value;
}

function getSelectedValues(select) {
  return Array.from(select.selectedOptions).map(option => option.value);
}

function optionalNumber(value) {
  if (value == null || value === '') {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function directionLabel(defaultDirection, currentDirection) {
  const isReversed = defaultDirection !== currentDirection;
  const text = currentDirection === 'higher_better' ? '高分优先' : '低分优先';
  return isReversed ? `${text} · 已反转` : text;
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
