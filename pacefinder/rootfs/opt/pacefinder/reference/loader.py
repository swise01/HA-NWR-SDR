import logging
from pathlib import Path
from typing import Optional

from db.store import _load_learned_track_ordinals, _effective_tracks
from parsers.forza import parse_forza as _parse_forza_core

_log = logging.getLogger("pacefinder")

# Mutable dicts — populated by load_forza_reference_data(), mutated in-place
# so that db/store._forza_tracks (which holds the same object) stays in sync.
FORZA_TRACKS: dict = {}
FORZA_CARS:   dict = {}

_FORZA_TRACKS_FALLBACK = {
    860: "Brands Hatch Tor Grand Prix",
    0:   "Test Track Airfield",
    1:   "Test Track Airfield Drag",
}

# Ordinals seen in live packets but not in FORZA_TRACKS — logged once each
_unknown_ordinals_seen: set = set()

# FM2023 track names for manual session track confirmation via Edit modal
FM2023_TRACKS = sorted([
    "Brands Hatch Grand Prix",
    "Brands Hatch Indy Circuit",
    "Circuit de Spa-Francorchamps",
    "Circuit de Spa-Francorchamps (24h Layout)",
    "Circuit de Catalunya Grand Prix",
    "Circuit de Catalunya National",
    "Daytona International Speedway (Oval)",
    "Daytona International Speedway (Road)",
    "Dubai Autodrome Club",
    "Dubai Autodrome Grand Prix",
    "Dubai Autodrome International",
    "Dubai Autodrome National",
    "Hakone Circuit",
    "Homestead-Miami Speedway",
    "Indianapolis Motor Speedway (Oval)",
    "Indianapolis Motor Speedway (Road)",
    "Kyalami Grand Prix Circuit",
    "Laguna Seca Full Circuit",
    "Le Mans Full Circuit",
    "Le Mans Old Mulsanne Circuit",
    "Lime Rock Full Circuit",
    "Maple Valley Full Circuit",
    "Maple Valley Short Circuit",
    "Mid-Ohio Sports Car Course",
    "Mugello Full Circuit",
    "Nürburgring 24h Course",
    "Nürburgring Grand Prix",
    "Nürburgring Nordschleife",
    "Road America East Route",
    "Road America Full Circuit",
    "Road America West Route",
    "Road Atlanta Full Circuit",
    "Sebring Full Circuit",
    "Sebring International Raceway",
    "Sebring Short Circuit",
    "Silverstone Grand Prix",
    "Silverstone International",
    "Silverstone National",
    "Suzuka East",
    "Suzuka Full Circuit",
    "Watkins Glen Grand Prix",
    "Watkins Glen Short Circuit",
    "Yas Marina Corkscrew",
    "Yas Marina Full Circuit",
    "Yas Marina North Corkscrew",
    "Yas Marina North Circuit",
    "Yas Marina South Circuit",
])


