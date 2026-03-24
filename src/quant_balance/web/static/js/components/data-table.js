/**
 * 知衡 QuantBalance — 成交明细表组件
 */

export function renderTradesTable(container, trades) {
  if (!trades || trades.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📋</div><p>运行回测后，成交明细将在这里展示</p></div>';
    return;
  }

  let sortKey = null;
  let sortAsc = true;

  function render(data) {
    container.innerHTML = `
      <div class="trades-table-wrapper">
        <table class="data-table" id="trades-table">
          <thead>
            <tr>
              <th data-sort="index">#</th>
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
            ${data.map((t, i) => {
              const pnlType = t.return_pct >= 0 ? 'profit' : 'loss';
              const pnlClass = t.return_pct >= 0 ? 'text-profit' : 'text-loss';
              return `
                <tr data-pnl="${pnlType}">
                  <td>${i + 1}</td>
                  <td>${formatDate(t.entry_time)}</td>
                  <td>${formatDate(t.exit_time)}</td>
                  <td data-align="right" class="mono">${formatNum(t.entry_price)}</td>
                  <td data-align="right" class="mono">${formatNum(t.exit_price)}</td>
                  <td data-align="right" class="mono">${t.size}</td>
                  <td data-align="right" class="mono ${pnlClass}">${formatPct(t.return_pct)}</td>
                  <td data-align="right" class="mono ${pnlClass}">${formatMoney(t.pnl)}</td>
                  <td>${t.duration}</td>
                </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;

    // 排序点击
    container.querySelectorAll('th[data-sort]').forEach(th => {
      th.onclick = () => {
        const key = th.dataset.sort;
        if (key === 'index') return;
        if (sortKey === key) {
          sortAsc = !sortAsc;
        } else {
          sortKey = key;
          sortAsc = true;
        }
        const sorted = [...trades].sort((a, b) => {
          const va = a[key] ?? 0;
          const vb = b[key] ?? 0;
          return sortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
        });
        render(sorted);
      };
    });
  }

  render(trades);
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
