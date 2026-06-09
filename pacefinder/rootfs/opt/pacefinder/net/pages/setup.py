SETUP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pacefinder · Setup</title>
<link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/base.css"><link rel="stylesheet" href="/static/nav.css">
<style>
/* Page-scoped reskin to match the layered-IA visual language. base.css
   is shared with admin/debug so we override here, not there. */
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  font-variant-numeric:tabular-nums;
  max-width:920px;margin:0 auto;padding:var(--space-4) var(--space-4) 60px;
}
.topbar{padding-bottom:var(--space-3);border-bottom:1px solid var(--color-border);margin-bottom:var(--space-6)}
.section-title{color:var(--color-text-tertiary);letter-spacing:0.08em}
.field label{color:var(--color-text-tertiary)}
.field .hint{color:var(--color-text-quaternary)}
.ip-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 20px 24px;
  margin-bottom: 24px;
}
.ip-card-title {
  font-size: var(--text-xs);
  font-weight: var(--fw-medium);
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--color-green);
  margin-bottom: 14px;
}
.ip-list { display: flex; flex-direction: column; gap: 8px; }
.ip-row {
  display: flex; align-items: center; gap: 10px;
  background: var(--color-surface-2); border: 1px solid var(--color-border);
  border-radius: var(--radius-sm); padding: 10px 14px;
}
.ip-addr {
  font-size: var(--text-md); font-weight: var(--fw-medium); color: var(--color-green);
  letter-spacing: .03em; flex: 1;
}
.copy-btn {
  background: var(--color-surface-2); border: 1px solid var(--color-border); color: var(--color-green);
  font-size: var(--text-xs); padding: 4px 10px; border-radius: var(--radius-sm);
  cursor: pointer; white-space: nowrap; font-family: inherit;
  transition: background .15s;
}
.copy-btn:hover { background: var(--color-surface); }
.copy-btn.copied { background: var(--color-surface); color: var(--color-green); }
.game-strings { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }
.game-string-row {
  display: flex; align-items: center; gap: 8px;
  background: var(--color-surface-2); border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-sm); padding: 7px 12px;
}
.game-label { font-size: var(--text-xs); color: var(--color-text-secondary); width: 90px; flex-shrink: 0; }
.game-value { font-size: var(--text-sm); color: var(--color-text-primary); font-family: var(--font-mono); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ip-loading { color: var(--color-text-muted); font-size: var(--text-sm); padding: 8px 0; }
.ip-uptime { font-size: var(--text-xs); color: var(--color-text-muted); margin-top: 10px; }

.udp-panel {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
  margin-bottom: 8px;
}
.udp-card {
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-sm); padding: 12px 14px;
}
.udp-game { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .06em; color: var(--color-text-muted); margin-bottom: 6px; }
.udp-status { display: flex; align-items: center; gap: 7px; margin-bottom: 4px; }
.udp-dot {
  width: 8px; height: 8px; min-width: 8px; min-height: 8px; border-radius: 50%;
  background: var(--color-surface-2); flex-shrink: 0;
  transition: background .3s;
}
.udp-dot.active { background: var(--color-green); box-shadow: 0 0 6px rgba(74,222,128,0.4); }
.udp-dot.recent { background: var(--color-amber); }
.udp-count { font-size: var(--text-sm); color: var(--color-text-secondary); }
.udp-last { font-size: var(--text-xs); color: var(--color-text-muted); }

.autostart-tabs { display: flex; gap: 0; margin-bottom: 0; border-bottom: 1px solid var(--color-border); }
.autostart-tab {
  background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--color-text-muted); font-size: var(--text-xs); font-family: inherit;
  padding: 8px 16px; cursor: pointer; margin-bottom: -1px;
  transition: color .15s, border-color .15s;
}
.autostart-tab.active { color: var(--color-text-primary); border-bottom-color: var(--color-accent); }
.autostart-panel { display: none; padding-top: 16px; }
.autostart-panel.active { display: block; }
.code-block {
  background: var(--color-bg); border: 1px solid var(--color-border);
  border-radius: var(--radius-sm); padding: 12px 14px;
  font-family: var(--font-mono); font-size: var(--text-xs);
  color: var(--color-text-secondary); white-space: pre-wrap; word-break: break-all;
  margin: 10px 0;
}
.step { margin: 10px 0; color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.5; }
.step b { color: var(--color-text-primary); }
</style>
</head>
<body>
<div id="pf-nav"></div>
<script src="/static/js/nav.js"></script>

