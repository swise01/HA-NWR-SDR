# Changelog

## [2.0.0] — 2026-04-06 — Initial community release

### Features
- All 7 NWR WX channels (162.400–162.550 MHz) pre-loaded in an HA input_select
- Channel selector drives Pi parser via MQTT — change channels from the dashboard, no SSH needed
- Generic audio support — any HA `media_player` entity, configurable from the Settings tab
- Dual mode: SDR + NWS API, or NWS API only (no hardware required)
- 5-tier alert system with per-tier notification, sound, and TTS controls
- NWS API cross-reference with 5 alert slots and countdown timers
- Dual data source merging (SAME + NWS API best-available headline/description)
- SAME event code reference links to weather.gov/nwr/eventcodes instead of hardcoding
- Safety relay automation (Tier 1 → strobe/siren, any HA switch entity)
- Parser heartbeat watchdog (notification if Pi goes offline)
- NWS API fallback automation (catches alerts even without SAME decode)
- All-clear automation (clears state when both SAME timer and NWS API agree)
- Beautiful three-tab Lovelace dashboard (NWR / Details / Settings)
- All personal/location details removed — community-ready
- `publish.sh` script for one-command GitHub publishing
- Comprehensive README with two-path install guide

### Architecture improvements over v1
- WX channel driven by `input_select` and MQTT `nwr/set_channel` topic
- `nwr_parser.py` subscribes to channel changes and restarts rtl_fm automatically
- Audio player configured via `input_text` entities — no YAML edits needed post-install
- Stream URL stored as `input_text` entity — editable from dashboard
- Station name stored as `input_text` — appears in dashboard header
- Reduced `# ← EDIT` touchpoints to ~10 clearly marked locations
- YAML anchors (`&blue_card`, `&orange_card`, `&header_style`) eliminate card_mod duplication
