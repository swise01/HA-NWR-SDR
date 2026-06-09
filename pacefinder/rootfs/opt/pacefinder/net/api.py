import json
import struct
import urllib.request as _urllib_req
from pathlib import Path
from typing import Optional


def build_inject_packets(game: str, p: dict, fm_format: str) -> list:
    """Build valid UDP telemetry packets from user-friendly params."""
    speed_mph = float(p.get("speed_mph", 0))
    throttle  = max(0.0, min(100.0, float(p.get("throttle_pct", 0))))
    brake     = max(0.0, min(100.0, float(p.get("brake_pct", 0))))
    rpm       = float(p.get("rpm", 1000))
    gear      = int(p.get("gear", 1))
    lap       = int(p.get("lap", 1))

    if game == "forza_motorsport":
        speed_ms = speed_mph / 2.237
        vals = [
            1, 0,                                                  # is_race_on, timestamp_ms
            8500.0, 800.0, rpm,                                    # engine max/idle/current rpm
            0.0, 0.0, 0.0,                                         # accel xyz
            speed_ms, 0.0, 0.0,                                    # velocity xyz
            0.0, 0.0, 0.0,                                         # angular velocity
            0.0, 0.0, 0.0,                                         # yaw pitch roll
            0.5, 0.5, 0.5, 0.5,                                    # norm suspension travel x4
            0.0, 0.0, max(0.0,(speed_mph-20)/300), max(0.0,(speed_mph-20)/280),  # tire slip ratio x4
            speed_ms*4, speed_ms*4, speed_ms*4, speed_ms*4,        # wheel rotation speed x4
            0.0, 0.0, 0.0, 0.0,                                    # rumble strip x4
            0.0, 0.0, 0.0, 0.0,                                    # puddle x4
            0.0, 0.0, 0.0, 0.0,                                    # surface rumble x4
            0.0, 0.0, 0.0, 0.0,                                    # slip angle x4
            0.0, 0.0, 0.0, 0.0,                                    # combined slip x4
            0.1, 0.1, 0.1, 0.1,                                    # suspension travel meters x4
            42, 3, 750, 1, 6,                                      # car_ordinal/class/pi/drivetrain/cylinders
            0.0, 0.0, 0.0,                                         # position xyz
            speed_ms, 250000.0, 400.0,                             # speed, power, torque
            85.0, 85.0, 85.0, 85.0,                                # tire temp x4
            0.5, 0.6, 0.0,                                         # boost, fuel, distance
            0.0, 0.0, 0.0, 0.0,                                    # best/last/current lap / race time
            lap, 1,                                                # lap_number (H), race_position (B)
            int(throttle/100*255), int(brake/100*255), 0, 0, gear, # accel brake clutch handbrake gear
            0, 0, 0,                                               # steer, norm_driving_lane, norm_ai_brake
        ]
        return [struct.pack(fm_format, *vals)]

    if game == "acc":
        speed_kmh = speed_mph * 1.60934
        vals = [
            0,                            # packet_id
            throttle / 100,               # gas
            brake / 100,                  # brake
            50.0,                         # fuel
            gear,                         # gear
            int(rpm),                     # rpm
            0.0,                          # steer
            speed_kmh,                    # speed_kmh
            0.0, 0.0, speed_kmh / 3.6,   # vel xyz
            0.0, 0.0, 0.0,               # acc xyz
            0.0, 0.0, 0.0, 0.0,          # wheelSlip x4
        ]
        return [struct.pack("<ifffiiffffffffffff", *vals).ljust(200, b'\x00')]

    if game == "f1":
        speed_kmh = int(speed_mph * 1.60934)
        uid = 0xDEADCAFE
        def hdr(pid):
            # packetId at offset 6 (where parse_f1 reads it), packetVersion=1 at offset 5
            return struct.pack("<HBBBBBQfIIBB", 2024, 24, 1, 0, 1, pid, uid, 0.0, 0, 0, 0, 255)
        # Session packet — primes track/session_type meta
        sess = hdr(1) + struct.pack("<BbbBHBb", 0, 25, 20, 50, 5793, 10, 11)
        # CarTelemetry packet — speed, inputs, tyre temps
        car = struct.pack(
            "<HfffBbHBBH4H4B4BH4f4B",
            speed_kmh, throttle/100, 0.0, brake/100, 0, gear, int(rpm), 0, 0, 0,
            0, 0, 0, 0, 85, 85, 85, 85, 90, 90, 90, 90, 105,
            23.5, 23.5, 22.8, 22.8, 0, 0, 0, 0,
        ).ljust(60, b'\x00')
        # LapData packet — lap number and timing (offsets: lastLap@0 curLap@4 lapNum@31)
        lap_car = struct.pack("<II", 0, 15000)           # lastLap=0, curLap=15s
        lap_car += struct.pack("<HB", 0, 0)              # sector1
        lap_car += struct.pack("<HB", 0, 0)              # sector2
        lap_car += struct.pack("<II", 0, 0)              # deltas
        lap_car += struct.pack("<ff", 500.0, 5000.0)     # distances
        lap_car += struct.pack("<BB", 1, lap)            # carPosition=1, currentLapNum
        lap_car = lap_car.ljust(50, b'\x00')
        lapdata = hdr(2) + lap_car
        # MotionEx packet — wheelSlip at hdr+64 (fl/fr/rl/rr)
        slip_scale = max(0.0, (speed_mph - 20) / 150)   # gentle slip proportional to speed
        pre_slip = b'\x00' * 64
        slip_data = struct.pack("<ffff", slip_scale * 0.5, slip_scale * 0.5,
                                slip_scale, slip_scale * 1.1)
        motionex = hdr(13) + pre_slip + slip_data
        # Send car first to create the session, then motionex+lapdata to prime caches,
        # then car again so the second telemetry packet sees the merged slip+lap data.
        return [sess, hdr(6) + car, motionex, lapdata, hdr(6) + car]

    return []