<!-- ── Point your game here ──────────────────────────────────────── -->
<div class="section">
  <div class="section-title">Point your game here</div>
  <div class="ip-card">
    <div class="ip-card-title">This machine's local IP address</div>
    <div id="ip-list" class="ip-list">
      <div class="ip-loading">Detecting…</div>
    </div>
    <div class="game-strings" id="game-strings" style="display:none"></div>
    <div class="ip-uptime" id="ip-uptime"></div>
  </div>
</div>

<!-- ── UDP Status ─────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-title">UDP Status</div>
  <div class="udp-panel" id="udp-panel">
    <div class="udp-card" id="udp-forza">
      <div class="udp-game">Forza</div>
      <div class="udp-status"><div class="udp-dot" id="dot-forza"></div><span class="udp-count" id="cnt-forza">0 packets</span></div>
      <div class="udp-last" id="last-forza">—</div>
    </div>
    <!-- ACC + F1 cards parked — see docs/specs/park-acc-f1.md -->
  </div>
</div>

<!-- ── Storage ────────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-title">Storage</div>
  <div class="field">
    <label>Storage path — where raw archives and session JSON files are saved</label>
    <div class="path-row">
      <input type="text" id="storage_path" placeholder="/mnt/usb/simtelemetry"
             oninput="scheduleValidate()" onblur="validateNow()">
      <button type="button" class="btn-browse" onclick="toggleBrowse()">Browse</button>
    </div>
    <div id="path-status" class="path-status"></div>
    <div id="browse-panel" class="browse-panel" style="display:none">
      <div class="browse-toolbar">
        <div id="breadcrumb" class="breadcrumb"></div>
        <button type="button" class="btn-use" onclick="selectDir()">Use this directory</button>
      </div>
      <div id="dir-list" class="dir-list"></div>
    </div>
    <div class="hint">USB mount point on Pi; any writable directory on Mac/Windows.</div>
  </div>
  <div id="disk-info" class="disk-info"></div>
</div>

<!-- ── Session ────────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-title">Session</div>
  <div class="field">
    <label>Session timeout (seconds) — silence before a session is closed</label>
    <input type="number" id="session_timeout_s" min="2" max="120" step="1">
  </div>
</div>

<!-- ── UDP Ports ──────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-title">UDP Ports <span style="color:var(--color-text-muted);font-size:var(--text-xs);margin-left:8px">restart required for port changes</span></div>
  <div class="ports-grid">
    <div class="field">
      <label>Forza Motorsport</label>
      <input type="number" id="port_forza" min="1024" max="65535">
    </div>
    <!-- ACC + F1 port fields parked — see docs/specs/park-acc-f1.md -->
  </div>
</div>

<!-- ── Auto-start ─────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-title">Auto-start</div>
  <div class="autostart-tabs">
    <button class="autostart-tab" id="tab-mac"     onclick="setOsTab('mac')">Mac</button>
    <button class="autostart-tab" id="tab-linux"   onclick="setOsTab('linux')">Linux / Pi</button>
    <button class="autostart-tab" id="tab-windows" onclick="setOsTab('windows')">Windows</button>
  </div>

  <div class="autostart-panel" id="panel-mac">
    <div class="step">From the cloned repo, run <b>install-mac.sh</b> once. It copies a launchd plist and loads it — Pacefinder will start on login and restart if it crashes.</div>
    <div class="code-block">bash install-mac.sh</div>
    <div class="step">Check status: <span style="font-family:monospace;color:#888">launchctl list | grep pacefinder</span></div>
    <div class="step">View logs: <span style="font-family:monospace;color:#888">tail -f ~/Library/Logs/pacefinder.log</span></div>
  </div>

  <div class="autostart-panel" id="panel-linux">
    <div class="step">Copy the service file and enable it with systemd:</div>
    <div class="code-block">sudo cp pacefinder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pacefinder
sudo systemctl start pacefinder</div>
    <div class="step">Check status: <span style="font-family:monospace;color:#888">sudo systemctl status pacefinder</span></div>
    <div class="step">View logs: <span style="font-family:monospace;color:#888">sudo journalctl -u pacefinder -f</span></div>
    <div class="step" style="margin-top:14px;font-size:.75rem;color:var(--color-text-muted)">
      <b>Already installed under the old <code>simtelemetry</code> name?</b> Migrate once:
    </div>
    <div class="code-block">sudo systemctl stop simtelemetry
