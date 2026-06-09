// All-events page — /sessions/session/events?id=<sid>
// Fetches /sessions/session/events-map (events + track outline) and
// renders a filterable list cross-linked to a track map.

const EVENT_LABELS = {
  lockup: 'Lockup',
  power_oversteer: 'Power-on oversteer',
  bad_shift: 'Bad shift',
};
function sevClass(s){ return s > 0.7 ? 'worst' : (s >= 0.4 ? 'major' : 'minor'); }
function sevColor(s){ return s > 0.7 ? '#dc2626' : (s >= 0.4 ? '#f87171' : '#fbbf24'); }
function escapeHtml(s){if(s==null)return '';return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

const _id = new URLSearchParams(location.search).get('id') || '';
let _events = [], _track = [], _sel = null;
let _fShow = 'all', _fType = '', _fSort = 'severity';
// Track-outline transform (set in drawTrack), maps a sample's
// distance_norm → svg x/y so markers land on the line.
let _xform = null;

async function init(){
  if(!_id){ location.href = '/sessions'; return; }
  document.getElementById('crumb').href = '/sessions/session?id=' + encodeURIComponent(_id);
  let d;
  try{ d = await fetch('/sessions/session/events-map?id=' + encodeURIComponent(_id)).then(r=>r.json()); }
  catch(e){ document.getElementById('ev-meta').textContent = 'Failed to load'; return; }
  if(d.error){ document.getElementById('ev-meta').textContent = 'Session not found'; return; }

  _events = d.events || [];
  _track  = d.track_xy || [];
  const s = d.session || {};
  const car = s.car_nickname || s.car || ('Car #' + (s.car_ordinal ?? '?'));
  const dt = s.started_at ? new Date(s.started_at).toLocaleDateString([], {month:'short',day:'numeric',year:'numeric'}) : '';
  document.getElementById('ev-meta').textContent =
    [s.track || 'unknown', car, dt, _events.length + ' event' + (_events.length===1?'':'s')]
      .filter(Boolean).join(' · ');
  document.title = 'Pacefinder · Events · ' + (s.track || '');

  if(!_events.length){
    document.querySelector('.body').style.display = 'none';
    document.getElementById('ev-empty').style.display = '';
    return;
  }
  drawTrack();
  attachFilters();
  render();
}

function drawTrack(){
  const svg = document.getElementById('map-svg');
  if(!_track.length){
    svg.setAttribute('viewBox', '0 0 1000 480');
    svg.innerHTML = '<text x="500" y="240" fill="#666" font-size="13" text-anchor="middle" font-family="sans-serif">No position data for this session</text>';
    _xform = null;
    return;
  }
  // viewBox sized to the track's own aspect ratio so a square circuit
  // doesn't get letterboxed inside a 2:1 rectangle. Cap 0.5–2.5 so a
  // long thin track like Le Mans can't collapse the panel to a sliver.
  const xs = _track.map(p=>p.x), ys = _track.map(p=>p.y);
  const minX=Math.min(...xs), maxX=Math.max(...xs);
  const minY=Math.min(...ys), maxY=Math.max(...ys);
  const spanX=(maxX-minX)||1, spanY=(maxY-minY)||1;
  const trackAspect=Math.max(0.5,Math.min(2.5,spanX/spanY));
  const pad=40;
  const W = trackAspect >= 1 ? 1000 : Math.round(1000 * trackAspect);
  const H = trackAspect >= 1 ? Math.round(1000 / trackAspect) : 1000;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const sc=Math.min((W-2*pad)/spanX, (H-2*pad)/spanY);
  const ox=(W-spanX*sc)/2, oy=(H-spanY*sc)/2;
  // Y is flipped so the loop isn't upside down (screen y grows down).
  _xform = (x,y) => [ ox + (x-minX)*sc, H - (oy + (y-minY)*sc) ];

  const path = _track.map((p,i) => {
    const [X,Y] = _xform(p.x, p.y);
    return (i===0?'M ':'L ') + X.toFixed(1) + ' ' + Y.toFixed(1);
  }).join(' ') + ' Z';
  svg.innerHTML =
    `<path d="${path}" fill="none" stroke="#3b3b3b" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>` +
    `<g id="map-markers"></g>`;
}

// Find the track point nearest a given distance_norm, return its svg xy.
function markerXY(dnorm){
  if(!_xform || !_track.length) return null;
  let best = _track[0], bd = Infinity;
  for(const p of _track){
    const dd = Math.abs((p.d ?? 0) - dnorm);
    if(dd < bd){ bd = dd; best = p; }
  }
  return _xform(best.x, best.y);
}

function visibleEvents(){
  let ev = _events.slice();
  if(_fType) ev = ev.filter(e => e.event_type === _fType);
  if(_fShow === 'worst'){
    ev = ev.slice().sort((a,b)=>b.severity-a.severity).slice(0,5);
  }
  if(_fSort === 'severity') ev.sort((a,b)=>b.severity-a.severity);
  else if(_fSort === 'lap') ev.sort((a,b)=>(a.lap_number-b.lap_number)||(b.severity-a.severity));
  return ev;
}

function render(){
  const ev = visibleEvents();
  const list = document.getElementById('events');
  list.innerHTML = ev.map((e,i) => {
    const label = EVENT_LABELS[e.event_type] || e.event_type;
    const lap = e.lap_number != null ? ('L' + (e.lap_number+1)) : '—';
    const dm = e.distance_m != null ? ('d ≈ ' + Math.round(e.distance_m) + ' m') : '';
    const detail = [dm, escapeHtml(e.description || '')].filter(Boolean).join(' · ');
    const selCls = (_sel === e) ? ' selected' : '';
    return `<div class="event-row${selCls}" data-i="${i}">
      <span class="event-lap">${lap}</span>
      <div>
        <div class="event-corner">${escapeHtml(label)}</div>
        <div class="event-detail">${detail}</div>
      </div>
      <span class="event-sev ${sevClass(e.severity)}">${(e.severity).toFixed(2)}</span>
    </div>`;
  }).join('');
  list.querySelectorAll('.event-row').forEach(row => {
    row.addEventListener('click', () => {
      _sel = ev[parseInt(row.dataset.i,10)];
      render(); renderMarkers(ev);
    });
  });
  renderMarkers(ev);
}

function renderMarkers(ev){
  const g = document.getElementById('map-markers');
  if(!g) return;
  let html = '';
  ev.forEach(e => {
    const xy = markerXY(e.distance_norm ?? 0);
    if(!xy) return;
    const isSel = (_sel === e);
    const r = isSel ? 9 : (4 + e.severity * 6);
    const fill = isSel ? 'var(--color-accent)' : sevColor(e.severity);
    const stroke = isSel ? '#fff' : '#0a0a0a';
    html += `<circle cx="${xy[0].toFixed(1)}" cy="${xy[1].toFixed(1)}" r="${r.toFixed(1)}" `+
            `fill="${fill}" stroke="${stroke}" stroke-width="2" style="cursor:pointer" `+
            `data-evt="${e.lap_number}_${e.event_type}_${e.distance_m}"/>`;
  });
  // Selected annotation
  if(_sel){
    const xy = markerXY(_sel.distance_norm ?? 0);
    if(xy){
      const label = (EVENT_LABELS[_sel.event_type]||_sel.event_type) +
        ' · L' + ((_sel.lap_number??0)+1) + ' · sev ' + _sel.severity.toFixed(2);
      html += `<text x="${xy[0].toFixed(1)}" y="${(xy[1]-16).toFixed(1)}" fill="var(--color-accent)" `+
              `font-size="12" font-family="monospace" text-anchor="middle">${escapeHtml(label)}</text>`;
    }
  }
  g.innerHTML = html;
  g.querySelectorAll('circle').forEach(c => {
    c.addEventListener('click', () => {
      const key = c.dataset.evt;
      _sel = ev.find(e => `${e.lap_number}_${e.event_type}_${e.distance_m}` === key) || null;
      render();
    });
  });
}

function attachFilters(){
  document.querySelectorAll('.filters .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if(chip.dataset.show != null){
        _fShow = chip.dataset.show;
        setOn(chip, '[data-show]');
      } else if(chip.dataset.type != null){
        _fType = chip.dataset.type;
        setOn(chip, '[data-type]');
      } else if(chip.dataset.sort != null){
        _fSort = chip.dataset.sort;
        setOn(chip, '[data-sort]');
      }
      _sel = null;
      render();
    });
  });
}
function setOn(chip, sel){
  document.querySelectorAll('.filters ' + sel).forEach(c => c.classList.remove('on'));
  chip.classList.add('on');
}

init();
