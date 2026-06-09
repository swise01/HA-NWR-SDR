# Car ordinal resolution — fallbacks for unknown cars (incl. ordinal 42)

## Purpose
Car ordinal `42` appears in existing sessions but is not in `fm8_cars.csv` (which starts at ordinal 247). Likely a Forza Motorsport 7 or earlier carryover. Need (a) a path to identify and seed missing car ordinals and (b) a graceful fallback when an ordinal is unresolved.

## Behavior

### Identify ordinal 42
- Out-of-band research task (Forza forums, FM7 car lists) — not code
- Once identified, add to `data/fm8_cars_extended.csv`

### New file: `data/fm8_cars_extended.csv`
Same format as `fm8_cars.csv`. Loaded with priority above the base CSV (mirrors the tracks-extended pattern). Seed with ordinal 42's resolved name once identified.

### Loader
- `_load_forza_reference_data()` loads `fm8_cars.csv` then `fm8_cars_extended.csv`
- Extended entries override base on duplicate ordinals
- On startup, log: `Loaded N base + M extended FM8 car mappings`

### Display fallback (when ordinal unresolved)
- UI displays `Unknown Car` — never the raw ordinal number to end users
- Internally still log/store the ordinal for debugging
- Session detail page has a "report this car" affordance (mailto/issue link) so users can help identify

### Post-race modal — manual fallback
- When car ordinal is unresolved, modal shows a free-text input pre-populated with `Unknown Car`
- User can type the actual car name
- On submit, persist as `car_name_manual TEXT` on the session row
- `car_name_manual`, when present, takes priority over the ordinal lookup for display
- Optional: also write the (ordinal, manual_name) pair into a `learned_car_ordinals` table (parallel to `learned_track_ordinals`) so the same ordinal pre-resolves next time

## Scope
- New file: `data/fm8_cars_extended.csv` (created empty or with ordinal 42 once researched)
- Loader update
- Display fallback (`Unknown Car` instead of raw ordinal)
- Post-race modal: free-text fallback input
- Schema: `sessions.car_name_manual TEXT` (nullable)
- Optional: `learned_car_ordinals` table

## Out of scope
- Resolving ordinals for any game other than FM2023
- Bulk re-render of historic sessions when an extended CSV ships (will resolve naturally on next page load)

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Is `learned_car_ordinals` overkill for now? Could defer until we have the equivalent for tracks working and a clear pattern. Recommend: defer, just do the manual fallback first.
- Where does the "report this car" link go — a GitHub issue template, a mailto, or a future in-app form? Recommend: GitHub issue template (cheap, public, searchable).
