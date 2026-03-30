/**
 * 知衡 QuantBalance — 全局设置与视觉偏好
 */

const SETTINGS_KEY = 'qb-settings';
const APPEARANCE_KEY = 'qb-appearance';
const RISE_STYLE_KEY = 'qb-rise-fall-style';

const DEFAULT_SETTINGS = {
  appearance: 'dark',
  rise_fall_style: 'international',
  notifications: {
    enabled: [],
    wecom: {
      webhook: '',
    },
    dingtalk: {
      webhook: '',
      secret: '',
    },
    serverchan: {
      sendkey: '',
    },
    email: {
      receiver: '',
      smtp_host: '',
      smtp_port: 465,
      sender: '',
      password: '',
      username: '',
      use_ssl: true,
      starttls: true,
    },
  },
  trading_defaults: {
    cash: 100000,
    commission: 0.001,
    rebalance_frequency: 'monthly',
    stop_loss_pct: 0.08,
    take_profit_pct: 0.15,
  },
};

let mediaQuery = null;
let initialized = false;

export function initSettings() {
  if (initialized) {
    applyVisualSettings();
    return getAppSettings();
  }
  initialized = true;
  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  mediaQuery.addEventListener?.('change', handleSystemThemeChange);
  applyVisualSettings();
  return getAppSettings();
}

export function getAppSettings() {
  return normalizeSettings(readStoredSettings());
}

export function updateAppSettings(patch) {
  const next = mergeSettings(getAppSettings(), patch);
  persistSettings(next);
  applyVisualSettings(next);
  emitSettingsChanged(next);
  return next;
}

export function updateAppearance(appearance) {
  return updateAppSettings({ appearance });
}

export function updateRiseFallStyle(style) {
  return updateAppSettings({ rise_fall_style: style });
}

export function resolveTheme(appearance) {
  if (appearance === 'light' || appearance === 'dark') {
    return appearance;
  }
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  return prefersDark ? 'dark' : 'light';
}

export function applyVisualSettings(settings = getAppSettings()) {
  const appearance = settings.appearance || 'dark';
  const resolvedTheme = resolveTheme(appearance);
  const riseFallStyle = settings.rise_fall_style || 'international';

  document.documentElement.setAttribute('data-theme', resolvedTheme);
  document.documentElement.setAttribute('data-appearance', appearance);
  document.documentElement.setAttribute('data-rise-style', riseFallStyle);
  localStorage.setItem(APPEARANCE_KEY, appearance);
  localStorage.setItem(RISE_STYLE_KEY, riseFallStyle);
  updateThemeButton(appearance, resolvedTheme);
  return { appearance, resolvedTheme, riseFallStyle };
}

export function cycleAppearanceMode() {
  const settings = getAppSettings();
  const sequence = ['dark', 'light', 'system'];
  const currentIndex = sequence.indexOf(settings.appearance || 'dark');
  const next = sequence[(currentIndex + 1) % sequence.length];
  return updateAppearance(next);
}

export function getVisualPalette() {
  const style = getComputedStyle(document.documentElement);
  return {
    textPrimary: cssVar(style, '--text-primary'),
    textSecondary: cssVar(style, '--text-secondary'),
    textMuted: cssVar(style, '--text-muted'),
    border: cssVar(style, '--border'),
    borderSubtle: cssVar(style, '--border-subtle'),
    accent: cssVar(style, '--chart-accent'),
    accentSoft: cssVar(style, '--chart-accent-soft'),
    benchmark: cssVar(style, '--chart-benchmark'),
    profit: cssVar(style, '--profit'),
    loss: cssVar(style, '--loss'),
    profitSoft: cssVar(style, '--profit-soft'),
    lossSoft: cssVar(style, '--loss-soft'),
    profitStrong: cssVar(style, '--profit-strong'),
    lossStrong: cssVar(style, '--loss-strong'),
    chartAxis: cssVar(style, '--chart-axis'),
    chartGrid: cssVar(style, '--chart-grid'),
    chartGridSubtle: cssVar(style, '--chart-grid-subtle'),
    tooltipBg: cssVar(style, '--chart-tooltip-bg'),
    tooltipBorder: cssVar(style, '--chart-tooltip-border'),
    focusBg: cssVar(style, '--chart-focus-bg'),
    volumeUp: cssVar(style, '--chart-volume-up'),
    volumeDown: cssVar(style, '--chart-volume-down'),
    bgInput: cssVar(style, '--bg-input'),
    bgElevated: cssVar(style, '--bg-elevated'),
  };
}

function handleSystemThemeChange() {
  const settings = getAppSettings();
  if (settings.appearance === 'system') {
    applyVisualSettings(settings);
    emitSettingsChanged(settings);
  }
}

function readStoredSettings() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
  } catch {
    return {};
  }
}

function persistSettings(settings) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  localStorage.setItem(APPEARANCE_KEY, settings.appearance || DEFAULT_SETTINGS.appearance);
  localStorage.setItem(RISE_STYLE_KEY, settings.rise_fall_style || DEFAULT_SETTINGS.rise_fall_style);
}

function emitSettingsChanged(settings) {
  window.dispatchEvent(new CustomEvent('qb-settings-changed', {
    detail: {
      settings,
      theme: resolveTheme(settings.appearance),
      riseFallStyle: settings.rise_fall_style,
    },
  }));
}

function normalizeSettings(raw) {
  return mergeSettings(DEFAULT_SETTINGS, {
    ...(raw || {}),
    notifications: normalizeNotificationSettings((raw || {}).notifications || {}),
  });
}

function mergeSettings(base, patch) {
  return {
    ...base,
    ...patch,
    notifications: normalizeNotificationSettings({
      ...(base.notifications || {}),
      ...(patch.notifications || {}),
    }),
    trading_defaults: {
      ...base.trading_defaults,
      ...(patch.trading_defaults || {}),
    },
  };
}

function normalizeNotificationSettings(raw) {
  return {
    enabled: Array.isArray(raw.enabled) ? [...new Set(raw.enabled)] : [],
    wecom: {
      webhook: raw.wecom?.webhook || raw.wecom_webhook || '',
    },
    dingtalk: {
      webhook: raw.dingtalk?.webhook || raw.dingding_webhook || '',
      secret: raw.dingtalk?.secret || raw.dingding_secret || '',
    },
    serverchan: {
      sendkey: raw.serverchan?.sendkey || raw.serverchan_sendkey || '',
    },
    email: {
      receiver: raw.email?.receiver || raw.email_recipient || '',
      smtp_host: raw.email?.smtp_host || '',
      smtp_port: Number(raw.email?.smtp_port ?? 465),
      sender: raw.email?.sender || '',
      password: raw.email?.password || '',
      username: raw.email?.username || '',
      use_ssl: raw.email?.use_ssl ?? true,
      starttls: raw.email?.starttls ?? true,
    },
  };
}

function updateThemeButton(appearance, resolvedTheme) {
  const button = document.getElementById('theme-toggle');
  if (!button) {
    return;
  }

  if (appearance === 'system') {
    button.textContent = '◐';
    button.title = `跟随系统（当前 ${resolvedTheme === 'dark' ? '深色' : '浅色'}）`;
    return;
  }

  button.textContent = resolvedTheme === 'dark' ? '☀' : '☾';
  button.title = resolvedTheme === 'dark' ? '切到浅色/跟随系统' : '切到跟随系统/深色';
}

function cssVar(style, name) {
  return style.getPropertyValue(name).trim();
}

