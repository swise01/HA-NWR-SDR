"""
replay.py — read a Pacefinder .bin raw archive and re-parse it.

Usage:
    python3 replay.py <file.bin> [--game forza_motorsport|acc|f1] [--csv] [--summary]

The script auto-detects the game from the first packet size when --game is omitted.
With --csv it writes a CSV of all samples to stdout.
With --summary it prints per-lap stats.
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from pathlib import Path

# Re-use parsers from listener
from listener import parse_forza, parse_acc, parse_f1

PARSERS = {
    "forza_motorsport": parse_forza,
    "acc":              parse_acc,
    "f1":               parse_f1,
}

# Heuristic: auto-detect game by first packet size
def detect_game(first_packet: bytes) -> str:
    size = len(first_packet)
    if size == 311:
        return "forza_motorsport"
    if 100 <= size <= 400:
        return "acc"
    return "f1"


def read_packets(path: Path):
    """Yield raw packet bytes from a .bin archive."""
    with open(path, "rb") as f:
        while True:
            length_bytes = f.read(4)
            if len(length_bytes) < 4:
                break
            length = struct.unpack("<I", length_bytes)[0]
            data = f.read(length)
            if len(data) < length:
                break
            yield data


def replay(path: Path, game: str | None, as_csv: bool, summary: bool):
    packets = list(read_packets(path))
    if not packets:
        print("No packets found.", file=sys.stderr)
        sys.exit(1)

    if game is None:
        game = detect_game(packets[0])
        print(f"Auto-detected game: {game}", file=sys.stderr)

    parser = PARSERS[game]
    samples = []
    for raw in packets:
        parsed = parser(raw)
        if parsed and parsed.get("_packet_type", "telemetry") == "telemetry":
            samples.append(parsed)
        elif parsed and "_packet_type" not in parsed:
            samples.append(parsed)

    print(f"Parsed {len(samples)} telemetry samples from {len(packets)} packets.", file=sys.stderr)

    if summary:
        _print_summary(samples, game)
        return

    if as_csv:
        _write_csv(samples)
        return

    # Default: JSON
    print(json.dumps(samples, indent=2))


def _print_summary(samples: list[dict], game: str):
    if not samples:
        print("No samples.")
        return

    speeds = [s.get("speed_mph", 0) for s in samples]
    throttles = [s.get("throttle_pct", 0) for s in samples]
    brakes = [s.get("brake_pct", 0) for s in samples]

    print(f"\n{'─'*40}")
    print(f"Game:           {game}")
    print(f"Total samples:  {len(samples)}")
    print(f"Max speed:      {max(speeds):.1f} mph")
    print(f"Avg speed:      {sum(speeds)/len(speeds):.1f} mph")
    print(f"Avg throttle:   {sum(throttles)/len(throttles):.1f}%")
    print(f"Avg brake:      {sum(brakes)/len(brakes):.1f}%")

    # Per-lap stats (Forza only — has lap_number field)
    if game == "forza_motorsport":
        laps: dict[int, list] = {}
        for s in samples:
            lap = s.get("lap_number", 0)
            laps.setdefault(lap, []).append(s)
        print(f"\n{'Lap':<6} {'Samples':<10} {'Max Speed':>10} {'Avg Thr':>9} {'Avg Brk':>9} {'Lap Time':>10}")
        print("─" * 60)
        for lap_num in sorted(laps):
            lap_samples = laps[lap_num]
            max_spd = max(s.get("speed_mph", 0) for s in lap_samples)
            avg_thr = sum(s.get("throttle_pct", 0) for s in lap_samples) / len(lap_samples)
            avg_brk = sum(s.get("brake_pct", 0) for s in lap_samples) / len(lap_samples)
            # last sample has last_lap_time for the previous lap
            last_lap_t = lap_samples[-1].get("last_lap_time", 0)
            print(f"{lap_num:<6} {len(lap_samples):<10} {max_spd:>9.1f}  {avg_thr:>8.1f}% {avg_brk:>8.1f}% {last_lap_t:>9.3f}s")

    print(f"{'─'*40}\n")


def _write_csv(samples: list[dict]):
    if not samples:
        return
    # Collect all keys across samples
    all_keys = []
    seen = set()
    for s in samples:
        for k in s:
            if k not in seen and not k.startswith("_"):
                all_keys.append(k)
                seen.add(k)

    writer = csv.DictWriter(sys.stdout, fieldnames=all_keys, extrasaction="ignore")
    writer.writeheader()
    for s in samples:
        writer.writerow({k: s.get(k, "") for k in all_keys})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay a Pacefinder .bin archive")
    parser.add_argument("file", type=Path, help=".bin archive to replay")
    parser.add_argument("--game", choices=list(PARSERS), default=None, help="Force game parser")
    parser.add_argument("--csv", action="store_true", help="Output CSV instead of JSON")
    parser.add_argument("--summary", action="store_true", help="Print per-lap summary stats")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    replay(args.file, args.game, args.csv, args.summary)
