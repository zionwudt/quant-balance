/**
 * 知衡 QuantBalance — 模拟盘页面
 */

import { toast } from '../components/toast.js';
import { renderEquityChart, disposeEquityChart } from '../components/chart-equity.js';
import {
  buildPaperReport,
  getPaperState,
  pausePaperTrading,
  resumePaperTrading,
  stopPaperTrading,
  subscribePaperState,
  summarizePaperState,
  tickPaperTrading,
} from '../data/paper-store.js';
import { downloadJson } from '../utils/download.js';

let refreshTimer = null;

export async function initPaperTradingPage(container) {
  container.innerHTML = buildHTML();

  const render = () => {
    const summary = summarizePaperState(getPaperState());
    renderState(container, summary);
  };

  const unsubscribe = subscribePaperState(() => {
    render();
  });

  bindEvents(container);
  render();
  refreshTimer = window.setInterval(() => {
    tickPaperTrading();
  }, 3000);

  return {
    exportCurrent() {
      exportPaperReport();
    },
    focusPrimary() {
      container.querySelector('#paper-toggle')?.focus();
    },
    dispose() {
      window.clearInterval(refreshTimer);
      refreshTimer = null;
      unsubscribe();
      disposeEquityChart();
    },
  };
}

function buildHTML() {
  return `
    <div class="paper-layout">
      <div class="results-overview">
        <div>
          <div class="results-title">模拟盘</div>
          <p class="results-subtitle">本地持仓、权益和成交日志会持续刷新；信号中心可直接把候选信号送入模拟盘执行。</p>
        </div>
        <div class="results-tags">
          <span class="result-tag" id="paper-status-tag">运行中</span>
          <span class="result-tag mono" id="paper-updated-tag">--</span>
        </div>
      </div>

      <div class="card paper-account-bar" id="paper-account-bar"></div>

      <div class="paper-toolbar">
        <button class="btn btn-secondary" id="paper-toggle">暂停模拟盘</button>
        <button class="btn btn-danger" id="paper-stop">停止并冻结</button>
        <button class="btn btn-primary" id="paper-report">生成报告</button>
      </div>

      <div class="paper-grid">
        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">当前持仓</div>
              <p class="card-subtitle">左侧列表展示持仓市值、成本价和浮动盈亏，方便跟踪模拟盘风险暴露。</p>
            </div>
          </div>
          <div class="paper-holdings-list" id="paper-holdings"></div>
        </div>

        <div class="paper-main-column">
          <div class="card">
            <div class="results-card-head">
              <div>
                <div class="card-title">权益曲线</div>
                <p class="card-subtitle">刷新频率约 3 秒；暂停后会停止更新，停止后保留最终快照供导出报告使用。</p>
              </div>
            </div>
            <div class="chart-container" id="paper-equity-chart"></div>
          </div>

          <div class="card">
            <div class="results-card-head">
              <div>
                <div class="card-title">最近成交</div>
                <p class="card-subtitle">记录来自信号中心或手工调仓的最近交易行为。</p>
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
  container.querySelector('#paper-toggle')?.addEventListener('click', () => {
    const state = getPaperState();
    if (state.status === 'stopped') {
      toast.info('模拟盘已停止，可直接导出最终报告');
      return;
    }

    if (state.status === 'running') {
      pausePaperTrading();
      toast.info('模拟盘已暂停');
      return;
    }
    resumePaperTrading();
    toast.success('模拟盘已恢复运行');
  });

  container.querySelector('#paper-stop')?.addEventListener('click', () => {
    const state = getPaperState();
    if (state.status === 'stopped') {
      toast.info('模拟盘已经处于停止状态');
      return;
    }
    stopPaperTrading();
    toast.info('模拟盘已停止，当前快照已冻结');
  });

  container.querySelector('#paper-report')?.addEventListener('click', () => {
    exportPaperReport();
  });
}

function renderState(container, summary) {
  const statusLabel = statusText(summary.status);
  container.querySelector('#paper-status-tag').textContent = statusLabel;
  container.querySelector('#paper-updated-tag').textContent = `更新于 ${formatDateTime(summary.last_tick_at)}`;
  container.querySelector('#paper-toggle').textContent = summary.status === 'running' ? '暂停模拟盘' : '继续运行';
  container.querySelector('#paper-toggle').disabled = summary.status === 'stopped';
  container.querySelector('#paper-stop').disabled = summary.status === 'stopped';

  container.querySelector('#paper-account-bar').innerHTML = `
    <div class="paper-account-item">
      <span class="paper-account-label">账户权益</span>
      <span class="paper-account-value mono">${formatMoney(summary.equity)}</span>
    </div>
    <div class="paper-account-item">
      <span class="paper-account-label">今日盈亏</span>
      <span class="paper-account-value mono ${summary.today_pnl >= 0 ? 'text-profit' : 'text-loss'}">${formatSignedMoney(summary.today_pnl)}</span>
    </div>
    <div class="paper-account-item">
      <span class="paper-account-label">可用现金</span>
      <span class="paper-account-value mono">${formatMoney(summary.cash)}</span>
    </div>
    <div class="paper-account-item">
      <span class="paper-account-label">仓位暴露</span>
      <span class="paper-account-value mono">${summary.exposure_pct.toFixed(2)}%</span>
    </div>
  `;

  const holdingsHost = container.querySelector('#paper-holdings');
  if (!summary.holdings.length) {
    holdingsHost.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📦</div><p>当前没有持仓，可从信号中心直接加入模拟盘</p></div>';
  } else {
    holdingsHost.innerHTML = summary.holdings.map((item) => `
      <div class="paper-holding-card">
        <div class="paper-holding-head">
          <div>
            <div class="paper-holding-title">${item.name}</div>
            <div class="paper-holding-meta mono">${item.symbol} · ${item.strategy || '-'}</div>
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
            <div class="mono ${item.pnl >= 0 ? 'text-profit' : 'text-loss'}">${formatSignedMoney(item.pnl)} / ${formatSignedPct(item.pnl_pct)}</div>
          </div>
        </div>
      </div>
    `).join('');
  }

  container.querySelector('#paper-trade-log').innerHTML = renderTradeTable(summary.trade_log.slice(0, 16));
  renderEquityChart(
    container.querySelector('#paper-equity-chart'),
    summary.equity_curve.map((item) => ({
      date: item.date,
      label: formatTimeAxis(item.date),
      equity: item.equity,
    })),
    summary.equity_curve[0]?.equity || summary.equity,
  );
  window.dispatchEvent(new CustomEvent('qb-status-message', {
    detail: { text: `模拟盘 · ${statusLabel}` },
  }));
}

function renderTradeTable(trades) {
  if (!trades.length) {
    return '<div class="empty-state"><div class="empty-state-icon">🧾</div><p>还没有新的交易记录</p></div>';
  }

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>时间</th>
          <th>动作</th>
          <th>标的</th>
          <th data-align="right">价格</th>
          <th data-align="right">数量</th>
          <th>原因</th>
        </tr>
      </thead>
      <tbody>
        ${trades.map((trade) => `
          <tr data-pnl="${trade.side === 'buy' ? 'profit' : 'loss'}">
            <td class="mono">${formatDateTime(trade.timestamp)}</td>
            <td>${trade.side === 'buy' ? '买入' : '卖出'}</td>
            <td>${trade.name} <span class="mono text-muted">${trade.symbol}</span></td>
            <td data-align="right" class="mono">${formatPrice(trade.price)}</td>
            <td data-align="right" class="mono">${trade.qty}</td>
            <td>${trade.reason || '-'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function exportPaperReport() {
  const report = buildPaperReport();
  downloadJson(`paper-trading-report-${Date.now()}.json`, report);
  toast.success('模拟盘报告已导出');
}

function statusText(status) {
  if (status === 'paused') {
    return '已暂停';
  }
  if (status === 'stopped') {
    return '已停止';
  }
  return '运行中';
}

function formatMoney(value) {
  return `¥${Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatSignedMoney(value) {
  const number = Number(value || 0);
  const prefix = number >= 0 ? '+' : '-';
  return `${prefix}${formatMoney(Math.abs(number))}`;
}

function formatPrice(value) {
  return Number(value || 0).toFixed(3);
}

function formatSignedPct(value) {
  const number = Number(value || 0);
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}%`;
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

function formatTimeAxis(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '--';
  }
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
