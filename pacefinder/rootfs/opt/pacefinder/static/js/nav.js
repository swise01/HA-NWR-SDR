// Shared chrome — the left rail (docs/specs/ia.md). Renders into
// <div id="pf-nav"></div>: Live state indicator (top), Home / Sessions
// / Tracks / Cars, Settings at the bottom. Fixed rail + a body offset
// (via html.pf-has-rail) so pages need no DOM changes. Collapsible to
// icons (persisted). Mobile (<760) is a bottom bar — CSS-driven, same
// DOM. The live indicator polls /status and links to the dashboard;
// the dramatic takeover is a separate layer.
(function(){
  var root = document.getElementById('pf-nav');
  if(!root) return;

  // Embedded telemetry (iframe in session detail): parent shows chrome.
  if(new URLSearchParams(location.search).get('embed') === '1'){
    root.style.display = 'none';
    return;
  }

  var doc = document.documentElement;
  doc.classList.add('pf-has-rail');
  if(localStorage.getItem('pf-rail-icons') === '1') doc.classList.add('pf-rail-icons');

  var p = location.pathname;
  function section(){
    if(p === '/' ) return 'home';
    if(p.indexOf('/sessions/track') === 0 || p.indexOf('/circuits') === 0) return 'tracks';
    if(p.indexOf('/cars') === 0) return 'cars';
    if(p.indexOf('/sessions') === 0) return 'sessions';
    if(p.indexOf('/setup') === 0) return 'settings';
    return '';
  }
  var cur = section();
  function item(id, href, ico, label, end){
    var badge = (id === 'sessions')
      ? '<span class="pf-bd new" id="pf-new" style="display:none"></span>'+
        '<span class="pf-bd" id="pf-rev" style="display:none"></span>' : '';
    return '<a class="pf-it' + (end?' pf-end':'') + (cur===id?' cur':'') +
      '" id="pf-i-' + id + '" href="' + href + '" data-tip="' + label + '">' +
      '<span class="pf-ic">' + ico + '</span><span class="pf-lb">' + label +
      '</span>' + badge + '</a>';
  }

  root.className = 'pf-rail';
  root.innerHTML =
    '<div class="pf-top">' +
      '<a href="/" class="pf-brand">pacefinder<span class="pf-dot">.</span></a>' +
      '<button class="pf-collapse" id="pf-collapse" title="Collapse">⇆</button>' +
    '</div>' +
    '<a class="pf-live" id="pf-live" href="/dashboard">' +
      '<span class="pf-ld"></span><span id="pf-live-t">Loading…</span>' +
    '</a>' +
    '<div class="pf-items">' +
      item('home','/','⌂','Home') +
      item('sessions','/sessions','≣','Sessions') +
      item('tracks','/circuits','⌖','Circuits') +
      item('cars','/cars','⚙','Cars') +
      item('settings','/setup','⚙','Settings', true) +
    '</div>';

  document.getElementById('pf-collapse').addEventListener('click', function(){
    var on = doc.classList.toggle('pf-rail-icons');
    localStorage.setItem('pf-rail-icons', on ? '1' : '0');
  });

  // Sessions badges:
  //  • "N new"      → sessions recorded since the user's last visit to
  //                   /sessions (capture is browser-independent, so
  //                   unattended races would otherwise be invisible —
  //                   see docs/specs/unattended-capture-confirmation.md).
  //  • "N to review" → metadata gaps the user can fix. Just a nudge —
  //                    Sessions still loads chrono-by-default, the user
  //                    opts into the filter from the toggle.
  // Both can show together; they're independent signals.
  (async function(){
    try{
      var n = (await fetch('/sessions/needs-review').then(function(r){return r.json();})).count || 0;
      if(n > 0){
        var b = document.getElementById('pf-rev');
        b.textContent = n + ' to review'; b.style.display = '';
      }
    }catch(e){}
  })();
  (async function(){
    var ts = localStorage.getItem('pf-last-seen-sessions');
    if(!ts) return;   // first-load seed happens on /sessions visit
    try{
      var n = (await fetch('/sessions/new-since?ts=' + encodeURIComponent(ts))
        .then(function(r){return r.json();})).count || 0;
      if(n > 0){
        var b = document.getElementById('pf-new');
        b.textContent = n + ' new'; b.style.display = '';
      }
    }catch(e){}
  })();

  var live = document.getElementById('pf-live');
  var lt   = document.getElementById('pf-live-t');

  // Dramatic live takeover — auto on session start. Bold (per the IA
  // call) with one quiet, non-blocking escape. Shown once per race;
  // never on the dashboard itself (you're already in the live view).
  var onDash = (p.indexOf('/dashboard') === 0);
  var to = document.createElement('div');
  to.className = 'pf-to';
  to.innerHTML =
    '<div class="pf-to-card">' +
      '<div class="pf-to-eyebrow"><span class="pf-ld"></span>Telemetry live</div>' +
      '<div class="pf-to-title">You’re in a race.</div>' +
      '<div class="pf-to-sub">Recording every lap.</div>' +
      '<div class="pf-to-actions">' +
        '<a class="pf-to-go" href="/dashboard">Open live dashboard</a>' +
        '<button class="pf-to-back" id="pf-to-back">‹ back to analysis</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(to);
  var shown = false;            // already taken over for this race
  document.getElementById('pf-to-back').addEventListener('click', function(){
    to.classList.remove('show');
  });

  function paint(s){
    var st = s && s.status;
    var hot = (st === 'racing' || st === 'paused');
    if(hot){
      live.className = 'pf-live live'; lt.textContent = 'Recording · view live';
      if(!shown && !onDash){ shown = true; to.classList.add('show'); }
    } else if(st === 'race_ended'){
      live.className = 'pf-live ended'; lt.textContent = 'Race ended';
      to.classList.remove('show');
    } else {
      live.className = 'pf-live'; lt.textContent = 'Idle · no session';
      to.classList.remove('show'); shown = false; // re-arm for next race
    }
    // Perf HUD lifecycle — mount on first /status saying debug_mode=true,
    // tear down if the toggle gets flipped off. Embed mode never gets it
    // (the parent page is the one showing chrome).
    if(s && s.debug_mode) mountPerfHud(); else unmountPerfHud();
  }

  // ── Perf overlay (debug mode) ───────────────────────────────────
  // Floating bottom-right card showing median + p95 + last request from
  // /debug/perf. Data is already collected by net/perf.py for every
  // request; this just surfaces it so you spot regressions live without
  // re-running bench_perf.py or grepping logs. See docs/specs/...
  var _perfTimer = null, _perfHud = null;
  function mountPerfHud(){
    if(_perfHud) return;
    _perfHud = document.createElement('div');
    _perfHud.className = 'pf-perf-hud';
    _perfHud.innerHTML =
      '<div class="pf-perf-head">' +
        '<span class="pf-perf-eyebrow">Perf · debug</span>' +
        '<button class="pf-perf-toggle" id="pf-perf-toggle">expand</button>' +
      '</div>' +
      '<div class="pf-perf-grid">' +
        '<span class="k">median</span><span class="v" id="pf-perf-med">—</span>' +
        '<span class="k">p95</span><span class="v" id="pf-perf-p95">—</span>' +
        '<span class="k">db share</span><span class="v" id="pf-perf-db">—</span>' +
        '<span class="k">samples</span><span class="v" id="pf-perf-n">—</span>' +
      '</div>' +
      '<div class="pf-perf-last" id="pf-perf-last">no requests yet</div>' +
      '<div class="pf-perf-list" id="pf-perf-list"></div>';
    document.body.appendChild(_perfHud);
    document.getElementById('pf-perf-toggle').addEventListener('click', function(){
      var expanded = _perfHud.classList.toggle('expanded');
      this.textContent = expanded ? 'collapse' : 'expand';
    });
    pollPerf();
    _perfTimer = setInterval(pollPerf, 3000);
  }
  function unmountPerfHud(){
    if(!_perfHud) return;
    clearInterval(_perfTimer); _perfTimer = null;
    _perfHud.remove(); _perfHud = null;
  }
  function _cls(ms){ return ms > 500 ? 'bad' : ms > 150 ? 'warn' : ''; }
  function _short(p){ return p.length > 38 ? p.slice(0,36) + '…' : p; }
  async function pollPerf(){
    var d;
    try{ d = await fetch('/debug/perf?json=1').then(function(r){return r.json();}); }
    catch(e){ return; }
    var rows = (d && d.server) || [];
    if(!rows.length){
      _setText('pf-perf-med','—'); _setText('pf-perf-p95','—');
      _setText('pf-perf-db','—'); _setText('pf-perf-n','0');
      _setText('pf-perf-last','no requests yet');
      var list = document.getElementById('pf-perf-list'); if(list) list.innerHTML = '';
      return;
    }
    var times = rows.map(function(r){return r.total_ms;}).sort(function(a,b){return a-b;});
    var med = times[Math.floor(times.length/2)];
    var p95 = times[Math.max(0, Math.floor(times.length*0.95)-1)];
    var dbSum = rows.reduce(function(a,r){return a + (r.db_ms||0);}, 0);
    var totSum = rows.reduce(function(a,r){return a + r.total_ms;}, 0);
    var dbPct = totSum > 0 ? Math.round(dbSum/totSum*100) : 0;
    _setText('pf-perf-med', med.toFixed(1)+'ms', _cls(med));
    _setText('pf-perf-p95', p95.toFixed(1)+'ms', _cls(p95));
    _setText('pf-perf-db', dbPct + '%');
    _setText('pf-perf-n', rows.length);
    var last = rows[rows.length-1];
    var lastEl = document.getElementById('pf-perf-last');
    if(lastEl){
      var cls = _cls(last.total_ms);
      lastEl.innerHTML = '<span style="color:var(--color-text-quaternary)">last</span> '+
        '<span class="'+cls+'" style="color:'+(cls==='bad'?'var(--color-red,#f87171)':cls==='warn'?'var(--color-amber,#fbbf24)':'inherit')+'">'+
        last.total_ms.toFixed(1)+'ms</span> '+_short(last.path);
    }
    var list = document.getElementById('pf-perf-list');
    if(list){
      // Tail of the ring, newest at the bottom. Aligns with how journalctl
      // reads — last-line-is-now is the muscle memory we're matching.
      list.innerHTML = rows.slice(-20).map(function(r){
        return '<div class="r">'+
          '<span class="p">'+r.method+' '+_short(r.path)+'</span>'+
          '<span class="t '+_cls(r.total_ms)+'">'+r.total_ms.toFixed(1)+'ms</span>'+
          '<span class="d">db '+(r.db_ms||0).toFixed(0)+'</span>'+
        '</div>';
      }).join('');
      list.scrollTop = list.scrollHeight;
    }
  }
  function _setText(id, txt, cls){
    var el = document.getElementById(id); if(!el) return;
    el.textContent = txt; el.className = 'v' + (cls ? ' '+cls : '');
  }
  async function poll(){
    try{ paint(await fetch('/status').then(function(r){return r.json();})); }
    catch(e){}
  }
  poll();
  setInterval(poll, 10000);
})();
