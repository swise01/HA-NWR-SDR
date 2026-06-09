TRACK_DETAIL_HTML_PRE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder &middot; Track</title>
<link rel="stylesheet" href="/static/tokens.css">
<link rel="stylesheet" href="/static/base.css">
<link rel="stylesheet" href="/static/sessions_track.css">
<link rel="stylesheet" href="/static/nav.css">
</head>
<body>
<div id="pf-nav"></div>
<script src="/static/js/_safe.js"></script>
<script src="/static/js/nav.js"></script>
<div class="page">

  <a href="/sessions" class="crumb">&larr; All circuits</a>

  <h1 class="title" id="hdr-name">Loading&hellip;</h1>
  <div class="subtitle" id="subtitle">&mdash;</div>

  <!-- Hero: personal best + gap to theoretical + progress chart -->
  <div class="hero">
    <div>
      <div class="hero-time" id="hero-pb">&mdash;</div>
      <div class="hero-time-sub" id="hero-pb-sub">Personal best</div>
      <div class="hero-gap" id="hero-gap" style="display:none">&mdash;</div>
      <div class="hero-gap-sub" id="hero-gap-sub" style="display:none">vs your theoretical</div>
      <div class="hero-trackmap" id="hero-trackmap" style="display:none"></div>
    </div>
    <div class="progress">
      <div class="chart-header">
        <div class="chart-title">Best lap by session</div>
        <div class="chart-meta" id="chart-meta"></div>
      </div>
      <div class="chart-plot">
        <span class="axis-cue top">faster &uarr;</span>
        <span class="axis-cue bot">slower &darr;</span>
        <svg class="progress-svg" id="progress-svg" viewBox="0 0 1000 200" preserveAspectRatio="none"></svg>
      </div>
      <div class="progress-empty" id="progress-empty" style="display:none">Not enough sessions to chart progress yet.</div>
    </div>
  </div>

  <!-- Theoretical breakdown -->
  <div class="theo" id="theo-card" style="display:none">
    <div>
      <div class="theo-label">Theoretical best</div>
      <div class="theo-time" id="theo-time">&mdash;</div>
      <div class="theo-note">Sum of your best sectors. Provenance &rarr;</div>
    </div>
    <div class="sectors">
      <div class="sect">
        <div class="sect-num">S1</div>
        <div class="sect-time" id="theo-s1">&mdash;</div>
        <div class="sect-prov" id="theo-s1-prov"></div>
      </div>
      <div class="sect">
        <div class="sect-num">S2</div>
        <div class="sect-time" id="theo-s2">&mdash;</div>
        <div class="sect-prov" id="theo-s2-prov"></div>
      </div>
      <div class="sect">
        <div class="sect-num">S3</div>
        <div class="sect-time" id="theo-s3">&mdash;</div>
        <div class="sect-prov" id="theo-s3-prov"></div>
      </div>
    </div>
  </div>

  <!-- AI track tip -->
  <div class="tip" id="tip-card">
    <div class="tip-head">
      <h2>Track tip</h2>
      <span class="tip-meta" id="tip-meta"></span>
    </div>
    <div class="tip-body" id="tip-text">No tip generated yet.</div>
    <button class="tip-gen" id="tip-btn" onclick="generateTip()">Generate AI tip</button>
  </div>

  <!-- Sessions list -->
  <div class="sessions">
    <div class="sessions-head">
      <h2>Sessions</h2>
      <span class="count" id="sessions-count">&mdash;</span>
    </div>
    <div class="filters" id="type-filter" style="display:none"></div>
    <div class="session-list" id="session-list"></div>
    <div class="empty-state" id="empty" style="display:none">No sessions at this track</div>
  </div>

