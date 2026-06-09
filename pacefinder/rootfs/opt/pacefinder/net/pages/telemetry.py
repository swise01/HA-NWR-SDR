TELEMETRY_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder &middot; Telemetry</title>
<link rel="stylesheet" href="/static/tokens.css">
<link rel="stylesheet" href="/static/base.css">
<link rel="stylesheet" href="/static/nav.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--color-bg);color:var(--color-text-primary);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;font-variant-numeric:tabular-nums;min-height:100vh;overflow-x:hidden}
a{color:inherit;text-decoration:none}
.tb{height:50px;display:flex;align-items:center;padding:0 var(--space-4);gap:14px;border-bottom:1px solid var(--color-border);background:var(--color-bg);z-index:20;position:sticky;top:0}
.tb h1{font-size:var(--text-md);color:var(--color-text-primary);letter-spacing:3px;text-transform:uppercase;flex:1}
.tb-nav{display:flex;gap:14px}
.tb-nav a{font-size:var(--text-xs);color:var(--color-text-secondary);letter-spacing:1px;text-transform:uppercase}
.tb-nav a:hover{color:var(--color-text-primary)}
.tb-nav a.cur{color:var(--color-text-primary);border-bottom:1px solid var(--color-text-secondary)}
.breadcrumb{font-size:var(--text-xs);color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.08em;padding:var(--space-2) var(--space-4);border-bottom:1px solid var(--color-border)}
.breadcrumb a{color:var(--color-text-tertiary)}.breadcrumb a:hover{color:var(--color-text-primary)}
.subnav{display:flex;align-items:center;gap:2px;padding:6px var(--space-4);border-bottom:1px solid var(--color-border);flex-wrap:wrap}
.subnav-item{font-size:var(--text-sm);color:var(--color-text-tertiary);text-decoration:none;padding:8px 14px;border-radius:6px;transition:color 120ms,background 120ms}
.subnav-item:hover{color:var(--color-text-primary);background:var(--color-surface)}
.subnav-item.active{color:var(--color-text-primary);background:var(--color-surface);box-shadow:inset 0 -2px 0 var(--color-accent)}
.tele-layout{display:flex;min-height:calc(100vh - 90px);gap:8px;padding:8px}
.ctrl-col{width:220px;flex-shrink:0;background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);padding:var(--sp-3) var(--sp-4);overflow-y:auto;position:sticky;top:58px;max-height:calc(100vh - 66px);align-self:flex-start}
/* Right-side HUD column — cockpit-style live readouts driven by paintCursor.
   Hidden until at least one lap is selected, hidden on narrow viewports. */
.hud-col{width:264px;flex-shrink:0;position:sticky;top:58px;max-height:calc(100vh - 66px);align-self:flex-start;
  display:flex;flex-direction:column;gap:10px;font-family:var(--font-mono,ui-monospace,monospace);font-variant-numeric:tabular-nums}
html.embed .hud-col{top:0;max-height:100vh}
.hud-head{display:flex;align-items:center;justify-content:space-between;padding:0 4px;gap:8px}
/* Lap selector — one chip per selected lap. Primary is filled, others
   are outlined; clicking a non-primary chip swaps focus. Keeps the HUD
   driven from inside the rail so you don't have to reach back to the
   left ctrl-col to switch which lap the numbers represent. */
.hud-lapsel{display:flex;flex-wrap:wrap;gap:4px;min-width:0;flex:1}
.hud-lapsel-btn{display:inline-flex;align-items:center;gap:5px;
  padding:3px 8px 3px 5px;background:transparent;cursor:pointer;
  border:1px solid var(--c,var(--color-border));border-radius:999px;
  font:inherit;font-size:11px;color:var(--color-text-tertiary);
  letter-spacing:0.04em;line-height:1;transition:background .12s,color .12s}
.hud-lapsel-btn::before{content:"";width:8px;height:8px;border-radius:50%;
  background:var(--c,var(--color-text-quaternary));flex-shrink:0;
  box-shadow:0 0 0 1px rgba(0,0,0,.5) inset}
