# Audio streaming

The Linux parser hosts a live MP3 stream of the tuned NOAA Weather Radio channel and publishes its URL on `nwr/audio/url`.

Default URL:

```text
http://<radio-host>:8765/nwr.mp3
```

Use `AUDIO_ADVERTISE_HOST` to override automatic LAN address discovery or `AUDIO_STREAM_URL` to publish a complete reverse-proxy URL.

The built-in endpoint has no authentication and listens on all interfaces. Keep it on a trusted LAN, restrict the port with a firewall, or put it behind an authenticated proxy. Do not expose port 8765 directly to the Internet.

Example user automation:

```yaml
triggers:
  - trigger: event
    event_type: nwr_same_alert_received
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.severity | int == 1 }}"
actions:
  - action: media_player.play_media
    target:
      entity_id: media_player.your_speaker
    data:
      media_content_id: "{{ states('sensor.nwr_audio_url') }}"
      media_content_type: music
```

Audio playback remains a user automation because volume, household, and emergency policies differ.