def summarize_lap(lap: dict) -> Optional[dict]:
    samples = lap.get("samples", [])
    if not samples or not lap.get("lap_time_s"):
        return None
    throttle = [s.get("throttle_pct", 0) for s in samples]
    brake    = [s.get("brake_pct", 0)    for s in samples]
    g_lat    = [abs(s.get("g_lat", 0))   for s in samples]
    slip_rl  = [abs(s.get("slip_rl", 0)) for s in samples]
    slip_rr  = [abs(s.get("slip_rr", 0)) for s in samples]
    slip_avg = [(a + b) / 2 for a, b in zip(slip_rl, slip_rr)]
    n = len(samples)
    return {
        "lap_number":      lap["lap_number"],
        "lap_time_s":      lap["lap_time_s"],
        "max_speed_mph":   lap.get("max_speed_mph", 0),
        "avg_throttle":    round(sum(throttle) / n, 1),
        "avg_brake":       round(sum(brake)    / n, 1),
        "avg_g_lat":       round(sum(g_lat)    / n, 3),
        "avg_slip":        round(sum(slip_avg) / n, 4),
        "peak_slip":       round(max(slip_avg),     4) if slip_avg else 0,
        "slip_above_pct":  round(sum(1 for v in slip_avg if v > 0.1) / n * 100, 1),
    }


