/**
 * 知衡 QuantBalance — 月度收益热力图
 */

let chartInstance = null;
let resizeObserver = null;

const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

export function renderMonthlyHeatmap(container, monthlyReturns) {
  if (!monthlyReturns || monthlyReturns.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🗓</div><p>暂无可用于绘制月度热力图的数据</p></div>';
    disposeMonthlyHeatmap();
    return;
  }
  if (typeof echarts === 'undefined') {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><p>ECharts 未加载，无法渲染热力图</p></div>';
    disposeMonthlyHeatmap();
    return;
  }

  disposeMonthlyHeatmap();

  const { years, values } = normalizeHeatmapData(monthlyReturns);
  chartInstance = echarts.init(container, null, { renderer: 'canvas' });
  chartInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      position: 'top',
      backgroundColor: '#151827',
      borderColor: '#243041',
      textStyle: { color: '#e5e7eb', fontSize: 12 },
      formatter(params) {
        const [monthIndex, yearIndex, returnPct] = params.data;
        const year = years[yearIndex];
        const month = MONTH_LABELS[monthIndex];
        return `<div style="font-weight:600;margin-bottom:4px">${year}年 ${month}</div><div>月收益: ${formatReturnPct(returnPct)}</div>`;
      },
    },
    grid: {
      left: 64,
      right: 20,
      top: 16,
      bottom: 48,
    },
    xAxis: {
      type: 'category',
      data: MONTH_LABELS,
      splitArea: { show: true },
      axisLine: { lineStyle: { color: '#223045' } },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: years,
      splitArea: { show: true },
      axisLine: { lineStyle: { color: '#223045' } },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
    },
    visualMap: {
      min: -5,
      max: 5,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 6,
      text: ['+5%', '-5%'],
      textStyle: { color: '#94a3b8', fontSize: 11 },
      inRange: {
        color: ['#7f1d1d', '#fca5a5', '#f8fafc', '#86efac', '#14532d'],
      },
    },
    series: [
      {
        name: '月收益',
        type: 'heatmap',
        data: values,
        label: {
          show: true,
          color: '#0f172a',
          fontSize: 11,
          formatter(params) {
            return `${Number(params.data[2]).toFixed(1)}%`;
          },
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(15, 23, 42, 0.35)',
          },
        },
      },
    ],
  });

  resizeObserver = new ResizeObserver(() => chartInstance?.resize());
  resizeObserver.observe(container);
}

export function disposeMonthlyHeatmap() {
  resizeObserver?.disconnect();
  resizeObserver = null;
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
}

function normalizeHeatmapData(monthlyReturns) {
  const map = new Map();
  const years = [];

  monthlyReturns.forEach((item) => {
    const monthText = String(item.month || '');
    const returnPct = Number(item.return_pct);
    if (!monthText || !Number.isFinite(returnPct)) {
      return;
    }

    const [yearText, monthValue] = monthText.split('-');
    const year = Number(yearText);
    const monthIndex = Number(monthValue) - 1;
    if (!Number.isFinite(year) || monthIndex < 0 || monthIndex > 11) {
      return;
    }

    if (!map.has(year)) {
      map.set(year, Array(12).fill(null));
      years.push(year);
    }
    map.get(year)[monthIndex] = returnPct;
  });

  years.sort((left, right) => right - left);
  const values = [];
  years.forEach((year, yearIndex) => {
    map.get(year).forEach((returnPct, monthIndex) => {
      if (returnPct == null) {
        return;
      }
      values.push([monthIndex, yearIndex, Number(returnPct.toFixed(2))]);
    });
  });

  return { years, values };
}

function formatReturnPct(value) {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${Number(value).toFixed(2)}%`;
}