sudo systemctl disable simtelemetry
sudo rm /etc/systemd/system/simtelemetry.service
sudo cp pacefinder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pacefinder
sudo systemctl start pacefinder</div>
  </div>

  <div class="autostart-panel" id="panel-windows">
    <div class="step"><b>Option 1 — Task Scheduler (recommended)</b></div>
    <div class="step">1. Open <b>Task Scheduler</b> → Create Basic Task<br>
    2. Trigger: <b>When I log on</b><br>
    3. Action: Start a program → <b>pythonw.exe</b> with argument <b>C:\path\to\listener.py</b><br>
    4. Check "Run whether user is logged on or not" for always-on.</div>
    <div class="step"><b>Option 2 — Startup folder</b></div>
    <div class="step">Press <b>Win+R</b>, type <span style="font-family:monospace;color:#888">shell:startup</span>, and drop a shortcut to <b>pythonw listener.py</b> there.</div>
    <div class="step"><b>Python install:</b> Download from <a href="https://python.org/downloads" target="_blank" style="color:var(--color-green)">python.org/downloads</a>. Check "Add Python to PATH" during install. Use <b>pythonw.exe</b> (not python.exe) to run without a console window.</div>
  </div>
</div>

<!-- ── AI Analysis ────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-title">AI Analysis</div>
  <div class="field">
    <label>Anthropic API key — used for post-session race analysis</label>
    <input type="password" id="anthropic_api_key" placeholder="sk-ant-…" autocomplete="off">
    <div class="hint">Get a key at console.anthropic.com. Stored locally in simtelemetry.config.json.</div>
  </div>
  <div class="field">
    <label>Model</label>
    <select id="anthropic_model" style="width:100%;background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-primary);font-family:inherit;font-size:var(--text-sm);padding:8px 10px;border-radius:var(--radius-sm);outline:none">
      <option value="claude-sonnet-4-6">Claude Sonnet 4.6 — best balance of speed and quality</option>
      <option value="claude-opus-4-7">Claude Opus 4.7 — most capable, slower</option>
      <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5 — fastest, lowest cost</option>
    </select>
  </div>
</div>

<!-- ── Display ────────────────────────────────────────────────────── -->
<div class="section">
  <div class="section-title">Display</div>
  <div class="field">
    <label>Time format</label>
    <select id="time_format" style="width:100%;background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-primary);font-family:inherit;font-size:var(--text-sm);padding:8px 10px;border-radius:var(--radius-sm);outline:none">
      <option value="24h">24-hour — 14:02 (default)</option>
      <option value="12h">12-hour — 2:02 PM</option>
    </select>
    <div class="hint">Applies to session times across the app. Pi log timestamps stay 24-hour ISO.</div>
  </div>
  <div class="field">
    <label style="display:flex;align-items:center;gap:10px;cursor:pointer">
      <input type="checkbox" id="debug_mode" style="width:auto;margin:0">
      Debug mode
    </label>
    <div class="hint">When on, the live dashboard speaks &ldquo;I think the race is over&rdquo; the moment race-end is detected — handy for sanity-checking detection timing against what happened on track.</div>
  </div>
</div>

<button class="btn" id="save-btn" onclick="save()">Save</button>
<div class="toast" id="toast"></div>

<script>
// ── OS tab detection ─────────────────────────────────────────────────────────
function detectOs() {
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes('win')) return 'windows';
  if (ua.includes('mac')) return 'mac';
  return 'linux';
}

function setOsTab(os) {
  ['mac','linux','windows'].forEach(k => {
    document.getElementById('tab-' + k).classList.toggle('active', k === os);
    document.getElementById('panel-' + k).classList.toggle('active', k === os);
  });
}

// ── IP card ──────────────────────────────────────────────────────────────────
let _ipsData = null;