def load_forza_reference_data() -> None:
    """Parse data/fm8_tracks*.csv and data/fm8_cars*.csv into FORZA_TRACKS / FORZA_CARS.

    Mutates the module-level dicts in-place so that any module holding a
    reference to them (e.g. db/store._forza_tracks) sees the updated data.

    Precedence (highest first):
      1. learned_track_ordinals from SQLite
      2. fm8_tracks_extended.csv (curated additions, simple 2-col format)
      3. fm8_tracks.csv (community bluemanos base, 5+ col format)
      4. _FORZA_TRACKS_FALLBACK hardcoded dict
    """
    import csv as _csv

    merged: dict = dict(_FORZA_TRACKS_FALLBACK)
    data_dir = Path(__file__).parent.parent / "data"

    # ── Tracks CSV — base (bluemanos format) ─────────────────────────────────
    tracks_csv = data_dir / "fm8_tracks.csv"
    track_count = 0
    if tracks_csv.exists():
        try:
            with tracks_csv.open(encoding="utf-8") as fh:
                for row in _csv.reader(fh):
                    if not row or row[0].startswith("#"):
                        continue
                    if len(row) < 5:
                        continue
                    try:
                        ordinal   = int(row[0].strip())
                        name_part = row[1].strip()
                        layout    = row[4].strip()
                        display   = f"{name_part} {layout}" if layout else name_part
                        merged[ordinal] = display
                        track_count += 1
                    except (ValueError, IndexError):
                        continue
        except Exception as exc:
            _log.warning(f"Could not parse fm8_tracks.csv: {exc}")

    # ── Tracks CSV — extended (curated, 2-col format, OVERRIDES base) ────────
    extended_csv = data_dir / "fm8_tracks_extended.csv"
    extended_count = 0
    if extended_csv.exists():
        try:
            with extended_csv.open(encoding="utf-8") as fh:
                for row in _csv.reader(fh):
                    if not row or row[0].startswith("#") or row[0].strip() == "ordinal":
                        continue
                    if len(row) < 2:
                        continue
                    try:
                        ordinal = int(row[0].strip())
                        display = row[1].strip()
                        if not display:
                            continue
                        merged[ordinal] = display
                        extended_count += 1
                    except (ValueError, IndexError):
                        continue
        except Exception as exc:
            _log.warning(f"Could not parse fm8_tracks_extended.csv: {exc}")

    # ── Cars CSV — base (bluemanos format) ───────────────────────────────────
    cars_csv = data_dir / "fm8_cars.csv"
    car_count = 0
    cars: dict = {}
    if cars_csv.exists():
        try:
            with cars_csv.open(encoding="utf-8") as fh:
                for row in _csv.reader(fh):
                    if not row or row[0].startswith("#"):
                        continue
                    if len(row) < 3:
                        continue
                    try:
                        ordinal = int(row[0].strip())
                        year    = int(row[1].strip())
                        make    = row[2].strip()
                        model   = row[3].strip() if len(row) > 3 else ""
                        if not make:
                            continue
                        full_name = f"{year} {make} {model}".strip() if year else f"{make} {model}".strip()
                        cars[ordinal] = {"name": full_name, "manufacturer": make, "year": year}
                        car_count += 1
                    except (ValueError, IndexError):
                        continue
        except Exception as exc:
            _log.warning(f"Could not parse fm8_cars.csv: {exc}")

    # ── Cars CSV — extended (curated, OVERRIDES base) ────────────────────────
    cars_extended_csv = data_dir / "fm8_cars_extended.csv"
    cars_extended_count = 0
    if cars_extended_csv.exists():
        try:
            with cars_extended_csv.open(encoding="utf-8") as fh:
                for row in _csv.reader(fh):
                    if not row or row[0].startswith("#") or row[0].strip() == "ordinal":
                        continue
                    if len(row) < 3:
                        continue
                    try:
                        ordinal = int(row[0].strip())
                        year    = int(row[1].strip())
                        make    = row[2].strip()
                        model   = row[3].strip() if len(row) > 3 else ""
                        if not make:
                            continue
                        full_name = f"{year} {make} {model}".strip() if year else f"{make} {model}".strip()
                        cars[ordinal] = {"name": full_name, "manufacturer": make, "year": year}
                        cars_extended_count += 1
                    except (ValueError, IndexError):
                        continue
        except Exception as exc:
            _log.warning(f"Could not parse fm8_cars_extended.csv: {exc}")

    # ── Merge learned DB ordinals (highest priority) ──────────────────────────
    try:
        learned = _load_learned_track_ordinals()
        merged.update(learned)
    except Exception:
        pass  # DB may not be init yet on first call

    # Mutate in-place so existing references (db/store._forza_tracks) stay valid
    FORZA_TRACKS.clear()
    FORZA_TRACKS.update(merged)
    FORZA_CARS.clear()
    FORZA_CARS.update(cars)

    _log.info(
        f"Loaded {track_count} base + {extended_count} extended FM tracks, "
        f"{car_count} base + {cars_extended_count} extended FM cars from reference data"
    )
    _log.debug(f"FORZA_TRACKS sample: {sorted(FORZA_TRACKS.items())[:20]}")


def parse_forza(data: bytes) -> Optional[dict]:
    return _parse_forza_core(data, _effective_tracks, _unknown_ordinals_seen, _log)
