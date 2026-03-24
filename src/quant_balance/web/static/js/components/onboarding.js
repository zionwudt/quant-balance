/**
 * 知衡 QuantBalance — Tushare Token 首次使用引导
 */

import { api, ApiError } from '../api.js';
import { toast } from '../components/toast.js';

/**
 * 检查配置状态，如需引导则弹出对话框。
 * @returns {Promise<boolean>} true 表示配置就绪，false 表示用户仍需配置
 */
export async function checkOnboarding() {
  try {
    const status = await api.getConfigStatus();
    if (status.token_configured && status.connection_ok) {
      return true;
    }
    await showOnboardingDialog(status);
    return true;
  } catch {
    // API 不可用时跳过引导，让用户正常使用
    return true;
  }
}

function showOnboardingDialog(status) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'onboarding-overlay';
    overlay.innerHTML = `
      <div class="onboarding-dialog">
        <div class="onboarding-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="28" height="28">
            <path d="M3 12h4l3-9 4 18 3-9h4"/>
          </svg>
          <h2>欢迎使用知衡 QuantBalance</h2>
        </div>
        <p class="text-secondary" style="margin-bottom:var(--space-4)">
          开始之前，请先配置 Tushare 数据源 Token。
        </p>

        <div class="onboarding-steps">
          <div class="onboarding-step">
            <span class="onboarding-step-num">1</span>
            <div>
              <div>获取 Token</div>
              <div class="text-secondary" style="font-size:var(--text-xs)">
                前往 <a href="https://tushare.pro/register" target="_blank" rel="noopener">tushare.pro/register</a> 注册并获取 Token
              </div>
            </div>
          </div>
          <div class="onboarding-step">
            <span class="onboarding-step-num">2</span>
            <div>
              <div>输入 Token</div>
              <div style="margin-top:var(--space-2)">
                <input class="input mono" id="onboarding-token" type="text"
                  placeholder="粘贴你的 Tushare Token"
                  style="width:100%"
                  ${status.token_configured ? `value="已配置"` : ''}>
              </div>
            </div>
          </div>
          <div class="onboarding-step">
            <span class="onboarding-step-num">3</span>
            <div>
              <div>验证连接</div>
              <div class="text-secondary" style="font-size:var(--text-xs)">
                测试 Token 可用性，确认数据源正常
              </div>
            </div>
          </div>
        </div>

        <div style="display:flex;gap:var(--space-3);margin-top:var(--space-6)">
          <button class="btn btn-secondary" id="onboarding-test" style="flex:1">测试连接</button>
          <button class="btn btn-primary" id="onboarding-save" style="flex:1" disabled>保存并开始</button>
        </div>
        <div id="onboarding-status" style="margin-top:var(--space-3);font-size:var(--text-sm);min-height:20px"></div>

        ${status.token_configured ? `
          <button class="btn btn-ghost" id="onboarding-skip"
            style="margin-top:var(--space-3);width:100%;font-size:var(--text-xs)">
            跳过（Token 已配置但连接失败，可能是网络问题）
          </button>
        ` : ''}
      </div>
    `;

    document.body.appendChild(overlay);

    const tokenInput = overlay.querySelector('#onboarding-token');
    const testBtn = overlay.querySelector('#onboarding-test');
    const saveBtn = overlay.querySelector('#onboarding-save');
    const statusEl = overlay.querySelector('#onboarding-status');
    const skipBtn = overlay.querySelector('#onboarding-skip');

    let validated = false;

    testBtn.onclick = async () => {
      const token = tokenInput.value.trim();
      if (!token || token === '已配置') {
        statusEl.innerHTML = '<span style="color:var(--loss)">请输入 Token</span>';
        return;
      }
      testBtn.disabled = true;
      testBtn.textContent = '验证中...';
      statusEl.innerHTML = '<span style="color:var(--text-muted)">正在验证 Token...</span>';

      try {
        await api.saveTushareToken(token, true);
        statusEl.innerHTML = '<span style="color:var(--profit)">✓ Token 验证成功</span>';
        validated = true;
        saveBtn.disabled = false;
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : '验证失败';
        statusEl.innerHTML = `<span style="color:var(--loss)">✗ ${msg}</span>`;
        validated = false;
        saveBtn.disabled = true;
      } finally {
        testBtn.disabled = false;
        testBtn.textContent = '测试连接';
      }
    };

    saveBtn.onclick = async () => {
      if (!validated) return;
      const token = tokenInput.value.trim();
      saveBtn.disabled = true;
      saveBtn.textContent = '保存中...';

      try {
        await api.saveTushareToken(token, false);
        toast.success('Tushare Token 已保存，欢迎使用知衡！');
        close();
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : '保存失败';
        statusEl.innerHTML = `<span style="color:var(--loss)">✗ ${msg}</span>`;
        saveBtn.disabled = false;
        saveBtn.textContent = '保存并开始';
      }
    };

    if (skipBtn) {
      skipBtn.onclick = close;
    }

    function close() {
      overlay.classList.add('onboarding-leaving');
      overlay.addEventListener('animationend', () => {
        overlay.remove();
        resolve();
      });
    }
  });
}
