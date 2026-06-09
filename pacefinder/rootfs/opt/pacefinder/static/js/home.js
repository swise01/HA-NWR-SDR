// Home page — / (idle landing)
// Fetches /home/data and renders the page. Polls /status every 10 s so
// the recording indicator flips green→red when telemetry starts (the
// driver can then click "Live dashboard" knowing it has a session).

// car class resolved via shared pfCarClass() — see static/js/class.js

function fmtLap(s){if(s == null) return '—'; const m = Math.floor(s/60); return m+':'+(s%60).toFixed(3).padStart(6,'0');}
function fmtShortDate(iso){if(!iso) return '—'; return new Date(iso).toLocaleDateString([], {month:'short', day:'numeric'});}
let _tf='24h';  // user time-format pref, set from /home/data
function fmtTime(iso){if(!iso) return ''; return new Date(iso).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', hour12:_tf==='12h'});}
function fmtRelative(iso){
  if(!iso) return '—';
  const dt = new Date(iso);
  const days = Math.floor((Date.now() - dt.getTime()) / 86400000);
  if(days < 1){
    const hours = Math.floor((Date.now() - dt.getTime()) / 3600000);
    if(hours < 1) return 'just now';
    if(hours === 1) return '1 hour ago';
    return hours + ' hours ago';
  }
  if(days === 1) return '1 day ago';
  if(days < 30) return days + ' days ago';
  const months = Math.floor(days / 30);
  if(months === 1) return '1 month ago';
  if(months < 12) return months + ' months ago';
  return Math.floor(months / 12) + ' year' + (Math.floor(months/12) === 1 ? '' : 's') + ' ago';
}
function fmtBytes(gb){
  if(gb == null) return '—';
  if(gb < 1) return (gb * 1024).toFixed(0) + ' MB';
  return gb.toFixed(1) + ' GB';
}
function escapeHtml(s){
  if(s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function carDisplay(s){
  // Priority: nickname > resolved name > "Car #N"
  if(s.car_nickname) return s.car_nickname;
  if(s.car_name)     return s.car_name;
  if(s.car && s.car !== 'unknown' && !/^Unknown Car/i.test(s.car)) return s.car;
  if(s.car_ordinal != null) return 'Car #' + s.car_ordinal;
  return '—';
}

async function init(){
  let d;
  try{d = await fetch('/home/data').then(r => r.json());}
  catch(e){ return; }  // nav.js owns the live status pill
  _tf = d.time_format || '24h';
  renderHeroLast(d.last_session, d.pb_at_track_s, d.stats);
  loadWatchlist();
  loadWorstSector();
  loadCareer();
  renderTopCircuits(d.top_circuits || []);
  renderTopCars(d.top_cars || []);
  renderRecent(d.recent_sessions || []);
}

// Hero card at the top of Home — answers "what happened while I was
// away?" and surfaces the single best CTA: jump into the trace you
// just drove. Replaces the throat-clearing "Welcome back" strip.
function renderHeroLast(last, pbAtTrack, stats){
  const hero = document.getElementById('hero-last');
  const empty = document.getElementById('hero-empty');
  if(!last || !last.session_id){
    if(stats && stats.total_sessions){
      // Has sessions but couldn't load last — fail silent, leave page bare.
      return;
    }
    empty.style.display = '';
    return;
  }
  hero.style.display = '';
  // Outline (speed-coloured mini, lazy-loaded). Uses the same renderer
  // as /sessions and /circuits — last-session's own best lap so the
  // shape is what the driver actually drove.
  const outline = document.getElementById('hl-outline');
  if(last.session_id && last.best_lap_number != null){
    outline.dataset.sid = last.session_id;
    outline.dataset.lap = last.best_lap_number;
  }
  // Track + car names with deep links
  const track = last.track || 'Unknown circuit';
  const carName = carDisplay(last);
  document.getElementById('hl-track').textContent = track;
  document.getElementById('hl-track-link').href =
    '/sessions/track?name=' + encodeURIComponent(track);
  document.getElementById('hl-car').textContent = carName;
  if(last.car_ordinal != null){
    document.getElementById('hl-car-link').href = '/cars/' + last.car_ordinal;
  } else {
    document.getElementById('hl-car-link').removeAttribute('href');
  }
  const cc = pfCarClass(last.car_pi, last.car_class);
  const cb = document.getElementById('hl-class-badge');
  if(cc){ cb.textContent = cc; cb.style.display = ''; }
  else { cb.style.display = 'none'; }
  // Big lap time + ± vs the same car at this circuit
  document.getElementById('hl-laptime').textContent = fmtLap(last.best_lap_time_s);
  const deltaEl = document.getElementById('hl-delta');
  if(last.best_lap_time_s != null && pbAtTrack != null){
    const d = last.best_lap_time_s - pbAtTrack;
    if(Math.abs(d) < 0.005){
      deltaEl.textContent = '= car PB here';
      deltaEl.className = 'hl-delta same';
    } else if(d < 0){
      // New PB. The trophy framing matches the session-detail hero.
      deltaEl.textContent = '★ New PB in this car here';
      deltaEl.className = 'hl-delta gain';
    } else {
      deltaEl.textContent = '+' + d.toFixed(2) + 's vs your PB here';
      deltaEl.className = 'hl-delta lost';
    }
  } else if(last.best_lap_time_s != null){
    deltaEl.textContent = 'First session in this car here';
    deltaEl.className = 'hl-delta';
  } else {
    deltaEl.textContent = 'No valid lap';
    deltaEl.className = 'hl-delta';
  }
  // Meta line: when + conditions
  const bits = [fmtRelative(last.started_at)];
  if(last.weather_condition) bits.push(last.weather_condition);
  if(last.tyre_compound)     bits.push(last.tyre_compound);
  if(last.track_temp_c != null) bits.push(Math.round(last.track_temp_c) + '°C');
  document.getElementById('hl-meta').textContent = bits.join(' · ');
  // CTAs
  const sidQ = '?id=' + encodeURIComponent(last.session_id);
  document.getElementById('hl-cta-telemetry').href = '/sessions/telemetry' + sidQ;
  document.getElementById('hl-cta-session').href = '/sessions/session' + sidQ;
  // Kick the lazy outline loader now that the data-* are set.
  if(window.pfLoadMinis) window.pfLoadMinis(hero);
}


function renderTopCircuits(circuits){
  const el = document.getElementById('top-circuits');
  if(!circuits.length){el.innerHTML = '<div class="panel-empty">No circuits yet.</div>'; return;}
  el.innerHTML = circuits.map(c => {
    const href = '/sessions/track?name=' + encodeURIComponent(c.track);
    return `<a href="${href}" class="panel-row">
      <div>
        <div class="panel-name">${escapeHtml(c.track)}</div>
        <div class="panel-meta">${c.sessions_count} session${c.sessions_count === 1 ? '' : 's'} · ${c.laps_count} lap${c.laps_count === 1 ? '' : 's'}</div>
      </div>
      <div class="panel-pb">${fmtLap(c.best_lap_s)}</div>
      <div class="panel-arrow">→</div>
    </a>`;
  }).join('');
}

function renderTopCars(cars){
  const el = document.getElementById('top-cars');
  if(!cars.length){el.innerHTML = '<div class="panel-empty">No cars yet.</div>'; return;}
  el.innerHTML = cars.map(c => {
    const href = '/cars/' + c.ordinal;
    const name = c.nickname || c.name || ('Car #' + c.ordinal);
    const _cc = pfCarClass(c.car_pi, c.class);
    const cls = _cc ? `<span class="class-badge" style="margin-left:6px">${_cc}</span>` : '';
    return `<a href="${href}" class="panel-row">
      <div>
        <div class="panel-name">${escapeHtml(name)} ${cls}</div>
        <div class="panel-meta">${c.sessions_count} session${c.sessions_count === 1 ? '' : 's'} · ${c.laps_count} lap${c.laps_count === 1 ? '' : 's'}${c.name && c.nickname ? ' · ' + escapeHtml(c.name) : ''}</div>
      </div>
      <div class="panel-pb">${fmtLap(c.best_lap_s)}</div>
      <div class="panel-arrow">→</div>
    </a>`;
  }).join('');
}

function renderRecent(recents){
  const list = document.getElementById('recent-list');
  if(!recents.length){
    list.innerHTML = '<div class="recent-empty">No sessions recorded yet. Open the <a href="/dashboard">live dashboard</a> and drive.</div>';
    return;
  }
  list.innerHTML = recents.map((s, i) => {
    const href = '/sessions/session?id=' + encodeURIComponent(s.session_id);
    const date = fmtShortDate(s.started_at);
    const time = fmtTime(s.started_at);
    const carName = carDisplay(s);
    const _cc = pfCarClass(s.car_pi, s.car_class);
    const cls = _cc ? `<span class="class-badge">${_cc}</span>` : '';
    const condBits = [];
    if(s.weather_condition) condBits.push(s.weather_condition);
    if(s.tyre_compound) condBits.push(s.tyre_compound);
    if(s.track_temp_c != null) condBits.push(Math.round(s.track_temp_c) + '°C');
    return `<a href="${href}" class="recent-row${i === 0 ? ' lead' : ''}">
      <span class="recent-date">${date}<small>${time}</small></span>
      <span class="recent-track">${escapeHtml(s.track || '—')}</span>
      <span class="recent-car">${escapeHtml(carName)} ${cls}</span>
      <span class="recent-cond">${condBits.join(' · ')}</span>
      <span class="recent-time">${fmtLap(s.best_lap_time_s)}</span>
      <span class="recent-arrow">→</span>
    </a>`;
  }).join('');
}

// ── Regression watchlist ─────────────────────────────────────────
// "Where you're slipping" — async because it shouldn't block the
// initial paint. Hides the whole section when nothing's regressing
// (no fake "all good" card; that's gamification, not coaching).
async function loadWatchlist(){
  let rows;
  try{ rows = await fetch('/home/regression-watchlist').then(r => r.json()); }
  catch(e){ return; }
  if(!Array.isArray(rows) || rows.length === 0) return;
  const wrap = document.getElementById('watchlist');
  const grid = document.getElementById('watchlist-grid');
  grid.innerHTML = rows.map(r => {
    const carDisplay = r.car_nickname || r.car_name || ('Car #' + r.car_ordinal);
    const cc = pfCarClass(r.car_pi, r.car_class);
    const cls = cc ? `<span class="class-badge">${cc}</span>` : '';
    const outAttr = (r.pb_session_id && r.pb_lap_number != null)
      ? ` data-sid="${escapeHtml(r.pb_session_id)}" data-lap="${r.pb_lap_number}"` : '';
    const href = '/sessions/telemetry?id=' + encodeURIComponent(r.last_session_id);
    return `<a href="${href}" class="wl-card">
      <div class="wl-outline track-outline"${outAttr}></div>
      <div class="wl-body">
        <div class="wl-name">${escapeHtml(r.track)}</div>
        <div class="wl-meta">${escapeHtml(carDisplay)} ${cls}</div>
        ${renderSpark(r.sparkline)}
        <div class="wl-delta">+${r.delta_s.toFixed(2)}s vs your earlier pace</div>
      </div>
      <div class="wl-arrow">→</div>
    </a>`;
  }).join('');
  wrap.style.display = '';
  if(window.pfLoadMinis) window.pfLoadMinis(grid);
}
// Compact red sparkline of last 6 best-lap times. Y inverted (lower
// = faster = up), so a downward slope = improving, upward = the
// regression we're flagging.
function renderSpark(vals){
  if(!vals || vals.length < 2) return '<div class="wl-spark-empty"></div>';
  const w = 100, h = 26;
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const rng = Math.max(mx - mn, 0.1);
  const xs = vals.map((_, i) => (i / (vals.length - 1)) * w);
  const ys = vals.map(v => h - ((v - mn) / rng) * (h - 4) - 2);
  const pts = xs.map((x, i) => x.toFixed(1) + ',' + ys[i].toFixed(1)).join(' ');
  const lastX = xs[xs.length - 1].toFixed(1);
  const lastY = ys[ys.length - 1].toFixed(1);
  return `<svg class="wl-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <polyline points="${pts}" fill="none" stroke="var(--color-red,#ef4444)" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" opacity=".9"/>
    <circle cx="${lastX}" cy="${lastY}" r="2.4" fill="var(--color-red,#ef4444)"/>
  </svg>`;
}

// ── Worst sector card — single biggest leak ─────────────────────
// Async; hidden when no sector exceeds the server's 0.3s threshold.
// Deep-links into the track detail page so the user can scrub any
// session there.
async function loadWorstSector(){
  let w;
  try{ w = await fetch('/home/worst-sector').then(r => r.json()); }
  catch(e){ return; }
  if(!w || !w.track || !w.sector) return;
  const card = document.getElementById('leak-card');
  document.getElementById('leak-sector').textContent = w.sector;
  document.getElementById('leak-track').textContent = w.track;
  document.getElementById('leak-gap').textContent = '+' + w.avg_gap_s.toFixed(2) + 's';
  document.getElementById('leak-sub').textContent =
    'on average across ' + w.session_count + ' session' + (w.session_count === 1 ? '' : 's');
  // Outline: the track's PB lap (any car, any session) — same target
  // the watchlist + circuits page use. Speed-coloured via track_mini.
  if(w.pb_session_id && w.pb_lap_number != null){
    const out = document.getElementById('leak-outline');
    out.dataset.sid = w.pb_session_id;
    out.dataset.lap = w.pb_lap_number;
  }
  // CTA: land on the circuit detail. From there the user picks any
  // session to scrub. Trying to deep-link a specific session was
  // tempting but the choice "which session?" is genuinely the
  // driver's — the leak is across all of them.
  card.href = '/sessions/track?name=' + encodeURIComponent(w.track);
  card.style.display = '';
  if(window.pfLoadMinis) window.pfLoadMinis(card);
}

// ── Career strip ──────────────────────────────────────────────────
function posToPct(fp){if(fp == null) return null; return Math.max(5, Math.min(100, Math.round(100 - (fp - 1) * 6)));}
function setCV(id, val, cls){
  const el = document.getElementById(id);
  el.textContent = (val == null) ? '—' : val;
  el.className = 'cs-v' + (cls ? ' ' + cls : '');
}
async function loadCareer(){
  let k = {}, form = [];
  try{k = await fetch('/sessions/career').then(r => r.json());}catch(e){}
  try{form = await fetch('/sessions/form?type=all&last=20').then(r => r.json());}catch(e){}
  const strip = document.getElementById('career-strip');
  if(!k || (k.total_sessions || 0) === 0){strip.style.display = 'none'; return;}
  strip.style.display = '';

  // Primary tier — reliable, telemetry-derived. Always shown.
  setCV('cs-total',    k.total_sessions || '0', 'muted');
  setCV('cs-laps',     k.total_laps     || '0', 'muted');
  setCV('cs-circuits', k.circuit_count  || '0', 'muted');
  setCV('cs-cars',     k.cars_driven    || '0', 'muted');

  // Circuit progression tally — the headline improvement signal.
  const up = k.trend_improving || 0, dn = k.trend_regressing || 0, fl = k.trend_flat || 0;
  const tally = document.getElementById('cs-trend-tally');
  if(up + dn + fl > 0){
    document.getElementById('cs-t-up').textContent = '▲' + up;
    document.getElementById('cs-t-dn').textContent = '▼' + dn;
    document.getElementById('cs-t-fl').textContent = '—' + fl;
    tally.style.display = '';
  } else { tally.style.display = 'none'; }

  // Results tier — gated on real races, sample labelled, never bare 0%.
  const realN = k.real_race_count || 0;
  const results = document.getElementById('career-results');
  if(realN >= 1){
    setCV('cs-finish', k.avg_finish_real != null ? 'P' + (+k.avg_finish_real.toFixed(1)) : null, 'blue');
    const pg = k.avg_pos_gained;
    setCV('cs-gained', pg != null ? ((pg >= 0 ? '+' : '') + (+pg.toFixed(1))) : null,
          pg > 0 ? 'green' : pg < 0 ? 'red' : null);
    setCV('cs-podium', k.podium_rate != null ? Math.round(k.podium_rate) + '%' : null, 'green');
    document.getElementById('cs-results-sample').textContent =
      'across ' + realN + ' real race' + (realN === 1 ? '' : 's');
    results.style.display = '';
  } else { results.style.display = 'none'; }

  renderCareerSpark(form);
}
function renderCareerSpark(form){
  const withPos = (form || []).filter(s => s.finish_pos != null);
  const trendEl = document.getElementById('cs-trend');
  const sparkEl = document.getElementById('cs-spark');
  const linkEl = document.getElementById('cs-form-link');
  if(withPos.length < 2){trendEl.textContent = ''; trendEl.className = 'cs-trend fl'; sparkEl.innerHTML = '';
    if(linkEl) linkEl.style.display = 'none'; return;}
  if(linkEl) linkEl.style.display = '';
  const pcts = withPos.map(s => posToPct(s.finish_pos));
  const half = Math.floor(pcts.length / 2);
  const a1 = pcts.slice(0, half).reduce((a, b) => a + b, 0) / (half || 1);
  const a2 = pcts.slice(half).reduce((a, b) => a + b, 0) / ((pcts.length - half) || 1);
  const diff = a2 - a1;
  let col;
  if(diff > 4){trendEl.textContent = '▲ Improving'; trendEl.className = 'cs-trend up'; col = '#22c55e';}
  else if(diff < -4){trendEl.textContent = '▼ Declining'; trendEl.className = 'cs-trend dn'; col = '#ef4444';}
  else{trendEl.textContent = '— Steady'; trendEl.className = 'cs-trend fl'; col = '#888';}
  const w = 120, h = 32, pad = 3;
  const mn = Math.min(...pcts), mx = Math.max(...pcts), rng = Math.max(mx - mn, 15);
  const xs = pcts.map((_, i) => pad + (w - pad * 2) * i / Math.max(pcts.length - 1, 1));
  const ys = pcts.map(v => h - pad - (h - pad * 2) * (v - mn) / rng);
  const pts = xs.map((x, i) => x.toFixed(1) + ',' + ys[i].toFixed(1)).join(' ');
  sparkEl.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:100%"><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" opacity=".85"/></svg>`;
}


init();
