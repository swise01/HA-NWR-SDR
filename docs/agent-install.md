# Agent-assisted installation

This playbook lets a user's coding or operations agent install HA-NWR-SDR without assuming Steven Wise's network, credentials, dashboards, or notification devices.

## Supported v4.1 topology

```text
RTL-SDR -> Debian-family radio host -> MQTT -> Home Assistant -> dashboard/automations
```

The radio may be attached to a Raspberry Pi, Debian host, or Ubuntu host. It is not attached directly to Home Assistant OS in v4.1.

## 1. Discover the target

Record without printing secrets:

- Home Assistant installation type and version
- radio-host distribution and architecture
- RTL-SDR serial or device index
- local NOAA Weather Radio frequency
- SAME county codes
- MQTT hostname, port, TLS mode, and a dedicated credential
- existing NWR integrations, packages, dashboards, and entity IDs

Stop if a requested topology is marked as planned in [modular-v5-plan.md](modular-v5-plan.md).

## 2. Install the radio host

From a release checkout on Debian, Ubuntu, or Raspberry Pi OS:

```bash
sudo ./install.sh install
sudo nwrctl edit
sudo nwrctl check
sudo nwrctl enable
```

Use a completed protected config to automate initial activation:

```bash
sudo ./install.sh install --config /secure/path/config.env
```

Do not put credentials on a command line. Keep `/opt/nwr/config.env` mode `0640` or stricter and `/var/lib/nwr/control.json` mode `0600`.

Verify:

```bash
systemctl is-active nwr.service
sudo nwrctl check
journalctl -u nwr.service -n 50 --no-pager
```

## 3. Install Home Assistant integration

1. Add `https://github.com/swise01/HA-NWR-SDR` as a HACS Integration repository.
2. Install HA-NWR-SDR and restart Home Assistant.
3. Add the integration under **Settings -> Devices & services**.
4. Enter the parser's MQTT topic root, normally `nwr`.
5. Confirm Home Assistant receives parser status and retained control state.

Backups of a custom integration must live under a backup directory, not as another directory beneath `custom_components`; Home Assistant scans that directory and may try to import the backup as an integration.

## 4. Add a dashboard

Use [the dashboard example](../examples/dashboards/nwr-overview.yaml) as a starting point. A clean install normally creates entity IDs prefixed with `noaa_weather_radio`, but the agent must resolve actual IDs because Home Assistant adds suffixes when names already exist.

Preferred method:

1. Create a new dashboard in Home Assistant.
2. Open its raw configuration editor.
3. paste the example and replace any entity IDs that differ.
4. Save and check desktop and mobile layouts.

When merging into an existing dashboard, add only the relevant cards. Do not replace the user's dashboard wholesale.

## 5. Acceptance test

Use restart or a no-change setting for the first control test. Confirm:

- MQTT acknowledges the request with `last_result: success`;
- the applied frequency, gain, and PPM remain correct;
- the parser rebuilds without a systemd crash restart;
- audio and any local recorder continue producing data;
- the four control entities remain available in Home Assistant.

Do not transmit a synthetic emergency alert to real notification devices unless the user explicitly authorizes that test.

## Rollback

Before upgrades, preserve the parser, service file, protected config, custom integration, and dashboard. Record exact timestamped paths in the handoff. Restore one layer at a time and validate before proceeding.
