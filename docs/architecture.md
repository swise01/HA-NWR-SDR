# v4.1 architecture

HA-NWR-SDR has two deliberately separate runtime layers.

The host installer and `nwrctl` manage the Linux radio-publisher layer only. They do not write Home Assistant configuration or store Home Assistant credentials.

## Linux radio publisher

The Linux host owns USB access and the native radio pipeline:

```text
rtl_fm -> ffmpeg -> multimon-ng -> normalized MQTT
       -> ffmpeg MP3 -> LAN audio stream
```

It performs only radio decoding, timestamp reconstruction, county filtering, duplicate-header suppression, retained-state expiry, and transport. It does not decide which phone, speaker, light, or siren should activate.

All pipeline children are one systemd control group. If any child exits, the parser terminates the rest and rebuilds the complete pipeline.

The parser also owns the radio-control boundary. MQTT requests enter a fixed command allow list, are validated and deduplicated, and are handled on the pipeline thread rather than the MQTT callback thread. Accepted frequency, gain, and PPM values are stored in `/var/lib/nwr/control.json`; accepted changes cause a clean pipeline rebuild. The parser publishes the applied settings and last command result as retained state.

## Home Assistant integration

The custom integration owns presentation and automation semantics:

- validates incoming payloads
- maps official SAME codes to names and severity tiers
- restores retained alert state without replaying events
- schedules alert expiry
- exposes entities, events, options, and diagnostics
- exposes bounded radio controls backed by parser acknowledgements

This boundary allows a future HAOS add-on to replace the external Linux publisher while keeping the same MQTT contract and Home Assistant entities.
