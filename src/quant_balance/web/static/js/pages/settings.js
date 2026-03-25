/**
 * 知衡 QuantBalance — 设置页面
 */

import { api, ApiError } from '../api.js';
import { toast } from '../components/toast.js';
import { getAppSettings, updateAppSettings } from '../settings.js';
import { downloadJson } from '../utils/download.js';

let latestConfigStatus = null;

export async function initSettingsPage(container) {
  latestConfigStatus = await loadConfigStatus();
  container.innerHTML = buildHTML(getAppSettings(), latestConfigStatus);
  bindEvents(container);
  renderConfigStatus(container, latestConfigStatus);
  window.dispatchEvent(new CustomEvent('qb-status-message', {
    detail: { text: '设置 · 已加载当前偏好' },
  }));

  return {
    exportCurrent() {
      downloadJson('quant-balance-settings.json', getAppSettings());
      toast.success('当前设置已导出');
    },
    focusPrimary() {
      container.querySelector('#settings-token')?.focus();
    },
  };
}

function buildHTML(settings, status) {
  const tradingDefaults = settings.trading_defaults || {};
  const notifications = settings.notifications || {};
  return `
    <div class="settings-layout">
      <div class="results-overview">
        <div>
          <div class="results-title">设置</div>
          <p class="results-subtitle">数据源、主题、涨跌配色、通知渠道和交易默认值都在这里集中管理，保存后立即生效。</p>
        </div>
        <div class="results-tags" id="settings-status-tags">
          ${buildStatusTags(status)}
        </div>
      </div>

      <div class="settings-grid">
        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">数据源配置</div>
              <p class="card-subtitle">可直接在 Web 端写入或验证 Tushare Token，无需手工编辑配置文件。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <label class="advanced-field">
              <span class="form-label">Tushare Token</span>
              <input class="input mono" id="settings-token" type="text" placeholder="${status?.token_configured ? '当前已配置，如需更新请重新粘贴' : '粘贴新的 Tushare Token'}">
              <span class="field-help">“测试连接”会优先验证输入框内的新 Token；留空时则仅刷新当前连接状态。</span>
            </label>
          </div>
          <div class="settings-actions">
            <button class="btn btn-secondary" id="settings-token-test">测试连接</button>
            <button class="btn btn-primary" id="settings-token-save">保存 Token</button>
          </div>
          <div class="settings-inline-status" id="settings-token-status"></div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">外观与交互</div>
              <p class="card-subtitle">支持深色 / 浅色 / 跟随系统，以及国际 / A 股两种涨跌配色方案。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <div class="advanced-field">
              <span class="form-label">主题模式</span>
              <div class="choice-group">
                ${buildRadio('appearance', 'dark', '深色', settings.appearance === 'dark')}
                ${buildRadio('appearance', 'light', '浅色', settings.appearance === 'light')}
                ${buildRadio('appearance', 'system', '跟随系统', settings.appearance === 'system')}
              </div>
              <span class="field-help">跟随系统模式会监听 <span class="mono">prefers-color-scheme</span>，并通过首屏脚本避免闪烁。</span>
            </div>

            <div class="advanced-field">
              <span class="form-label">涨跌颜色</span>
              <div class="choice-group">
                ${buildRadio('rise-style', 'international', '国际样式', settings.rise_fall_style === 'international')}
                ${buildRadio('rise-style', 'ashare', 'A 股样式', settings.rise_fall_style === 'ashare')}
              </div>
              <span class="field-help">保存后会立即刷新全局色板，K 线、权益图、热力图和盈亏文本都会同步更新。</span>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">通知渠道</div>
              <p class="card-subtitle">当前先保存为本地偏好，后续可直接接到策略告警或定时任务。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <label class="advanced-field">
              <span class="form-label">企业微信 Webhook</span>
              <input class="input mono" id="settings-wecom" type="text" value="${escapeAttr(notifications.wecom_webhook || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">钉钉 Webhook</span>
              <input class="input mono" id="settings-dingding" type="text" value="${escapeAttr(notifications.dingding_webhook || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">Server酱 SendKey</span>
              <input class="input mono" id="settings-serverchan" type="text" value="${escapeAttr(notifications.serverchan_sendkey || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">Email</span>
              <input class="input" id="settings-email" type="email" value="${escapeAttr(notifications.email_recipient || '')}">
            </label>
          </div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">交易默认值</div>
              <p class="card-subtitle">新开回测和模拟盘时会优先读取这些默认值，避免每次重复输入。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <label class="advanced-field">
              <span class="form-label">初始资金</span>
              <input class="input mono" id="settings-cash" type="number" min="1000" step="1000" value="${tradingDefaults.cash ?? 100000}">
            </label>
            <label class="advanced-field">
              <span class="form-label">默认手续费</span>
              <input class="input mono" id="settings-commission" type="number" min="0" step="0.0005" value="${tradingDefaults.commission ?? 0.001}">
            </label>
            <label class="advanced-field">
              <span class="form-label">默认再平衡频率</span>
              <select class="input" id="settings-rebalance">
                ${['daily', 'weekly', 'monthly', 'quarterly'].map((item) => `
                  <option value="${item}"${item === tradingDefaults.rebalance_frequency ? ' selected' : ''}>${rebalanceLabel(item)}</option>
                `).join('')}
              </select>
            </label>
            <label class="advanced-field">
              <span class="form-label">默认止损</span>
              <input class="input mono" id="settings-stop-loss" type="number" min="0" step="0.01" value="${tradingDefaults.stop_loss_pct ?? 0.08}">
            </label>
            <label class="advanced-field">
              <span class="form-label">默认止盈</span>
              <input class="input mono" id="settings-take-profit" type="number" min="0" step="0.01" value="${tradingDefaults.take_profit_pct ?? 0.15}">
            </label>
          </div>
        </div>
      </div>

      <div class="settings-actions settings-actions-footer">
        <button class="btn btn-secondary" id="settings-export">导出设置</button>
        <button class="btn btn-primary" id="settings-save">保存偏好</button>
      </div>
    </div>
  `;
}

