// Cars index page — /cars
// Lists every car the user has driven, sorted by session count desc.

const DRIVETRAIN_LABELS = {0: 'FWD', 1: 'RWD', 2: 'AWD'};
// car class resolved via shared pfCarClass() — see static/js/class.js

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
  let d;
  try{d = await fetch('/cars/data').then(r => r.json());}
  catch(e){document.getElementById('cars-subtitle').textContent = 'Failed to load cars.'; return;}
  const cars = d.cars || [];
  document.getElementById('cars-subtitle').textContent =
    cars.length + ' car' + (cars.length === 1 ? '' : 's') + ' driven';
  document.getElementById('cars-count').textContent =
    cars.length + (cars.length === 1 ? ' car' : ' cars');
  render(cars);
}

function render(cars){
  const list = document.getElementById('cars-list');
  if(!cars.length){
    list.innerHTML = '<div class="empty">No cars driven yet.</div>';
    return;
  }
  list.innerHTML = cars.map(car => {
    const href = '/cars/' + car.ordinal;
    const displayName = car.nickname || car.name || ('Unknown Car (#' + car.ordinal + ')');
    const canonical = car.nickname && car.name
      ? (car.year ? car.year + ' ' : '') + car.name
      : '';
    const cls = pfCarClass(car.pi, car.class);
    const pi = car.pi || '';
    const dt = car.drivetrain_type != null ? DRIVETRAIN_LABELS[car.drivetrain_type] : '';

    const bestTrack = car.best_at_track || '—';
    const bestSubtitle = car.best_at_track
      ? `${escapeHtml(car.best_at_track)} · ${car.sessions_count} session${car.sessions_count === 1 ? '' : 's'} · ${car.laps_count} lap${car.laps_count === 1 ? '' : 's'}`
      : `${car.sessions_count} session${car.sessions_count === 1 ? '' : 's'} · ${car.laps_count} lap${car.laps_count === 1 ? '' : 's'}`;

    const badges = [
      cls ? `<span class="class-badge">${cls}</span>` : '',
      pi  ? `<span class="pi-badge">PI ${pi}</span>` : '',
      dt  ? `<span class="drivetrain">${dt}</span>` : '',
    ].filter(Boolean).join(' ');

    return `<a href="${href}" class="track-row">
      <div class="track-outline"></div>
      <div>
        <div class="track-name">
          ${escapeHtml(displayName)}
          ${canonical ? `<span style="font-size:11px;color:var(--color-text-quaternary);font-weight:400;margin-left:8px">${escapeHtml(canonical)}</span>` : ''}
        </div>
        <div class="track-meta">${bestSubtitle}</div>
      </div>
      <div class="track-pb">${fmtLap(car.best_lap_s)}</div>
      <div style="display:flex;gap:4px;justify-content:flex-end;align-items:center">${badges}</div>
      <div class="track-sessions">${fmtRelative(car.last_driven)}</div>
      <div class="track-arrow">→</div>
    </a>`;
  }).join('');
}

init();
