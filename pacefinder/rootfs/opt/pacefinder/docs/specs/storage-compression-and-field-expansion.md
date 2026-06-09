# Storage compression + per-sample field expansion

## Purpose
We currently log only 13 of ~50 useful per-sample telemetry fields ([session/manager.py:62](session/manager.py:62)) which blocks features built on rumble strips, driving line, slip angles, AI brake delta, suspension, etc. Adding the missing fields naively would 3–4× per-session storage. Compressing the JSON sample blobs first means we can capture the full set and *still* shrink overall storage. Bundle compression with the field expansion in one PR so the new data lands already compact.

## Behavior

### Compression
- `lap_samples.samples_json` and `track_references.samples_json` switch from `TEXT` to `BLOB` storing **gzip-compressed JSON** (stdlib `gzip`, no new deps)
- `_db_save_lap_samples` compresses on write; `_db_get_lap_samples` decompresses on read
- Backwards-compatible: detect uncompressed legacy rows by sniff (first byte `{` = JSON, `\x1f` = gzip magic) so a one-time migration isn't required — existing rows keep working, new rows are compressed
- One-shot rewrite script `scripts/recompress_samples.py --apply` to compact existing rows on demand
- Track table additionally stores an `is_compressed` flag if simpler than sniffing — pick whichever is cleaner during implementation

### Per-sample field expansion
Add to `LapBuffer.add_sample()` (resolve correct file/class during implementation):

**Wheel state (4 fields × 4 corners = 16):**
- `wheel_on_rumble_strip_*` → `rumble_fl/fr/rl/rr`
- `wheel_in_puddle_*` → `puddle_fl/fr/rl/rr`
- `surface_rumble_*` → `surf_rumble_fl/fr/rl/rr`
- `wheel_rotation_speed_*` → `wsp_fl/fr/rl/rr`

**Slip & suspension (12):**
- `tire_slip_ratio_fl/fr` → `slip_fl/slip_fr` (rears already stored)
- `tire_slip_angle_*` → `sa_fl/fr/rl/rr`
- `tire_combined_slip_*` → `cs_fl/fr/rl/rr`

**Suspension travel (8):**
- `normalized_suspension_travel_*` → `sus_n_fl/fr/rl/rr`
- `suspension_travel_meters_*` → `sus_m_fl/fr/rl/rr`

**Driving line / AI (2):**
- `normalized_driving_lane` → `lane`
- `normalized_ai_brake_difference` → `ai_brk_diff`

**Wear (FH5 only, 4):**
- `tire_wear_*` → `wear_fl/fr/rl/rr`

**Skipped for now** (heavy, not tied to a planned feature): raw `acceleration_*` / `velocity_*` / `angular_velocity_*` / `yaw/pitch/roll`, `power`, `torque`, `boost`, `handbrake`, `distance_traveled`, `engine_max/idle_rpm`. Easy to add later — the new fields will simply fall through `parsed.get(...)`.

### Per-session columns
Add three columns to the `sessions` table:
- `car_ordinal INTEGER` — raw ordinal (was thrown away after car-name resolution)
- `drivetrain_type INTEGER` — 0 FWD / 1 RWD / 2 AWD per Forza spec
- `num_cylinders INTEGER`

Captured from the same `parsed` dict at session start in `Session._capture_car_metadata()` (or wherever class/PI are captured today — see [session/manager.py:207](session/manager.py:207)).

### Acceptance
- A typical 30-lap session goes from ~2 MB uncompressed-JSON-with-13-fields to **≤1 MB** gzipped-with-~50-fields (verified empirically on a real session)
- Telemetry page load time stays within 10 % of baseline (gzip decompress overhead is real but small — use the perf instrumentation from the perf spec to confirm)
- Existing pre-compression rows still load correctly
- `/debug/raw` shows all the new fields populated during a live race

## Scope
- gzip compress/decompress in `db/store.py` save/load helpers
- Schema additions: `car_ordinal`, `drivetrain_type`, `num_cylinders` (use the `ALTER TABLE … ADD COLUMN` pattern already in `_db_init`)
- `LapBuffer.add_sample` field additions
- `Session.update_packet` / car-metadata capture additions
- Backfill sniff-on-read for legacy uncompressed rows
- One-shot `scripts/recompress_samples.py --apply` for opt-in retroactive compression
- Update `replay.py` if it reads samples directly so it handles the new format

## Out of scope
- Columnar layout (column-arrays-of-values vs array-of-records) — bigger payoff but bigger surgery; revisit if gzip+JSON isn't compact enough
- msgpack / zstd — burns the "stdlib only" promise
- Removing fields ever stored before — stays for backward compatibility
- UI to surface the new fields — that's per-feature (rumble usage, line deviation, etc.)

## Cross-repo work
- `pacefinderapp` only

## Open questions
- Should we drop `is_race_on=False` packets from the per-sample buffer? They're skipped today (parser returns `None` if not racing), so probably already a non-issue — verify during implementation.
- For FM2023 (no `tire_wear_*`), the fields will just be missing from the JSON. Confirm the chart code tolerates absent keys (it should — it uses `parsed.get(...)`).
- Migration of `track_references.samples_json` — recompute on next session per track is the cheap option (already the recommendation from the recent fix). Or include them in `recompress_samples.py`.
- Do we want a `samples_format` version field per row to make future format changes cleaner? Probably overkill for v1 — the gzip-magic-byte sniff is enough.
