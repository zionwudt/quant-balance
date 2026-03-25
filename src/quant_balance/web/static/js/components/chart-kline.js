/**
 * 知衡 QuantBalance — K 线图组件 (ECharts)
 */

import { getVisualPalette } from '../settings.js';

let chartInstance = null;
let resizeObserver = null;
let chartState = {
  container: null,
  priceBars: [],
  chartOverlays: {},
  selectedTrade: null,
};
let visualSyncBound = false;

export function renderKlineChart(container, priceBars, chartOverlays = {}, selectedTrade = null) {
  chartState = {
    container,
    priceBars: priceBars || [],
    chartOverlays: chartOverlays || {},
    selectedTrade,
  };
  ensureVisualSync();

  if (!priceBars || priceBars.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🕯</div><p>运行回测后，K 线图会展示价格、成交量和买卖点</p></div>';
    disposeKlineChart();
    return;
  }
  if (typeof echarts === 'undefined') {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><p>ECharts 未加载，无法渲染 K 线图</p></div>';
    disposeKlineChart();
    return;
  }

  if (chartInstance) {
    chartInstance.dispose();
  }
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }

  chartInstance = echarts.init(container, null, { renderer: 'canvas' });
  chartInstance.setOption(buildOption(chartState), true);

  resizeObserver = new ResizeObserver(() => chartInstance?.resize());
  resizeObserver.observe(container);
}

export function highlightKlineTrade(trade) {
  chartState.selectedTrade = trade || null;
  if (!chartInstance || !chartState.priceBars.length) {
    return;
  }
  chartInstance.setOption(buildOption(chartState), true);
}

export function disposeKlineChart() {
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
  chartState = {
    container: null,
    priceBars: [],
    chartOverlays: {},
    selectedTrade: null,
  };
}

