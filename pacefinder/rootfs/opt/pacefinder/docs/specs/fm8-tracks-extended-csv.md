# FM2023 extended track ordinal CSV

## Purpose
The base `fm8_tracks.csv` (from bluemanos) doesn't cover every circuit variant or ordinal that appears in real sessions. Add a parallel extended CSV for community-/user-discovered ordinals, loaded with priority below `learned_track_ordinals` but above the base CSV.

## Behavior

### File format
Same format as `data/fm8_tracks.csv`:
```csv
ordinal,track
35,Mugello Circuit Full
67,Maple Valley Full Circuit
510,Yas Marina Full Circuit
530,Circuit de Spa-Francorchamps
540,Mount Panorama Circuit
860,Brands Hatch Grand Prix Circuit
990,Virginia International Raceway Full
1630,Grand Oak Raceway National
1643,Hakone Club Reversed
```

Path: `data/fm8_tracks_extended.csv`

### Loader behavior
- `_load_forza_reference_data()` (or whatever the current loader is post-refactor) loads the base CSV first, then the extended CSV
- Extended entries **override** base entries on the same ordinal (extended is more specific / curated)
- On startup, log: `Loaded N base + M extended FM8 track mappings`
- Missing extended file → no error, just log `0 extended mappings`

### Documentation
- Add `data/README.md` documenting:
  - Where each CSV came from
  - How to contribute new ordinals (file an issue with `ordinal,track` pairs OR PR the CSV directly)
  - Source attribution for bluemanos's list

## Scope
- New file: `data/fm8_tracks_extended.csv` seeded with the 9 mappings above
- Loader update in `reference/loader.py` (or wherever lookup is post-refactor)
- New file: `data/README.md`

## Out of scope
- Web UI for crowdsourcing ordinals (later)
- Same pattern for cars — see separate spec
- Automatic CSV updates from upstream

## Cross-repo work
- `pacefinderapp` only

## Open questions
- The 9 seeded mappings — were these confirmed by you against actual race results, or best-guess from circuit recognition? Worth noting in the CSV header comment if any are tentative.
- Should `learned_track_ordinals` migrate confirmed entries upstream to the extended CSV periodically (so the user's corrections become contributable), or kept strictly local? Recommend: keep separate, surface a "promote to extended" command later if useful.