async function loadIps() {
  try {
    const d = await fetch('/setup/ips').then(r => r.json());
    _ipsData = d;
    const listEl = document.getElementById('ip-list');
    const gsEl   = document.getElementById('game-strings');
    if (!d.ips || !d.ips.length) {
      listEl.innerHTML = '<div class="ip-loading" style="color:var(--color-red)">Could not detect IP — check network connection.</div>';
      return;
    }
    listEl.innerHTML = d.ips.map(ip => `
      <div class="ip-row">
        <span class="ip-addr">${ip}</span>
        <button class="copy-btn" onclick="copyIp('${ip}',this)">Copy</button>
      </div>`).join('');

    const primary = d.ips[0];
    const ports = d.ports || {};
    const games = [
      { label: 'Forza Motorsport', value: `IP: ${primary}  Port: ${ports.forza_motorsport || 5300}  Format: Car Dash` },
      // ACC + F1 entries parked — see docs/specs/park-acc-f1.md
    ];
    gsEl.style.display = '';
    gsEl.innerHTML = games.map(g => `
      <div class="game-string-row">
        <span class="game-label">${g.label}</span>
        <span class="game-value">${g.value}</span>
        <button class="copy-btn" onclick="copyText('${g.value}',this)">Copy</button>
      </div>`).join('');

    const h = Math.floor(d.uptime_s / 3600);
    const m = Math.floor((d.uptime_s % 3600) / 60);
    const s = d.uptime_s % 60;
    const upStr = h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`;
    document.getElementById('ip-uptime').textContent = `Listener uptime: ${upStr}`;
  } catch(e) {
    document.getElementById('ip-list').innerHTML = '<div class="ip-loading" style="color:var(--color-red)">Failed to load: ' + e.message + '</div>';
  }
}

function copyIp(ip, btn) { copyText(ip, btn); }
function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!'; btn.classList.add('copied');
    setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); }, 1500);
  });
}

// ── UDP status polling ───────────────────────────────────────────────────────
let _udpPollTimer = null;

async function pollUdp() {
  try {
    const d = await fetch('/setup/ips').then(r => r.json());
    const recv = d.udp_received || {};
    const last = d.udp_last_at  || {};
    const now  = new Date();
    ['forza_motorsport','acc','f1'].forEach(game => {
      const key = game === 'forza_motorsport' ? 'forza' : game;
      const cnt  = recv[game] || 0;
      const lastStr = last[game];
      const dot  = document.getElementById('dot-' + key);
      const cntEl = document.getElementById('cnt-' + key);
      const lastEl = document.getElementById('last-' + key);
      cntEl.textContent = cnt.toLocaleString() + ' packets';
      if (lastStr) {
        const ago = Math.round((now - new Date(lastStr)) / 1000);
        lastEl.textContent = ago < 5 ? 'just now' : ago < 60 ? ago + 's ago' : Math.round(ago/60) + 'm ago';
        dot.className = 'udp-dot ' + (ago < 5 ? 'active' : ago < 30 ? 'recent' : '');
      } else {
        lastEl.textContent = cnt > 0 ? 'receiving' : '—';
        dot.className = 'udp-dot' + (cnt > 0 ? ' active' : '');
      }
    });
  } catch(e) {}
  _udpPollTimer = setTimeout(pollUdp, 2000);
}

// ── path validation ──────────────────────────────────────────────────────────
let _vTimer = null;
function scheduleValidate() { clearTimeout(_vTimer); _vTimer = setTimeout(validateNow, 350); }
function validateNow() { validatePath(document.getElementById('storage_path').value.trim()); }

async function validatePath(path) {
  const el = document.getElementById('path-status');
  if (!path) { el.textContent = ''; return; }
  el.style.color = '#555'; el.textContent = 'checking…';
  try {
    const d = await fetch('/browse?path=' + encodeURIComponent(path)).then(r => r.json());
    if (d.exists) {
      el.style.color = '#22c55e'; el.textContent = '✓ path exists';
    } else if (d.parent_exists) {
      el.style.color = '#f59e0b'; el.textContent = '⚠ will be created on save';
    } else {
      el.style.color = '#ef4444'; el.textContent = '✗ parent directory does not exist';
    }
  } catch(e) { el.style.color = '#444'; el.textContent = ''; }
}

// ── file browser ─────────────────────────────────────────────────────────────
let _browseOpen = false;

function toggleBrowse() {
  _browseOpen = !_browseOpen;
  document.getElementById('browse-panel').style.display = _browseOpen ? 'block' : 'none';
  if (_browseOpen) loadPath(document.getElementById('storage_path').value.trim() || '/');
}

async function loadPath(path) {
  const panel = document.getElementById('browse-panel');
  const list  = document.getElementById('dir-list');
  panel.dataset.cur = path;
  list.innerHTML = '<div class="dir-empty">Loading…</div>';
  try {
    const d = await fetch('/browse?path=' + encodeURIComponent(path)).then(r => r.json());
    panel.dataset.cur = d.path;
    renderBreadcrumb(d.path);
    list.innerHTML = '';
    if (d.parent && d.parent !== d.path) {
      const up = mkDir('↑  ..', () => loadPath(d.parent));
      up.style.color = '#444';
      list.appendChild(up);
    }
    if (!d.entries || !d.entries.length) {
      list.innerHTML += '<div class="dir-empty">No subdirectories</div>';
    }
    (d.entries || []).forEach(e => {
      const full = d.path.replace(/\/+$/, '') + '/' + e.name;
      list.appendChild(mkDir('▸  ' + e.name, () => loadPath(full)));
    });
  } catch(e) {
    list.innerHTML = '<div class="dir-empty" style="color:var(--color-red)">' + e.message + '</div>';
  }
}

function mkDir(text, onclick) {
  const el = document.createElement('div');
  el.className = 'dir-item'; el.textContent = text; el.onclick = onclick;
  return el;
}

function renderBreadcrumb(path) {
  const bc = document.getElementById('breadcrumb');
  const parts = path.split('/').filter(Boolean);
  let html = '<span class="crumb" data-p="/">/</span>';
  let built = '';
  parts.forEach((seg, i) => {
    built += '/' + seg;
    html += '<span class="crumb-sep"> / </span>';
    const cls = i === parts.length - 1 ? 'crumb-cur' : 'crumb';
    html += '<span class="' + cls + '" data-p="' + built + '">' + seg + '</span>';
  });
  bc.innerHTML = html;
  bc.querySelectorAll('.crumb').forEach(el => { el.onclick = () => loadPath(el.dataset.p); });
}

function selectDir() {
  const path = document.getElementById('browse-panel').dataset.cur;
  if (path) { document.getElementById('storage_path').value = path; validatePath(path); }
  _browseOpen = false;
  document.getElementById('browse-panel').style.display = 'none';
}

// ── config load / save ────────────────────────────────────────────────────────
async function load() {
  const d = await fetch('/config').then(r => r.json());
  document.getElementById('storage_path').value      = d.storage_path || '';
  document.getElementById('session_timeout_s').value = d.session_timeout_s || 10;
  document.getElementById('port_forza').value        = (d.ports || {}).forza_motorsport || 5300;
  // Server never returns the real key (see _redact_config). Show a 'set'
  // placeholder when one is configured so the user knows it's there without
  // exposing the value. Typing a new key overwrites; leaving blank keeps it.
  const keyEl = document.getElementById('anthropic_api_key');
  keyEl.value = '';
  keyEl.placeholder = d.anthropic_api_key_set ? '•••• key set — leave blank to keep' : 'sk-ant-…';
  const modelSel = document.getElementById('anthropic_model');
  if (d.anthropic_model) modelSel.value = d.anthropic_model;
  document.getElementById('time_format').value = (d.time_format === '12h') ? '12h' : '24h';
  document.getElementById('debug_mode').checked = !!d.debug_mode;
  renderDisk(d.disk);
  if (d.storage_path) validatePath(d.storage_path);
}

function renderDisk(disk) {
  const el = document.getElementById('disk-info');
  if (!disk || disk.total_gb == null) { el.textContent = ''; return; }
  const pct = Math.round(disk.used_gb / disk.total_gb * 100);
  el.innerHTML = `
    <div class="disk-bar-bg"><div class="disk-bar-fill" style="width:${pct}%"></div></div>
    <span>${disk.used_gb} GB used of ${disk.total_gb} GB &mdash; <span>${disk.free_gb} GB free</span></span>`;
}

async function save() {
  const btn = document.getElementById('save-btn');
  const toast = document.getElementById('toast');
  btn.disabled = true; toast.className = 'toast';
  const keyVal = document.getElementById('anthropic_api_key').value.trim();
  const body = {
    storage_path:      document.getElementById('storage_path').value.trim(),
    session_timeout_s: parseInt(document.getElementById('session_timeout_s').value, 10),
    ports: {
      forza_motorsport: parseInt(document.getElementById('port_forza').value, 10),
    },
    anthropic_model:   document.getElementById('anthropic_model').value,
    time_format:       document.getElementById('time_format').value,
    debug_mode:        document.getElementById('debug_mode').checked,
  };
  // Only send the key when the user actually typed one — blank means
  // "keep existing." Server treats "" as no-op, null as explicit clear.
  if (keyVal) body.anthropic_api_key = keyVal;
  try {
    const r = await fetch('/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const d = await r.json();
    if (r.ok) {
      toast.className = 'toast ok'; toast.textContent = d.message || 'Saved.';
      renderDisk(d.disk); validatePath(body.storage_path);
    } else {
      toast.className = 'toast err'; toast.textContent = d.error || 'Save failed.';
    }
  } catch(e) { toast.className = 'toast err'; toast.textContent = 'Network error: ' + e.message; }
  btn.disabled = false;
}

// ── init ─────────────────────────────────────────────────────────────────────
setOsTab(detectOs());
loadIps();
pollUdp();
load();
</script>
</body>
</html>
"""
