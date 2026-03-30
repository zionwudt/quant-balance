/**
 * 知衡 QuantBalance — 组合归因图表
 */

import { getVisualPalette } from '../settings.js';

let stockChart = null;
let sectorChart = null;
let stockObserver = null;
let sectorObserver = null;
let chartState = {
  stockContainer: null,
  stockContributions: [],
  sectorContainer: null,
  sectorSummary: [],
};
let visualSyncBound = false;

export function renderPortfolioAttributionCharts(
  stockContainer,
  stockContributions,
  sectorContainer,
  sectorSummary,
) {
  chartState = {
    stockContainer,
    stockContributions: stockContributions || [],
    sectorContainer,
    sectorSummary: sectorSummary || [],
  };
  ensureVisualSync();
  renderStockContributionChart(stockContainer, chartState.stockContributions);
  renderSectorAttributionChart(sectorContainer, chartState.sectorSummary);
}

export function disposePortfolioAttributionCharts() {
  stockObserver?.disconnect();
  stockObserver = null;
  sectorObserver?.disconnect();
  sectorObserver = null;
  stockChart?.dispose();
  stockChart = null;
  sectorChart?.dispose();
  sectorChart = null;
  chartState = {
    stockContainer: null,
    stockContributions: [],
    sectorContainer: null,
    sectorSummary: [],
  };
}

function renderStockContributionChart(container, stockContributions) {
  if (!container) {
    return;
  }
  stockChart?.dispose();
  stockChart = null;
  stockObserver?.disconnect();
  stockObserver = null;

  if (!stockContributions.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🧩</div><p>暂无个股贡献数据</p></div>';
    return;
  }
  if (typeof echarts === 'undefined') {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><p>ECharts 未加载，无法渲染归因图表</p></div>';
    return;
  }

  stockChart = echarts.init(container, null, { renderer: 'canvas' });
  stockChart.setOption(buildStockOption(stockContributions), true);
  stockObserver = new ResizeObserver(() => stockChart?.resize());
  stockObserver.observe(container);
}

function renderSectorAttributionChart(container, sectorSummary) {
  if (!container) {
    return;
  }
  sectorChart?.dispose();
  sectorChart = null;
  sectorObserver?.disconnect();
  sectorObserver = null;

  if (!sectorSummary.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🏭</div><p>暂无行业归因数据</p></div>';
    return;
  }
  if (typeof echarts === 'undefined') {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><p>ECharts 未加载，无法渲染归因图表</p></div>';
    return;
  }

  sectorChart = echarts.init(container, null, { renderer: 'canvas' });
  sectorChart.setOption(buildSectorOption(sectorSummary), true);
  sectorObserver = new ResizeObserver(() => sectorChart?.resize());
  sectorObserver.observe(container);
}

function buildStockOption(stockContributions) {
  const palette = getVisualPalette();
  const items = normalizeStockPieData(stockContributions);
  return {
    backgroundColor: 'transparent',
    color: items.map(item => item.itemStyle.color),
    tooltip: {
      trigger: 'item',
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.textPrimary, fontSize: 12 },
      formatter(params) {
        const raw = params.data.raw;
        return `
          <div style="font-weight:600;margin-bottom:4px">${raw.name || raw.symbol}</div>
          <div>${raw.symbol} · ${raw.sector || '未分类'}</div>
          <div>贡献: ${formatSignedPct(raw.contribution_pct)}</div>
          <div>PnL: ${formatSignedMoney(raw.pnl)}</div>
          <div>期末权重: ${formatPct(raw.final_weight_pct)}</div>
        `;
      },
    },
    legend: {
      bottom: 0,
      left: 'center',
      textStyle: {
        color: palette.chartAxis,
        fontSize: 11,
      },
      formatter(name) {
        return name.length > 10 ? `${name.slice(0, 10)}…` : name;
      },
    },
    series: [
      {
        name: '个股贡献',
        type: 'pie',
        radius: ['36%', '68%'],
        center: ['50%', '42%'],
        minAngle: 4,
        avoidLabelOverlap: true,
        label: {
          color: palette.textSecondary,
          fontSize: 11,
          formatter(params) {
            return params.data.shortLabel;
          },
        },
        labelLine: {
          lineStyle: { color: palette.chartGrid },
        },
        itemStyle: {
          borderColor: palette.bgElevated,
          borderWidth: 2,
        },
        data: items,
      },
    ],
  };
}

