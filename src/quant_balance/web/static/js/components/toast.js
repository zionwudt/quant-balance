/**
 * 知衡 QuantBalance — Toast 通知组件
 */

let container = null;

function ensureContainer() {
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  return container;
}

function show(message, type = 'info', duration = 0) {
  const c = ensureContainer();

  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `
    <div class="toast-body">${escapeHtml(message)}</div>
    <button class="toast-close">&times;</button>
  `;

  const close = () => {
    el.classList.add('toast-leaving');
    el.addEventListener('animationend', () => el.remove());
  };

  el.querySelector('.toast-close').onclick = close;
  c.appendChild(el);

  const autoClose = duration || (type === 'error' ? 0 : 3000);
  if (autoClose > 0) {
    setTimeout(close, autoClose);
  }
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

export const toast = {
  success: (msg) => show(msg, 'success'),
  error:   (msg) => show(msg, 'error'),
  info:    (msg) => show(msg, 'info'),
};
