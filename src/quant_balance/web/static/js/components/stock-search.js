/**
 * 知衡 QuantBalance — 股票代码搜索组件
 */

import { api } from '../api.js';

export function createStockSearch(container, options = {}) {
  const {
    placeholder = '输入代码或名称，如 600519 / 茅台',
    caption = '支持按代码或名称模糊搜索，回车可直接使用手动输入代码',
    limit = 8,
    initialSelection = null,
    filterItem = () => true,
    onChange = null,
  } = options;

  let selectedItem = normalizeItem(initialSelection);
  let results = [];
  let activeIndex = -1;
  let searchTimer = null;
  let requestSerial = 0;

  container.innerHTML = `
    <div class="symbol-search">
      <div class="symbol-search-selected hidden"></div>
      <div class="symbol-search-input-row">
        <input class="input symbol-search-input" autocomplete="off" spellcheck="false" placeholder="${placeholder}">
      </div>
      <div class="symbol-search-dropdown hidden"></div>
      <div class="symbol-search-caption">${caption}</div>
    </div>
  `;

  const selectedEl = container.querySelector('.symbol-search-selected');
  const inputRow = container.querySelector('.symbol-search-input-row');
  const input = container.querySelector('.symbol-search-input');
  const dropdown = container.querySelector('.symbol-search-dropdown');

  function renderSelected() {
    if (!selectedItem) {
      selectedEl.classList.add('hidden');
      inputRow.classList.remove('hidden');
      return;
    }

    selectedEl.classList.remove('hidden');
    inputRow.classList.add('hidden');
    selectedEl.innerHTML = `
      <div class="symbol-pill">
        <div class="symbol-pill-main">
          <span class="symbol-pill-code mono">${selectedItem.symbol}</span>
          <span class="symbol-pill-name">${selectedItem.name || '手动输入'}</span>
        </div>
        <button type="button" class="symbol-pill-clear" aria-label="重新选择">×</button>
      </div>
    `;
    selectedEl.querySelector('.symbol-pill-clear')?.addEventListener('click', () => {
      selectedItem = null;
      results = [];
      activeIndex = -1;
      input.value = '';
      renderDropdown();
      renderSelected();
      input.focus();
      onChange?.(null);
    });
  }

  function renderDropdown(message = '') {
    if (!input.value.trim()) {
      dropdown.classList.add('hidden');
      dropdown.innerHTML = '';
      return;
    }

    if (!results.length && message) {
      dropdown.innerHTML = `<div class="symbol-search-empty">${message}</div>`;
      dropdown.classList.remove('hidden');
      return;
    }
    if (!results.length) {
      dropdown.classList.add('hidden');
      dropdown.innerHTML = '';
      return;
    }

    dropdown.innerHTML = results.map((item, index) => `
      <button type="button" class="symbol-search-item${index === activeIndex ? ' active' : ''}" data-index="${index}">
        <span class="symbol-search-item-main">
          <span class="symbol-search-item-code mono">${item.symbol}</span>
          <span class="symbol-search-item-name">${item.name || '未命名'}</span>
        </span>
        <span class="symbol-search-item-meta">${item.market || item.industry || item.kind || ''}</span>
      </button>
    `).join('');
    dropdown.classList.remove('hidden');
    dropdown.querySelectorAll('.symbol-search-item').forEach(item => {
      item.addEventListener('mousedown', (event) => {
        event.preventDefault();
      });
      item.addEventListener('click', () => {
        const index = Number(item.dataset.index);
        selectItem(results[index]);
      });
    });
  }

  function selectItem(item) {
    selectedItem = normalizeItem(item);
    results = [];
    activeIndex = -1;
    input.value = '';
    renderSelected();
    renderDropdown();
    onChange?.(selectedItem);
  }

  function commitManualValue() {
    const manualValue = input.value.trim().toUpperCase();
    if (!manualValue) {
      return null;
    }
    const item = {
      symbol: manualValue,
      name: '手动输入',
      market: '自定义',
      asset_type: 'stock',
      kind: 'manual',
    };
    selectItem(item);
    return item;
  }

  async function runSearch(query) {
    const normalized = query.trim();
    if (!normalized) {
      results = [];
      activeIndex = -1;
      renderDropdown();
      return;
    }

    const currentRequest = requestSerial + 1;
    requestSerial = currentRequest;
    try {
      const response = await api.searchSymbols(normalized, limit);
      if (currentRequest !== requestSerial) {
        return;
      }
      results = (response.items || []).filter(filterItem);
      activeIndex = results.length ? 0 : -1;
      renderDropdown('未找到匹配结果，可直接回车使用输入代码');
    } catch {
      if (currentRequest !== requestSerial) {
        return;
      }
      results = [];
      activeIndex = -1;
      renderDropdown('搜索失败，可直接回车使用输入代码');
    }
  }

  input.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      void runSearch(input.value);
    }, 180);
  });
  input.addEventListener('focus', () => {
    if (input.value.trim()) {
      void runSearch(input.value);
    }
  });
  input.addEventListener('blur', () => {
    window.setTimeout(() => {
      dropdown.classList.add('hidden');
    }, 120);
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown' && results.length) {
      event.preventDefault();
      activeIndex = (activeIndex + 1) % results.length;
      renderDropdown();
      return;
    }
    if (event.key === 'ArrowUp' && results.length) {
      event.preventDefault();
      activeIndex = activeIndex <= 0 ? results.length - 1 : activeIndex - 1;
      renderDropdown();
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      if (results[activeIndex]) {
        selectItem(results[activeIndex]);
      } else {
        commitManualValue();
      }
      return;
    }
    if (event.key === 'Escape') {
      dropdown.classList.add('hidden');
    }
  });

  renderSelected();

  return {
    clear() {
      selectedItem = null;
      input.value = '';
      results = [];
      activeIndex = -1;
      renderSelected();
      renderDropdown();
    },
    focus() {
      if (selectedItem) {
        selectedEl.querySelector('.symbol-pill-clear')?.focus();
      } else {
        input.focus();
      }
    },
    getSelectedItem() {
      return selectedItem;
    },
    getValue() {
      return selectedItem?.symbol || input.value.trim().toUpperCase();
    },
    setSelection(item) {
      if (!item) {
        this.clear();
        return;
      }
      selectItem(item);
    },
  };
}

function normalizeItem(item) {
  if (!item || !item.symbol) {
    return null;
  }
  return {
    symbol: String(item.symbol).toUpperCase(),
    name: String(item.name || ''),
    market: String(item.market || ''),
    asset_type: String(item.asset_type || 'stock'),
    kind: String(item.kind || 'stock'),
  };
}
