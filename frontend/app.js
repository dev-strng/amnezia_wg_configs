(() => {
'use strict';

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  results: [],
  scanning: false,
  ws: null,
  jobId: null,
  total: 0,
  completed: 0,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ── Tabs ───────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $(`pane-${btn.dataset.tab}`).classList.add('active');
  });
});

// ── IP Ranges tag input ─────────────────────────────────────────────────────
const DEFAULT_RANGES = [
  '162.159.192.0/24', '162.159.193.0/24', '162.159.195.0/24',
  '188.114.96.0/24', '188.114.97.0/24',
];
const DEFAULT_PORTS = [2408];
let selectedRanges = [...DEFAULT_RANGES];
let selectedPorts = [...DEFAULT_PORTS];

function renderTags(containerId, items, onRemove) {
  const wrap = $(containerId);
  const input = wrap.querySelector('input');
  wrap.querySelectorAll('.tag').forEach(t => t.remove());
  items.forEach((item, idx) => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.innerHTML = `${item} <button title="Remove">×</button>`;
    tag.querySelector('button').addEventListener('click', () => {
      items.splice(idx, 1);
      renderTags(containerId, items, onRemove);
      if (onRemove) onRemove();
    });
    wrap.insertBefore(tag, input);
  });
}

function setupTagInput(containerId, items) {
  const wrap = $(containerId);
  const input = wrap.querySelector('input');
  renderTags(containerId, items, null);
  input.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ',') && input.value.trim()) {
      e.preventDefault();
      const val = input.value.trim().replace(/,/g, '');
      if (val && !items.includes(val)) {
        items.push(val);
        renderTags(containerId, items, null);
      }
      input.value = '';
    }
    if (e.key === 'Backspace' && !input.value && items.length) {
      items.pop();
      renderTags(containerId, items, null);
    }
  });
}

setupTagInput('ranges-input', selectedRanges);
setupTagInput('ports-input', selectedPorts);

// ── Scanner ────────────────────────────────────────────────────────────────
$('scan-btn').addEventListener('click', startScan);
$('stop-btn').addEventListener('click', stopScan);

