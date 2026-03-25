/**
 * 知衡 QuantBalance — 应用入口
 */

import { initTheme, toggleTheme } from './theme.js';
import { initBacktestPage } from './pages/backtest.js';
import { checkOnboarding } from './components/onboarding.js';

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  initSidebar();
  initTopbar();

  // 首次使用引导
  await checkOnboarding();

  // 默认加载回测页面
  await navigateTo('backtest');
});

// ── 侧栏 ──
function initSidebar() {
  document.querySelectorAll('.sidebar-item[data-page]').forEach(item => {
    item.onclick = () => navigateTo(item.dataset.page);
  });
}

// ── 顶栏 ──
function initTopbar() {
  // 主题切换
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.onclick = toggleTheme;

  // 汉堡菜单
  const hamburger = document.querySelector('.topbar-hamburger');
  if (hamburger) {
    hamburger.onclick = () => {
      document.querySelector('.sidebar').classList.toggle('open');
    };
  }
}

// ── 路由 ──
const pages = {
  backtest: { title: '回测中心', init: initBacktestPage },
};

async function navigateTo(page) {
  const config = pages[page];
  if (!config) return;

  // 更新侧栏激活状态
  document.querySelectorAll('.sidebar-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });

  // 渲染页面
  const main = document.querySelector('.main-content');
  main.innerHTML = '';
  await config.init(main);
}

// ── 全局快捷键 ──
document.addEventListener('keydown', (e) => {
  // Ctrl+K 聚焦搜索
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.querySelector('.symbol-search-input');
    const clearButton = document.querySelector('.symbol-pill-clear');
    if (searchInput && searchInput.offsetParent !== null) {
      searchInput.focus();
    } else if (clearButton) {
      clearButton.focus();
    }
  }

  // Escape 关闭侧栏
  if (e.key === 'Escape') {
    document.querySelector('.sidebar')?.classList.remove('open');
  }
});
