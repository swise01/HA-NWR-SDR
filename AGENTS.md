# HA-NWR-SDR agent instructions

Use these instructions when an AI coding or operations agent installs, upgrades, or configures this project for someone else.

## Establish scope first

1. Identify the Home Assistant installation type: Home Assistant OS, Supervised, Container, or Core.
2. Identify the requested alert source and state what this release supports:
   - v4.1 supports an RTL-SDR on a separate Debian, Ubuntu, or Raspberry Pi OS host.
   - Internet-only NWS alerts and a direct-attached Home Assistant OS RTL-SDR are planned for v5 and must not be represented as implemented.
3. Resolve the user's county/zone, NOAA transmitter, MQTT broker, and dashboard preference without copying Steven Wise's private homelab configuration.
4. Never expose MQTT passwords, Home Assistant tokens, precise private coordinates, or notification targets in logs, commits, examples, or diagnostics.

## Installation workflow

Follow [docs/agent-install.md](docs/agent-install.md). Prefer the supported installer and HACS flow over hand-written service files or Home Assistant storage edits.

Before changing a live system:

- inspect the existing parser, integration, entity IDs, and dashboard;
- preserve local recorder, audio, or automation extensions instead of replacing them blindly;
- create timestamped backups outside `custom_components`;
- validate Python, shell, JSON/YAML, and Home Assistant configuration;
- restart one layer at a time and verify MQTT state after each restart.

For dashboards, start from [examples/dashboards/nwr-overview.yaml](examples/dashboards/nwr-overview.yaml), resolve the actual entity IDs from the target Home Assistant entity registry, and merge through Home Assistant's dashboard editor. Never overwrite `.storage` dashboard files without explicit authorization, a backup, JSON validation, and a Home Assistant restart plan.

## Completion requirements

- Parser status is `running` and the audio URL is reachable on the intended network.
- Retained `control/state` matches the applied frequency, gain, and PPM.
- Home Assistant configuration passes and the integration entities are available.
- A restart-only control request rebuilds the pipeline without incrementing systemd restart count.
- The dashboard renders without missing entities.
- Report rollback paths and any unimplemented v5 capability clearly.

Do not publish, create a release, or convert a draft PR to ready without the repository owner's explicit approval.