async function startScan() {
  if (state.scanning) return;
  state.results = [];
  state.scanning = true;
  state.completed = 0;
  state.total = 0;
  updateScanUI();
  renderResults();

  const body = {
    ip_ranges: selectedRanges,
    ports: selectedPorts.map(Number),
    count_per_range: parseInt($('count-per-range').value) || 50,
    timeout: parseFloat($('scan-timeout').value) || 2.0,
  };

  try {
    const res = await fetch('/api/scan/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const { job_id } = await res.json();
    state.jobId = job_id;
    connectWS(job_id);
  } catch (e) {
    toast('Ошибка запуска сканирования: ' + e.message, 'err');
    state.scanning = false;
    updateScanUI();
  }
}

function stopScan() {
  if (state.ws) { state.ws.close(); state.ws = null; }
  state.scanning = false;
  updateScanUI();
  toast('Сканирование остановлено', 'ok');
}

function connectWS(jobId) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/api/scan/ws/${jobId}`);
  state.ws = ws;

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'start') {
      state.total = msg.total;
      updateProgress(0, msg.total);
    } else if (msg.type === 'result') {
      state.completed = msg.completed;
      state.total = msg.total;
      updateProgress(msg.completed, msg.total);
      if (msg.result) {
        state.results.push(msg.result);
        appendResultRow(msg.result);
        updateStats();
      }
    } else if (msg.type === 'done') {
      state.scanning = false;
      state.ws = null;
      updateScanUI();
      sortResults();

      // Auto-paste fastest endpoint if cfg-endpoint is empty
      if (!$('cfg-endpoint').value && state.results.length > 0) {
        const fastestOkEndpoint = state.results
          .filter(r => r.status === 'ok' && r.latency_ms != null)
          .sort((a, b) => a.latency_ms - b.latency_ms)[0];
        if (fastestOkEndpoint) {
          $('cfg-endpoint').value = `${fastestOkEndpoint.ip}:${fastestOkEndpoint.port}`;
          toast(`Автоматически выбран самый быстрый эндпоинт: ${fastestOkEndpoint.ip}:${fastestOkEndpoint.port}`, 'ok');
        }
      }
      toast(`✅ Готово! Найдено ${state.results.filter(r => r.status === 'ok').length} рабочих эндпоинтов`, 'ok');
    }
  };

  ws.onerror = () => {
    toast('WebSocket ошибка', 'err');
    state.scanning = false;
    updateScanUI();
  };
  ws.onclose = () => {
    state.ws = null;
    if (state.scanning) {
      state.scanning = false;
      updateScanUI();
    }
  };
}

function updateScanUI() {
  $('scan-btn').disabled = state.scanning;
  $('stop-btn').style.display = state.scanning ? 'inline-flex' : 'none';
  if (state.scanning) {
    $('scan-btn').innerHTML = '<span class="spinner"></span> Сканирование...';
  } else {
    $('scan-btn').innerHTML = '🔍 Запустить сканирование';
  }
}

function updateProgress(done, total) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  $('progress-bar').style.width = pct + '%';
  $('progress-done').textContent = done;
  $('progress-total').textContent = total;
  $('progress-pct').textContent = pct + '%';
}

function updateStats() {
  const ok = state.results.filter(r => r.status === 'ok');
  const timeouts = state.results.filter(r => r.status === 'timeout');
  const avgLat = ok.length
    ? Math.round(ok.reduce((a, b) => a + (b.latency_ms || 0), 0) / ok.length)
    : 0;
  const best = ok.length ? Math.round(Math.min(...ok.map(r => r.latency_ms || 9999))) : 0;

  $('stat-total').textContent = state.results.length;
  $('stat-ok').textContent = ok.length;
  $('stat-timeout').textContent = timeouts.length;
  $('stat-avg').textContent = ok.length ? avgLat + ' ms' : '—';
}

// ── Results table ──────────────────────────────────────────────────────────
const tbody = $('results-tbody');
const emptyState = $('empty-state');

function renderResults() {
  tbody.innerHTML = '';
  emptyState.style.display = state.results.length ? 'none' : 'block';
}

function appendResultRow(r) {
  emptyState.style.display = 'none';
  const tr = document.createElement('tr');
  const lat = r.latency_ms;
  const latClass = r.status !== 'ok' ? 'timeout' : lat < 50 ? 'fast' : lat < 150 ? 'mid' : 'slow';
  const latText = r.status === 'ok' && lat != null ? lat.toFixed(1) + ' ms' : 'timeout';
  const dotClass = r.status === 'ok' ? 'ok' : 'timeout';

  tr.innerHTML = `
    <td>${r.ip}</td>
    <td>${r.port}</td>
    <td><span class="latency-badge ${latClass}">${latText}</span></td>
    <td><span class="status-dot ${dotClass}"></span>${r.status === 'ok' ? 'Рабочий' : 'Timeout'}</td>
    <td>${r.status === 'ok' ? `<button class="use-btn" onclick="useEndpoint('${r.ip}', ${r.port})">Использовать</button>` : '—'}</td>
  `;
  tbody.appendChild(tr);
}

function sortResults() {
  const rows = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a, b) => {
    const la = parseFloat(a.querySelector('.latency-badge').textContent) || 9999;
    const lb = parseFloat(b.querySelector('.latency-badge').textContent) || 9999;
    return la - lb;
  });
  rows.forEach(r => tbody.appendChild(r));
}

window.useEndpoint = function(ip, port) {
  const endpoint = `${ip}:${port}`;
  $('cfg-endpoint').value = endpoint;
  switchTab('config');
  toast(`Эндпоинт ${endpoint} выбран`, 'ok');
};

// ── WARP Register ──────────────────────────────────────────────────────────
$('warp-register-btn').addEventListener('click', async () => {
  const btn = $('warp-register-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Регистрация...';
  try {
    const res = await fetch('/api/warp/register', { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    $('cfg-private-key').value = data.private_key;
    $('cfg-peer-key').value = data.public_key;
    $('cfg-address').value = data.address_v4;
    if (!$('cfg-endpoint').value) $('cfg-endpoint').value = data.default_endpoint;
    toast('✅ WARP-аккаунт зарегистрирован, ключи загружены!', 'ok');
  } catch (e) {
    toast('Ошибка регистрации WARP: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '☁️ Зарегистрировать WARP аккаунт';
  }
});

$('gen-keys-btn').addEventListener('click', async () => {
  try {
    const res = await fetch('/api/keys/generate', { method: 'POST' });
    const data = await res.json();
    $('cfg-private-key').value = data.private_key;
    toast('Новая пара ключей сгенерирована', 'ok');
  } catch (e) {
    toast('Ошибка генерации ключей', 'err');
  }
});

// ── Config Builder ─────────────────────────────────────────────────────────
$('generate-btn').addEventListener('click', generateConfig);

async function generateConfig() {
  const body = {
    private_key: $('cfg-private-key').value.trim(),
    peer_public_key: $('cfg-peer-key').value.trim(),
    peer_endpoint: $('cfg-endpoint').value.trim(),
    address: $('cfg-address').value.trim(),
    dns: $('cfg-dns').value.trim(),
    allowed_ips: $('cfg-allowed').value.trim(),
    jc: parseInt($('awg-jc').value),
    jmin: parseInt($('awg-jmin').value),
    jmax: parseInt($('awg-jmax').value),
    s1: parseInt($('awg-s1').value),
    s2: parseInt($('awg-s2').value),
    h1: parseInt($('awg-h1').value),
    h2: parseInt($('awg-h2').value),
    h3: parseInt($('awg-h3').value),
    h4: parseInt($('awg-h4').value),
    persistent_keepalive: parseInt($('awg-keepalive').value),
    mtu: parseInt($('awg-mtu').value),
  };

  if (!body.private_key || !body.peer_public_key || !body.peer_endpoint) {
    toast('Заполните обязательные поля: PrivateKey, PeerPublicKey, Endpoint', 'err');
    return;
  }

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    renderConfig(data.config, data.filename);
    switchTab('output');
    toast('✅ Конфиг сгенерирован!', 'ok');
  } catch (e) {
    toast('Ошибка генерации конфига: ' + e.message, 'err');
  }
}

// ── Config output ──────────────────────────────────────────────────────────
let currentFilename = 'amnezia.conf';
let currentConfig = '';

function renderConfig(cfg, filename) {
  currentConfig = cfg;
  currentFilename = filename;
  $('cfg-filename').textContent = filename;

  // Syntax highlight
  const highlighted = cfg
    .replace(/^(\[.+\])$/gm, '<span class="c-section">$1</span>')
    .replace(/^([A-Za-z0-9]+)( = )/gm, '<span class="c-key">$1</span><span class="c-eq"> = </span>')
    .replace(/^(#.*)$/gm, '<span class="c-comment">$1</span>');

  $('config-out').innerHTML = highlighted;
  $('output-section').style.display = 'block';
}

$('copy-btn').addEventListener('click', () => {
  navigator.clipboard.writeText(currentConfig).then(() => toast('Скопировано!', 'ok'));
});

$('download-btn').addEventListener('click', () => {
  const blob = new Blob([currentConfig], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = currentFilename;
  a.click();
  URL.revokeObjectURL(a.href);
  toast('Файл скачан: ' + currentFilename, 'ok');
});

// ── Helpers ────────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelector(`[data-tab="${name}"]`).classList.add('active');
  $(`pane-${name}`).classList.add('active');
}

function toast(msg, type = 'ok') {
  const container = $('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ── Load defaults from API ──────────────────────────────────────────────────
(async () => {
  try {
    const res = await fetch('/api/params');
    const p = await res.json();
    $('awg-jc').value = p.jc ?? 4;
    $('awg-jmin').value = p.jmin ?? 40;
    $('awg-jmax').value = p.jmax ?? 70;
    $('awg-s1').value = p.s1 ?? 0;
    $('awg-s2').value = p.s2 ?? 0;
    $('awg-h1').value = p.h1 ?? 1;
    $('awg-h2').value = p.h2 ?? 2;
    $('awg-h3').value = p.h3 ?? 3;
    $('awg-h4').value = p.h4 ?? 4;
    $('awg-keepalive').value = p.persistent_keepalive ?? 25;
    $('awg-mtu').value = p.mtu ?? 1280;
    $('cfg-dns').value = p.dns ?? '1.1.1.1, 1.0.0.1';
    $('cfg-allowed').value = p.allowed_ips ?? '0.0.0.0/0, ::/0';
  } catch (_) {}

  // Generate keys on load if fields are empty
  if (!$('cfg-private-key').value) {
    try {
      const res = await fetch('/api/keys/generate', { method: 'POST' });
      const data = await res.json();
      $('cfg-private-key').value = data.private_key;
      // Peer public key is not generated here, it comes from WARP API or user input.
      // $('cfg-peer-key').value = data.public_key; // This would overwrite a user-provided or WARP-generated public key
    } catch (e) {
      console.error('Ошибка автоматической генерации ключей:', e);
    }
  }

  // Register WARP account and populate Peer Public Key, Address, Endpoint if empty
  if (!$('cfg-peer-key').value) {
    try {
      const res = await fetch('/api/warp/register', { method: 'POST' });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      $('cfg-peer-key').value = data.public_key;
      if (!$('cfg-address').value) $('cfg-address').value = data.address_v4;
      if (!$('cfg-endpoint').value) $('cfg-endpoint').value = data.default_endpoint;
      console.log('Автоматически зарегистрирован WARP аккаунт и загружен публичный ключ пира.');
    } catch (e) {
      console.error('Ошибка автоматической регистрации WARP аккаунта:', e);
    }
  }
})();

})();
