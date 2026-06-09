# Detect race end from Forza telemetry instead of timeout

## Purpose
Sessions currently close after **10 seconds of silence** (the idle/timeout watchdog). This means the post-race modal appears 10s after you stop racing — too slow, and it misses the natural moment right after crossing the line when you'd actually want to confirm metadata.

Forza broadcasts `is_race_on` (int, 0 or 1) in every UDP packet. Use the `1 → 0` transition to detect race end and close the session immediately.

## Behavior

### Detection
- Track `last_is_race_on` on the `Session` object
- On each ingested packet: if `last_is_race_on == 1` and current `is_race_on == 0`, the race just ended
- Trigger `session.close()` immediately
- Set `closed_reason = 'race_end'` in session metadata (vs. `'timeout'` for the existing watchdog path)
- Surface the post-race modal immediately on race-end detection (no wait)

### Fallback
- Keep the existing 10s timeout watchdog as a safety net for sessions where the transition isn't cleanly captured (packet loss, abrupt game exit)
- Sessions closed by the watchdog get `closed_reason = 'timeout'`

### Session metadata
- Add `closed_reason TEXT` to the `sessions` table — values: `'race_end'`, `'timeout'`, `'manual'` (if a manual close path exists)
- Useful for debugging "why did this session close" later

### Expected result
Post-race modal appears within **1–2 seconds** of crossing the finish line on a normal race exit. Falls back to ≤10s on edge cases.

## Scope
- `Session` class: track `last_is_race_on`, detect transition in ingest path, call `close()` early
- Schema: add `closed_reason TEXT` column
- Watchdog: unchanged (still runs as fallback)
- Modal trigger: ensure it fires on synchronous close, not just on watchdog-driven close

## Out of scope
- Race-end detection for ACC and F1 (different packet structures; separate work if/when needed)
- "Pause vs end" disambiguation — Forza's `is_race_on` may flip 1→0 during pause too. Verify behavior and handle in open question.
- Multi-stint/endurance racing where `is_race_on` may toggle within one logical session

## Cross-repo work
- `pacefinderapp` only

## Open questions
- **Critical:** does `is_race_on` go to 0 on **pause** as well as end-of-race? If yes, naive detection will close sessions on every pause. Need to either (a) require a sustained `0` for N packets before closing, or (b) check additional signal (e.g. `current_race_time` resets, position resets, etc.). Verify by testing with a paused session before shipping.
- What is the timing relationship between the last "real" packet and `is_race_on=0`? Is there enough buffer to capture the finish-line crossing in the recorded telemetry, or does the game stop broadcasting useful signals immediately?
- Does `is_race_on` reliably exist for both FM2023 and FH5 packet formats? CLAUDE.md says FH5 is +20 bytes — is `is_race_on` in the shared header?