function buildSectorOption(sectorSummary) {
  const palette = getVisualPalette();
  const sectors = sectorSummary.map(item => item.sector);
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.textPrimary, fontSize: 12 },
      formatter(params) {
        if (!params.length) {
          return '';
        }
        const item = sectorSummary[params[0].dataIndex];
        const lines = [
          `<div style="font-weight:600;margin-bottom:4px">${item.sector}</div>`,
          `<div>配置效应: ${formatSignedPct(item.allocation_effect_pct)}</div>`,
          `<div>选股效应: ${formatSignedPct(item.selection_effect_pct)}</div>`,
          `<div>交互效应: ${formatSignedPct(item.interaction_effect_pct)}</div>`,
          `<div>主动超额: ${formatSignedPct(item.active_contribution_pct)}</div>`,
          `<div>组合权重 / 基准权重: ${formatPct(item.portfolio_weight_pct)} / ${formatPct(item.benchmark_weight_pct)}</div>`,
        ];
        return lines.join('');
      },
    },
    legend: {
      top: 0,
      textStyle: { color: palette.chartAxis, fontSize: 12 },
      data: ['配置效应', '选股效应', '交互效应'],
    },
    grid: {
      left: 56,
      right: 20,
      top: 36,
      bottom: 56,
    },
    xAxis: {
      type: 'category',
      data: sectors,
      axisLine: { lineStyle: { color: palette.chartGrid } },
      axisLabel: { color: palette.chartAxis, fontSize: 11, interval: 0, rotate: sectors.length > 4 ? 18 : 0 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: palette.chartGrid, type: 'dashed' } },
      axisLabel: {
        color: palette.chartAxis,
        fontSize: 11,
        formatter(value) {
          return `${Number(value).toFixed(1)}%`;
        },
      },
    },
    series: [
      {
        name: '配置效应',
        type: 'bar',
        stack: 'effect',
        data: sectorSummary.map(item => item.allocation_effect_pct),
        itemStyle: { color: palette.benchmark, borderRadius: [4, 4, 0, 0] },
      },
      {
        name: '选股效应',
        type: 'bar',
        stack: 'effect',
        data: sectorSummary.map(item => item.selection_effect_pct),
        itemStyle: { color: palette.accent, borderRadius: [4, 4, 0, 0] },
      },
      {
        name: '交互效应',
        type: 'bar',
        stack: 'effect',
        data: sectorSummary.map(item => item.interaction_effect_pct),
        itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] },
      },
    ],
  };
}

function normalizeStockPieData(stockContributions) {
  const palette = getVisualPalette();
  const sorted = [...stockContributions].sort(
    (left, right) => Math.abs(Number(right.contribution_pct || 0)) - Math.abs(Number(left.contribution_pct || 0)),
  );
  const topItems = sorted.slice(0, 8);
  const restItems = sorted.slice(8);
  const items = topItems.map((item, index) => ({
    value: Math.max(Math.abs(Number(item.contribution_pct || 0)), 0.0001),
    name: item.name || item.symbol,
    shortLabel: item.symbol,
    raw: item,
    itemStyle: {
      color: Number(item.contribution_pct || 0) >= 0
        ? blendHex(palette.profitStrong, index * 0.06)
        : blendHex(palette.lossStrong, index * 0.06),
    },
  }));
  if (restItems.length) {
    const contribution = restItems.reduce((sum, item) => sum + Number(item.contribution_pct || 0), 0);
    const pnl = restItems.reduce((sum, item) => sum + Number(item.pnl || 0), 0);
    items.push({
      value: restItems.reduce((sum, item) => sum + Math.abs(Number(item.contribution_pct || 0)), 0),
      name: `其他 ${restItems.length} 只`,
      shortLabel: '其他',
      raw: {
        symbol: 'OTHER',
        name: `其他 ${restItems.length} 只`,
        sector: '混合',
        contribution_pct: contribution,
        pnl,
        final_weight_pct: restItems.reduce((sum, item) => sum + Number(item.final_weight_pct || 0), 0),
      },
      itemStyle: {
        color: palette.chartGridSubtle,
      },
    });
  }
  return items;
}

function ensureVisualSync() {
  if (visualSyncBound) {
    return;
  }
  visualSyncBound = true;
  window.addEventListener('qb-settings-changed', () => {
    if (stockChart && chartState.stockContainer && chartState.stockContributions.length) {
      stockChart.setOption(buildStockOption(chartState.stockContributions), true);
    }
    if (sectorChart && chartState.sectorContainer && chartState.sectorSummary.length) {
      sectorChart.setOption(buildSectorOption(chartState.sectorSummary), true);
    }
  });
}

function blendHex(hex, amount) {
  if (!hex || !hex.startsWith('#')) {
    return hex;
  }
  const value = hex.slice(1);
  const normalized = value.length === 3
    ? value.split('').map(char => char + char).join('')
    : value;
  const red = Number.parseInt(normalized.slice(0, 2), 16);
  const green = Number.parseInt(normalized.slice(2, 4), 16);
  const blue = Number.parseInt(normalized.slice(4, 6), 16);
  const next = (channel) => Math.min(255, Math.round(channel + (255 - channel) * amount));
  return `rgb(${next(red)}, ${next(green)}, ${next(blue)})`;
}

function formatPct(value) {
  if (!Number.isFinite(Number(value))) {
    return '-';
  }
  return `${Number(value).toFixed(2)}%`;
}

function formatSignedPct(value) {
  if (!Number.isFinite(Number(value))) {
    return '-';
  }
  const numeric = Number(value);
  const sign = numeric >= 0 ? '+' : '';
  return `${sign}${numeric.toFixed(2)}%`;
}

function formatSignedMoney(value) {
  if (!Number.isFinite(Number(value))) {
    return '-';
  }
  const numeric = Number(value);
  const sign = numeric >= 0 ? '+' : '';
  return `${sign}${numeric.toFixed(2)}`;
}
