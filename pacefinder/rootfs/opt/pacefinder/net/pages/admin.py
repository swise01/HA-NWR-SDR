ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pacefinder · Admin</title>
<link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/base.css">
</head>
<body>
<div class="topbar">
  <h1>Pacefinder</h1>
  <nav>
    <a href="/dashboard">Live</a>
    <a href="/sessions">Sessions</a>
    <a href="/setup">Setup</a>
    <a href="/admin" class="active">Admin</a>
  </nav>
</div>

<div class="tabs">
  <button class="tab active" onclick="setGame('forza_motorsport',this)">Forza</button>
  <button class="tab" onclick="setGame('acc',this)">ACC</button>
  <button class="tab" onclick="setGame('f1',this)">F1</button>
</div>

<div class="ctrl-grid">
  <div class="ctrl">
    <label>Speed <span class="val"><span id="speed-val">0</span> mph</span></label>
    <input type="range" id="speed" min="0" max="220" step="1" value="0" oninput="sync('speed','speed-val')">
  </div>
  <div class="ctrl">
    <label>RPM <span class="val"><span id="rpm-val">1000</span></span></label>
    <input type="range" id="rpm" min="0" max="12000" step="100" value="1000" oninput="sync('rpm','rpm-val')">
  </div>
  <div class="ctrl">
    <label>Throttle <span class="val"><span id="thr-val">0</span>%</span></label>
    <input type="range" id="throttle" min="0" max="100" step="1" value="0" oninput="sync('throttle','thr-val')">
  </div>
  <div class="ctrl">
    <label>Brake <span class="val"><span id="brk-val">0</span>%</span></label>
    <input type="range" id="brake" min="0" max="100" step="1" value="0" oninput="sync('brake','brk-val')">
  </div>
</div>

<div class="ctrl" style="margin-bottom:16px">
  <label>Gear</label>
  <div class="gear-row" id="gear-row">
    <button class="gear-btn" onclick="setGear(-1,this)">R</button>
    <button class="gear-btn" onclick="setGear(0,this)">N</button>
    <button class="gear-btn active" onclick="setGear(1,this)">1</button>
    <button class="gear-btn" onclick="setGear(2,this)">2</button>
    <button class="gear-btn" onclick="setGear(3,this)">3</button>
    <button class="gear-btn" onclick="setGear(4,this)">4</button>
    <button class="gear-btn" onclick="setGear(5,this)">5</button>
    <button class="gear-btn" onclick="setGear(6,this)">6</button>
    <button class="gear-btn" onclick="setGear(7,this)">7</button>
    <button class="gear-btn" onclick="setGear(8,this)">8</button>
  </div>
</div>

<div class="ctrl" style="margin-bottom:16px">
  <label>Lap</label>
  <div class="lap-row">
    <input type="number" class="lap-input" id="lap" value="1" min="0" max="99">
    <button class="btn-nextlap" onclick="nextLap()">Next Lap ↑</button>
  </div>
</div>

<hr class="admin-divider">

<div class="preset-row">
  <button class="preset-btn" onclick="applyPreset('idle')">Idle</button>
  <button class="preset-btn" onclick="applyPreset('cruise')">Cruise</button>
  <button class="preset-btn" onclick="applyPreset('full')">Full Throttle</button>
  <button class="preset-btn" onclick="applyPreset('brake')">Braking</button>
  <button class="preset-btn" onclick="applyPreset('pit')">Pit Lane</button>
</div>

<div class="action-row" style="margin-top:20px">
  <button class="btn-inject" onclick="sendOnce()">Send Once</button>
  <button class="btn-stream" id="stream-btn" onclick="toggleStream()">▶ Stream</button>
  <select class="hz-sel" id="hz-sel">
    <option value="1000">1 Hz</option>
    <option value="200">5 Hz</option>
    <option value="100" selected>10 Hz</option>
    <option value="50">20 Hz</option>
    <option value="33">30 Hz</option>
  </select>
  <div class="sent-lbl">Sent: <span id="sent-count">0</span></div>
