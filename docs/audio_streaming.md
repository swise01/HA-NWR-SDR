# Audio Streaming

The v2 Pi parser hosts a live MP3 stream of the tuned NOAA Weather Radio channel.

Default URL:

```text
http://<pi-ip>:8765/nwr.mp3
```

The parser publishes this URL to MQTT:

```text
nwr/audio/url
```

Home Assistant exposes it as:

```text
sensor.nwr_audio_url
```

The bridge package does not automatically play audio. That is intentional: users have different speakers, volume policies, household needs, and emergency workflows.

Example user automation:

```yaml
trigger:
  - platform: event
    event_type: nwr_same_alert_received
condition:
  - condition: template
    value_template: "{{ trigger.event.data.severity | int == 1 }}"
action:
  - service: media_player.play_media
    target:
      entity_id: media_player.your_speaker
    data:
      media_content_id: "{{ states('sensor.nwr_audio_url') }}"
      media_content_type: music
```

## Firewall

The Home Assistant host must be able to reach the Pi on the configured audio stream port, default `8765`.

## Tuning

The stream path uses a voice-focused filter chain in `pi/nwr_parser.py`.

The SAME decode path is separate and runs two decoders:

- raw resampled audio
- filtered audio

Keep both until logs show which one is more reliable for your local transmitter.
