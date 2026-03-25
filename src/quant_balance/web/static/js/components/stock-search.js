/**
 * 知衡 QuantBalance — 股票代码搜索组件
 */

import { api } from '../api.js';

export function createStockSearch(container, options = {}) {
  return createSearchInstance(container, {
    ...options,
    multiple: false,
  });
}

export function createMultiStockSearch(container, options = {}) {
  return createSearchInstance(container, {
    ...options,
    multiple: true,
  });
}

function createSearchInstance(container, options) {
  const {
    placeholder = '输入代码或名称，如 600519 / 茅台',
    caption = '支持按代码或名称模糊搜索，回车可直接使用手动输入代码',
    limit = 8,
    initialSelection = null,
    filterItem = () => true,
    onChange = null,
    multiple = false,
  } = options;

  let selectedItems = multiple
    ? normalizeItems(initialSelection)
    : normalizeItems(initialSelection).slice(0, 1);
  let results = [];
  let activeIndex = -1;
  let searchTimer = null;
  let requestSerial = 0;

  container.innerHTML = `
    <div class="symbol-search${multiple ? ' symbol-search-multiple' : ''}">
      <div class="symbol-search-input-row">
        <div class="symbol-search-selected"></div>
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

  function emitChange() {
    onChange?.(multiple ? [...selectedItems] : selectedItems[0] || null);
  }

  function renderSelected() {
    if (!selectedItems.length) {
      selectedEl.innerHTML = '';
      selectedEl.classList.add('hidden');
      input.classList.remove('hidden');
      input.placeholder = placeholder;
      return;
    }

    selectedEl.classList.remove('hidden');
    selectedEl.innerHTML = selectedItems.map(item => `
      <div class="symbol-pill" data-symbol="${item.symbol}">
        <div class="symbol-pill-main">
          <span class="symbol-pill-code mono">${item.symbol}</span>
          <span class="symbol-pill-name">${item.name || '手动输入'}</span>
        </div>
        <button type="button" class="symbol-pill-clear" aria-label="移除 ${item.symbol}">×</button>
      </div>
    `).join('');

    if (!multiple) {
      input.classList.add('hidden');
    } else {
      input.classList.remove('hidden');
      input.placeholder = '继续添加股票代码';
    }

    selectedEl.querySelectorAll('.symbol-pill-clear').forEach((button) => {
      button.addEventListener('click', () => {
        const symbol = button.closest('.symbol-pill')?.dataset.symbol || '';
        removeItem(symbol);
      });
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

  function removeItem(symbol) {
    selectedItems = selectedItems.filter(item => item.symbol !== symbol);
    renderSelected();
    emitChange();
    input.focus();
  }

  function selectItem(item) {
    const normalized = normalizeItem(item);
    if (!normalized) {
      return;
    }

    if (!multiple) {
      selectedItems = [normalized];
    } else if (!selectedItems.some(entry => entry.symbol === normalized.symbol)) {
      selectedItems = [...selectedItems, normalized];
    }

    results = [];
    activeIndex = -1;
    input.value = '';
    renderSelected();
    renderDropdown();
    emitChange();
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
      results = (response.items || []).filter(item => {
        if (!filterItem(item)) {
          return false;
        }
        return multiple || !selectedItems.some(selected => selected.symbol === item.symbol);
      });
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
    if (event.key === 'Backspace' && multiple && !input.value && selectedItems.length) {
      removeItem(selectedItems[selectedItems.length - 1].symbol);
      return;
    }
    if (event.key === 'Escape') {
      dropdown.classList.add('hidden');
    }
  });

  renderSelected();

  return {
    clear() {
      selectedItems = [];
      input.value = '';
      results = [];
      activeIndex = -1;
      renderSelected();
      renderDropdown();
    },
    focus() {
      if (!multiple && selectedItems.length) {
        selectedEl.querySelector('.symbol-pill-clear')?.focus();
      } else {
        input.focus();
      }
    },
    getSelectedItem() {
      return selectedItems[0] || null;
    },
    getSelectedItems() {
      return [...selectedItems];
    },
    getValue() {
      return multiple
        ? selectedItems.map(item => item.symbol)
        : selectedItems[0]?.symbol || input.value.trim().toUpperCase();
    },
    getValues() {
      const value = this.getValue();
      return Array.isArray(value) ? value : (value ? [value] : []);
    },
    setSelection(item) {
      selectedItems = normalizeItems(item).slice(0, 1);
      renderSelected();
      emitChange();
    },
    setSelections(items) {
      selectedItems = multiple
        ? normalizeItems(items)
        : normalizeItems(items).slice(0, 1);
      renderSelected();
      emitChange();
    },
  };
}

function normalizeItems(items) {
  const raw = Array.isArray(items) ? items : (items ? [items] : []);
  const normalized = [];
  const seen = new Set();

  raw.forEach((item) => {
    const entry = normalizeItem(item);
    if (!entry || seen.has(entry.symbol)) {
      return;
    }
    seen.add(entry.symbol);
    normalized.push(entry);
  });
  return normalized;
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
