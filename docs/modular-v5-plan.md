# Modular v5 architecture decision

Status: accepted design; implementation follows v4.1.

## Decision

HA-NWR-SDR remains one product with one HACS integration and one normalized alert model. The integration will offer three source modes:

| Mode | Home Assistant requirement | Radio requirement | Internet requirement |
|---|---|---|---|
| Internet | HACS integration | none | NWS API |
| External SDR | HACS integration + MQTT | RTL-SDR on Debian, Ubuntu, or Raspberry Pi OS | none for radio alerts |
| Hybrid | HACS integration + MQTT | external or HAOS-attached RTL-SDR | NWS API for corroboration/failover |

Internet-only support belongs in this repository. It shares alert normalization, severity tiers, events, entities, diagnostics, and dashboards with the radio modes; a separate Internet edition would duplicate the most important logic and create confusing releases.

## Direct RTL-SDR on the Home Assistant machine

Direct USB access should run as a Home Assistant OS app (formerly add-on), not inside the custom integration. Home Assistant apps are supervised containers and can request USB/udev access while keeping native `rtl_fm`, `ffmpeg`, and `multimon-ng` outside Home Assistant Core. The official app configuration supports raw USB and udev mapping, persistent `/data`, architecture declarations, and narrowly scoped permissions: [Home Assistant app configuration](https://developers.home-assistant.io/docs/apps/configuration/).

The app should eventually live in a small companion repository, tentatively `HA-NWR-SDR-Apps`, because container images, multi-architecture builds, app releases, and Supervisor repository metadata have a different lifecycle from HACS releases. It remains part of the same documented product and publishes the same MQTT contract. Home Assistant recommends pre-built multi-architecture images for established apps: [publishing Home Assistant apps](https://developers.home-assistant.io/docs/apps/publishing/).

Home Assistant Container and Core installations do not have Supervisor apps. Those users continue to use the external Linux publisher or manage an equivalent container themselves.

## Shared normalized event model

Every source adapter produces the same internal alert object:

- stable source alert ID
- event code and official event name
- issued, received, effective, and expiry timestamps
- affected SAME/FIPS and NWS zone identifiers
- headline, description, instruction, and area
- source (`radio`, `nws_api`, or `synthetic_test`)
- source health and last-success timestamp

Source adapters do not notify phones, speakers, lights, or sirens. Home Assistant events and automations remain the policy boundary.

## Internet source

The HACS integration will poll `api.weather.gov/alerts/active` with point or zone filters, cache responses, deduplicate CAP alert IDs, and expire withdrawn alerts. NWS requires an identifying `User-Agent`, provides county/zone filtering, and applies reasonable unpublished rate limits, so polling must use conditional requests, backoff, and a conservative interval: [NWS API documentation](https://www.weather.gov/documentation/services-web-api).

Internet mode must not load or require MQTT. External SDR mode must not require Internet access after installation. Hybrid mode keeps independent health for both sources and deduplicates alerts without hiding source disagreement.

## Configuration flow

V5 config flow:

1. Choose `Internet`, `External SDR`, or `Hybrid`.
2. For Internet/Hybrid, confirm Home Assistant coordinates or provide NWS county/zone codes and an identifying contact string.
3. For SDR/Hybrid, select the MQTT topic root and verify parser state.
4. Choose test-event effective severity.
5. Show a summary of dependencies before creating the entry.

Changing source mode is an options-flow operation and reloads the config entry. Diagnostics redact contact strings, coordinates, broker credentials, and raw descriptions unless explicitly downloaded by an administrator.

## Dashboard contract

The default example remains ordinary Lovelace YAML with no required custom cards. V5 adds:

- active alert summary
- radio and NWS source-health rows
- last successful radio decode and API poll
- source mode and failover state
- radio controls only when a parser advertises control capability

## Release sequence

1. **v4.1:** acknowledged SDR controls, secure persistence, dashboard example, and agent install guide.
2. **v5.0 alpha:** Internet source adapter, source-mode config flow, common alert store, and source-health entities.
3. **Companion app alpha:** direct HAOS USB publisher for `amd64` and `aarch64`, built as pre-published containers.
4. **v5.0 stable:** hybrid arbitration, migration tests, complete dashboards, and documented rollback.

V4.1 must not advertise Internet-only or direct-USB operation as shipped functionality. V5 becomes stable only after Internet-only operation works with no MQTT integration configured and the HAOS app passes real USB tests on both supported architectures.
