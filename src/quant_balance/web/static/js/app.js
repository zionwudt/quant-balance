/**
 * 知衡 QuantBalance — 应用入口
 */

import { initTheme, toggleTheme } from './theme.js';
import { initBacktestPage } from './pages/backtest.js';
import { initStockPoolPage } from './pages/stock-pool.js';
import { checkOnboarding } from './components/onboarding.js';

const pages = {
  backtest: { title: '回测中心', init: initBacktestPage },
  'stock-pool': { title: '股票池研究', init: initStockPoolPage },
};

document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  initSidebar();
  initTopbar();

  await checkOnboarding();
  await syncRoute({ normalizeHash: true });
});

window.addEventListener('hashchange', () => {
  void syncRoute();
});

function initSidebar() {
  document.querySelectorAll('.sidebar-item[data-page]').forEach(item => {
    item.onclick = () => {
      void navigateTo(item.dataset.page);
    };
  });
}

function initTopbar() {
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    themeBtn.onclick = toggleTheme;
  }
}

async function syncRoute(options = {}) {
  const { normalizeHash = false } = options;
  let route = parseRoute(window.location.hash);

  if (!pages[route.page]) {
    route = { page: 'backtest', params: {} };
  }
  if (normalizeHash || window.location.hash !== buildHash(route.page, route.params)) {
    window.history.replaceState(null, '', buildHash(route.page, route.params));
  }

  await renderPage(route.page, route.params);
}

export async function navigateTo(page, params = {}, options = {}) {
  if (!pages[page]) {
    return;
  }

  const hash = buildHash(page, params);
  const replace = options.replace === true;
  if (replace) {
    window.history.replaceState(null, '', hash);
    await renderPage(page, params);
    return;
  }

  if (window.location.hash !== hash) {
    window.location.hash = hash;
    return;
  }
  await renderPage(page, params);
}

async function renderPage(page, params) {
  const config = pages[page];
  if (!config) {
    return;
  }

  document.title = `知衡 QuantBalance · ${config.title}`;
  document.querySelectorAll('.sidebar-item').forEach((element) => {
    element.classList.toggle('active', element.dataset.page === page);
  });

  const main = document.querySelector('.main-content');
  main.innerHTML = '';
  await config.init(main, {
    page,
    params,
    navigateTo,
  });
}

function parseRoute(hash) {
  const normalized = String(hash || '').replace(/^#\/?/, '');
  if (!normalized) {
    return { page: 'backtest', params: {} };
  }

  const [page, query = ''] = normalized.split('?');
  return {
    page: page || 'backtest',
    params: Object.fromEntries(new URLSearchParams(query)),
  };
}

function buildHash(page, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === '') {
      return;
    }
    query.set(key, String(value));
  });

  const queryText = query.toString();
  return `#/${page}${queryText ? `?${queryText}` : ''}`;
}

document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
    event.preventDefault();
    const searchInput = document.querySelector('.symbol-search-input');
    const clearButton = document.querySelector('.symbol-pill-clear');
    if (searchInput && searchInput.offsetParent !== null) {
      searchInput.focus();
    } else if (clearButton) {
      clearButton.focus();
    }
  }
});
