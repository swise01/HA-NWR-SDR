// Shared mini track-outline renderer used by /circuits, /sessions, and
// anywhere else a small "what does this track look like" glyph helps.
//
// Each call paints a per-segment polyline into an element, coloured by
// the lap's speed (blue slow → green mid → red fast). Same hue map as
// the telemetry HUD track map so the visual language stays consistent.
//
// • viewBox is sized to the track's actual aspect ratio (capped 0.5–2.5)
//   so a square circuit doesn't letterbox inside a wide rectangle.
// • Lap samples are cached by `sid:lap` so repeated rows of the same
//   track on /sessions share one fetch.
// • Use pfLoadMinis() with elements carrying data-sid + data-lap to lazy
//   load on scroll via IntersectionObserver.

(function(){
  const _cache = new Map();  // key "sid:lap" → samples[] or null

  async function _fetchSamples(sid, lap){
    const key = sid + ':' + lap;
    if(_cache.has(key)) return _cache.get(key);
    try{
      // ?outline=1 — server decimates to ≤80 points and strips to the 6
      // fields this renderer + the fingerprint glyph need. Cuts the
      // wire payload + JSON parse by ~95% vs the full sample stream.
      const s = await fetch('/sessions/lap-samples?session_id=' + encodeURIComponent(sid)
        + '&lap=' + encodeURIComponent(lap) + '&outline=1').then(r => r.json());
      const ok = Array.isArray(s) && s.length >= 8 && !s.some(p => p.px == null);
      _cache.set(key, ok ? s : null);
      return ok ? s : null;
    } catch(e){ _cache.set(key, null); return null; }
  }

  // Speed → RGB. Mirrors the telemetry HUD's spdRgb: blue (slow) →
  // green (mid) → red (fast). t is [0,1].
  function _spdRgb(t){
    t = Math.max(0, Math.min(1, t));
    if(t < 0.5){
      const k = t / 0.5;            // 0..1 from blue→green
      const r = Math.round(0x60 + (0x4a - 0x60) * k);
      const g = Math.round(0xa5 + (0xde - 0xa5) * k);
      const b = Math.round(0xfa + (0x80 - 0xfa) * k);
      return `rgb(${r},${g},${b})`;
    } else {
      const k = (t - 0.5) / 0.5;    // 0..1 from green→red
      const r = Math.round(0x4a + (0xf8 - 0x4a) * k);
      const g = Math.round(0xde + (0x71 - 0xde) * k);
      const b = Math.round(0x80 + (0x71 - 0x80) * k);
      return `rgb(${r},${g},${b})`;
    }
  }

  async function pfDrawMini(el){
    const sid = el.dataset.sid, lap = el.dataset.lap;
    if(!sid || lap == null) return;
    const s = await _fetchSamples(sid, lap);
    if(!s) return;
    const hasPz = s.some(p => p.pz != null);
    const zf = hasPz ? p => p.pz : p => (p.py ?? 0);
    const xs = s.map(p => p.px), zs = s.map(zf);
    const spds = s.map(p => p.speed_mph ?? 0);
    const mnX = Math.min(...xs), mxX = Math.max(...xs);
    const mnZ = Math.min(...zs), mxZ = Math.max(...zs);
    const mnS = Math.min(...spds), mxS = Math.max(...spds);
    const spanX = (mxX - mnX) || 1, spanZ = (mxZ - mnZ) || 1;
    // viewBox aspect follows the track shape so a square circuit doesn't
    // letterbox inside a fixed-width rectangle.
    const trackAspect = Math.max(0.5, Math.min(2.5, spanX / spanZ));
    const W = trackAspect >= 1 ? 100 : Math.round(100 * trackAspect);
    const H = trackAspect >= 1 ? Math.round(100 / trackAspect) : 100;
    const pd = 4;
    const sc = Math.min((W - pd*2) / spanX, (H - pd*2) / spanZ);
    const ox = (W - spanX * sc) / 2;
    const oz = (H - spanZ * sc) / 2;
    const cx = x => (ox + (x - mnX) * sc).toFixed(1);
    const cy = z => (H - oz - (z - mnZ) * sc).toFixed(1);
    // Decimate to ~80 segments for a clean, light render. Each segment
    // takes its color from the speed at its end-point.
    const step = Math.max(1, Math.floor(s.length / 80));
    const segs = [];
    let prevI = 0;
    for(let i = step; i < s.length; i += step){
      const t = mxS > mnS ? (spds[i] - mnS) / (mxS - mnS) : 0.5;
      segs.push(
        `<line x1="${cx(s[prevI].px)}" y1="${cy(zf(s[prevI]))}" `+
        `x2="${cx(s[i].px)}" y2="${cy(zf(s[i]))}" stroke="${_spdRgb(t)}"/>`
      );
      prevI = i;
    }
    // Close back to start so the loop looks complete.
    segs.push(
      `<line x1="${cx(s[prevI].px)}" y1="${cy(zf(s[prevI]))}" `+
      `x2="${cx(s[0].px)}" y2="${cy(zf(s[0]))}" stroke="${_spdRgb(0.5)}"/>`
    );
    el.innerHTML =
      `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" `+
      `role="img" aria-label="Track outline">`+
      `<g class="tm-line">${segs.join('')}</g>`+
      `</svg>`;
  }

  function pfLoadMinis(root){
    const scope = root || document;
    const els = scope.querySelectorAll('.track-outline[data-sid]:empty');
    if(!('IntersectionObserver' in window)){ els.forEach(pfDrawMini); return; }
    const io = new IntersectionObserver((entries, obs) => {
      entries.forEach(e => {
        if(e.isIntersecting){ obs.unobserve(e.target); pfDrawMini(e.target); }
      });
    }, {rootMargin: '200px 0px'});
    els.forEach(el => io.observe(el));
  }

  window.pfDrawMini = pfDrawMini;
  window.pfLoadMinis = pfLoadMinis;
})();
