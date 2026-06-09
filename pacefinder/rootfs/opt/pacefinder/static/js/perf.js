// Lightweight per-page perf instrumentation.
// Spec: docs/specs/perf-audit-and-instrument.md
// Usage:
//   import './perf.js' (or include via <script>)
//   Perf.mark('fetch:start');
//   ...
//   Perf.measure('fetch', 'fetch:start');   // records elapsed since the mark
//   Perf.report();                          // POST + console.table on page-stable
//
// `report()` is debounced — only the last call within 500ms after page-stable
// actually fires. Safe to call from many places (e.g. after each render pass).

window.Perf = (function(){
  const _marks = {};
  const _measures = {};
  let _reportTimer = null;
  let _stableTimer = null;
  let _autoReportPath = null;

  function _now(){ return performance.now(); }

  function mark(name){
    _marks[name] = _now();
  }

  function measure(name, startMark){
    const t0 = _marks[startMark];
    if (t0 == null) return;
    _measures[name] = +((_now() - t0).toFixed(1));
  }

  function setMeasure(name, ms){
    _measures[name] = +(+ms).toFixed(1);
  }

  function _navTimings(){
    // Pull the standard browser-supplied page-load milestones — no work in the
    // page itself required to surface dom-content-loaded vs full-load times.
    const e = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || null;
    if (!e) return {};
    return {
      'nav:dom':  +(e.domContentLoadedEventEnd - e.startTime).toFixed(1),
      'nav:load': +(e.loadEventEnd - e.startTime).toFixed(1),
      'nav:ttfb': +(e.responseStart - e.startTime).toFixed(1),
    };
  }

  async function _post(path){
    try {
      await fetch('/debug/perf/client', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          path: path || location.pathname,
          ua: navigator.userAgent,
          marks: { ..._navTimings(), ..._measures },
        }),
        keepalive: true,
      });
    } catch(_) { /* swallow */ }
  }

  function report(path){
    clearTimeout(_reportTimer);
    _reportTimer = setTimeout(() => {
      try { console.table(_measures); } catch(_) {}
      _post(path);
    }, 100);
  }

  // Schedule report() to fire 500ms after the page becomes "stable" — defined
  // as no further calls to mark/measure for 500ms straight. Cheap heuristic.
  function autoReport(path){
    _autoReportPath = path || location.pathname;
    bumpStable();
  }
  function bumpStable(){
    clearTimeout(_stableTimer);
    _stableTimer = setTimeout(() => report(_autoReportPath), 500);
  }
  // Patch mark/measure to bump stability if autoReport was armed.
  const _origMark = mark;
  const _origMeasure = measure;
  return {
    mark: function(n){ _origMark(n); if (_autoReportPath) bumpStable(); },
    measure: function(n,s){ _origMeasure(n,s); if (_autoReportPath) bumpStable(); },
    setMeasure: setMeasure,
    report: report,
    autoReport: autoReport,
  };
})();
