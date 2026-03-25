/**
 * 知衡 QuantBalance — 下载工具
 */

export function downloadText(filename, content, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mimeType });
  downloadBlob(filename, blob);
}

export function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadJson(filename, payload) {
  const text = JSON.stringify(payload, null, 2);
  downloadText(filename, text, 'application/json;charset=utf-8');
}

export function downloadCsv(filename, rows, columns = null) {
  const normalizedRows = Array.isArray(rows) ? rows : [];
  const headers = Array.isArray(columns) && columns.length
    ? columns
    : collectColumns(normalizedRows);
  const lines = [headers.map(escapeCsv).join(',')];

  normalizedRows.forEach((row) => {
    lines.push(headers.map((header) => escapeCsv(row?.[header])).join(','));
  });

  downloadText(filename, lines.join('\n'), 'text/csv;charset=utf-8');
}

function collectColumns(rows) {
  const columns = [];
  const seen = new Set();

  rows.forEach((row) => {
    Object.keys(row || {}).forEach((key) => {
      if (!seen.has(key)) {
        seen.add(key);
        columns.push(key);
      }
    });
  });

  return columns;
}

function escapeCsv(value) {
  if (value == null) {
    return '';
  }
  const text = String(value);
  if (!/[,"\n]/.test(text)) {
    return text;
  }
  return `"${text.replace(/"/g, '""')}"`;
}
