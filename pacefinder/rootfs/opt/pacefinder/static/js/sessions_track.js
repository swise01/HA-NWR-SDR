// Circuit detail — /sessions/track?name=
// Rebuilt for the layered-IA design (circuit-mock.html). Fetches the
// enriched /sessions/track/data payload: { sessions, personal_best,
// progress, theoretical }.

// car class resolved via shared pfCarClass() — see static/js/class.js
const GAME_LABELS = {'forza_motorsport':'Forza','acc':'ACC','f1':'F1'};

function fmtLap(s){if(s==null)return '—';const m=Math.floor(s/60);return m+':'+(s%60).toFixed(3).padStart(6,'0');}
function fmtDate(iso){if(!iso)return '—';return new Date(iso).toLocaleDateString([],{month:'short',day:'numeric',year:'numeric'});}
function fmtShort(iso){if(!iso)return '—';return new Date(iso).toLocaleDateString([],{month:'short',day:'numeric'});}
let _tf='24h';  // user time-format pref, set from /sessions/track/data
function fmtTime(iso){if(!iso)return '';return new Date(iso).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:_tf==='12h'});}
function escapeHtml(s){if(s==null)return '';return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

const _track = new URLSearchParams(location.search).get('name') || '';
const _game  = new URLSearchParams(location.search).get('game') || '';

let _sessions = [], _pb = null, _progress = [], _theo = null;
let _carFilter = null;   // car name string or null
let _condFilter = null;  // weather string or null

async function init(){
  if(!_track){location.href='/sessions';return;}
  document.title = 'Pacefinder · ' + _track;
  document.getElementById('hdr-name').textContent = _track;
  let d;
  const url = '/sessions/track/data?name='+encodeURIComponent(_track)+(_game?'&game='+encodeURIComponent(_game):'');
  try{ d = await fetch(url).then(r=>r.json()); }
  catch(e){ document.getElementById('hdr-name').textContent='Track not found'; return; }
  _sessions = d.sessions || [];
  _pb       = d.personal_best || null;
  _progress = d.progress || [];
  _theo     = d.theoretical || null;
  _tf       = d.time_format || '24h';

  renderSubtitle();
  renderHero();
  renderTrackMap();
  renderTheo();
  renderTip();
  renderFilters();
  renderSessions();
}

// Faint outline of the PB lap's racing line — a license-free, authentic
// "this is the track" cue (your own line, not a logo). Bbox-normalized;
// hidden when the PB lap has no stored position samples.
async function renderTrackMap(){
  const el = document.getElementById('hero-trackmap');
  if(!el || !_pb || !_pb.session_id || _pb.lap_number == null) return;
  let s;
  try{
    s = await fetch('/sessions/lap-samples?session_id='+encodeURIComponent(_pb.session_id)
      +'&lap='+_pb.lap_number).then(r=>r.json());
  }catch(e){ return; }
  if(!s || s.length < 8 || s.some(p=>p.px==null)) return;
  const hasPz = s.some(p=>p.pz!=null);
  const zf = hasPz ? p=>p.pz : p=>(p.py??0);
  const xs = s.map(p=>p.px), zs = s.map(zf);
  const mnX=Math.min(...xs), mxX=Math.max(...xs), mnZ=Math.min(...zs), mxZ=Math.max(...zs);
  const W=220, H=150, pd=10;
  const sc=Math.min((W-pd*2)/((mxX-mnX)||1),(H-pd*2)/((mxZ-mnZ)||1));
  const ox=(W-(mxX-mnX)*sc)/2, oz=(H-(mxZ-mnZ)*sc)/2;
  const cx=x=>(ox+(x-mnX)*sc).toFixed(1);
  const cy=z=>(H-oz-(z-mnZ)*sc).toFixed(1);
  const step=Math.max(1,Math.floor(s.length/240));
  const pts=[];
  for(let i=0;i<s.length;i+=step) pts.push(cx(s[i].px)+','+cy(zf(s[i])));
  pts.push(cx(s[0].px)+','+cy(zf(s[0])));   // close the loop
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Track outline">`+
    `<polyline class="tm-line" points="${pts.join(' ')}"/>`+
    `<circle class="tm-start" cx="${cx(s[0].px)}" cy="${cy(zf(s[0]))}" r="4"/></svg>`;
  el.style.display='';
}

function renderSubtitle(){
  const laps = _sessions.reduce((a,s)=>a+(s.lap_count||0),0);
  const bits = [
    _sessions.length + ' session' + (_sessions.length===1?'':'s'),
    laps + ' lap' + (laps===1?'':'s'),
  ];
  if(_game) bits.unshift(GAME_LABELS[_game] || _game);
  document.getElementById('subtitle').innerHTML =
    bits.map(b=>`<span>${escapeHtml(b)}</span>`).join('<span class="dot">·</span>');
}

function renderHero(){
  if(_pb && _pb.best_lap_time_s != null){
    document.getElementById('hero-pb').textContent = fmtLap(_pb.best_lap_time_s);
    document.getElementById('hero-pb-sub').textContent =
      'Personal best · ' + (_pb.started_at ? fmtDate(_pb.started_at) : '—');
  } else {
    document.getElementById('hero-pb').textContent = '—';
    document.getElementById('hero-pb-sub').textContent = 'No completed laps yet';
  }
  // Gap to theoretical
  if(_pb && _theo && _theo.theoretical_best_s && _pb.best_lap_time_s){
    const gap = _pb.best_lap_time_s - _theo.theoretical_best_s;
    if(gap > 0.001){
      const g = document.getElementById('hero-gap');
      g.textContent = '+' + gap.toFixed(3) + 's';
      g.style.display = '';
      document.getElementById('hero-gap-sub').style.display = '';
    }
  }
  renderProgressChart();
}

function renderProgressChart(){
  const svg = document.getElementById('progress-svg');
  const empty = document.getElementById('progress-empty');
  const meta = document.getElementById('chart-meta');
  const pts = _progress.filter(p => p.best_lap_s != null);
  if(pts.length < 2){
    svg.style.display = 'none';
    empty.style.display = '';
    return;
  }
  const W = 1000, H = 200, padL = 8, padR = 8, padT = 16, padB = 24;
  const times = pts.map(p => p.best_lap_s);
  const minT = Math.min(...times), maxT = Math.max(...times);
  const span = (maxT - minT) || 1;
  const xAt = i => padL + (i / (pts.length - 1)) * (W - padL - padR);
  // Lower time = faster = should sit HIGHER on the chart (better).
  const yAt = t => padT + ((t - minT) / span) * (H - padT - padB);

  const linePts = pts.map((p,i) => xAt(i).toFixed(1)+','+yAt(p.best_lap_s).toFixed(1)).join(' ');
  const best = Math.min(...times);

  let dots = '';
  pts.forEach((p,i) => {
    const isBest = Math.abs(p.best_lap_s - best) < 0.001;
    const r = isBest ? 6 : 4;
    const fill = isBest ? 'var(--color-accent)' : 'var(--color-blue)';
    dots += `<circle cx="${xAt(i).toFixed(1)}" cy="${yAt(p.best_lap_s).toFixed(1)}" r="${r}" fill="${fill}" stroke="#0a0a0a" stroke-width="2"/>`;
  });

  // PB baseline (dashed) at the fastest lap's y
  const pbY = yAt(best).toFixed(1);

  svg.innerHTML =
    `<line x1="${padL}" y1="${pbY}" x2="${W-padR}" y2="${pbY}" stroke="var(--color-accent)" stroke-width="1" stroke-dasharray="2,4" opacity="0.4"/>` +
    `<polyline points="${linePts}" fill="none" stroke="var(--color-blue)" stroke-width="2"/>` +
    `<polyline points="${padL},${H} ${linePts} ${W-padR},${H}" fill="var(--color-blue)" opacity="0.06" stroke="none"/>` +
    dots +
    `<text x="${padL}" y="${H-6}" fill="#666" font-size="10" font-family="monospace">${fmtShort(pts[0].started_at)}</text>` +
    `<text x="${W-padR}" y="${H-6}" fill="#666" font-size="10" font-family="monospace" text-anchor="end">${fmtShort(pts[pts.length-1].started_at)}</text>`;
  meta.textContent = pts.length + ' sessions · PB ' + fmtLap(best);
  svg.style.display = '';
  empty.style.display = 'none';
}

function renderTheo(){
  if(!_theo || _theo.theoretical_best_s == null) return;
  document.getElementById('theo-card').style.display = '';
  document.getElementById('theo-time').textContent = fmtLap(_theo.theoretical_best_s);
  const prov = (s_s, sid, lap) => {
    if(s_s == null) return '';
    const lapTxt = (lap != null) ? 'L'+(lap+1) : '';
    if(sid){
      return `${lapTxt} · <a href="/sessions/session?id=${encodeURIComponent(sid)}">view</a>`;
    }
    return lapTxt;
  };
  document.getElementById('theo-s1').textContent = _theo.theoretical_s1_s != null ? _theo.theoretical_s1_s.toFixed(3) : '—';
  document.getElementById('theo-s2').textContent = _theo.theoretical_s2_s != null ? _theo.theoretical_s2_s.toFixed(3) : '—';
  document.getElementById('theo-s3').textContent = _theo.theoretical_s3_s != null ? _theo.theoretical_s3_s.toFixed(3) : '—';
  document.getElementById('theo-s1-prov').innerHTML = prov(_theo.theoretical_s1_s, _theo.theoretical_s1_session_id, _theo.theoretical_s1_lap);
  document.getElementById('theo-s2-prov').innerHTML = prov(_theo.theoretical_s2_s, _theo.theoretical_s2_session_id, _theo.theoretical_s2_lap);
  document.getElementById('theo-s3-prov').innerHTML = prov(_theo.theoretical_s3_s, _theo.theoretical_s3_session_id, _theo.theoretical_s3_lap);
}

async function renderTip(){
  try{
    const d = await fetch('/sessions/track/tip?name='+encodeURIComponent(_track)).then(r=>r.json());
    if(d && d.tip){
      document.getElementById('tip-text').textContent = d.tip;
      document.getElementById('tip-text').style.fontStyle = 'italic';
      const btn = document.getElementById('tip-btn');
      btn.textContent = '↻ Re-generate';
      if(d.generated_at){
        document.getElementById('tip-meta').textContent =
          '— ' + (d.model || 'Claude') + ' · ' + fmtDate(d.generated_at);
      }
    }
  }catch(e){}
}

async function generateTip(){
  const btn = document.getElementById('tip-btn');
  btn.disabled = true; btn.textContent = 'Generating…';
  try{
    const d = await fetch('/sessions/track/tip?name='+encodeURIComponent(_track)+'&generate=true').then(r=>r.json());
    if(d && d.tip){
      document.getElementById('tip-text').textContent = d.tip;
      document.getElementById('tip-text').style.fontStyle = 'italic';
      btn.textContent = '↻ Re-generate'; btn.disabled = false;
      if(d.generated_at){
        document.getElementById('tip-meta').textContent =
          '— ' + (d.model || 'Claude') + ' · ' + fmtDate(d.generated_at);
      }
    } else {
      btn.textContent = 'Generate AI tip'; btn.disabled = false;
    }
  }catch(e){
    btn.textContent = 'Error — retry'; btn.disabled = false;
  }
}

function renderFilters(){
  // Distinct cars + conditions across this track's sessions
  const cars = [...new Set(_sessions.map(s => s.car).filter(Boolean))];
  const conds = [...new Set(_sessions.map(s => s.weather_condition).filter(Boolean))];
  if(cars.length <= 1 && conds.length <= 1){
    document.getElementById('type-filter').style.display = 'none';
    return;
  }
  const wrap = document.getElementById('type-filter');
  let html = '';
  if(cars.length > 1){
    html += `<span class="chip ${_carFilter===null?'on':''}" data-car="">All cars</span>`;
    cars.forEach(c => {
      html += `<span class="chip ${_carFilter===c?'on':''}" data-car="${escapeHtml(c)}">${escapeHtml(c)}</span>`;
    });
  }
  if(conds.length > 1){
    html += `<span class="chip ${_condFilter===null?'on':''}" data-cond="">All conditions</span>`;
    conds.forEach(c => {
      html += `<span class="chip ${_condFilter===c?'on':''}" data-cond="${escapeHtml(c)}">${escapeHtml(c)}</span>`;
    });
  }
  wrap.innerHTML = html;
  wrap.style.display = '';
  wrap.querySelectorAll('[data-car]').forEach(el => el.addEventListener('click', () => {
    _carFilter = el.dataset.car || null;
    renderFilters(); renderSessions();
  }));
  wrap.querySelectorAll('[data-cond]').forEach(el => el.addEventListener('click', () => {
    _condFilter = el.dataset.cond || null;
    renderFilters(); renderSessions();
  }));
}

function renderSessions(){
  const filtered = _sessions.filter(s => {
    if(_carFilter !== null && s.car !== _carFilter) return false;
    if(_condFilter !== null && s.weather_condition !== _condFilter) return false;
    return true;
  });
  document.getElementById('sessions-count').textContent =
    filtered.length + ' session' + (filtered.length===1?'':'s');
  const list = document.getElementById('session-list');
  const empty = document.getElementById('empty');
  if(!filtered.length){
    list.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';
  const bestId = _pb ? _pb.session_id : null;
  list.innerHTML = filtered.map(s => {
    const isBest = s.session_id === bestId;
    const href = '/sessions/session?id=' + encodeURIComponent(s.session_id) +
                 (s.game ? '&game=' + encodeURIComponent(s.game) : '');
    const _cc = pfCarClass(s.car_pi, s.car_class);
    const cls = _cc ? `<span class="cc cc-${_cc}">${_cc}</span>` : '';
    const condBits = [];
    if(s.weather_condition) condBits.push(escapeHtml(s.weather_condition));
    if(s.tyre_compound) condBits.push(escapeHtml(s.tyre_compound));
    const cond = condBits.join('<span class="sep">·</span>');
    const star = isBest ? '<span class="best-star">★</span>' : '';
    return `<a href="${href}" class="session-row${isBest?' is-best':''}">
      <span class="session-date">${fmtShort(s.started_at)}<small>${fmtTime(s.started_at)}</small></span>
      <span class="session-car">${escapeHtml(s.car || '—')} ${cls}</span>
      <span class="session-cond">${cond}</span>
      <span class="session-time">${fmtLap(s.best_lap_time_s)}${star}</span>
      <span class="session-arrow">→</span>
    </a>`;
  }).join('');
}

init();
