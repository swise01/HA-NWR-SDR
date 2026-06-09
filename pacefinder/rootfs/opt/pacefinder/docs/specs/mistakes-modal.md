# Mistakes / Opportunities — modal-only from Telemetry

## Purpose

The "where you lost time" analysis exists twice: a full page
(`/sessions/session/events`, linked from the Session Overview card) and
a modal on the Telemetry page. Two surfaces for one thing blurs the IA
and doubles the maintenance. Reconcile to **one**: a modal, dug into
from Telemetry — the forensic layer where per-corner detail belongs.

## Behavior

- **Telemetry owns it.** Mistakes/Opportunities is a modal opened from
  the Telemetry page only. This is the deep-dive home.
- **Session Overview keeps a teaser, not a page.** The "Where you lost
  time" card stays as a concise summary (top ~3 detected events). Its
  CTA changes from "View all N events →" (full page) to entering
  Telemetry with the modal open — e.g. links to
  `/sessions/telemetry?id=…&events=1`, and Telemetry auto-opens the
  modal when `events=1`.
- **The full page is retired.** `/sessions/session/events`,
  `SESSION_EVENTS_HTML`, and `net/pages/events.py` are removed. The old
  URL 301s to the Telemetry page (with `events=1`) so any bookmark
  still lands on the same content, now as the modal.
- Data endpoints the modal already uses (`/sessions/session/events-map`,
  detector `lap_events`) are unchanged.

## Scope

- Telemetry: ensure the modal opens on `?events=1` (deep-link from the
  Overview teaser and the old-URL redirect).
- Session Overview: repoint the card CTA to Telemetry+`events=1`; keep
  the summary, drop the full-page link.
- Remove `SESSION_EVENTS_HTML` / `events.py` / the
  `/sessions/session/events` page route; replace with a 301 →
  `/sessions/telemetry?id=…&events=1`.
- No change to the detector, `lap_events`, or `events-map` data.

## Out of scope

- Detector tuning / thresholds.
- A summary anywhere other than the existing Overview card.

## Cross-repo work

- pacefinderapp: all of the above.
- pacefindermarketing: none.

## Open questions

- Old-URL 301 needs the session id from the query — confirm the legacy
  `/sessions/session/events?id=…` always carried `id` (it did) so the
  redirect can preserve it.