function buildOption(state) {
  const palette = getVisualPalette();
  const priceBars = state.priceBars || [];
  const chartOverlays = state.chartOverlays || {};
  const selectedTrade = state.selectedTrade || null;
  const dates = priceBars.map(item => item.date);
  const candleData = priceBars.map(item => [
    toNumber(item.open),
    toNumber(item.close),
    toNumber(item.low),
    toNumber(item.high),
  ]);
  const volumeData = priceBars.map(item => toNumber(item.volume));
  const lineSeries = (chartOverlays.line_series || []).map(item => ({
    name: item.name,
    type: 'line',
    xAxisIndex: 0,
    yAxisIndex: 0,
    data: item.values || [],
    symbol: 'none',
    smooth: false,
    connectNulls: false,
    animation: false,
    lineStyle: {
      width: 1.6,
      color: item.color || palette.accent,
      type: item.style === 'dashed' ? 'dashed' : 'solid',
    },
    emphasis: { focus: 'series' },
  }));
  const tradeMarkers = chartOverlays.trade_markers || [];
  const buyMarkers = tradeMarkers
    .filter(item => item.side === 'buy')
    .map(item => ({
      value: [item.date, toNumber(item.price)],
      trade_index: item.trade_index,
      label: item.label,
    }));
  const sellMarkers = tradeMarkers
    .filter(item => item.side === 'sell')
    .map(item => ({
      value: [item.date, toNumber(item.price)],
      trade_index: item.trade_index,
      label: item.label,
    }));
  const highlightedArea = buildHighlightedArea(selectedTrade);

  return {
    animation: false,
    backgroundColor: 'transparent',
    legend: {
      top: 0,
      right: 0,
      textStyle: { color: palette.chartAxis, fontSize: 12 },
      data: ['K线', ...lineSeries.map(item => item.name), '买点', '卖点', '成交量'],
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: { backgroundColor: palette.focusBg },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: palette.tooltipBg,
      borderColor: palette.tooltipBorder,
      textStyle: { color: palette.textPrimary, fontSize: 12, fontFamily: 'var(--font-mono)' },
      formatter(params) {
        const items = Array.isArray(params) ? params : [params];
        const candle = items.find(item => item.seriesType === 'candlestick');
        const volume = items.find(item => item.seriesName === '成交量');
        const overlays = items.filter(item => item.seriesType === 'line');
        const marker = items.find(item => item.seriesType === 'scatter');
        const date = items[0]?.axisValue || '-';

        let html = `<div style="font-weight:600;margin-bottom:4px">${date}</div>`;
        if (candle?.data) {
          const [open, close, low, high] = candle.data;
          html += `<div>开 ${formatNum(open)} 高 ${formatNum(high)} 低 ${formatNum(low)} 收 ${formatNum(close)}</div>`;
        }
        if (volume?.data != null) {
          html += `<div>量 ${formatVolume(volume.data)}</div>`;
        }
        overlays.forEach(item => {
          html += `<div style="color:${item.color || palette.benchmark}">${item.seriesName}: ${formatNum(item.data)}</div>`;
        });
        if (marker?.data?.label) {
          html += `<div>${marker.data.label}: ${formatNum(marker.data.value?.[1])}</div>`;
        }
        return html;
      },
    },
    grid: [
      { left: 56, right: 18, top: 36, height: '58%' },
      { left: 56, right: 18, top: '74%', height: '15%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: palette.chartGrid } },
        axisLabel: { color: palette.chartAxis, fontSize: 11 },
        axisTick: { show: false },
        splitLine: { show: false },
        min: 'dataMin',
        max: 'dataMax',
      },
      {
        type: 'category',
        gridIndex: 1,
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: palette.chartGrid } },
        axisLabel: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        min: 'dataMin',
        max: 'dataMax',
      },
    ],
    yAxis: [
      {
        scale: true,
        splitNumber: 5,
        axisLine: { show: false },
        axisLabel: { color: palette.chartAxis, fontSize: 11 },
        splitLine: { lineStyle: { color: palette.chartGrid, type: 'dashed' } },
      },
      {
        gridIndex: 1,
        splitNumber: 2,
        axisLine: { show: false },
        axisLabel: { color: palette.chartAxis, fontSize: 11, formatter: formatVolume },
        splitLine: { lineStyle: { color: palette.chartGridSubtle } },
      },
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: 0,
        end: 100,
        moveOnMouseMove: true,
        zoomOnMouseWheel: true,
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
      },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: candleData,
        itemStyle: {
          color: palette.profit,
          color0: palette.loss,
          borderColor: palette.profit,
          borderColor0: palette.loss,
        },
        markArea: highlightedArea,
      },
      ...lineSeries,
      {
        name: '买点',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: buyMarkers,
        symbol: 'triangle',
        symbolRotate: 0,
        symbolSize: 12,
        z: 10,
        itemStyle: { color: palette.profit },
        label: {
          show: true,
          position: 'top',
          formatter: (params) => params.data?.label || '',
          color: palette.profitSoft,
          fontSize: 10,
        },
      },
      {
        name: '卖点',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: sellMarkers,
        symbol: 'triangle',
        symbolRotate: 180,
        symbolSize: 12,
        z: 10,
        itemStyle: { color: palette.loss },
        label: {
          show: true,
          position: 'bottom',
          formatter: (params) => params.data?.label || '',
          color: palette.lossSoft,
          fontSize: 10,
        },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumeData,
        barMaxWidth: 10,
        itemStyle: {
          color(params) {
            const index = params.dataIndex;
            const bar = priceBars[index] || {};
            return toNumber(bar.close) >= toNumber(bar.open)
              ? hexToRgba(palette.volumeUp, 0.7)
              : hexToRgba(palette.volumeDown, 0.72);
          },
        },
      },
    ],
  };
}

function buildHighlightedArea(trade) {
  if (!trade?.entry_time || !trade?.exit_time) {
    return undefined;
  }
  const entryDate = String(trade.entry_time).split(' ')[0];
  const exitDate = String(trade.exit_time).split(' ')[0];
  return {
    silent: true,
    itemStyle: {
      color: hexToRgba(getVisualPalette().accent, 0.08),
      borderColor: hexToRgba(getVisualPalette().accent, 0.45),
      borderWidth: 1,
    },
    data: [[
      {
        name: `交易 ${trade.trade_index || ''}`,
        xAxis: entryDate,
      },
      {
        xAxis: exitDate,
      },
    ]],
  };
}

function toNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatNum(value) {
  if (!Number.isFinite(Number(value))) {
    return '-';
  }
  return Number(value).toFixed(2);
}

function formatVolume(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  if (Math.abs(numeric) >= 100000000) {
    return `${(numeric / 100000000).toFixed(2)}亿`;
  }
  if (Math.abs(numeric) >= 10000) {
    return `${(numeric / 10000).toFixed(2)}万`;
  }
  return numeric.toFixed(0);
}

function ensureVisualSync() {
  if (visualSyncBound) {
    return;
  }
  visualSyncBound = true;
  window.addEventListener('qb-settings-changed', () => {
    if (chartInstance && chartState.priceBars.length) {
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
