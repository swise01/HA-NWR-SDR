# Contributing to HA-NWR-SDR

First — thank you for being here.

I built this to solve a real problem at my house: I wanted my home to know when a tornado warning was issued before I heard it on TV. It works, my family is safer for it, and I decided to share it.

I am not a professional developer. I am someone who learns by doing, breaks things, fixes them, and keeps going. This project reflects that. I am genuinely excited to see where the community takes it.

**If you are more skilled than me — please make this better. I mean that sincerely.**

---

## Where help is most needed

- **Screenshots** — I haven't added any to the README. If you get this running, a screenshot PR would help everyone who comes after you
- **Testing on different hardware** — RTL-SDR V3, generic dongles, different Pi models, different antennas
- **Automation examples** — notifications, audio playback, lights, alert panels, and alarm workflows built from the standard integration events
- **Audio examples** — Sonos, Google Home, TTS, browser players, and other `media_player` targets
- **Non-US adaptations** — Canadian Weatheradio uses similar SAME codes; other countries may have equivalents
- **Home Assistant polish** — repairs, more diagnostics, and config flow improvements
- **HAOS add-on** — direct SDR support for users who want the dongle plugged into the HAOS host

---

## How to contribute

1. **Bugs** — open an issue using the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md)
2. **Ideas** — open an issue and describe what you want to build and why
3. **PRs** — for anything significant, open an issue first so we can talk through the approach. For fixes and doc improvements, just go for it.

---

## Code style

- Python: PEP 8, clear comments, no magic numbers without explanation
- YAML: 2-space indent, descriptive entity names
- Prefer simple and readable over clever

---

## License

By contributing you agree your work will be released under the [MIT License](LICENSE).