</div>
<script>
const FORZA_TRACK_NAMES=
"""

TRACK_DETAIL_HTML_POST = """;</script>
<script src="/static/js/perf.js"></script>
<script>Perf.autoReport('/sessions/track');</script>
<script src="/static/js/class.js"></script>
<script src="/static/js/sessions_track.js"></script>
<div id="sp-tip"></div>
</body>
</html>
"""

SESSION_DETAIL_HTML_PRE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder &middot; Session</title>
<link rel="stylesheet" href="/static/tokens.css">
<link rel="stylesheet" href="/static/base.css">
<link rel="stylesheet" href="/static/sessions_session.css">
<link rel="stylesheet" href="/static/widgets/autocomplete.css">
<link rel="stylesheet" href="/static/nav.css">
</head>
<body>
<div id="pf-nav"></div>
<script src="/static/js/nav.js"></script>
<div class="page">

  <div class="breadcrumb" id="sess-breadcrumb">
    <a href="/sessions">Sessions</a> &rsaquo;
    <a href="#" id="bc-game" style="display:none"></a><span id="bc-gsep" style="display:none"> &rsaquo; </span>
    <a href="#" id="bc-track">Track</a> &rsaquo;
    <span id="bc-sess-cur">Session</span>
  </div>

  <div class="subnav">
    <span class="subnav-item active">Overview</span>
    <a class="subnav-item" id="link-telemetry" href="#">Full telemetry</a>
  </div>

  <div class="page-head">
    <div>
      <h1 class="page-h1" id="hdr-track">Loading&hellip;</h1>
      <div class="page-sub">
        <a class="page-sub-link" id="hdr-circuit-link" href="#"><span id="hdr-circuit-name">Circuit</span></a>
        <span class="page-sub-meta" id="hdr-submeta"></span>
        <a class="page-h2" id="hdr-car-link" href="#" style="display:none">
          <span id="hdr-car-name"></span>
          <span class="class-badge" id="hdr-car-class" style="display:none"></span>
          <span class="pi" id="hdr-car-pi" style="display:none"></span>
          <span class="page-h2-arrow">&rarr;</span>
        </a>
      </div>
    </div>
    <div class="page-head-result" id="hdr-result" style="display:none">
      <div class="result-eyebrow">Grid &rarr; Finish</div>
      <div class="result-positions">
        <span id="hdr-grid-p">&mdash;</span>
        <span class="arrow">&rarr;</span>
        <span class="finish" id="hdr-finish-p">&mdash;</span>
      </div>
      <div class="result-delta" id="hdr-gained">&mdash;</div>
    </div>
  </div>

  <div class="strip">
    <span class="strip-spacer"></span>
    <button class="edit-btn" onclick="openEdit()" title="Edit session metadata">Edit &#x2303;</button>
  </div>
<!-- Edit modal -->
<div class="edit-ovl" id="edit-ovl" onclick="if(event.target===this)closeEdit()">
  <div class="edit-panel">
    <div class="edit-head">
      <div class="edit-ttl">Edit Session</div>
      <button class="edit-x" onclick="closeEdit()" aria-label="Close" title="Close">&times;</button>
    </div>
    <div class="edit-row"><label class="edit-lbl">Track</label>
      <input class="edit-sel" id="edit-track" placeholder="Search or type track name"></div>
    <div class="edit-row"><label class="edit-lbl">Car</label>
      <input class="edit-sel" id="edit-car" placeholder="e.g. 2018 Honda Civic Type R" autocomplete="off"></div>
    <div class="edit-row" id="edit-nickname-row" style="display:none">
      <label class="edit-lbl">Nickname <span style="font-weight:normal;text-transform:none;color:var(--color-text-muted)">(applies to every session in this car)</span></label>
      <input class="edit-sel" id="edit-nickname" placeholder="e.g. Lady Bug, Dreamliner" autocomplete="off" maxlength="40">
    </div>
    <div class="edit-row"><label class="edit-lbl">Type</label>
      <div class="edit-chips">
        <button class="etype" data-val="practice" onclick="editSelType(this)">Practice</button>
        <button class="etype" data-val="qualifying" onclick="editSelType(this)">Qualifying</button>
        <button class="etype" data-val="race" onclick="editSelType(this)">Race</button>
        <button class="etype" data-val="race_ai" onclick="editSelType(this)">AI Race</button>
        <button class="etype" data-val="hot_lap" onclick="editSelType(this)">Hot Lap</button>
        <button class="etype" data-val="time_trial" onclick="editSelType(this)">Time Trial</button>
      </div>
    </div>
    <div class="edit-row"><label class="edit-lbl">Weather</label>
      <div class="edit-chips" id="edit-weather-chips">
        <button class="etype" data-val="Dry"  onclick="editSelWeather(this)">Dry</button>
        <button class="etype" data-val="Damp" onclick="editSelWeather(this)">Damp</button>
        <button class="etype" data-val="Wet"  onclick="editSelWeather(this)">Wet</button>
        <button class="etype" data-val="Snow" onclick="editSelWeather(this)">Snow</button>
      </div>
    </div>
    <div class="edit-row"><label class="edit-lbl">Tyres</label>
      <!-- Forza Motorsport compounds. FH5 uses different categories
           (Street/Sport/Race/Slick/Rally/Off-Road/Drag) — to be split per
           game once FH5 support comes back online (see issue #84). -->
      <div class="edit-chips" id="edit-tyre-chips">
        <button class="etype" data-val="Soft"    onclick="editSelTyre(this)">Soft</button>
        <button class="etype" data-val="Medium"  onclick="editSelTyre(this)">Medium</button>
        <button class="etype" data-val="Hard"    onclick="editSelTyre(this)">Hard</button>
        <button class="etype" data-val="Wet"     onclick="editSelTyre(this)">Wet</button>
      </div>
    </div>
    <div class="edit-row">
      <!-- Grid + finish — Forza assesses penalties post-race in a screen
           we never see, so the captured finish_pos is the on-track result.
           Manual override here so corrected positions can be recorded. -->
      <label class="edit-lbl">Grid → Finish</label>
      <div style="display:flex;gap:8px;align-items:center">
        <span style="font-size:.7rem;color:var(--color-text-muted)">P</span>
        <input id="edit-grid" type="number" min="1" max="100" placeholder="—"
               style="width:60px;background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-primary);font-family:var(--font-mono);font-size:var(--text-sm);padding:6px 8px;border-radius:var(--radius-sm)"/>
        <span style="font-size:.7rem;color:var(--color-text-muted)">→ P</span>
        <input id="edit-finish" type="number" min="1" max="100" placeholder="—"
               style="width:60px;background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-primary);font-family:var(--font-mono);font-size:var(--text-sm);padding:6px 8px;border-radius:var(--radius-sm)"/>
      </div>
    </div>
    <div class="edit-row" id="edit-conditions-row" style="display:none">
      <label class="edit-lbl">Conditions</label>
      <span id="edit-conditions" style="font-size:.7rem;color:var(--color-text-secondary);font-variant-numeric:tabular-nums"></span>
    </div>
    <div class="edit-btns">
      <button class="edit-cancel" onclick="closeEdit()">Cancel</button>
      <button class="edit-save" onclick="saveEdit()">Save</button>
    </div>
    <div class="edit-danger">
      <button class="edit-delete-link" id="edit-del-link" onclick="deleteSession()">Delete session</button>
      <span class="edit-del-confirm" id="edit-del-confirm" style="display:none">
        Permanently delete this session?
        <button class="edit-del-yes" onclick="deleteSession(true)">Confirm delete</button>
        <button class="edit-del-no" onclick="cancelDelete()">Keep</button>
      </span>
    </div>
  </div>
</div>
  <!-- Hero: best lap + gap to theoretical + delta line + sector deltas -->
  <div class="hero">
    <div class="hero-numbers">
      <div class="hero-time" id="hero-best">&mdash;</div>
      <div class="hero-time-sub" id="hero-best-sub">Best lap</div>
      <div class="hero-gap" id="hero-gap" style="display:none">&mdash;</div>
      <div class="hero-gap-sub" id="hero-gap-sub" style="display:none">left on the table vs theoretical</div>
    </div>
    <div class="hero-chart">
      <div class="delta-header" id="delta-header" style="display:none">
        <span class="delta-title" id="delta-title">&Delta; — 2nd-best vs your best lap</span>
        <span class="delta-meta" id="delta-meta"></span>
      </div>
      <div class="delta-caption" id="delta-caption" style="display:none">
        Where your 2nd-best lap <span class="dc-slow">lost time</span> or
        <span class="dc-fast">gained time</span> against your best, around the lap.
      </div>
      <svg class="delta-svg" id="hero-delta-svg" viewBox="0 0 1000 180" preserveAspectRatio="none" style="display:none">
        <defs>
          <clipPath id="clipSlow"><rect x="0" y="0" width="1000" height="90"/></clipPath>
          <clipPath id="clipFast"><rect x="0" y="90" width="1000" height="90"/></clipPath>
        </defs>
        <line x1="333" y1="0" x2="333" y2="180" stroke="#1e1e1e" stroke-width="1" stroke-dasharray="3,4"/>
        <line x1="666" y1="0" x2="666" y2="180" stroke="#1e1e1e" stroke-width="1" stroke-dasharray="3,4"/>
        <line x1="0" y1="90" x2="1000" y2="90" stroke="#3a3a3a" stroke-width="1"/>
        <text x="166" y="14" fill="#888" font-size="10" font-family="monospace" text-anchor="middle" letter-spacing="0.1em">S1</text>
        <text x="500" y="14" fill="#888" font-size="10" font-family="monospace" text-anchor="middle" letter-spacing="0.1em">S2</text>
        <text x="833" y="14" fill="#888" font-size="10" font-family="monospace" text-anchor="middle" letter-spacing="0.1em">S3</text>
        <!-- y-axis cues: above the line = 2nd-best losing time, below = gaining -->
        <text x="6" y="20" fill="#f87171" font-size="10" font-family="monospace">slower ↑</text>
        <text x="6" y="86" fill="#8a8a8a" font-size="10" font-family="monospace">your best lap (0)</text>
        <text x="6" y="174" fill="#4ade80" font-size="10" font-family="monospace">faster ↓</text>
        <path id="hero-delta-fill-slow" d="" fill="#f87171" opacity="0.28" clip-path="url(#clipSlow)"/>
        <path id="hero-delta-fill-fast" d="" fill="#4ade80" opacity="0.26" clip-path="url(#clipFast)"/>
        <path id="hero-delta-line" d="" fill="none" stroke="#cfcfcf" stroke-width="1.5"/>
      </svg>
      <div class="delta-empty" id="delta-empty" style="display:none"></div>
      <div class="sector-row" id="hero-sectors" style="display:none">
        <div><div class="val" id="hero-s1">&mdash;</div><div class="lbl">S1 &Delta; vs theoretical</div></div>
        <div><div class="val" id="hero-s2">&mdash;</div><div class="lbl">S2 &Delta; vs theoretical</div></div>
        <div><div class="val" id="hero-s3">&mdash;</div><div class="lbl">S3 &Delta; vs theoretical</div></div>
      </div>
    </div>
  </div>

  <!-- Session profile strip (5-cell aggregate, immediately under hero) -->
  <div class="profile" id="profile" style="display:none">
    <div class="profile-cell">
      <div class="profile-label">Throttle avg</div>
      <div class="profile-value" id="prof-thr">&mdash;</div>
      <div class="profile-bar"><span id="prof-thr-bar" style="width:0"></span></div>
    </div>
    <div class="profile-cell">
      <div class="profile-label">Brake avg</div>
      <div class="profile-value" id="prof-brk">&mdash;</div>
      <div class="profile-bar brake"><span id="prof-brk-bar" style="width:0"></span></div>
    </div>
    <div class="profile-cell">
      <div class="profile-label">Slip avg</div>
      <div class="profile-value" id="prof-slip">&mdash;</div>
      <div class="profile-bar slip"><span id="prof-slip-bar" style="width:0"></span></div>
    </div>
    <div class="profile-cell">
      <div class="profile-label">Peak slip</div>
      <div class="profile-value" id="prof-pslip">&mdash;</div>
      <div class="profile-bar slip"><span id="prof-pslip-bar" style="width:0"></span></div>
    </div>
    <div class="profile-cell">
      <div class="profile-label">Slip &gt; 0.1</div>
      <div class="profile-value" id="prof-above">&mdash;</div>
      <div class="profile-bar slip"><span id="prof-above-bar" style="width:0"></span></div>
    </div>
  </div>

  <!-- Lap table -->
  <div class="laps">
    <div class="laps-head">
      <h2>Laps</h2>
      <span class="laps-hint">Click a header to sort &middot; click a row to inspect in telemetry</span>
    </div>
    <table class="lap-table">
      <thead><tr>
        <th class="sorted" data-sort="lap"  data-dir="asc">Lap <span class="sort-ind">&#x25B2;</span></th>
        <th data-sort="time">Time <span class="sort-ind">&#x21D5;</span></th>
        <th data-sort="s1">S1 &Delta; <span class="sort-ind">&#x21D5;</span></th>
        <th data-sort="s2">S2 &Delta; <span class="sort-ind">&#x21D5;</span></th>
        <th data-sort="s3">S3 &Delta; <span class="sort-ind">&#x21D5;</span></th>
        <th></th>
      </tr></thead>
      <tbody id="lap-tbody"></tbody>
    </table>
  </div>

  <!-- Three drill-in cards -->
  <div class="cards">
    <div class="card" id="card-loss">
      <div class="card-title">Where you lost time</div>
      <div class="card-headline" id="card-loss-headline">&mdash;</div>
      <div class="card-body" id="card-loss-body"></div>
      <a class="card-link" id="card-loss-link" href="#">Open in telemetry &rarr;</a>
    </div>
    <div class="card" id="card-car">
      <div class="card-title">Car context</div>
      <div class="card-headline" id="card-car-headline">&mdash;</div>
      <div class="card-body" id="card-car-body"></div>
      <a class="card-link" id="card-car-link" href="#" style="display:none">Show car history &rarr;</a>
    </div>
    <div class="card" id="card-ai">
      <div class="card-title">Coaching</div>
      <div class="card-body" id="card-ai-body" style="display:none"></div>
      <div class="ai-controls" id="ai-controls">
        <button class="btn-analyze" id="btn-analyze" onclick="runAnalysis(false)">Analyze with Claude</button>
        <button class="btn-re" id="btn-re" onclick="runAnalysis(true)" style="display:none">Re-analyze</button>
        <div class="ai-meta" id="ai-meta"></div>
      </div>
      <div class="ai-err" id="ai-err"></div>
    </div>
  </div>

</div> <!-- /.page -->
<script>
const TRACK_NAMES=
"""