.hud-lapsel-btn:hover{color:var(--color-text-primary)}
.hud-lapsel-btn.is-primary{background:color-mix(in srgb,var(--c) 18%,transparent);
  color:var(--color-text-primary);cursor:default}
.hud-pos{font-size:10px;color:var(--color-text-quaternary);flex-shrink:0;align-self:center}
.hud-refrow{padding:0 4px;font-size:10px;color:var(--color-text-quaternary);text-transform:uppercase;
  letter-spacing:0.06em;margin-top:-4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hud-refrow #hud-ref-name{color:var(--color-text-tertiary)}
.hud-card{background:var(--color-surface);border:1px solid var(--color-border);border-radius:8px;padding:12px 14px}
.hud-card-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:4px}
.hud-lbl{font-size:10px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.08em}
.hud-ref{font-size:10px;color:var(--color-text-quaternary)}
.hud-big{font-size:42px;font-weight:500;line-height:1;letter-spacing:-1px;color:var(--color-text-primary)}
.hud-unit{font-size:13px;color:var(--color-text-quaternary);margin-left:6px;letter-spacing:0}
.hud-delta{display:flex;align-items:center;gap:6px;margin-top:4px;font-size:11px;color:var(--color-text-quaternary);min-height:14px}
.hud-delta .v{font-variant-numeric:tabular-nums}
.hud-delta .v.gain{color:var(--color-green,#4ade80)}
.hud-delta .v.lost{color:var(--color-red,#f87171)}
.hud-bar-row{display:grid;grid-template-columns:36px 1fr 40px;gap:8px;align-items:center;margin-top:8px}
.hud-bar-row:first-of-type{margin-top:4px}
.hud-bar-lbl{font-size:10px;color:var(--color-text-tertiary)}
.hud-bar{position:relative;height:10px;background:var(--color-surface-2);border-radius:2px;overflow:hidden}
.hud-bar-fill{position:absolute;left:0;top:0;bottom:0;width:0;transition:width 60ms linear}
.hud-bar-fill.thr{background:linear-gradient(90deg,rgba(74,222,128,.33),#4ade80)}
.hud-bar-fill.brk{background:linear-gradient(90deg,rgba(248,113,113,.33),#f87171)}
.hud-bar-tick{position:absolute;top:-1px;bottom:-1px;width:1px;background:rgba(255,255,255,.55);display:none}
.hud-bar-val{font-size:13px;text-align:right;font-variant-numeric:tabular-nums}
.hud-bar-val.thr{color:var(--color-green,#4ade80)}
.hud-bar-val.brk{color:var(--color-red,#f87171)}
.hud-row2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.hud-row2 .hud-card{padding:10px 12px}
.hud-mid{font-size:28px;font-weight:500;line-height:1;margin-top:4px}
.hud-mid.gain{color:var(--color-green,#4ade80)}.hud-mid.lost{color:var(--color-red,#f87171)}
.hud-delta-sub{font-size:10px;color:var(--color-text-quaternary);margin-left:4px}
@media(max-width:1180px){.hud-col{display:none}}
/* Track map lives inside the HUD column now. Strip the wide-layout
   sticky/shadow and the inset border so the SVG goes edge-to-edge of
   the rail. HUD column is already sticky — no need for own sticky. */
.hud-map{position:static;top:auto;box-shadow:none;background:transparent;margin:0;
  border:none;border-radius:0;overflow:visible}
.hud-map .tm-lbl{padding:0 2px 6px;border-bottom:none}
.hud-map #track-map-inner{background:transparent}
.hud-map #track-map-inner svg{max-height:none !important;background:transparent}
/* In embed mode the iframe's own .tb is hidden, so anchor sticky to 0 and
   give the iframe body min-height:0 so it doesn't double-scroll the parent. */
html.embed body{min-height:0}
html.embed .tele-layout{min-height:0}
html.embed .ctrl-col{top:0;max-height:100vh}
@media(max-width:768px){.tele-layout{flex-direction:column}.ctrl-col{width:100%;position:static;max-height:none;border-right:none;border-bottom:1px solid var(--border-sub)}}
.ctrl-section{margin-bottom:var(--sp-4)}
.ctrl-lbl{font-size:10px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:var(--space-2)}
.lap-item{display:flex;align-items:center;gap:8px;padding:6px var(--space-2);font-size:var(--text-sm);cursor:pointer;border-radius:var(--radius-sm);user-select:none}
.lap-item:hover{background:var(--color-surface-2)}
.lap-swatch{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.lap-time-s{color:var(--color-text-tertiary);margin-left:auto;font-size:11px;font-variant-numeric:tabular-nums}
.lap-best-badge{font-size:10px;color:var(--color-accent)}
input[type=checkbox]{accent-color:var(--color-accent);width:12px;height:12px;flex-shrink:0}
.ch-grid{display:grid;grid-template-columns:1fr 1fr;gap:2px}
.ch-tog{display:flex;align-items:center;gap:6px;font-size:var(--text-sm);color:var(--color-text-secondary);padding:6px var(--space-2);border-radius:var(--radius-sm);cursor:pointer;user-select:none}
.ch-tog:hover{background:var(--color-surface-2);color:var(--color-text-primary)}
.xmode-btns{display:flex;gap:3px}
.xmode-btn{flex:1;background:var(--color-surface-2);border:1px solid var(--surface-bd);color:var(--color-text-secondary);font-family:inherit;font-size:var(--text-xs);padding:4px 0;border-radius:var(--radius-sm);cursor:pointer;text-align:center}
.xmode-btn.active{background:var(--accent-bg);border-color:var(--accent-bd);color:var(--accent-soft)}
.ctrl-sel{width:100%;background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-primary);font-family:inherit;font-size:var(--text-sm);padding:6px 8px;border-radius:var(--radius-sm)}
.panels-col{flex:1;min-width:0;padding:var(--sp-3) var(--sp-4) var(--sp-6)}
/* Track map promoted to a sticky panel at the top of the charts column.
   JS (renderTrackMap) still controls visibility — it only un-hides the
   wrap when the lap actually has px/pz position samples. */
.track-map-wrap{
  position:sticky;top:58px;z-index:20;
  margin:0 0 var(--sp-3);
  border:1px solid var(--color-border);border-radius:var(--radius-md);
  background:var(--color-bg);overflow:hidden;
  /* Hard mask: opaque page-bg + a shadow so charts scrolling under the
     pinned panel can never read through (was bleeding — the SVG
     letterboxes with transparent margins inside a wide column). */
  box-shadow:0 8px 14px -6px rgba(0,0,0,0.95);
}
/* The map SVG meet-fits with transparent side margins; give the SVG box
   the page bg so those margins are solid, not see-through. Cap height so
   the pinned panel stays compact instead of a tall void. */
#track-map-inner{background:var(--color-bg)}
#track-map-inner svg{
  background:var(--color-bg);
  width:100%;display:block;
}
html.embed .track-map-wrap{top:0}
.sector-hdr{margin-bottom:var(--sp-3);border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface);overflow:hidden}
.s-hdr-row{display:flex;align-items:center;padding:8px var(--sp-3);gap:var(--sp-2);border-bottom:1px solid var(--color-border-subtle);font-size:11px}
.s-hdr-row:last-child{border-bottom:none}
.s-row-lbl{width:24px;color:var(--color-text-tertiary);font-size:10px;text-transform:uppercase;letter-spacing:0.08em;flex-shrink:0}
.s-cell{flex:1;text-align:center;font-variant-numeric:tabular-nums;font-size:var(--text-sm);color:var(--color-text-secondary)}
.s-cell.best{color:var(--color-accent);font-weight:600}
.s-cell-d{flex:.7}
.s-cell-hd{flex:1;text-align:center;font-size:10px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.08em}
.lap-summaries{margin-bottom:var(--sp-3);display:flex;flex-direction:column;gap:4px}
.lap-sum-bar{display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap;padding:10px var(--sp-3);border-radius:var(--radius-md);background:var(--color-surface);border:1px solid var(--color-border);border-left:3px solid}
.lsb-l{font-size:var(--text-sm);font-weight:600;width:48px;flex-shrink:0}
.lsb-t{font-size:var(--text-md);font-weight:700;font-variant-numeric:tabular-nums;width:84px;flex-shrink:0}
.lsb-s{font-size:11px;color:var(--color-text-tertiary);font-variant-numeric:tabular-nums}
.lsb-d{font-size:var(--text-sm);font-variant-numeric:tabular-nums;margin-left:auto}
.lsb-slip{font-size:var(--text-md);color:var(--color-text-tertiary)}
.panel-wrap{margin-bottom:8px}
.panel-lbl-row{display:flex;align-items:baseline;margin-bottom:6px;min-height:14px}
.p-lbl{font-size:10px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.08em;font-weight:500}
.ref-tag{margin-left:auto;font-size:10px;color:var(--color-text-tertiary);letter-spacing:0.08em;text-transform:uppercase;padding:2px 7px;border:1px solid var(--color-border);border-radius:4px}
.panel-svg-wrap{position:relative;overflow:hidden;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-surface);cursor:crosshair}
.panel-svg-wrap.panning{cursor:grab}
.chart-zoom-ctrl{position:absolute;top:4px;right:4px;display:flex;gap:3px;z-index:10;pointer-events:auto}
.czc-btn{background:rgba(20,20,28,.75);border:1px solid var(--color-border);color:var(--color-text-secondary);font-family:inherit;font-size:calc(var(--text-xs) * 1.3);padding:2px 7px;border-radius:var(--radius-sm);cursor:pointer;line-height:1.5;backdrop-filter:blur(4px)}
.czc-btn:hover{border-color:var(--color-text-secondary);color:var(--color-text-primary)}
.panel-svg-wrap svg{display:block;width:100%}
.px-line{position:absolute;top:0;bottom:0;width:1px;background:rgba(255,255,255,.16);pointer-events:none;display:none}
.px-line.locked{background:var(--color-accent,#f59e0b);width:2px;opacity:.85;box-shadow:0 0 4px rgba(245,158,11,.4)}
#tele-tip{position:fixed;background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-primary);font-size:var(--text-xs);padding:5px 10px;border-radius:4px;pointer-events:none;display:none;z-index:200;white-space:pre;line-height:1.7;font-family:var(--font-mono);min-width:160px}
.tm-lbl{font-size:10px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:0.08em;padding:8px var(--sp-3);border-bottom:1px solid var(--color-border-subtle)}
#drag-sel{position:absolute;background:rgba(245,158,11,.18);border:2px dashed rgba(245,158,11,.85);box-shadow:inset 0 0 0 1px rgba(0,0,0,.4),0 0 8px rgba(245,158,11,.35);pointer-events:none;display:none;top:0;bottom:0;border-radius:2px;z-index:5}
.tele-help{display:flex;flex-wrap:wrap;gap:10px;padding:8px 12px;margin-bottom:var(--sp-3);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);font-size:11px;color:var(--color-text-tertiary)}
.tele-help kbd{background:var(--color-surface-2);border:1px solid var(--color-border);border-bottom-width:2px;border-radius:3px;padding:1px 5px;font-family:var(--font-mono);font-size:10px;color:var(--color-text-secondary)}
.tele-help-sep{color:var(--color-text-quaternary)}
.x-lbl-row{display:flex;justify-content:space-between;font-size:10px;color:var(--color-text-quaternary);margin-top:3px;padding:0 1px;font-family:var(--font-mono)}
/* Per-chart mini-axis (issue #12 polish bundle). Same percentages as
   .x-lbl-row but rendered under every chart for at-a-glance scanning. */
.px-axis{display:flex;justify-content:space-between;font-size:10px;color:var(--color-text-quaternary);padding:2px 1px 4px;line-height:1;font-family:var(--font-mono)}
#tele-loading{color:var(--color-text-tertiary);font-size:var(--text-sm);padding:60px;text-align:center}
.delta-neg{color:var(--color-green)}.delta-pos{color:var(--color-red)}
.ctrl-sub{font-size:11px;color:var(--color-text-tertiary);margin-top:4px;padding-left:2px}
.cs-ovl{display:none;position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:300;align-items:center;justify-content:center}
.cs-ovl.open{display:flex}
.mo-ovl{display:none;position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:310;align-items:center;justify-content:center;padding:24px}
.mo-ovl.open{display:flex}
.mo-card{position:relative;width:min(1000px,96vw);height:min(86vh,820px);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);overflow:hidden}
.mo-if{width:100%;height:100%;border:0;background:var(--color-bg)}
.mo-x{position:absolute;top:8px;right:10px;z-index:2;background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-primary);border-radius:6px;font-size:18px;line-height:1;padding:4px 10px;cursor:pointer}
.mo-x:hover{border-color:var(--color-text-secondary)}
.cs-panel{background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);padding:18px 20px;min-width:360px;max-width:640px;max-height:80vh;overflow:auto}
.cs-ttl{font-size:var(--text-md);color:var(--color-text-primary);margin-bottom:14px;font-weight:600}
.cs-sess{padding:10px 12px;border:1px solid var(--color-border-subtle);border-radius:var(--radius-sm);margin-bottom:6px;cursor:pointer;background:var(--color-bg)}
.cs-sess:hover{border-color:var(--color-text-tertiary)}
.cs-sess-hd{display:flex;justify-content:space-between;font-size:var(--text-sm);color:var(--color-text-primary)}
.cs-sess-meta{font-size:11px;color:var(--color-text-tertiary);margin-top:2px}
.cs-laps{display:none;margin-top:8px;padding-top:8px;border-top:1px solid var(--color-border-subtle)}
.cs-sess.expanded .cs-laps{display:block}
.cs-lap{padding:5px 8px;font-size:var(--text-sm);color:var(--color-text-secondary);cursor:pointer;border-radius:var(--radius-sm);font-variant-numeric:tabular-nums}
.cs-lap:hover{background:var(--color-surface-2);color:var(--color-text-primary)}
.cs-empty{padding:18px;text-align:center;color:var(--color-text-tertiary);font-size:var(--text-sm)}
.cs-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}
.cs-btn{background:var(--color-surface-2);border:1px solid var(--color-border);color:var(--color-text-primary);font-family:inherit;font-size:var(--text-sm);padding:6px 14px;border-radius:var(--radius-sm);cursor:pointer}
.cs-btn:hover{border-color:var(--color-text-secondary)}
@media(max-width:768px){.lsb-slip,.lsb-s{display:none}.lap-sum-bar{flex-wrap:nowrap}}
</style>
</head>
<body>
<div id="pf-nav"></div>
<script src="/static/js/_safe.js"></script>
<script src="/static/js/nav.js"></script>
<script>
// Embedded in the session-detail iframe: nav.js hides #pf-nav itself;
// here we also drop the in-iframe breadcrumb/subnav (the parent page
// already shows them) and pin .ctrl-col to the top.
if(new URLSearchParams(location.search).get('embed')==='1'){
  document.documentElement.classList.add('embed');
  const bc=document.getElementById('tele-breadcrumb');
  if(bc) bc.style.display='none';
  const sn=document.getElementById('tele-subnav');
  if(sn) sn.style.display='none';
}
</script>
<div class="breadcrumb" id="tele-breadcrumb">
  <a href="/sessions">Sessions</a> &rsaquo;
  <a href="#" id="bc-game" style="display:none"></a><span id="bc-gsep" style="display:none"> &rsaquo; </span>
  <a href="#" id="bc-track"></a> &rsaquo;
  <a href="#" id="bc-sess"></a> &rsaquo;
  <span>Telemetry</span>
</div>
<div class="subnav" id="tele-subnav">
  <a class="subnav-item" id="link-overview" href="#">Overview</a>
  <span class="subnav-item active">Full telemetry</span>
  <button class="subnav-item" id="link-mistakes" style="background:none;border:none;cursor:pointer;font:inherit">Mistakes &amp; opportunities</button>
</div>
<div class="mo-ovl" id="mo-ovl">
  <div class="mo-card">
    <button class="mo-x" id="mo-x" aria-label="Close">&times;</button>
    <iframe class="mo-if" id="mo-if" title="Mistakes &amp; opportunities"></iframe>
  </div>
</div>
<div class="tele-layout">
<div class="ctrl-col" id="ctrl-col">
  <div id="ctrl-loading" style="color:var(--n-400);font-size:.78rem;padding:8px 0">Loading&hellip;</div>
  <div id="ctrl-inner" style="display:none">
    <div class="ctrl-section">
      <div class="ctrl-lbl" title="Up to 4 laps can be selected for overlay comparison. Capped at 4 so the chart and track-map colors stay legible — picking a 5th drops the oldest selection.">Laps (up to 4)</div>
      <div id="lap-list"></div>
    </div>
    <div class="ctrl-section">
      <div class="ctrl-lbl">Reference</div>
      <select class="ctrl-sel" id="ref-sel" onchange="onRefChange()">
        <option value="">None</option>
        <option value="best_lap" selected>My Best Lap</option>
        <option value="theoretical">Theoretical Best</option>
        <option value="last_lap">Last Lap</option>
        <option value="cross_session">Lap from another session…</option>
      </select>
      <div id="cs-ref-label" class="ctrl-sub" style="display:none"></div>
      <div id="ref-status" class="ctrl-sub" style="display:none;color:var(--warn,#f59e0b)"></div>
    </div>
    <div class="ctrl-section">
      <div class="ctrl-lbl">Channels</div>
      <div class="ch-grid">
        <label class="ch-tog"><input type="checkbox" id="ch-speed" checked onchange="renderAll()"> Speed</label>
        <label class="ch-tog"><input type="checkbox" id="ch-throttle" checked onchange="renderAll()"> Throttle</label>
        <label class="ch-tog"><input type="checkbox" id="ch-brake" checked onchange="renderAll()"> Brake</label>
        <label class="ch-tog"><input type="checkbox" id="ch-gear" checked onchange="renderAll()"> Gear</label>
        <label class="ch-tog"><input type="checkbox" id="ch-steer" onchange="renderAll()"> Steering</label>
        <label class="ch-tog"><input type="checkbox" id="ch-slip" checked onchange="renderAll()"> Slip</label>
        <label class="ch-tog"><input type="checkbox" id="ch-tyre" onchange="renderAll()"> Tyres</label>
      </div>
    </div>
    <!-- X-axis toggle hidden until Time mode has a clear use case;
         distance is the default per-distance industry standard.
         Buttons kept off-page so setXMode() callers don't NPE. -->
    <div class="xmode-btns" style="display:none">
      <button class="xmode-btn active" id="xm-dist">Distance</button>
      <button class="xmode-btn" id="xm-time">Time</button>
    </div>
  </div>
</div>
<div class="panels-col">
  <div id="tele-loading">Loading telemetry data&hellip;</div>
  <div id="panels-inner" style="display:none">
    <div id="sector-hdr" class="sector-hdr"></div>
    <div id="lap-summaries" class="lap-summaries"></div>
    <div class="tele-help" id="tele-help">
      <span><kbd>drag</kbd> zoom to selection</span>
      <span class="tele-help-sep">·</span>
      <span><kbd>space</kbd>+<kbd>drag</kbd> pan when zoomed</span>
      <span class="tele-help-sep">·</span>
      <span><kbd>click</kbd> lock cursor</span>
      <span class="tele-help-sep">·</span>
      <span><kbd>←</kbd> <kbd>→</kbd> nudge (with <kbd>shift</kbd> = 10×)</span>
      <span class="tele-help-sep">·</span>
      <span><kbd>esc</kbd> unlock</span>
    </div>
    <div id="charts-area" style="position:relative">
      <div class="chart-zoom-ctrl">
        <button class="czc-btn" onclick="resetZoom()">Reset</button>
        <button class="czc-btn" onclick="stepZoom(-1)">−</button>
        <button class="czc-btn" onclick="stepZoom(1)">+</button>
      </div>
      <div id="drag-sel"></div>
      <div id="panels-empty" style="display:none;color:var(--n-400);font-size:.9rem;padding:60px;text-align:center">Select at least one lap to view telemetry.</div>
      <div id="panel-delta" class="panel-wrap"></div>
      <div id="panel-speed" class="panel-wrap"></div>
      <div id="panel-throttle" class="panel-wrap"></div>
      <div id="panel-brake" class="panel-wrap"></div>
      <div id="panel-gear" class="panel-wrap"></div>
      <div id="panel-steer" class="panel-wrap"></div>
      <div id="panel-slip" class="panel-wrap"></div>
      <div id="panel-tyre" class="panel-wrap"></div>
    </div>
    <div class="x-lbl-row"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>
  </div>
</div>
<aside class="hud-col" id="hud-col" style="display:none">
  <div class="track-map-wrap hud-map" id="track-map-wrap" style="display:none">
    <div class="tm-lbl">Track map &mdash; colour = speed</div>
    <div id="track-map-inner"></div>
  </div>
  <div class="hud-head">
    <div class="hud-lapsel" id="hud-lapsel" title="Click a lap to focus the HUD on it"></div>
    <span class="hud-pos" id="hud-pos">— %</span>
  </div>
  <div class="hud-refrow" id="hud-refrow" style="display:none">
    vs <span id="hud-ref-name">—</span>
  </div>
  <div class="hud-card">
    <div class="hud-card-head">
      <span class="hud-lbl">Speed</span>
      <span class="hud-ref" id="hud-speed-ref"></span>
    </div>
    <div class="hud-big"><span id="hud-speed-val">—</span><span class="hud-unit">mph</span></div>
    <div class="hud-delta" id="hud-speed-delta"></div>
  </div>
  <div class="hud-card">
    <div class="hud-card-head">
      <span class="hud-lbl">Inputs</span>
      <span class="hud-ref" id="hud-inputs-ref">vs ref ghost</span>
    </div>
    <div class="hud-bar-row">
      <span class="hud-bar-lbl">THR</span>
      <div class="hud-bar"><div class="hud-bar-fill thr" id="hud-thr-fill"></div><div class="hud-bar-tick" id="hud-thr-tick"></div></div>
      <span class="hud-bar-val thr" id="hud-thr-val">—</span>
    </div>
    <div class="hud-bar-row">
      <span class="hud-bar-lbl">BRK</span>
      <div class="hud-bar"><div class="hud-bar-fill brk" id="hud-brk-fill"></div><div class="hud-bar-tick" id="hud-brk-tick"></div></div>
      <span class="hud-bar-val brk" id="hud-brk-val">—</span>
    </div>
  </div>
  <div class="hud-row2">
    <div class="hud-card">
      <span class="hud-lbl">Gear</span>
      <div class="hud-mid" id="hud-gear-val">—</div>
    </div>
    <div class="hud-card">
      <span class="hud-lbl">Δ vs ref</span>
      <div class="hud-mid" id="hud-delta-val">—<span class="hud-delta-sub">here</span></div>
    </div>
  </div>
</aside>
</div>
<div id="tele-tip"></div>
<script src="/static/js/perf.js"></script>
<script>Perf.mark('page:start');Perf.autoReport('/sessions/telemetry');</script>
<script src="/static/js/charts.js"></script>
<!-- Cross-session reference picker — opened from the Reference dropdown -->
<div class="cs-ovl" id="cs-ovl">
  <div class="cs-panel">
    <div class="cs-ttl" id="cs-ttl">Pick a reference lap</div>
    <div id="cs-list"><div class="cs-empty">Loading…</div></div>
    <div class="cs-actions">
      <button class="cs-btn" onclick="closeCrossSessionPicker()">Cancel</button>
    </div>
  </div>
</div>
<script src="/static/js/telemetry.js"></script>
</body>
</html>
"""
