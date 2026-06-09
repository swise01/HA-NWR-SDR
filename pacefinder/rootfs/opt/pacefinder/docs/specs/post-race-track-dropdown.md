# Post-race modal — track dropdown populated from all sources

## Purpose
The post-race modal's track name dropdown currently underrepresents available track data. Many sessions land as `Track #N` because the dropdown isn't drawing from every known source. Merge all three sources so the user can always pick the right name (or confirm the auto-detected one).

## Behavior

### Sources merged (in priority order — higher wins on duplicate ordinal)
1. **`learned_track_ordinals`** SQLite table — user-confirmed mappings from previous sessions (highest priority; reflects the user's own corrections)
2. **`data/fm8_tracks_extended.csv`** — community/user-extended ordinal map (see separate spec)
3. **`data/fm8_tracks.csv`** — bluemanos's base FM8 track list

### Dropdown UX
- All three sources merged, deduplicated by ordinal, sorted alphabetically by track name for the picker
- If the session has a detected ordinal that matches a known entry in any source → **pre-select it**
- Otherwise → no pre-selection; user picks from full list
- Dropdown is **searchable** — type to filter (substring match on track name, case-insensitive)
- "Unknown / not in list" option at top, which falls back to manual text entry (covered by car-ordinal spec but applies here too)

### On submit
- If user picks a name that came from `extended` or `bluemanos` sources, write the (ordinal, name) pair into `learned_track_ordinals` so future sessions with the same ordinal pre-select correctly without re-merging
- If the session had a different auto-detected name and the user changed it, the user's choice always wins — `learned_track_ordinals` row is upserted with the user's name

## Scope
- Track-name resolution in the modal-handling endpoint
- Modal UI: searchable dropdown, pre-selection logic
- Persistence: upsert into `learned_track_ordinals` on user confirmation

## Out of scope
- Creating `fm8_tracks_extended.csv` itself — separate spec
- Track resolution outside the modal (e.g. live dashboard, session list) — future spec if needed
- F1/ACC track handling — different lookup path, unchanged

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Searchable dropdown — keep stdlib-only (custom HTML datalist + filter JS) to match the project's "no framework" ethos, or pull in a tiny dependency? Recommend: stay stdlib.
- On `learned_track_ordinals` upsert: should the timestamp/source-tracking columns be added so we know how each mapping was learned? Useful for debugging mis-attributions later.