# CAR_CATALOG is spliced between the two halves below — see listener.py.
SESSION_DETAIL_HTML_MID = """;
const CAR_CATALOG=
"""

SESSION_DETAIL_HTML_POST = """;</script>
<script src="/static/js/widgets/autocomplete.js"></script>
<script src="/static/js/class.js"></script>
<script src="/static/js/sessions_session.js"></script>
</body>
</html>
"""


# Sessions — the core content surface: a filter mechanism over every
# recorded session. H1 stays "Sessions"; filtering narrows all → slice.
# See docs/specs/ia.md.
SESSIONS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder &middot; Sessions</title>
<link rel="stylesheet" href="/static/tokens.css">
<link rel="stylesheet" href="/static/base.css">
<link rel="stylesheet" href="/static/sessions_car.css">
<link rel="stylesheet" href="/static/nav.css">
<style>
  .filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:var(--space-3) 0}
  .fdrop{position:relative}
  .fdrop-btn{display:flex;align-items:center;gap:7px;border:1px solid var(--color-border);
    background:var(--color-surface);color:var(--color-text-secondary);padding:7px 15px;
    border-radius:7px;font-size:14px;cursor:pointer}
  .fdrop-btn:hover{border-color:var(--color-text-tertiary);color:var(--color-text-primary)}
  .fdrop-btn.on{border-color:var(--color-accent);color:var(--color-text-primary)}
  .fdrop-btn .fct{background:var(--color-accent);color:#000;font-weight:700;border-radius:999px;
    padding:0 8px;font-size:13px}
  .fdrop-btn .fcar{color:var(--color-text-quaternary);font-size:12px}
  .fdrop-panel{display:none;position:absolute;top:calc(100% + 6px);left:0;z-index:50;
    min-width:240px;background:var(--color-surface);border:1px solid var(--color-border);
    border-radius:8px;box-shadow:0 12px 32px rgba(0,0,0,.5)}
  .fdrop.open .fdrop-panel{display:block}
  .fdrop.rich .fdrop-panel{min-width:430px}
  .fopt.rich .fnm{min-width:150px}
  .fdrop-top{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;
    border-bottom:1px solid var(--color-border);font-size:13px;text-transform:uppercase;
    letter-spacing:.08em;color:var(--color-text-quaternary)}
  .fclear{background:none;border:none;color:var(--color-accent);font:inherit;font-size:13px;cursor:pointer}
  .fclear:disabled{color:var(--color-text-quaternary);cursor:default}
  .fsrch{display:block;width:calc(100% - 16px);margin:8px;padding:7px 10px;
    background:var(--color-surface-2);border:1px solid var(--color-border);border-radius:6px;
    color:var(--color-text-primary);font:inherit;font-size:14px;outline:none}
  .fsrch:focus{border-color:var(--color-accent)}
  .fdrop-list{max-height:360px;overflow-y:auto;padding:6px}
  .fempty{padding:10px 12px;color:var(--color-text-quaternary);font-size:14px}
  .fopt{display:flex;align-items:center;gap:10px;width:100%;background:none;border:none;
    color:var(--color-text-secondary);font:inherit;font-size:16px;text-align:left;
    padding:8px 10px;border-radius:6px;cursor:pointer}
  .fopt:hover{background:var(--color-surface-2);color:var(--color-text-primary)}
  .fopt.on{color:var(--color-text-primary)}
  .fopt .fck{flex:0 0 18px;width:18px;height:18px;border:1.5px solid var(--color-text-tertiary);
    border-radius:4px;display:inline-flex;align-items:center;justify-content:center;
    background:var(--color-surface-2);color:transparent;font-size:12px;line-height:1}
  .fopt:hover .fck{border-color:var(--color-text-secondary)}
  .fopt.on .fck{background:var(--color-accent);border-color:var(--color-accent);color:#000}
  .fopt .fnm{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .fopt .fn{color:var(--color-text-quaternary);font-size:13px}
  .fopt.rich{display:grid;grid-template-columns:18px 1fr auto auto auto auto;gap:10px;align-items:center}
  .fopt .fbest{font-variant-numeric:tabular-nums;color:var(--color-text-secondary);font-size:14px}
  .fopt .fsp{display:block}
  .ftr{font-size:13px}
  .ftr.up{color:#22c55e}.ftr.dn{color:#ef4444}.ftr.fl{color:var(--color-text-quaternary)}
  .fclear-all{background:none;border:1px solid var(--color-border);color:var(--color-text-tertiary);
    padding:7px 15px;border-radius:7px;font-size:14px;cursor:pointer}
  .fclear-all:hover{color:var(--color-text-primary);border-color:var(--color-text-tertiary)}
  .stbl-wrap{overflow-x:auto;margin-top:var(--space-3)}
  .stbl{width:100%;border-collapse:collapse;font-size:14px}
  .sess-stickyhead{position:sticky;top:0;z-index:20;background:var(--color-bg);
    margin:0 calc(var(--space-4) * -1);padding:var(--space-3) var(--space-4) 8px;
    border-bottom:1px solid var(--color-border-subtle)}
  .stbl th{text-align:left;
    font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--color-text-tertiary);
    font-weight:600;padding:10px 14px;border-bottom:1px solid var(--color-border);
    cursor:pointer;white-space:nowrap;user-select:none}
  .stbl th:hover{color:var(--color-text-primary)}
  .stbl th.on{color:var(--color-text-primary)}
  .stbl th .ar{color:var(--color-accent);font-size:10px;margin-left:5px}
  .stbl th.num,.stbl td.num{text-align:right;font-variant-numeric:tabular-nums}
  .stbl td{padding:11px 14px;border-bottom:1px solid var(--color-border-subtle);
    color:var(--color-text-secondary);white-space:nowrap}
  .stbl tbody tr{cursor:pointer}
  .stbl tbody tr:hover td{background:var(--color-surface)}
  .stbl .c-name{color:var(--color-text-primary);font-weight:500}
  .stbl .c-sub{color:var(--color-text-quaternary);font-size:12px;margin-top:2px}
  .stbl .c-empty{padding:26px;text-align:center;color:var(--color-text-quaternary);font-style:italic}
  /* Tiny track outline next to the circuit name — speed-colored, shape
     recognizable at a glance. Empty before lazy-loaded; no border. */
  .stbl .c-cell{display:flex;align-items:center;gap:12px}
  .stbl .track-outline{width:56px;height:42px;flex-shrink:0;display:flex;
    align-items:center;justify-content:center}
  .stbl .track-outline svg{width:100%;height:100%;overflow:visible}
  .stbl .track-outline .tm-line line{stroke-width:1.6;stroke-linecap:round}
  @media(max-width:700px){.stbl .track-outline{display:none}}
  .swt{display:inline-flex;align-items:center;gap:9px;cursor:pointer;color:var(--color-text-secondary);font-size:14px;user-select:none}
  .swt input{position:absolute;opacity:0;width:0;height:0}
  .swt .tr{width:34px;height:19px;border-radius:999px;background:var(--color-surface-2);
    border:1px solid var(--color-border);position:relative;transition:background .15s}
  .swt .tr::after{content:"";position:absolute;top:2px;left:2px;width:13px;height:13px;border-radius:50%;
    background:var(--color-text-tertiary);transition:transform .15s,background .15s}
  .swt input:checked + .tr{background:rgba(232,184,75,.25);border-color:var(--color-accent)}
  .swt input:checked + .tr::after{transform:translateX(15px);background:var(--color-accent)}
  .swt.on{color:var(--color-text-primary)}
  .swt-help{position:relative;display:inline-flex;align-items:center;justify-content:center;
    width:16px;height:16px;border-radius:50%;border:1px solid var(--color-border);
    color:var(--color-text-quaternary);font-size:10px;font-weight:600;
    cursor:help;margin-left:6px;user-select:none;vertical-align:middle;
    background:var(--color-surface-2);transition:color .12s,border-color .12s}
  .swt-help:hover,.swt-help:focus{color:var(--color-text-primary);
    border-color:var(--color-accent);outline:none}
  /* Real popover instead of native title — was rendering nothing on some
     browsers / blocked by the click-to-close behaviour of the parent <label>. */
  .swt-help-tip{
    position:absolute;left:50%;transform:translateX(-50%);
    bottom:calc(100% + 8px);width:240px;
    padding:8px 10px;background:var(--color-surface-2);
    border:1px solid var(--color-border);border-radius:6px;
    color:var(--color-text-secondary);font-size:11px;font-weight:400;
    text-transform:none;letter-spacing:0;line-height:1.45;text-align:left;
    box-shadow:0 6px 14px -4px rgba(0,0,0,.6);
    opacity:0;visibility:hidden;pointer-events:none;
    transition:opacity .12s,visibility .12s;z-index:30;cursor:default}
  .swt-help-tip::after{content:"";position:absolute;left:50%;top:100%;
    transform:translateX(-50%);border:5px solid transparent;
    border-top-color:var(--color-border)}
  .swt-help:hover .swt-help-tip,
  .swt-help:focus .swt-help-tip{opacity:1;visibility:visible}
  /* Day separator — quiet banner between sessions of different days.
     Inserted as a <tr class="day-sep"> by sessions_list.js renderTable.
     Makes the page read like a journal (Sat: 5 sessions, Sun: 0…). */
  .stbl tr.day-sep td{
    background:transparent;border-top:1px solid var(--color-border);
    padding:18px 0 8px;
    color:var(--color-text-quaternary);
    font-size:var(--text-xs);text-transform:uppercase;letter-spacing:0.08em;
    cursor:default;
  }
  .stbl tr.day-sep:first-child td{border-top:none}
  .stbl tr.day-sep:hover td{background:transparent}
  .stbl tr.day-sep .day-sep-wkd{color:var(--color-text-tertiary);margin-left:6px}
  .stbl tr.day-sep .day-sep-cnt{margin-left:auto;color:var(--color-text-quaternary);
    text-transform:none;letter-spacing:0;font-size:11px}
  .stbl tr.day-sep td .day-sep-row{display:flex;align-items:baseline;gap:6px}

  /* Session-type chip — neutral letter badge that prefixes the row's
     sub-text (e.g. [R] Wet · Soft). Colour-neutral by design: the
     lap-time column already uses red/amber/green for the PB gap, so
     stacking another colour scale on race type was confusing. */
  .stbl .rt-chip{
    display:inline-flex;align-items:center;justify-content:center;
    min-width:20px;height:16px;padding:0 5px;margin-right:6px;
    background:var(--color-surface-2);border:1px solid var(--color-border);
    color:var(--color-text-secondary);
    border-radius:3px;font-size:9px;font-weight:700;
    letter-spacing:0.04em;font-variant-numeric:tabular-nums;
    vertical-align:middle;line-height:1;
  }
  /* Lap-count pill in the Date cell — tells apart a 1-lap test
     session from a 47-lap race without forcing a column. */
  .stbl .lap-count{
    display:inline-block;margin-left:8px;padding:1px 7px;
    background:var(--color-surface-2);border:1px solid var(--color-border);
    border-radius:999px;font-size:10px;color:var(--color-text-tertiary);
    font-variant-numeric:tabular-nums;letter-spacing:0.02em;vertical-align:middle;
  }
  /* Lap-time coloured by Δ to the track PB (across all cars). PBs
     get a ★; soft green for close; amber/red as the gap grows. */
  .stbl .bl{font-variant-numeric:tabular-nums}
  .stbl .bl-pb   {color:var(--color-green,#22c55e);font-weight:600}
  .stbl .bl-close{color:#86efac}
  .stbl .bl-mid  {color:var(--color-text-primary)}
  .stbl .bl-amber{color:var(--color-amber,#fbbf24)}
  .stbl .bl-bad  {color:var(--color-red,#f87171)}
  .stbl .bl-pb-star{margin-right:3px}

  /* Per-row lap-time sparkline — answers "how did this session go?"
     X = lap order, Y = lap_time_s (inverted: faster = up). A descending
     curve = improving over the session; ascending = fading; tight
     cluster = consistent. Best lap marked with an accent dot. Renders
     inline from s.lap_times (no fetch). Hidden when <2 valid laps. */
  .stbl .lap-spark{width:80px;height:36px;flex-shrink:0;
    display:flex;align-items:center;justify-content:center}
  .stbl .lap-spark svg{width:100%;height:100%;display:block}
  .stbl .lap-spark .ls-line{stroke:var(--color-text-secondary);stroke-width:1.3;
    fill:none;opacity:.7;stroke-linejoin:round;stroke-linecap:round}
  .stbl .lap-spark .ls-best{fill:var(--color-accent);stroke:none}
  .stbl .lap-spark:not([data-has-laps]){visibility:hidden}
  @media(max-width:900px){.stbl .lap-spark{display:none}}

  /* Pagination — filtering applies to ALL sessions; pager just slices
     to a 25-row page. Hidden when total filtered count fits one page. */
  .pager{display:flex;align-items:center;justify-content:center;gap:6px;
    margin:var(--space-4) 0;flex-wrap:wrap}
  .pg-btn{background:var(--color-surface);border:1px solid var(--color-border);
    color:var(--color-text-secondary);font:inherit;font-size:var(--text-sm);
    padding:6px 12px;border-radius:6px;cursor:pointer;
    transition:border-color 120ms,color 120ms,background 120ms}
  .pg-btn:hover:not(:disabled){color:var(--color-text-primary);border-color:var(--color-text-secondary)}
  .pg-btn:disabled{opacity:.35;cursor:default}
  .pg-pages{display:flex;gap:4px;flex-wrap:wrap}
  .pg-num{background:none;border:1px solid transparent;
    color:var(--color-text-secondary);font:inherit;font-size:var(--text-sm);
    min-width:32px;padding:6px 10px;border-radius:6px;cursor:pointer;
    font-variant-numeric:tabular-nums}
  .pg-num:hover{color:var(--color-text-primary);background:var(--color-surface)}
  .pg-num.cur{background:var(--color-accent);color:#000;font-weight:600;cursor:default}
  .pg-gap{padding:6px 4px;color:var(--color-text-quaternary);user-select:none}
</style>
</head>
<body>
<div id="pf-nav"></div>
<script src="/static/js/nav.js"></script>
<div class="page">

  <div class="sess-stickyhead">
    <div class="breadcrumb"><a href="/">Home</a> &rsaquo; <span>Sessions</span></div>

    <div class="titlewrap">
      <h1 class="nickname">Sessions</h1>
      <span class="canonical" id="sess-sub">Loading&hellip;</span>
    </div>

    <div class="filters" id="filters"></div>
  </div>

  <div class="stbl-wrap">
    <table class="stbl">
      <thead id="sess-head"></thead>
      <tbody id="sess-list"></tbody>
    </table>
  </div>

  <!-- Pagination — filtering applies to the full set; only the current
       page renders into the table. JS toggles visibility based on total
       filtered count. See sessions_list.js renderPager(). -->
  <div class="pager" id="sess-pager" style="display:none">
    <button class="pg-btn" id="pg-prev" aria-label="Previous page">&lsaquo; Prev</button>
    <div class="pg-pages" id="pg-pages"></div>
    <button class="pg-btn" id="pg-next" aria-label="Next page">Next &rsaquo;</button>
  </div>

</div>

<script src="/static/js/class.js"></script>
<script src="/static/js/track_mini.js"></script>
<script src="/static/js/sessions_list.js"></script>
</body>
</html>
"""