</div>
<div class="inject-err" id="inject-err"></div>

<script>
let _game = 'forza_motorsport';
let _gear = 1;
let _streamTimer = null;
let _sentCount = 0;

function setGame(g, el) {
  _game = g;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
}

function sync(sliderId, valId) {
  document.getElementById(valId).textContent = document.getElementById(sliderId).value;
}

function setGear(g, el) {
  _gear = g;
  document.querySelectorAll('.gear-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

function nextLap() {
  const el = document.getElementById('lap');
  el.value = parseInt(el.value || 0) + 1;
}

const PRESETS = {
  idle:   { speed: 0,   rpm: 900,  throttle: 0,  brake: 0,  gear: 0  },
  cruise: { speed: 100, rpm: 4000, throttle: 35, brake: 0,  gear: 5  },
  full:   { speed: 160, rpm: 9500, throttle: 100,brake: 0,  gear: 6  },
  brake:  { speed: 80,  rpm: 5000, throttle: 0,  brake: 90, gear: 4  },
  pit:    { speed: 37,  rpm: 2500, throttle: 20, brake: 0,  gear: 2  },
};

function applyPreset(name) {
  const p = PRESETS[name];
  if (!p) return;
  document.getElementById('speed').value    = p.speed;    sync('speed','speed-val');
  document.getElementById('rpm').value      = p.rpm;      sync('rpm','rpm-val');
  document.getElementById('throttle').value = p.throttle; sync('throttle','thr-val');
  document.getElementById('brake').value    = p.brake;    sync('brake','brk-val');
  // set gear button
  const gearMap = { '-1':'R', '0':'N', '1':'1','2':'2','3':'3','4':'4','5':'5','6':'6','7':'7','8':'8' };
  document.querySelectorAll('.gear-btn').forEach(b => {
    const g = b.textContent.trim();
    const match = String(p.gear) === Object.keys(gearMap).find(k => gearMap[k] === g);
    b.classList.toggle('active', match);
    if (match) _gear = p.gear;
  });
  _gear = p.gear;
  document.querySelectorAll('.gear-btn').forEach(b => {
    b.classList.remove('active');
    if ((p.gear === -1 && b.textContent === 'R') ||
        (p.gear === 0 && b.textContent === 'N') ||
        (String(p.gear) === b.textContent)) {
      b.classList.add('active');
    }
  });
}

function params() {
  return {
    game:         _game,
    speed_mph:    parseFloat(document.getElementById('speed').value),
    rpm:          parseFloat(document.getElementById('rpm').value),
    throttle_pct: parseFloat(document.getElementById('throttle').value),
    brake_pct:    parseFloat(document.getElementById('brake').value),
    gear:         _gear,
    lap:          parseInt(document.getElementById('lap').value || 1),
  };
}

async function sendOnce() {
  const errEl = document.getElementById('inject-err');
  errEl.textContent = '';
  try {
    const r = await fetch('/admin/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params()),
    });
    const d = await r.json();
    if (!r.ok) { errEl.textContent = d.error || 'Inject failed'; return; }
    _sentCount += d.sent || 1;
    document.getElementById('sent-count').textContent = _sentCount;
  } catch(e) { errEl.textContent = 'Network error: ' + e.message; }
}

function toggleStream() {
  const btn = document.getElementById('stream-btn');
  if (_streamTimer) {
    clearInterval(_streamTimer);
    _streamTimer = null;
    btn.classList.remove('on');
    btn.textContent = '▶ Stream';
  } else {
    const hz = parseInt(document.getElementById('hz-sel').value);
    _streamTimer = setInterval(sendOnce, hz);
    btn.classList.add('on');
    btn.textContent = '■ Stop';
  }
}
</script>
</body>
</html>
"""
