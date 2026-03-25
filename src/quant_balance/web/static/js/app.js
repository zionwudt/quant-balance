/**
 * 知衡 QuantBalance — 应用入口
 */

import { initTheme, toggleTheme } from './theme.js';
import { getAppSettings, resolveTheme } from './settings.js';
import { initBacktestPage } from './pages/backtest.js';
import { initStockPoolPage } from './pages/stock-pool.js';
import { initPaperTradingPage } from './pages/paper-trading.js';
import { initSignalsPage } from './pages/signals.js';
import { initSettingsPage } from './pages/settings.js';
import { checkOnboarding } from './components/onboarding.js';

const pages = {
  backtest: { title: '回测中心', init: initBacktestPage },
  'stock-pool': { title: '股票池研究', init: initStockPoolPage },
  'paper-trading': { title: '模拟盘', init: initPaperTradingPage },
  signals: { title: '信号中心', init: initSignalsPage },
  settings: { title: '设置', init: initSettingsPage },
};
const navOrder = ['backtest', 'stock-pool', 'paper-trading', 'signals', 'settings'];
let currentPageController = null;
let renderSerial = 0;

document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  initSidebar();
  initTopbar();
  initStatusbar();
  bindGlobalEvents();

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

function initStatusbar() {
  updateVisualStatusbar();
  setStatusText('就绪');
}

function bindGlobalEvents() {
  document.addEventListener('keydown', handleGlobalKeydown);
  window.addEventListener('qb-settings-changed', updateVisualStatusbar);
  window.addEventListener('qb-status-message', (event) => {
    setStatusText(event.detail?.text || '就绪');
  });
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
  const currentRender = renderSerial + 1;
  renderSerial = currentRender;
  disposeCurrentPage();

  document.title = `知衡 QuantBalance · ${config.title}`;
  document.querySelectorAll('.sidebar-item').forEach((element) => {
    element.classList.toggle('active', element.dataset.page === page);
  });

  const main = document.querySelector('.main-content');
  main.innerHTML = '';
  const controller = await config.init(main, {
    page,
    params,
    navigateTo,
  });
  if (currentRender !== renderSerial) {
    controller?.dispose?.();
    return;
  }
  currentPageController = controller || null;
  setStatusText(config.title);
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

function handleGlobalKeydown(event) {
  if (event.defaultPrevented) {
    return;
  }
  const lowerKey = String(event.key || '').toLowerCase();
  const editing = isEditingContext(event.target) || isEditingContext(document.activeElement);

  if ((event.ctrlKey || event.metaKey) && lowerKey === 'k') {
    if (editing) {
      return;
    }
    event.preventDefault();
    if (currentPageController?.focusPrimary) {
      currentPageController.focusPrimary();
      return;
    }
    focusSearchFallback();
    return;
  }

  if (editing) {
    return;
  }

  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    currentPageController?.runPrimary?.();
    return;
  }

  if ((event.ctrlKey || event.metaKey) && lowerKey === 'e') {
    event.preventDefault();
    currentPageController?.exportCurrent?.();
    return;
  }

  if (!event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey && /^[1-5]$/.test(event.key)) {
    const page = navOrder[Number(event.key) - 1];
    if (page) {
      event.preventDefault();
      void navigateTo(page);
    }
    return;
  }

  if (event.key === 'Escape') {
    event.preventDefault();
    currentPageController?.handleEscape?.();
    window.dispatchEvent(new CustomEvent('qb-escape'));
  }
}

function focusSearchFallback() {
  const searchInput = document.querySelector('.symbol-search-input');
  const clearButton = document.querySelector('.symbol-pill-clear');
  if (searchInput && searchInput.offsetParent !== null) {
    searchInput.focus();
    return;
  }
  clearButton?.focus();
}

function isEditingContext(target) {
  const element = target instanceof Element ? target : null;
  if (!element) {
    return false;
  }
  return Boolean(
    element.closest('input, textarea, select, [contenteditable="true"]')
      || element instanceof HTMLInputElement
      || element instanceof HTMLTextAreaElement
      || element instanceof HTMLSelectElement,
  );
}

function updateVisualStatusbar() {
  const settings = getAppSettings();
  const resolvedTheme = resolveTheme(settings.appearance);
  const themeLabel = settings.appearance === 'system'
    ? `跟随系统（当前${resolvedTheme === 'dark' ? '深色' : '浅色'}）`
    : (resolvedTheme === 'dark' ? '深色' : '浅色');
  const riseLabel = settings.rise_fall_style === 'ashare' ? 'A股红涨绿跌' : '国际绿涨红跌';

  const themeEl = document.getElementById('statusbar-theme');
  const riseEl = document.getElementById('statusbar-rise-style');
  if (themeEl) {
    themeEl.textContent = `主题：${themeLabel}`;
  }
  if (riseEl) {
    riseEl.textContent = `涨跌色：${riseLabel}`;
  }
}

function setStatusText(text) {
  const element = document.getElementById('statusbar-state');
  if (element) {
    element.textContent = text;
  }
}

function disposeCurrentPage() {
  currentPageController?.dispose?.();
  currentPageController = null;
}
