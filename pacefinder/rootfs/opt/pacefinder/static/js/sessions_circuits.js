// Circuits index page — /circuits
// Lists every circuit driven, most-recent first. Rows link into the
// per-circuit detail. Data from /sessions/tracks (bare list).

function fmtLap(s){if(s == null) return '—'; const m = Math.floor(s/60); return m+':'+(s%60).toFixed(3).padStart(6,'0');}
function fmtRelative(iso){
  if(!iso) return '—';
  const dt = new Date(iso);
  const days = Math.floor((Date.now() - dt.getTime()) / 86400000);
  if(days < 1) return 'today';
  if(days === 1) return '1 day ago';
  if(days < 30) return days + ' days ago';
  const months = Math.floor(days / 30);
  if(months === 1) return '1 month ago';
  if(months < 12) return months + ' months ago';
  return Math.floor(months / 12) + ' year' + (Math.floor(months/12) === 1 ? '' : 's') + ' ago';
}
function escapeHtml(s){
  if(s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function init(){
  let tracks;
  try{tracks = await fetch('/sessions/tracks').then(r => r.json());}
  catch(e){document.getElementById('circuits-subtitle').textContent = 'Failed to load circuits.'; return;}
  tracks = tracks || [];
  document.getElementById('circuits-subtitle').textContent =
    tracks.length + ' circuit' + (tracks.length === 1 ? '' : 's') + ' driven';
  document.getElementById('circuits-count').textContent =
    tracks.length + (tracks.length === 1 ? ' circuit' : ' circuits');
  render(tracks);
}

function render(tracks){
  const list = document.getElementById('circuits-list');
  if(!tracks.length){
    list.innerHTML = '<div class="empty">No circuits driven yet.</div>';
    return;
  }
  list.innerHTML = tracks.map(t => {
    const href = '/sessions/track?name=' + encodeURIComponent(t.track);
    const name = (t.track === 'unknown' || !t.track) ? 'Unknown Circuit' : t.track;
    const sc = t.session_count || 0;
    const meta = sc + ' session' + (sc === 1 ? '' : 's')
      + (t.best_car ? ' · best in ' + escapeHtml(t.best_car) : '');
    const outAttr = (t.pb_session_id && t.pb_lap_number != null)
      ? ` data-sid="${escapeHtml(t.pb_session_id)}" data-lap="${t.pb_lap_number}"` : '';
    return `<a href="${href}" class="track-row">
      <div class="track-outline"${outAttr}></div>
      <div>
        <div class="track-name">${escapeHtml(name)}</div>
        <div class="track-meta">${meta}</div>
      </div>
      <div class="track-pb">${fmtLap(t.best_lap_time_s)}</div>
      <div class="track-sessions">${fmtRelative(t.last_raced)}</div>
      <div class="track-arrow">→</div>
    </a>`;
  }).join('');
  // Outline rendering lives in /static/js/track_mini.js — shared with
  // the Sessions list. Lazy-loads via IntersectionObserver.
  if(window.pfLoadMinis) window.pfLoadMinis();
}

init();
