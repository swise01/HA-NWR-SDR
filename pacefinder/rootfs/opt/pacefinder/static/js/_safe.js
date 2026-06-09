// Tiny HTML-escape helper for ${...} template literals that flow into
// innerHTML. Apply to any string sourced from the DB — especially fields
// the user can mutate (car nicknames, track names, car names, weather).
//
// Without this, a nickname like `<img src=x onerror=fetch('/config')>` would
// fire whenever the value renders. _redact_config() means the key is no
// longer leaked, but the XSS surface is broader than just /config.
window.escHtml = function (v) {
  if (v == null) return '';
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};
