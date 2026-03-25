/**
 * 知衡 QuantBalance — 成交明细表组件
 */

export function renderTradesTable(container, trades, options = {}) {
  if (!trades || trades.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📋</div><p>运行回测后，成交明细将在这里展示</p></div>';
    return;
  }

  const { onRowSelect = null } = options;
  const normalizedTrades = trades.map((trade, index) => ({
    ...trade,
    trade_index: trade.trade_index ?? index + 1,
  }));

  let sortKey = null;
  let sortAsc = true;
  let selectedTradeIndex = null;

  function render(data) {
    container.innerHTML = `
      <div class="trades-table-wrapper">
        <table class="data-table" id="trades-table">
          <thead>
            <tr>
              <th data-sort="trade_index">#</th>
              <th data-sort="entry_time">入场日期</th>
              <th data-sort="exit_time">出场日期</th>
              <th data-sort="entry_price" data-align="right">入场价</th>
              <th data-sort="exit_price" data-align="right">出场价</th>
              <th data-sort="size" data-align="right">数量</th>
              <th data-sort="return_pct" data-align="right">盈亏%</th>
              <th data-sort="pnl" data-align="right">盈亏额</th>
              <th data-sort="duration">持仓时长</th>
            </tr>
          </thead>
          <tbody>
            ${data.map((trade) => {
              const pnlType = trade.return_pct >= 0 ? 'profit' : 'loss';
              const pnlClass = trade.return_pct >= 0 ? 'text-profit' : 'text-loss';
              const selectedClass = trade.trade_index === selectedTradeIndex ? ' is-selected' : '';
              return `
                <tr class="${selectedClass.trim()}" data-pnl="${pnlType}" data-trade-index="${trade.trade_index}">
                  <td>${trade.trade_index}</td>
                  <td>${formatDate(trade.entry_time)}</td>
                  <td>${formatDate(trade.exit_time)}</td>
                  <td data-align="right" class="mono">${formatNum(trade.entry_price)}</td>
                  <td data-align="right" class="mono">${formatNum(trade.exit_price)}</td>
                  <td data-align="right" class="mono">${trade.size}</td>
                  <td data-align="right" class="mono ${pnlClass}">${formatPct(trade.return_pct)}</td>
                  <td data-align="right" class="mono ${pnlClass}">${formatMoney(trade.pnl)}</td>
                  <td>${trade.duration}</td>
                </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;

    container.querySelectorAll('th[data-sort]').forEach(header => {
      header.addEventListener('click', () => {
        const key = header.dataset.sort;
        if (sortKey === key) {
          sortAsc = !sortAsc;
        } else {
          sortKey = key;
          sortAsc = true;
        }
        render(sortTrades());
      });
    });

    container.querySelectorAll('tbody tr[data-trade-index]').forEach(row => {
      row.addEventListener('click', () => {
        const tradeIndex = Number(row.dataset.tradeIndex);
        const nextSelectedIndex = selectedTradeIndex === tradeIndex ? null : tradeIndex;
        selectedTradeIndex = nextSelectedIndex;
        render(data);
        onRowSelect?.(normalizedTrades.find(item => item.trade_index === nextSelectedIndex) || null);
      });
    });
  }

  function sortTrades() {
    if (!sortKey) {
      return [...normalizedTrades];
    }
    return [...normalizedTrades].sort((left, right) => compareValues(left[sortKey], right[sortKey], sortAsc));
  }

  render(sortTrades());
}

function compareValues(left, right, asc) {
  const leftValue = left ?? 0;
  const rightValue = right ?? 0;
  if (leftValue === rightValue) {
    return 0;
  }
  const result = leftValue > rightValue ? 1 : -1;
  return asc ? result : -result;
}

function formatDate(str) {
  if (!str) return '-';
  return str.split(' ')[0];
}

function formatNum(n) {
  if (n == null) return '-';
  return Number(n).toFixed(2);
}

function formatPct(n) {
  if (n == null) return '-';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${Number(n).toFixed(2)}%`;
}

function formatMoney(n) {
  if (n == null) return '-';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${Number(n).toFixed(2)}`;
}
