/**
 * 知衡 QuantBalance — 权益曲线图 (ECharts)
 */

let chartInstance = null;

export function renderEquityChart(container, equityCurve, initialEquity) {
  if (!equityCurve || equityCurve.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📈</div><p>运行回测后，权益曲线将在这里展示</p></div>';
    return;
  }
  if (typeof echarts === 'undefined') {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><p>ECharts 未加载，无法渲染图表</p></div>';
    return;
  }

  if (chartInstance) {
    chartInstance.dispose();
  }

  chartInstance = echarts.init(container, null, { renderer: 'canvas' });

  const dates = equityCurve.map(d => d.date.split(' ')[0]);
  const equities = equityCurve.map(d => d.equity);
  const hasBenchmark = equityCurve.some(d => Number.isFinite(Number(d.benchmark_equity)));

  // 计算净值（归一化到1）
  const base = initialEquity || equities[0] || 1;
  const netValues = equities.map(e => +(e / base).toFixed(4));
  const benchmarkNetValues = hasBenchmark
    ? equityCurve.map(d => +(Number(d.benchmark_equity) / base).toFixed(4))
    : [];

  // 计算回撤
  let peak = netValues[0];
  const drawdowns = netValues.map(v => {
    if (v > peak) peak = v;
    return peak > 0 ? +((v - peak) / peak * 100).toFixed(2) : 0;
  });

  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a1a28',
      borderColor: '#2a2a3e',
      textStyle: { color: '#e8e8ed', fontSize: 12, fontFamily: 'var(--font-mono)' },
      formatter(params) {
        const date = params[0].axisValue;
        let html = `<div style="font-weight:600;margin-bottom:4px">${date}</div>`;
        params.forEach(p => {
          if (p.seriesName === '策略净值') {
            html += `<div>净值: ${p.value.toFixed(4)}</div>`;
          } else if (p.seriesName === '基准净值') {
            html += `<div style="color:#94a3b8">基准: ${p.value.toFixed(4)}</div>`;
          } else if (p.seriesName === '回撤') {
            html += `<div style="color:#ef4444">回撤: ${p.value.toFixed(2)}%</div>`;
          }
        });
        return html;
      },
    },
    legend: {
      data: hasBenchmark ? ['策略净值', '基准净值', '回撤'] : ['策略净值', '回撤'],
      textStyle: { color: '#8888a0', fontSize: 12 },
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
        axisLine: { lineStyle: { color: '#1e1e2e' } },
        axisLabel: { color: '#8888a0', fontSize: 11 },
        axisTick: { show: false },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        axisLine: { lineStyle: { color: '#1e1e2e' } },
        axisLabel: { show: false },
        axisTick: { show: false },
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        splitLine: { lineStyle: { color: '#1e1e2e', type: 'dashed' } },
        axisLabel: { color: '#8888a0', fontSize: 11 },
      },
      {
        type: 'value',
        gridIndex: 1,
        splitLine: { lineStyle: { color: '#1e1e2e', type: 'dashed' } },
        axisLabel: { color: '#8888a0', fontSize: 11, formatter: '{value}%' },
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
        borderColor: '#1e1e2e',
        fillerColor: 'rgba(99, 102, 241, 0.18)',
        backgroundColor: '#0f0f18',
        handleStyle: {
          color: '#6366f1',
          borderColor: '#818cf8',
        },
        moveHandleStyle: {
          color: '#6366f1',
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
        lineStyle: { color: '#6366f1', width: 2 },
        itemStyle: { color: '#6366f1' },
        showSymbol: false,
        smooth: false,
      },
      ...(hasBenchmark ? [{
        name: '基准净值',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: benchmarkNetValues,
        lineStyle: { color: '#94a3b8', width: 1.5, type: 'dashed' },
        itemStyle: { color: '#94a3b8' },
        showSymbol: false,
        smooth: false,
      }] : []),
      {
        name: '回撤',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: drawdowns,
        lineStyle: { color: '#ef4444', width: 1 },
        areaStyle: { color: 'rgba(239, 68, 68, 0.08)' },
        itemStyle: { color: '#ef4444' },
        showSymbol: false,
      },
    ],
  };

  chartInstance.setOption(option);

  // 响应式
  const ro = new ResizeObserver(() => chartInstance?.resize());
  ro.observe(container);
}

export function disposeEquityChart() {
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
}
