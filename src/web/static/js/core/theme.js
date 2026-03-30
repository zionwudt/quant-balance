/**
 * 知衡 QuantBalance — 主题切换
 */

import { cycleAppearanceMode, initSettings } from './settings.js';

export function initTheme() {
  initSettings();
}

export function toggleTheme() {
  cycleAppearanceMode();
}

