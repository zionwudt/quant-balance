/**
 * 知衡 QuantBalance — 设置页面
 */

import { api, ApiError, getApiKey, setApiKey } from '../api.js';
import { toast } from '../components/toast.js';
import { getAppSettings, updateAppSettings, getDataProvider } from '../settings.js';
import { downloadJson } from '../utils/download.js';

let latestConfigStatus = null;
let latestSchedulerStatus = null;
let latestMarketRegime = null;

export async function initSettingsPage(container) {
  latestConfigStatus = await loadConfigStatus();
  container.innerHTML = buildHTML(getAppSettings(), latestConfigStatus);
  bindEvents(container);
  renderConfigStatus(container, latestConfigStatus);
  void refreshSchedulerStatus(container, { silent: true });
  void refreshMarketRegime(container, { silent: true });
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
  const enabledChannels = new Set(notifications.enabled || []);
  const wecom = notifications.wecom || {};
  const dingtalk = notifications.dingtalk || {};
  const serverchan = notifications.serverchan || {};
  const email = notifications.email || {};
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
              <div class="card-title">全局行情数据源</div>
              <p class="card-subtitle">选择后全局生效，所有页面的数据均使用此数据源。如某些功能该数据源不支持，会自动降级（跳过该筛选条件）。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <div class="advanced-field">
              <span class="form-label">数据源</span>
              <div class="choice-group">
                ${buildRadio('data-provider', '', '自动选择', !settings.data_provider)}
                ${buildRadio('data-provider', 'akshare', 'AkShare（免费）', settings.data_provider === 'akshare')}
                ${buildRadio('data-provider', 'baostock', 'BaoStock（免费）', settings.data_provider === 'baostock')}
                ${buildRadio('data-provider', 'tushare', 'Tushare（需Token）', settings.data_provider === 'tushare')}
              </div>
              <span class="field-help">
                切换数据源后全局生效。AkShare / BaoStock 免费无需配置，Tushare 需在上方配置有效 Token。
              </span>
            </div>
          </div>
          <details class="provider-compare-details" style="margin:12px 16px 16px;">
            <summary style="cursor:pointer;font-size:13px;color:var(--text-secondary);user-select:none;">📊 三个数据源能力对比</summary>
            <div style="overflow-x:auto;margin-top:8px;">
              <table class="provider-compare-table" style="width:100%;border-collapse:collapse;font-size:12px;line-height:1.8;">
                <thead>
                  <tr style="background:var(--bg-secondary);text-align:left;">
                    <th style="padding:6px 8px;border-bottom:1px solid var(--border-color);">功能</th>
                    <th style="padding:6px 8px;border-bottom:1px solid var(--border-color);">AkShare</th>
                    <th style="padding:6px 8px;border-bottom:1px solid var(--border-color);">BaoStock</th>
                    <th style="padding:6px 8px;border-bottom:1px solid var(--border-color);">Tushare</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td style="padding:4px 8px;">A 股股票列表</td><td>✅ 沪深5100+</td><td>✅ 沪深5500+</td><td>✅ 沪深京全量</td></tr>
                  <tr><td style="padding:4px 8px;">上市日期</td><td>✅ 完整</td><td>❌ 不提供</td><td>✅ 完整</td></tr>
                  <tr><td style="padding:4px 8px;">行业分类</td><td>✅ 深市有</td><td>✅ 证监会分类</td><td>✅ 完整</td></tr>
                  <tr><td style="padding:4px 8px;">日线行情 (OHLCV)</td><td>✅ 东方财富源</td><td>✅ 证交所源</td><td>✅ 需积分</td></tr>
                  <tr><td style="padding:4px 8px;">分钟线行情</td><td>✅ 东方财富源</td><td>❌ 不提供</td><td>✅ 需高积分</td></tr>
                  <tr><td style="padding:4px 8px;">财务数据 (PE/PB/ROE)</td><td>❌ 降级跳过</td><td>❌ 降级跳过</td><td>✅ 完整</td></tr>
                  <tr><td style="padding:4px 8px;">历史更名 (ST检测)</td><td>❌ 用当前名称</td><td>❌ 用当前名称</td><td>✅ 精确历史</td></tr>
                  <tr><td style="padding:4px 8px;">可转债数据</td><td>❌ 不支持</td><td>❌ 不支持</td><td>✅ 完整</td></tr>
                  <tr><td style="padding:4px 8px;">免费额度</td><td>✅ 完全免费</td><td>✅ 完全免费</td><td>⚠️ 有频率限制</td></tr>
                  <tr><td style="padding:4px 8px;">Token 配置</td><td>✅ 无需</td><td>✅ 无需</td><td>❌ 必须配置</td></tr>
                </tbody>
              </table>
              <p style="margin:8px 0 0;font-size:11px;color:var(--text-tertiary);">
                💡 降级说明：选择 AkShare/BaoStock 后，因子排名中的 PE/PB/ROE 等财务指标将不可用（自动跳过）；
                市值/PE 筛选条件将不生效；ST 检测使用当前名称而非历史名称。如需完整财务分析功能，请使用 Tushare。
              </p>
            </div>
          </details>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">API Key</div>
              <p class="card-subtitle">当后端启用 API Key 中间件时，Web 端会从这里读取本地凭证并自动附加请求头。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <label class="advanced-field" style="grid-column: span 2;">
              <span class="form-label">当前 API Key</span>
              <input class="input mono" id="settings-api-key" type="password" value="${escapeAttr(getApiKey())}" placeholder="留空表示不附带 Authorization">
              <span class="field-help">仅保存在当前浏览器本地，不会自动写入后端配置。</span>
            </label>
          </div>
          <div class="settings-actions">
            <button class="btn btn-secondary" id="settings-api-key-clear">清除 API Key</button>
            <button class="btn btn-primary" id="settings-api-key-save">保存 API Key</button>
          </div>
          <div class="settings-inline-status" id="settings-api-key-status"></div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">调度器</div>
              <p class="card-subtitle">查看每日盘后扫描调度器状态，并支持手动触发一次扫描。</p>
            </div>
            <div class="results-tags" id="settings-scheduler-tags">
              <span class="result-tag">等待加载</span>
            </div>
          </div>
          <div class="settings-section-grid">
            <label class="advanced-field">
              <span class="form-label">手动扫描日期</span>
              <input class="input" id="settings-scheduler-date" type="date" value="${formatDateInput(new Date())}">
            </label>
            <div class="advanced-field">
              <span class="form-label">操作</span>
              <div class="settings-actions">
                <button class="btn btn-secondary" id="settings-scheduler-refresh">刷新状态</button>
                <button class="btn btn-primary" id="settings-scheduler-run">立即扫描</button>
              </div>
            </div>
          </div>
          <div class="settings-inline-status" id="settings-scheduler-status"></div>
        </div>

        <div class="card">
          <div class="results-card-head">
            <div>
              <div class="card-title">市场状态</div>
              <p class="card-subtitle">直接查询 <span class="mono">market/regime</span>，便于核对当前筛选与因子研究的市场环境。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <label class="advanced-field">
              <span class="form-label">指数代码</span>
              <input class="input mono" id="settings-regime-symbol" type="text" value="000300.SH">
            </label>
            <label class="advanced-field">
              <span class="form-label">开始日期</span>
              <input class="input" id="settings-regime-start" type="date" value="${formatDateInput(new Date(Date.now() - 120 * 24 * 3600 * 1000))}">
            </label>
            <label class="advanced-field">
              <span class="form-label">结束日期</span>
              <input class="input" id="settings-regime-end" type="date" value="${formatDateInput(new Date())}">
            </label>
            <div class="advanced-field">
              <span class="form-label">操作</span>
              <div class="settings-actions">
                <button class="btn btn-secondary" id="settings-regime-refresh">刷新市场状态</button>
              </div>
            </div>
          </div>
          <div class="settings-inline-status" id="settings-regime-status"></div>
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
              <p class="card-subtitle">本地偏好会保存在浏览器；“测试已启用渠道”会调用后端真实发送链路验证当前表单配置。</p>
            </div>
          </div>
          <div class="settings-section-grid">
            <div class="advanced-field">
              <span class="form-label">启用渠道</span>
              <div class="choice-group">
                ${buildCheckbox('notify-enabled', 'wecom', '企业微信', enabledChannels.has('wecom'))}
                ${buildCheckbox('notify-enabled', 'dingtalk', '钉钉', enabledChannels.has('dingtalk'))}
                ${buildCheckbox('notify-enabled', 'serverchan', 'Server酱', enabledChannels.has('serverchan'))}
                ${buildCheckbox('notify-enabled', 'email', '邮件', enabledChannels.has('email'))}
              </div>
              <span class="field-help">只会测试勾选中的渠道；调度任务实际发送仍读取后端 <span class="mono">config/config.toml</span>。</span>
            </div>
            <label class="advanced-field">
              <span class="form-label">企业微信 Webhook</span>
              <input class="input mono" id="settings-wecom-webhook" type="text" value="${escapeAttr(wecom.webhook || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">钉钉 Webhook</span>
              <input class="input mono" id="settings-dingtalk-webhook" type="text" value="${escapeAttr(dingtalk.webhook || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">钉钉 Secret</span>
              <input class="input mono" id="settings-dingtalk-secret" type="text" value="${escapeAttr(dingtalk.secret || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">Server酱 SendKey</span>
              <input class="input mono" id="settings-serverchan-sendkey" type="text" value="${escapeAttr(serverchan.sendkey || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">SMTP Host</span>
              <input class="input mono" id="settings-email-smtp-host" type="text" value="${escapeAttr(email.smtp_host || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">SMTP Port</span>
              <input class="input mono" id="settings-email-smtp-port" type="number" min="1" max="65535" step="1" value="${Number(email.smtp_port ?? 465)}">
            </label>
            <label class="advanced-field">
              <span class="form-label">发件人</span>
              <input class="input" id="settings-email-sender" type="text" value="${escapeAttr(email.sender || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">SMTP 用户名</span>
              <input class="input" id="settings-email-username" type="text" value="${escapeAttr(email.username || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">SMTP 密码</span>
              <input class="input" id="settings-email-password" type="password" value="${escapeAttr(email.password || '')}">
            </label>
            <label class="advanced-field">
              <span class="form-label">收件人</span>
              <input class="input" id="settings-email-receiver" type="email" value="${escapeAttr(email.receiver || '')}">
            </label>
            <div class="advanced-field">
              <span class="form-label">邮件安全</span>
              <div class="choice-group">
                ${buildCheckbox('email-use-ssl', 'true', 'SSL', email.use_ssl !== false)}
                ${buildCheckbox('email-starttls', 'true', 'STARTTLS', email.starttls !== false)}
              </div>
              <span class="field-help">使用 SSL 时通常端口为 465；不启用 SSL 时可保留 STARTTLS。</span>
            </div>
          </div>
          <div class="settings-actions">
            <button class="btn btn-secondary" id="settings-notify-test">测试已启用渠道</button>
          </div>
          <div class="settings-inline-status" id="settings-notify-status"></div>
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

  container.querySelectorAll('input[name="data-provider"]').forEach((input) => {
    input.addEventListener('change', async () => {
      const provider = container.querySelector('input[name="data-provider"]:checked')?.value || '';
      const previousProvider = getDataProvider();
      updateAppSettings({ data_provider: provider });
      try {
        await api.setDataProvider(provider);
        toast.success(`全局数据源已切换为：${provider || '自动选择'}`);
      } catch (error) {
        updateAppSettings({ data_provider: previousProvider });
        const prev = container.querySelector(`input[name="data-provider"][value="${previousProvider}"]`);
        if (prev) prev.checked = true;
        const message = error instanceof ApiError ? error.message : '数据源切换失败';
        toast.error(message);
      }
    });
  });

  container.querySelector('#settings-api-key-save')?.addEventListener('click', () => {
    const key = container.querySelector('#settings-api-key').value.trim();
    setApiKey(key);
    container.querySelector('#settings-api-key-status').innerHTML = key
      ? '<span class="text-profit">API Key 已保存到当前浏览器。</span>'
      : '<span class="text-muted">当前未配置 API Key。</span>';
    toast.success(key ? 'API Key 已保存' : 'API Key 已清空');
  });

  container.querySelector('#settings-api-key-clear')?.addEventListener('click', () => {
    setApiKey('');
    container.querySelector('#settings-api-key').value = '';
    container.querySelector('#settings-api-key-status').innerHTML = '<span class="text-muted">API Key 已清除。</span>';
    toast.success('API Key 已清除');
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

  container.querySelector('#settings-notify-test')?.addEventListener('click', async () => {
    const statusEl = container.querySelector('#settings-notify-status');
    const payload = collectNotifyTestPayload(container);
    if (!payload.enabled.length) {
      toast.error('请先勾选至少一个通知渠道');
      return;
    }

    statusEl.textContent = '正在测试通知连通性...';
    try {
      const result = await api.testNotifications(payload);
      renderNotifyTestStatus(statusEl, result.items || []);
      if ((result.failure_count || 0) > 0) {
        toast.info(`通知测试完成：成功 ${result.success_count || 0}，失败 ${result.failure_count || 0}`);
      } else {
        toast.success(`通知测试成功：已发送 ${result.success_count || 0} 个渠道`);
      }
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '通知测试失败';
      statusEl.innerHTML = `<span class="text-loss">${message}</span>`;
      toast.error(message);
    }
  });

  container.querySelector('#settings-scheduler-refresh')?.addEventListener('click', async () => {
    await refreshSchedulerStatus(container);
  });

  container.querySelector('#settings-scheduler-run')?.addEventListener('click', async () => {
    const statusEl = container.querySelector('#settings-scheduler-status');
    statusEl.textContent = '正在触发扫描...';
    try {
      const result = await api.runScheduler({
        trade_date: container.querySelector('#settings-scheduler-date').value || null,
        force: true,
      });
      statusEl.innerHTML = `<span class="text-profit">${escapeHtml(result.message || '手动扫描已触发')}</span>`;
      toast.success('手动扫描已触发');
      await refreshSchedulerStatus(container, { silent: true });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '手动扫描失败';
      statusEl.innerHTML = `<span class="text-loss">${escapeHtml(message)}</span>`;
      toast.error(message);
    }
  });

  container.querySelector('#settings-regime-refresh')?.addEventListener('click', async () => {
    await refreshMarketRegime(container);
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
    data_provider: container.querySelector('input[name="data-provider"]:checked')?.value || '',
    notifications: collectNotificationSettings(container),
    trading_defaults: {
      cash: Number(container.querySelector('#settings-cash').value || 100000),
      commission: Number(container.querySelector('#settings-commission').value || 0.001),
      rebalance_frequency: container.querySelector('#settings-rebalance').value || 'monthly',
      stop_loss_pct: Number(container.querySelector('#settings-stop-loss').value || 0),
      take_profit_pct: Number(container.querySelector('#settings-take-profit').value || 0),
    },
  };
}

function collectNotificationSettings(container) {
  return {
    enabled: Array.from(container.querySelectorAll('input[name="notify-enabled"]:checked')).map((input) => input.value),
    wecom: {
      webhook: container.querySelector('#settings-wecom-webhook').value.trim(),
    },
    dingtalk: {
      webhook: container.querySelector('#settings-dingtalk-webhook').value.trim(),
      secret: container.querySelector('#settings-dingtalk-secret').value.trim(),
    },
    serverchan: {
      sendkey: container.querySelector('#settings-serverchan-sendkey').value.trim(),
    },
    email: {
      receiver: container.querySelector('#settings-email-receiver').value.trim(),
      smtp_host: container.querySelector('#settings-email-smtp-host').value.trim(),
      smtp_port: Number(container.querySelector('#settings-email-smtp-port').value || 465),
      sender: container.querySelector('#settings-email-sender').value.trim(),
      password: container.querySelector('#settings-email-password').value,
      username: container.querySelector('#settings-email-username').value.trim(),
      use_ssl: container.querySelector('input[name="email-use-ssl"]')?.checked ?? true,
      starttls: container.querySelector('input[name="email-starttls"]')?.checked ?? true,
    },
  };
}

function collectNotifyTestPayload(container) {
  const notifications = collectNotificationSettings(container);
  return {
    enabled: notifications.enabled,
    title: '知衡通知测试',
    content: `这是一条来自 QuantBalance 的测试通知。\n发送时间：${new Date().toLocaleString('zh-CN', { hour12: false })}`,
    wecom_webhook: notifications.wecom.webhook,
    dingtalk_webhook: notifications.dingtalk.webhook,
    dingtalk_secret: notifications.dingtalk.secret,
    serverchan_sendkey: notifications.serverchan.sendkey,
    email_receiver: notifications.email.receiver,
    email_smtp_host: notifications.email.smtp_host,
    email_smtp_port: notifications.email.smtp_port,
    email_sender: notifications.email.sender,
    email_password: notifications.email.password,
    email_username: notifications.email.username,
    email_use_ssl: notifications.email.use_ssl,
    email_starttls: notifications.email.starttls,
  };
}

function renderNotifyTestStatus(statusEl, items) {
  if (!items.length) {
    statusEl.innerHTML = '<span class="text-muted">未返回通知结果</span>';
    return;
  }

  statusEl.innerHTML = items.map((item) => {
    const isOk = item.status === 'sent';
    const detail = item.detail ? `：${escapeHtml(item.detail)}` : '';
    return `<div class="${isOk ? 'text-profit' : 'text-loss'}">${channelLabel(item.channel)} ${isOk ? '已发送' : '失败'}${detail}</div>`;
  }).join('');
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

async function refreshSchedulerStatus(container, options = {}) {
  const { silent = false } = options;
  const statusEl = container.querySelector('#settings-scheduler-status');
  if (statusEl) {
    statusEl.textContent = '正在读取调度器状态...';
  }
  try {
    latestSchedulerStatus = await api.getSchedulerStatus();
    renderSchedulerStatus(container, latestSchedulerStatus);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : '无法获取调度器状态';
    if (statusEl) {
      statusEl.innerHTML = `<span class="text-loss">${escapeHtml(message)}</span>`;
    }
    if (!silent) {
      toast.error(message);
    }
  }
}

function renderSchedulerStatus(container, status) {
  container.querySelector('#settings-scheduler-tags').innerHTML = `
    <span class="result-tag">${status?.enabled ? '已启用' : '未启用'}</span>
    <span class="result-tag">${status?.running ? '运行中' : '未运行'}</span>
    <span class="result-tag">${status?.next_run_time ? `下次 ${status.next_run_time}` : '无下次执行时间'}</span>
  `;
  container.querySelector('#settings-scheduler-status').innerHTML = `
    <div>${status?.message || '调度器状态已更新。'}</div>
    <div class="text-muted">最后扫描：${status?.last_scan?.trade_date || status?.last_scan?.completed_at || '暂无'}</div>
  `;
}

async function refreshMarketRegime(container, options = {}) {
  const { silent = false } = options;
  const statusEl = container.querySelector('#settings-regime-status');
  if (statusEl) {
    statusEl.textContent = '正在读取市场状态...';
  }
  try {
    latestMarketRegime = await api.getMarketRegime({
      symbol: container.querySelector('#settings-regime-symbol').value.trim() || '000300.SH',
      start_date: container.querySelector('#settings-regime-start').value || '',
      end_date: container.querySelector('#settings-regime-end').value || '',
      data_provider: getDataProvider() || '',
    });
    renderMarketRegime(container, latestMarketRegime);
  } catch (error) {
    const rawMessage = error instanceof ApiError ? error.message : '无法获取市场状态';
    const message = explainMarketRegimeError(rawMessage);
    if (statusEl) {
      statusEl.innerHTML = `<span class="text-loss">${escapeHtml(message)}</span>`;
    }
    if (!silent) {
      toast.error(message);
    }
  }
}

function renderMarketRegime(container, payload) {
  const latest = payload?.latest || {};
  const recentRows = (payload?.series || []).slice(-5).reverse();
  container.querySelector('#settings-regime-status').innerHTML = `
    <div class="signals-history-status">
      <span>最新状态：<strong>${escapeHtml(latest.regime || '-')}</strong> · ${escapeHtml(latest.date || '-')}</span>
      <span class="mono">close ${latest.close ?? '-'}</span>
    </div>
    <div class="portfolio-table-wrapper" style="margin-top:12px;">
      <table class="data-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>状态</th>
            <th data-align="right">趋势强度</th>
            <th data-align="right">动量</th>
          </tr>
        </thead>
        <tbody>
          ${recentRows.map((item) => `
            <tr>
              <td class="mono">${item.date}</td>
              <td>${escapeHtml(item.regime)}</td>
              <td data-align="right" class="mono">${item.trend_strength_pct == null ? '-' : `${Number(item.trend_strength_pct).toFixed(2)}%`}</td>
              <td data-align="right" class="mono">${item.momentum_pct == null ? '-' : `${Number(item.momentum_pct).toFixed(2)}%`}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
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

function buildCheckbox(name, value, label, checked) {
  return `
    <label class="choice-pill">
      <input type="checkbox" name="${name}" value="${value}" ${checked ? 'checked' : ''}>
      <span>${label}</span>
    </label>
  `;
}

function channelLabel(value) {
  if (value === 'wecom') return '企业微信';
  if (value === 'dingtalk') return '钉钉';
  if (value === 'serverchan') return 'Server酱';
  if (value === 'email') return '邮件';
  return value || '未知渠道';
}

function rebalanceLabel(value) {
  if (value === 'daily') return '每日';
  if (value === 'weekly') return '每周';
  if (value === 'quarterly') return '每季度';
  return '每月';
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function explainMarketRegimeError(message) {
  const normalized = String(message || '').trim();
  if (normalized && normalized !== '内部服务器错误') {
    return normalized;
  }
  return '市场状态读取失败。该能力依赖指数行情权限；如果当前 Tushare Token 未开通相关接口，会返回失败。';
}

function escapeAttr(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escapeHtml(value) {
  return escapeAttr(value).replace(/'/g, '&#39;');
}
