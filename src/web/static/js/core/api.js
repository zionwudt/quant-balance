/**
 * 知衡 QuantBalance — API 封装
 */

const API_TIMEOUT = 30_000;

function getApiKey() {
  return localStorage.getItem('qb_api_key') || '';
}

function setApiKey(key) {
  if (key) {
    localStorage.setItem('qb_api_key', key.trim());
  } else {
    localStorage.removeItem('qb_api_key');
  }
}

function authHeaders() {
  const key = getApiKey();
  return key ? { Authorization: `Bearer ${key}` } : {};
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), API_TIMEOUT);

  try {
    const resp = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
        ...options.headers,
      },
    });

    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new ApiError(body.detail || `请求失败 (${resp.status})`, resp.status);
    }

    return await resp.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ApiError('请求超时，请重试', 0);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function requestBinary(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), API_TIMEOUT);

  try {
    const resp = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        ...authHeaders(),
        ...options.headers,
      },
    });

    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new ApiError(body.detail || `请求失败 (${resp.status})`, resp.status);
    }

    return {
      blob: await resp.blob(),
      filename: parseDownloadFilename(resp.headers.get('content-disposition')),
      contentType: resp.headers.get('content-type') || '',
    };
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ApiError('请求超时，请重试', 0);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function parseDownloadFilename(contentDisposition) {
  const text = String(contentDisposition || '');
  const match = text.match(/filename="?([^"]+)"?/i);
  return match ? decodeURIComponent(match[1]) : null;
}

export const api = {
  getHealth() {
    return request('/health');
  },

  getMeta() {
    return request('/api/meta');
  },

  getStrategies() {
    return request('/api/strategies');
  },

  searchSymbols(query, limit = 8) {
    const url = new URL('/api/symbols/search', window.location.origin);
    url.searchParams.set('q', query);
    url.searchParams.set('limit', String(limit));
    return request(url.pathname + url.search);
  },

  runFactorRanking(params) {
    return request('/api/factors/rank', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  filterStockPool(params) {
    return request('/api/stock-pool/filter', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  runBacktest(params) {
    return request('/api/backtest/run', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  runPortfolio(params) {
    return request('/api/portfolio/run', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  runOptimize(params) {
    return request('/api/backtest/optimize', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  getBacktestHistory(params = {}) {
    const url = new URL('/api/backtest/history', window.location.origin);
    Object.entries(params).forEach(([key, value]) => {
      if (value == null || value === '') {
        return;
      }
      url.searchParams.set(key, String(value));
    });
    return request(url.pathname + url.search);
  },

  getBacktestHistoryDetail(runId) {
    return request(`/api/backtest/history/${encodeURIComponent(runId)}`);
  },

  compareBacktests(ids) {
    const url = new URL('/api/backtest/compare', window.location.origin);
    url.searchParams.set('ids', Array.isArray(ids) ? ids.join(',') : String(ids || ''));
    return request(url.pathname + url.search);
  },

  deleteBacktestHistory(runId) {
    return request(`/api/backtest/history/${encodeURIComponent(runId)}`, {
      method: 'DELETE',
    });
  },

  runScreening(params) {
    return request('/api/screening/run', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  getMarketRegime(params = {}) {
    const url = new URL('/api/market/regime', window.location.origin);
    Object.entries(params).forEach(([key, value]) => {
      if (value == null || value === '') {
        return;
      }
      url.searchParams.set(key, String(value));
    });
    return request(url.pathname + url.search);
  },

  getConfigStatus() {
    return request('/api/config/status');
  },

  getDataProvider() {
    return request('/api/config/data-provider');
  },

  setDataProvider(provider) {
    return request('/api/config/data-provider', {
      method: 'POST',
      body: JSON.stringify({ provider: provider || '' }),
    });
  },

  saveTushareToken(token, validateOnly = false) {
    return request('/api/config/tushare-token', {
      method: 'POST',
      body: JSON.stringify({ token, validate_only: validateOnly }),
    });
  },

  testNotifications(payload) {
    return request('/api/notify/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  getSchedulerStatus() {
    return request('/api/scheduler/status');
  },

  runScheduler(payload = {}) {
    return request('/api/scheduler/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  getSignalsRecent(limit = 20, tradeDate = null) {
    const url = new URL('/api/signals/recent', window.location.origin);
    url.searchParams.set('limit', String(limit));
    if (tradeDate) {
      url.searchParams.set('trade_date', tradeDate);
    }
    return request(url.pathname + url.search);
  },

  getSignalsToday(limit = 200, date = null) {
    const url = new URL('/api/signals/today', window.location.origin);
    url.searchParams.set('limit', String(limit));
    if (date) {
      url.searchParams.set('date', date);
    }
    return request(url.pathname + url.search);
  },

  getSignalsHistory(days = 30, page = 1, pageSize = 20) {
    const url = new URL('/api/signals/history', window.location.origin);
    url.searchParams.set('days', String(days));
    url.searchParams.set('page', String(page));
    url.searchParams.set('page_size', String(pageSize));
    return request(url.pathname + url.search);
  },

  updateSignalStatus(signalId, status) {
    return request(`/api/signals/${encodeURIComponent(signalId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  },

  exportSignals(format = 'csv', date = null) {
    const url = new URL('/api/signals/export', window.location.origin);
    url.searchParams.set('format', format);
    if (date) {
      url.searchParams.set('date', date);
    }
    return requestBinary(url.pathname + url.search);
  },

  getPaperStatus(sessionId = null, date = null) {
    const url = new URL('/api/paper/status', window.location.origin);
    if (sessionId) {
      url.searchParams.set('session_id', sessionId);
    }
    if (date) {
      url.searchParams.set('date', date);
    }
    return request(url.pathname + url.search);
  },

  startPaper(payload) {
    return request('/api/paper/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  pausePaper(sessionId = null) {
    return request('/api/paper/pause', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    });
  },

  stopPaper(sessionId = null, date = null) {
    return request('/api/paper/stop', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, date }),
    });
  },
};

export { ApiError };
export { getApiKey, setApiKey };
