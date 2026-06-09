# Car detail page — /cars/<ordinal>
#
# Mirrors the structure of TRACK_DETAIL_HTML: PRE/POST split so the
# (currently small) embedded constants can grow without rewriting the
# whole page each time. No MID splice today — the page reads its data
# entirely from /cars/<ordinal>/data at load time.

CAR_INDEX_HTML_PRE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder &middot; Cars</title>
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

  <a href="/sessions" class="crumb">&larr; All sessions</a>

  <div class="titlewrap">
    <h1 class="nickname">Cars</h1>
    <span class="canonical" id="cars-subtitle">Loading&hellip;</span>
  </div>

  <div class="section" style="padding-top:var(--space-3)">
    <div class="section-head">
      <h2>All cars driven</h2>
      <span class="count" id="cars-count">&mdash;</span>
    </div>
    <div class="track-list" id="cars-list"></div>
  </div>

</div>

<script src="/static/js/class.js"></script>
<script src="/static/js/track_mini.js"></script>
<script src="/static/js/sessions_cars.js"></script>
</body>
</html>
"""

CAR_DETAIL_HTML_PRE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Pacefinder &middot; Car</title>
<link rel="stylesheet" href="/static/tokens.css">
<link rel="stylesheet" href="/static/base.css">
<link rel="stylesheet" href="/static/sessions_car.css">
<link rel="stylesheet" href="/static/nav.css">
</head>
<body>
<div id="pf-nav"></div>
<script src="/static/js/nav.js"></script>
<div class="page">

  <a href="/sessions" class="crumb" id="crumb">&larr; All sessions</a>

  <div class="titlewrap">
    <h1 class="nickname" id="nickname">Loading&hellip;</h1>
    <span class="canonical" id="canonical"></span>
    <span class="class-badge" id="car-class" style="display:none"></span>
    <span class="pi-badge" id="car-pi" style="display:none"></span>
    <span class="drivetrain" id="drivetrain" style="display:none"></span>
  </div>
  <div class="subtitle" id="subtitle">&mdash;</div>

  <!-- Hero: best lap + stat tiles -->
  <div class="hero">
    <div>
      <div class="hero-time" id="hero-best">&mdash;</div>
      <div class="hero-time-sub" id="hero-best-sub">Best ever &mdash;</div>
    </div>
    <div class="stat-grid">
      <div class="stat">
        <div class="stat-label">Circuits driven</div>
        <div class="stat-value" id="stat-tracks">&mdash;</div>
      </div>
      <div class="stat">
        <div class="stat-label">Avg lap</div>
        <div class="stat-value" id="stat-avg">&mdash;</div>
      </div>
      <div class="stat">
        <div class="stat-label">Total time</div>
        <div class="stat-value" id="stat-total">&mdash;</div>
      </div>
      <div class="stat">
        <div class="stat-label">Last driven</div>
        <div class="stat-value" id="stat-last">&mdash;</div>
      </div>
    </div>
  </div>

  <!-- Tracks-in-this-car table -->
  <div class="section">
    <div class="section-head">
      <h2>Circuits in this car</h2>
      <span class="count" id="tracks-count">&mdash;</span>
    </div>
    <div class="track-list" id="track-list"></div>
  </div>

  <!-- Recent sessions -->
  <div class="section">
    <div class="section-head">
      <h2>Recent sessions</h2>
      <span class="count" id="recent-count">&mdash;</span>
    </div>
    <div class="recent-list" id="recent-list"></div>
  </div>

</div>

<script src="/static/js/class.js"></script>
<script src="/static/js/track_mini.js"></script>
<script src="/static/js/sessions_car.js"></script>
</body>
</html>
"""
