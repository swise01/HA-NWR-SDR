# Pacefinder reference data

Static reference data loaded at listener startup by [`reference/loader.py`](../reference/loader.py).

## Files

| File | Format | Source | Purpose |
|---|---|---|---|
| `fm8_tracks.csv` | `ordinal,name,?,?,layout` (5+ cols) | [bluemanos/forza-motorsport-7-track-list](https://github.com/bluemanos) (community) | Base FM8 track-ordinal → display-name map. **Currently not yet vendored in this repo.** |
| `fm8_tracks_extended.csv` | `ordinal,track` (2 cols) | This project + user submissions | Curated additions and overrides for circuit variants the base list doesn't cover well |
| `fm8_cars.csv` | `ordinal,year,make,model` (4+ cols) | [bluemanos/forza-motorsport-7-car-list](https://github.com/bluemanos) (community) | Base FM8 car-ordinal → name/make/year map |
| `fm8_cars_extended.csv` | `ordinal,year,make,model` (4+ cols) | This project + user submissions | Curated additions for cars missing from the base list (e.g. ordinal 42, FM7 carryovers) — **not yet created; tracked in #6** |

## Precedence

When the same ordinal exists in multiple sources, the highest-priority entry wins. From highest to lowest:

1. `learned_track_ordinals` SQLite table (per-user, learned from confirmed sessions)
2. `fm8_tracks_extended.csv` (curated, manually validated)
3. `fm8_tracks.csv` (community-sourced bulk list)
4. Hardcoded fallbacks in `reference/loader.py` (`_FORZA_TRACKS_FALLBACK`)

## Format details

### Base track CSV (`fm8_tracks.csv`)

5+ columns. Loader uses columns 0 (ordinal), 1 (name), and 4 (layout). Display name is `f"{name} {layout}"`.

```csv
# ordinal,name,?,?,layout
123,Silverstone,,,Grand Prix
```

### Extended track CSV (`fm8_tracks_extended.csv`)

2 columns. Display name is the second column verbatim — no concatenation.

```csv
# ordinal,track_display_name
510,Yas Marina Full Circuit
```

Comment lines start with `#`; blank lines are ignored.

## Contributing

Found an unresolved ordinal in your sessions? Open a PR adding a row to `fm8_tracks_extended.csv` (or `fm8_cars_extended.csv` once it exists). Include a brief note in the PR body about how you confirmed the mapping (race result, in-game UI, community source).

The Setup page at `localhost:8000/setup` shows live ordinal counts; unresolved ordinals are logged once each on first sighting in `listener.log`.
