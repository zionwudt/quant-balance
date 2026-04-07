/**
 * 知衡 QuantBalance — 权益曲线图 (ECharts)
 */

import { getVisualPalette } from '../settings.js';

let chartInstance = null;
let resizeObserver = null;
let chartState = {
  container: null,
  mode: 'single',
  equityCurve: [],
  curves: [],
  initialEquity: null,
};
let visualSyncBound = false;

export function renderEquityChart(container, equityCurve, initialEquity) {
  chartState = {
    container,
    mode: 'single',
    equityCurve: equityCurve || [],
    curves: [],
    initialEquity,
  };
  ensureVisualSync();

  if (!equityCurve || equityCurve.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📈</div><p>运行回测后，权益曲线将在这里展示</p></div>';
    disposeEquityChart();
    return;
  }
  if (typeof echarts === 'undefined') {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><p>ECharts 未加载，无法渲染图表</p></div>';
    disposeEquityChart();
    return;
  }

  if (chartInstance) {
    chartInstance.dispose();
  }
  resizeObserver?.disconnect();

  chartInstance = echarts.init(container, null, { renderer: 'canvas' });
  chartInstance.setOption(buildOption(chartState), true);

  resizeObserver = new ResizeObserver(() => chartInstance?.resize());
  resizeObserver.observe(container);
}

export function renderMultiEquityChart(container, curves = []) {
  const normalizedCurves = Array.isArray(curves) ? curves.filter(item => Array.isArray(item?.equity_curve) && item.equity_curve.length) : [];
  chartState = {
    container,
    mode: 'multi',
    equityCurve: [],
    curves: normalizedCurves,
    initialEquity: null,
  };
  ensureVisualSync();

  if (!normalizedCurves.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📉</div><p>选择 2-3 条回测记录后，对比权益曲线会显示在这里</p></div>';
    disposeEquityChart();
    return;
  }
  if (typeof echarts === 'undefined') {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><p>ECharts 未加载，无法渲染图表</p></div>';
    disposeEquityChart();
    return;
  }

  if (chartInstance) {
    chartInstance.dispose();
  }
  resizeObserver?.disconnect();

  chartInstance = echarts.init(container, null, { renderer: 'canvas' });
  chartInstance.setOption(buildOption(chartState), true);

  resizeObserver = new ResizeObserver(() => chartInstance?.resize());
  resizeObserver.observe(container);
}

export function disposeEquityChart() {
  resizeObserver?.disconnect();
  resizeObserver = null;
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
  chartState = {
    container: null,
    mode: 'single',
    equityCurve: [],
    curves: [],
    initialEquity: null,
  };
}

function buildOption(state) {
  if (state.mode === 'multi') {
    return buildMultiOption(state);
  }
  return buildSingleOption(state);
}

function buildSingleOption(state) {
  const palette = getVisualPalette();
  const dates = state.equityCurve.map(item => item.label || item.date.split(' ')[0]);
  const equities = state.equityCurve.map(item => item.equity);
  const hasBenchmark = state.equityCurve.some(item => Number.isFinite(Number(item.benchmark_equity)));

  const base = state.initialEquity || equities[0] || 1;
  const netValues = equities.map(value => +(value / base).toFixed(4));
  const benchmarkNetValues = hasBenchmark
    ? state.equityCurve.map(item => +(Number(item.benchmark_equity) / base).toFixed(4))
    : [];

  let peak = netValues[0];
  const drawdowns = netValues.map((value) => {
    if (value > peak) peak = value;
    return peak > 0 ? +((value - peak) / peak * 100).toFixed(2) : 0;
  });

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.textPrimary, fontSize: 12, fontFamily: 'var(--font-mono)' },
      formatter(params) {
        const date = params[0].axisValue;
        let html = `<div style="font-weight:600;margin-bottom:4px">${date}</div>`;
        params.forEach(item => {
          if (item.seriesName === '策略净值') {
            html += `<div>净值: ${item.value.toFixed(4)}</div>`;
          } else if (item.seriesName === '基准净值') {
            html += `<div style="color:${palette.benchmark}">基准: ${item.value.toFixed(4)}</div>`;
          } else if (item.seriesName === '回撤') {
            html += `<div style="color:${palette.loss}">回撤: ${item.value.toFixed(2)}%</div>`;
          }
        });
        return html;
      },
    },
    legend: {
      data: hasBenchmark ? ['策略净值', '基准净值', '回撤'] : ['策略净值', '回撤'],
      textStyle: { color: palette.chartAxis, fontSize: 12 },
      top: 0,
      right: 0,
    },
    grid: [
      { left: 50, right: 20, top: 30, height: '55%' },
      { left: 50, right: 20, top: '72%', height: '20%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        gridIndex: 0,
        axisLine: { lineStyle: { color: palette.chartGrid } },
        axisLabel: { color: palette.chartAxis, fontSize: 11 },
        axisTick: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        axisLine: { lineStyle: { color: palette.chartGrid } },
        axisLabel: { show: false },
        axisTick: { show: false },
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        splitLine: { lineStyle: { color: palette.chartGrid, type: 'dashed' } },
        axisLabel: { color: palette.chartAxis, fontSize: 11 },
      },
      {
        type: 'value',
        gridIndex: 1,
        splitLine: { lineStyle: { color: palette.chartGrid, type: 'dashed' } },
        axisLabel: { color: palette.chartAxis, fontSize: 11, formatter: '{value}%' },
      },
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: 0,
        end: 100,
      },
      {
        type: 'slider',
        xAxisIndex: [0, 1],
        bottom: 0,
        height: 18,
        borderColor: palette.chartGrid,
        fillerColor: palette.accentSoft,
        backgroundColor: palette.bgInput,
        handleStyle: {
          color: palette.accent,
          borderColor: palette.accent,
        },
        moveHandleStyle: {
          color: palette.accent,
        },
      },
    ],
    series: [
      {
        name: '策略净值',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: netValues,
        lineStyle: { color: palette.accent, width: 2 },
        itemStyle: { color: palette.accent },
        showSymbol: false,
        smooth: false,
      },
      ...(hasBenchmark ? [{
        name: '基准净值',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: benchmarkNetValues,
        lineStyle: { color: palette.benchmark, width: 1.5, type: 'dashed' },
        itemStyle: { color: palette.benchmark },
        showSymbol: false,
        smooth: false,
      }] : []),
      {
        name: '回撤',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: drawdowns,
        lineStyle: { color: palette.loss, width: 1 },
        areaStyle: { color: hexToRgba(palette.loss, 0.1) },
        itemStyle: { color: palette.loss },
        showSymbol: false,
      },
    ],
  };
}