def build_analysis_prompt(session: dict, laps: list, historical: list,
                          sessions_dir: Path,
                          prev_analyses: Optional[list] = None) -> str:
    game  = session.get("game", "unknown").replace("_", " ").title()
    track = session.get("track", "unknown")
    date  = (session.get("started_at") or "")[:10]

    summaries = [s for lap in laps if (s := summarize_lap(lap))]
    valid_times = [s["lap_time_s"] for s in summaries]
    best_time = min(valid_times) if valid_times else None
    avg_time  = sum(valid_times) / len(valid_times) if valid_times else None

    hdr = "Lap | Time      | Throttle% | Brake% | MaxSpd | AvgSlip | PeakSlip | Slip>0.1%\n"
    hdr += "-" * 80 + "\n"
    rows = ""
    for s in summaries:
        marker = " ◄" if best_time and abs(s["lap_time_s"] - best_time) < 0.001 else ""
        rows += (
            f"{s['lap_number']:<3} | {s['lap_time_s']:.3f}s   | "
            f"{s['avg_throttle']:.0f}%        | {s['avg_brake']:.0f}%     | "
            f"{s['max_speed_mph']:.0f}mph  | {s['avg_slip']:.4f}  | "
            f"{s['peak_slip']:.4f}   | {s['slip_above_pct']:.1f}%{marker}\n"
        )

    hist_block = ""
    if historical:
        hist_sessions = historical[-3:]
        h_best_times  = [h.get("best_lap_time_s") for h in hist_sessions if h.get("best_lap_time_s")]
        h_avg_slip_vals = []
        for h in hist_sessions:
            try:
                hlaps = json.loads((sessions_dir / f"{h['session_id']}_laps.json").read_text())
                hsums = [s for lap in hlaps if (s := summarize_lap(lap))]
                if hsums:
                    h_avg_slip_vals.append(sum(s["avg_slip"] for s in hsums) / len(hsums))
            except Exception:
                pass
        h_best_str = f"{min(h_best_times):.3f}s" if h_best_times else "—"
        h_avg_str  = f"{sum(valid_times)/len(valid_times):.3f}s" if valid_times else "—"
        h_slip_str = f"{sum(h_avg_slip_vals)/len(h_avg_slip_vals):.4f}" if h_avg_slip_vals else "—"
        hist_block = (
            f"\nHISTORICAL BASELINE (last {len(hist_sessions)} sessions at this track):\n"
            f"Best lap: {h_best_str} | Avg lap: {h_avg_str} | Avg slip: {h_slip_str}\n"
        )

    return (
        f"Track: {track} | Game: {game} | Session: {date}\n\n"
        f"THIS SESSION — LAP TABLE:\n{hdr}{rows}\n"
        f"{hist_block}\n"
        "You're a race engineer doing a strat debrief. The driver is tired, "
        "sweaty, and won't read essays. Speak the way an engineer talks on the "
        "radio: short sentences, numbers instead of adjectives, imperative voice.\n\n"
        "Respond with ONLY a JSON object (no markdown fences, no prose before "
        "or after) in exactly this shape:\n"
        "{\n"
        '  "summary": "ONE sentence, max 15 words. The session in a punchline.",\n'
        '  "findings": [\n'
        '    {"area":  "3-6 word title — e.g. \'Lap 0 spin\', \'Brake oscillation\'",\n'
        '     "issue": "max 20 words. State the fact + the number that proves it.",\n'
        '     "fix":   "max 15 words, starts with a verb. The driver\'s next move."}\n'
        "  ],\n"
        '  "strengths": ["max 5 words each", "max 5 words each"]\n'
        "}\n\n"
        "Rules — non-negotiable:\n"
        "• 2-4 findings. Most-costly first. If you can't fit a finding inside "
        "  the word limit, it isn't important enough — drop it.\n"
        "• 1-3 strengths. Each ≤5 words. No \"meaningful\", no \"real\".\n"
        "• Numbers replace adjectives. \"Lap 5 was 4.9s slower\" beats \"Lap 5 was "
        "  significantly slower\". \"Peak slip 13.9 vs 1.4 average\" beats "
        "  \"costly instability\".\n"
        "• Imperative voice on fix. \"Brake later at T7\" not \"you might "
        "  consider braking later\".\n"
        "• Banned words anywhere in the output: productive, meaningful, "
        "  meaningfully, significant, significantly, costly, real, "
        "  competitive, likely, indicating, suggesting, demonstrably.\n"
        "• No throat-clearing summary like \"A productive session with…\". The "
        "  summary is one punchline only.\n"
        "• Plain text inside JSON strings — no markdown, no bullets."
    )


def build_track_tip_prompt(track: str, stats: dict) -> str:
    best = f"{stats['best_lap_time_s']:.3f}s" if stats.get("best_lap_time_s") else "unknown"
    return (
        f"Track: {track} | Sessions: {stats.get('session_count',0)} | Best lap: {best} | Trend: {stats.get('trend','fl')}\n\n"
        "Write exactly one coaching focus sentence (max 20 words) for this sim racing driver at this track. "
        "Be specific to the track's characteristics if you know it. No intro, no padding, just the sentence."
    )


def call_claude_api(prompt: str, api_key: str, model: str) -> str:
    if not api_key:
        raise ValueError("Anthropic API key not set — add it in Setup → AI Analysis")
    payload = json.dumps({
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = _urllib_req.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload, method="POST",
    )
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    with _urllib_req.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"]
