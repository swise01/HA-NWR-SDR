# Car picker in edit modal

## Purpose
Today the session-edit modal's Car field is a free-text input. That works as an escape hatch for unmapped ordinals, but it's a bad first-line UX: the user has to type the full car name from memory, can't browse what's available, and "did I spell Porsche right?" is a real friction point. Replace the free-text field with a searchable picker drawing from the shipped car ordinal database — so picking the right car is one click + a few characters. Keep free-text as the fallback when an ordinal isn't in the DB yet (the user can hunt down specs and add later).

## Behavior

### Visual + interaction
- Replace the existing `<input id="edit-car">` on the session-edit modal with a searchable autocomplete (per the [autocomplete-widget spec](searchable-autocomplete-widget.md)) populated with the full `FORZA_CARS` catalog.
- Each option renders as `"<year> <name>"` (e.g. `"2018 Honda Civic Type R"`) — same format the existing car-name resolution uses.
- `allowFreeText: true` so unmapped ordinals can still be set manually.
- When the user picks an option, save persists the chosen car name into `sessions.car` (existing column).

### Backing data
Two options:
1. **Inline JSON dump** — server renders `FORZA_CARS` as a `<script>` data block on /sessions, JS picks it up. Cheapest; no extra request. Recommended for v1.
2. **New endpoint** `GET /cars/catalog` returning `[{ordinal, year, name, manufacturer}, ...]`. Adds a request but matches the pattern other endpoints use.

The catalog is small (a few hundred cars), so the JSON inline option adds negligible page weight.

### Persistence
- The `car` field on the session row continues to be the human-readable string. No schema changes needed.
- The `car_ordinal` column (added in Bundle 2) keeps the raw Forza ordinal — that doesn't change when the user picks a different name; the user is overriding the *display* name.
- If the picked option corresponds to an ordinal in `FORZA_CARS`, optionally also write that ordinal to `car_ordinal` so the next time the user races in this car (or a backfill job runs), name resolution picks up the user's correction. Defer this for v1 — explicit free-text-with-ordinal-mismatch is rare enough not to bake in.

### Acceptance
- Edit modal Car field: click → dropdown opens with all known cars
- Type "civic" → filtered list shows just Civic variants
- Pick one → input fills, save persists
- Type a brand-new car name not in the list → save persists as today (free-text fallback)
- Existing nickname behavior still works (Bundle 3) — set a nickname AND a car name, both persist independently

## Scope
- Inline JSON of `FORZA_CARS` on the /sessions page (or a `/cars/catalog` endpoint — pick during impl)
- Replace the `edit-car` input with an instance of the autocomplete widget configured with the catalog
- No schema changes
- No nickname-flow changes (Bundle 3 already covers that)

## Out of scope
- Filter-by-car on the sessions home (separate feature)
- "Best lap in this car" cross-track view (separate feature)
- Setup sync per car (#70 placeholder)
- Auto-learn mappings: when user picks a car name for an ordinal that wasn't in `FORZA_CARS`, write to a `learned_car_ordinals` table similar to how track ordinals work. Worth doing eventually; defer until users actually need it.

## Cross-repo work
- `pacefinderapp` only
- Depends on the autocomplete widget spec landing first

## Open questions
- Sort order in the dropdown — alphabetical by name, or grouped by manufacturer? Recommend alphabetical-by-name; matches how Forza's own car selector reads. Manufacturer grouping is nice but adds noise on a long list.
- For unmapped sessions (`car_ordinal` set, name = "Unknown Car (#641)"), pre-select nothing in the picker so the user starts fresh? Or pre-fill the typed-in name so the user can edit it? Recommend pre-fill with the existing name string so the user has a starting point.
