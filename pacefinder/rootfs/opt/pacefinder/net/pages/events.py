# All-events page — /sessions/session/events?id=<sid>
#
# Production form of static/mistakes-mock.html. Renders every detected
# event for a session (from the #133 lap_events detector) as a filterable
# list beside a track map with per-event markers. Reached from the
# session-detail "Where you lost time" card.

SESSION_EVENTS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder &middot; Events</title>
<link rel="stylesheet" href="/static/tokens.css">
<link rel="stylesheet" href="/static/base.css">
<link rel="stylesheet" href="/static/sessions_events.css">
<style>html.embed .tb,html.embed #crumb{display:none}html.embed .page{padding-top:var(--space-3)}</style>
<script>if(new URLSearchParams(location.search).get('embed')==='1')document.documentElement.classList.add('embed');</script>
</head>
<body>
<div class="tb">
  <h1>Pacefinder</h1>
  <nav class="tb-nav">
    <a href="/dashboard">Live</a><a href="/">Home</a><a href="/sessions">Career</a><a href="/setup">Setup</a>
  </nav>
</div>
<div class="page">

  <a href="#" class="crumb" id="crumb">&larr; Back to session</a>

  <div class="ev-head">
    <div>
      <div class="ev-eyebrow">All events &middot; this session</div>
      <h1 class="ev-title">Mistakes &amp; opportunities</h1>
    </div>
    <span class="ev-meta" id="ev-meta">Loading&hellip;</span>
  </div>

  <div class="filters">
    <span class="filter-label">Show</span>
    <span class="chip on" data-show="all">All laps</span>
    <span class="chip" data-show="worst">Worst 5</span>
    <span class="filter-sep">&middot;</span>
    <span class="filter-label">Type</span>
    <span class="chip on" data-type="">All</span>
    <span class="chip" data-type="lockup">Lockup</span>
    <span class="chip" data-type="power_oversteer">Oversteer</span>
    <span class="chip" data-type="bad_shift">Bad shift</span>
    <span class="filter-sep">&middot;</span>
    <span class="filter-label">Sort</span>
    <span class="chip on" data-sort="severity">Severity</span>
    <span class="chip" data-sort="lap">By lap</span>
  </div>

  <div class="body">
    <div class="events" id="events"></div>
    <div class="map-pane">
      <div class="map-frame">
        <svg class="map-svg" id="map-svg" viewBox="0 0 1000 480" preserveAspectRatio="xMidYMid meet"></svg>
      </div>
      <div class="legend">
        <span class="legend-item"><span class="legend-dot" style="background:#dc2626"></span>Worst (sev &gt; .7)</span>
        <span class="legend-item"><span class="legend-dot" style="background:#f87171"></span>Major (.4&ndash;.7)</span>
        <span class="legend-item"><span class="legend-dot" style="background:#fbbf24"></span>Minor (&lt; .4)</span>
        <span class="legend-item"><span class="legend-dot" style="background:var(--color-accent)"></span>Selected</span>
        <span style="margin-left:auto;color:var(--color-text-quaternary)">Click a row or marker to cross-highlight</span>
      </div>
    </div>
  </div>

  <div class="ev-empty" id="ev-empty" style="display:none">No events detected for this session.</div>

</div>
<script src="/static/js/_safe.js"></script>
<script src="/static/js/sessions_events.js"></script>
</body>
</html>
"""
