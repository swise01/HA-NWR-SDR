# Circuits index page — /circuits
#
# Mirrors CAR_INDEX_HTML: lists every circuit driven, linking into the
# per-circuit detail at /sessions/track?name=. Data from /sessions/tracks.

CIRCUIT_INDEX_HTML_PRE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder &middot; Circuits</title>
<link rel="stylesheet" href="/static/tokens.css">
<link rel="stylesheet" href="/static/base.css">
<link rel="stylesheet" href="/static/sessions_car.css">
<link rel="stylesheet" href="/static/nav.css">
</head>
<body>
<div id="pf-nav"></div>
<script src="/static/js/_safe.js"></script>
<script src="/static/js/nav.js"></script>
<div class="page">

  <a href="/" class="crumb">&larr; Home</a>

  <div class="titlewrap">
    <h1 class="nickname">Circuits</h1>
    <span class="canonical" id="circuits-subtitle">Loading&hellip;</span>
  </div>

  <div class="section" style="padding-top:var(--space-3)">
    <div class="section-head">
      <h2>All circuits driven</h2>
      <span class="count" id="circuits-count">&mdash;</span>
    </div>
    <div class="track-list" id="circuits-list"></div>
  </div>

</div>

<script src="/static/js/track_mini.js"></script>
<script src="/static/js/sessions_circuits.js"></script>
</body>
</html>
"""