function bindEvents(container) {
  const syncVisualPreview = () => {
    updateAppSettings({
      appearance: container.querySelector('input[name="appearance"]:checked')?.value || 'dark',
      rise_fall_style: container.querySelector('input[name="rise-style"]:checked')?.value || 'international',
    });
  };

  container.querySelectorAll('input[name="appearance"], input[name="rise-style"]').forEach((input) => {
    input.addEventListener('change', syncVisualPreview);
  });

  container.querySelector('#settings-token-test')?.addEventListener('click', async () => {
    const token = container.querySelector('#settings-token').value.trim();
    const statusEl = container.querySelector('#settings-token-status');
    statusEl.textContent = '正在测试连接...';

    try {
      if (token) {
        await api.saveTushareToken(token, true);
        statusEl.innerHTML = '<span class="text-profit">连接验证成功，可直接保存到本地配置。</span>';
      } else {
        latestConfigStatus = await loadConfigStatus();
        renderConfigStatus(container, latestConfigStatus);
        statusEl.innerHTML = latestConfigStatus.connection_ok
          ? '<span class="text-profit">当前已配置 Token，连接状态正常。</span>'
          : `<span class="text-loss">${latestConfigStatus.message || '当前连接仍不可用'}</span>`;
      }
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '连接测试失败';
      statusEl.innerHTML = `<span class="text-loss">${message}</span>`;
    }
  });

  container.querySelector('#settings-token-save')?.addEventListener('click', async () => {
    const token = container.querySelector('#settings-token').value.trim();
    const statusEl = container.querySelector('#settings-token-status');
    if (!token) {
      toast.error('请先输入新的 Tushare Token');
      return;
    }

    statusEl.textContent = '正在保存 Token...';
    try {
      await api.saveTushareToken(token, false);
      latestConfigStatus = await loadConfigStatus();
      renderConfigStatus(container, latestConfigStatus);
      statusEl.innerHTML = '<span class="text-profit">Token 已保存并写入配置文件。</span>';
      toast.success('Tushare Token 已保存');
      container.querySelector('#settings-token').value = '';
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '保存 Token 失败';
      statusEl.innerHTML = `<span class="text-loss">${message}</span>`;
      toast.error(message);
    }
  });

  container.querySelector('#settings-export')?.addEventListener('click', () => {
    downloadJson('quant-balance-settings.json', getAppSettings());
    toast.success('设置已导出');
  });

  container.querySelector('#settings-save')?.addEventListener('click', () => {
    const patch = collectSettingsPatch(container);
    updateAppSettings(patch);
    toast.success('设置已保存并立即生效');
  });
}

function collectSettingsPatch(container) {
  return {
    appearance: container.querySelector('input[name="appearance"]:checked')?.value || 'dark',
    rise_fall_style: container.querySelector('input[name="rise-style"]:checked')?.value || 'international',
    notifications: {
      wecom_webhook: container.querySelector('#settings-wecom').value.trim(),
      dingding_webhook: container.querySelector('#settings-dingding').value.trim(),
      serverchan_sendkey: container.querySelector('#settings-serverchan').value.trim(),
      email_recipient: container.querySelector('#settings-email').value.trim(),
    },
    trading_defaults: {
      cash: Number(container.querySelector('#settings-cash').value || 100000),
      commission: Number(container.querySelector('#settings-commission').value || 0.001),
      rebalance_frequency: container.querySelector('#settings-rebalance').value || 'monthly',
      stop_loss_pct: Number(container.querySelector('#settings-stop-loss').value || 0),
      take_profit_pct: Number(container.querySelector('#settings-take-profit').value || 0),
    },
  };
}

function renderConfigStatus(container, status) {
  container.querySelector('#settings-status-tags').innerHTML = buildStatusTags(status);
}

async function loadConfigStatus() {
  try {
    return await api.getConfigStatus();
  } catch {
    return {
      config_exists: false,
      token_configured: false,
      connection_ok: false,
      message: '当前无法获取配置状态',
    };
  }
}

function buildStatusTags(status) {
  return `
    <span class="result-tag">${status?.config_exists ? '配置文件已加载' : '配置文件未创建'}</span>
    <span class="result-tag">${status?.token_configured ? 'Token 已配置' : 'Token 未配置'}</span>
    <span class="result-tag">${status?.connection_ok ? '连接正常' : '连接异常'}</span>
    <span class="result-tag">${status?.message || '等待检查'}</span>
  `;
}

function buildRadio(name, value, label, checked) {
  return `
    <label class="choice-pill">
      <input type="radio" name="${name}" value="${value}" ${checked ? 'checked' : ''}>
      <span>${label}</span>
    </label>
  `;
}

function rebalanceLabel(value) {
  if (value === 'daily') return '每日';
  if (value === 'weekly') return '每周';
  if (value === 'quarterly') return '每季度';
  return '每月';
}

function escapeAttr(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