function buildMultiOption(state) {
  const palette = getVisualPalette();
  const paletteSeries = [
    palette.accent,
    palette.benchmark,
    palette.profit,
    '#f59e0b',
    '#60a5fa',
  ];
  const baseDates = state.curves[0]?.equity_curve?.map(item => item.label || item.date.split(' ')[0]) || [];
  const series = state.curves.map((curve, index) => {
    const equityCurve = curve.equity_curve || [];
    const base = Number(equityCurve[0]?.equity || 1);
    return {
      name: curve.label || `策略 ${index + 1}`,
      type: 'line',
      data: equityCurve.map(item => {
        const value = Number(item.equity);
        if (!Number.isFinite(value) || base <= 0) {
          return null;
        }
        return +(value / base).toFixed(4);
      }),
      symbol: 'none',
      smooth: false,
      lineStyle: {
        width: 2,
        color: paletteSeries[index % paletteSeries.length],
      },
      itemStyle: {
        color: paletteSeries[index % paletteSeries.length],
      },
    };
  });

  return {
    animation: false,
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.textPrimary, fontSize: 12, fontFamily: 'var(--font-mono)' },
      formatter(params) {
        const items = Array.isArray(params) ? params : [params];
        let html = `<div style="font-weight:600;margin-bottom:4px">${items[0]?.axisValue || '-'}</div>`;
        items.forEach(item => {
          html += `<div style="color:${item.color}">${item.seriesName}: ${Number(item.value).toFixed(4)}</div>`;
        });
        return html;
      },
    },
    legend: {
      data: series.map(item => item.name),
      textStyle: { color: palette.chartAxis, fontSize: 12 },
      top: 0,
      right: 0,
    },
    grid: {
      left: 50,
      right: 20,
      top: 36,
      bottom: 48,
    },
    xAxis: {
      type: 'category',
      data: baseDates,
      axisLine: { lineStyle: { color: palette.chartGrid } },
      axisLabel: { color: palette.chartAxis, fontSize: 11 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: palette.chartGrid, type: 'dashed' } },
      axisLabel: { color: palette.chartAxis, fontSize: 11 },
    },
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
      },
      {
        type: 'slider',
        bottom: 0,
        height: 18,
        borderColor: palette.chartGrid,
        fillerColor: palette.accentSoft,
        backgroundColor: palette.bgInput,
        handleStyle: {
          color: palette.accent,
          borderColor: palette.accent,
        },
      },
    ],
    series,
  };
}

function ensureVisualSync() {
  if (visualSyncBound) {
    return;
  }
  visualSyncBound = true;
  window.addEventListener('qb-settings-changed', () => {
    if (chartInstance && chartState.equityCurve.length) {
      chartInstance.setOption(buildOption(chartState), true);
    }
  });
}

function hexToRgba(hex, alpha) {
  if (!hex.startsWith('#')) {
    return hex;
  }
  const value = hex.slice(1);
  const normalized = value.length === 3
    ? value.split('').map(char => char + char).join('')
    : value;
  const red = Number.parseInt(normalized.slice(0, 2), 16);
  const green = Number.parseInt(normalized.slice(2, 4), 16);
  const blue = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}
