# Audio Streaming (Path A — Self-Hosted)

If you're running Path A (RTL-SDR + Raspberry Pi), the Pi can host a live NWR audio stream that any HA media player can play.

## How it works

The `nwr_parser.py` script pipes `rtl_fm` audio through `ffmpeg`, which serves it as an MP3 stream on port 8765.

```
rtl_fm → ffmpeg (volume boost + MP3 encode) → HTTP stream at :8765
```

## Stream URL

```
http://<your-pi-ip>:8765/nwr.mp3
```

Example: `http://10.0.1.251:8765/nwr.mp3`

## Using the stream in HA

In the NWR Settings tab, enter the stream URL in the **Stream Player URL** field.
Set your media player entity ID in the **Stream Player** field.

HA will call `media_player.play_media` with the stream URL when an alert fires (if stream mode is enabled for that tier).

## Firewall note

Port 8765 must be reachable from your HA instance to the Pi.
If HA and the Pi are on the same LAN, no extra config is needed.

## Volume tuning

The default ffmpeg command applies a `+10dB` volume boost, which works well for most speakers.
To adjust, edit the `VOLUME_BOOST` variable in `nwr_parser.py`.

## Supported players

Any HA media player that supports HTTP MP3 streams:
- Alexa (Echo devices via Nabu Casa or local)
- Google / Nest speakers
- VLC via HA VLC add-on
- Sonos (via HA Sonos integration)
- Any browser-based player
