import math
import struct
from typing import Optional

# FM2023 Data Out "Car Dash" packet: 311 bytes
# Reference: https://support.forzamotorsport.net/hc/en-us/articles/21742934024211

FM_PACKET_SIZE    = 311  # Forza Motorsport 2023 / FM7 Car Dash
FM_PACKET_SIZE_FH = 331  # Forza Horizon 4 / 5 Car Dash (adds tire wear + track ordinal)
FM_PACKET_SIZE_FH6 = 324  # Observed Forza Horizon 6 dashboard packet

# i I [51×f] [5×i: car_ordinal/class/pi/drivetrain/cylinders] [17×f] H [6×B] [3×b]
# drivetrain_type and num_cylinders are int32 per spec, not float.
FM_FORMAT    = "<iIfffffffffffffffffffffffffffffffffffffffffffffffffffiiiiifffffffffffffffffHBBBBBBbbb"
# FH4/FH5 appends: tireWearFL tireWearFR tireWearRL tireWearRR (4f) + trackOrdinal (i)
FM_FORMAT_FH = FM_FORMAT + "ffffi"

FM_FIELDS = [
    "is_race_on", "timestamp_ms",
    "engine_max_rpm", "engine_idle_rpm", "current_engine_rpm",
    "acceleration_x", "acceleration_y", "acceleration_z",
    "velocity_x", "velocity_y", "velocity_z",
    "angular_velocity_x", "angular_velocity_y", "angular_velocity_z",
    "yaw", "pitch", "roll",
    "normalized_suspension_travel_fl", "normalized_suspension_travel_fr",
    "normalized_suspension_travel_rl", "normalized_suspension_travel_rr",
    "tire_slip_ratio_fl", "tire_slip_ratio_fr",
    "tire_slip_ratio_rl", "tire_slip_ratio_rr",
    "wheel_rotation_speed_fl", "wheel_rotation_speed_fr",
    "wheel_rotation_speed_rl", "wheel_rotation_speed_rr",
    "wheel_on_rumble_strip_fl", "wheel_on_rumble_strip_fr",
    "wheel_on_rumble_strip_rl", "wheel_on_rumble_strip_rr",
    "wheel_in_puddle_fl", "wheel_in_puddle_fr",
    "wheel_in_puddle_rl", "wheel_in_puddle_rr",
    "surface_rumble_fl", "surface_rumble_fr",
    "surface_rumble_rl", "surface_rumble_rr",
    "tire_slip_angle_fl", "tire_slip_angle_fr",
    "tire_slip_angle_rl", "tire_slip_angle_rr",
    "tire_combined_slip_fl", "tire_combined_slip_fr",
    "tire_combined_slip_rl", "tire_combined_slip_rr",
    "suspension_travel_meters_fl", "suspension_travel_meters_fr",
    "suspension_travel_meters_rl", "suspension_travel_meters_rr",
    "car_ordinal", "car_class", "car_performance_index",
    "drivetrain_type", "num_cylinders",
    "position_x", "position_y", "position_z",
    "speed", "power", "torque",
    "tire_temp_fl", "tire_temp_fr", "tire_temp_rl", "tire_temp_rr",
    "boost", "fuel", "distance_traveled",
    "best_lap_time", "last_lap_time", "current_lap_time",
    "current_race_time",
    "lap_number", "race_position",
    "accel", "brake", "clutch", "handbrake",
    "gear", "steer",
    "normalized_driving_lane", "normalized_ai_brake_difference",
]


def _read_float(data: bytes, offset: int) -> float:
    if offset + 4 > len(data):
        return 0.0
    value = struct.unpack_from("<f", data, offset)[0]
    return 0.0 if math.isnan(value) or math.isinf(value) else value


def _read_i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0] if offset + 4 <= len(data) else 0


def _read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0] if offset + 4 <= len(data) else 0


def _read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0] if offset + 2 <= len(data) else 0


def _read_u8(data: bytes, offset: int) -> int:
    return data[offset] if offset + 1 <= len(data) else 0


def _read_i8(data: bytes, offset: int) -> int:
    return struct.unpack_from("<b", data, offset)[0] if offset + 1 <= len(data) else 0


def _parse_fh6_324(data: bytes) -> dict:
    offsets = {
        "position": 244,
        "speed": 256,
        "power": 260,
        "torque": 264,
        "tire_temp": 268,
        "boost": 284,
        "fuel": 288,
        "distance": 292,
        "best_lap": 296,
        "last_lap": 300,
        "current_lap": 304,
        "current_race": 308,
        "lap_number": 312,
        "race_position": 314,
        "accel": 315,
        "brake": 316,
        "clutch": 317,
        "handbrake": 318,
        "gear": 319,
        "steer": 320,
        "driving_line": 321,
        "ai_brake_diff": 322,
    }
    parsed = {
        "is_race_on": _read_i32(data, 0),
        "timestamp_ms": _read_u32(data, 4),
        "engine_max_rpm": _read_float(data, 8),
        "engine_idle_rpm": _read_float(data, 12),
        "current_engine_rpm": _read_float(data, 16),
        "acceleration_x": _read_float(data, 20),
        "acceleration_y": _read_float(data, 24),
        "acceleration_z": _read_float(data, 28),
        "velocity_x": _read_float(data, 32),
        "velocity_y": _read_float(data, 36),
        "velocity_z": _read_float(data, 40),
        "angular_velocity_x": _read_float(data, 44),
        "angular_velocity_y": _read_float(data, 48),
        "angular_velocity_z": _read_float(data, 52),
        "yaw": _read_float(data, 56),
        "pitch": _read_float(data, 60),
        "roll": _read_float(data, 64),
        "normalized_suspension_travel_fl": _read_float(data, 68),
        "normalized_suspension_travel_fr": _read_float(data, 72),
        "normalized_suspension_travel_rl": _read_float(data, 76),
        "normalized_suspension_travel_rr": _read_float(data, 80),
        "tire_slip_ratio_fl": _read_float(data, 84),
        "tire_slip_ratio_fr": _read_float(data, 88),
        "tire_slip_ratio_rl": _read_float(data, 92),
        "tire_slip_ratio_rr": _read_float(data, 96),
        "wheel_rotation_speed_fl": _read_float(data, 100),
        "wheel_rotation_speed_fr": _read_float(data, 104),
        "wheel_rotation_speed_rl": _read_float(data, 108),
        "wheel_rotation_speed_rr": _read_float(data, 112),
        "wheel_on_rumble_strip_fl": _read_u8(data, 116),
        "wheel_on_rumble_strip_fr": _read_u8(data, 117),
        "wheel_on_rumble_strip_rl": _read_u8(data, 118),
        "wheel_on_rumble_strip_rr": _read_u8(data, 119),
        "wheel_in_puddle_fl": _read_u8(data, 120),
        "wheel_in_puddle_fr": _read_u8(data, 121),
        "wheel_in_puddle_rl": _read_u8(data, 122),
        "wheel_in_puddle_rr": _read_u8(data, 123),
        "surface_rumble_fl": _read_float(data, 124),
        "surface_rumble_fr": _read_float(data, 128),
        "surface_rumble_rl": _read_float(data, 132),
        "surface_rumble_rr": _read_float(data, 136),
        "tire_slip_angle_fl": _read_float(data, 140),
        "tire_slip_angle_fr": _read_float(data, 144),
        "tire_slip_angle_rl": _read_float(data, 148),
        "tire_slip_angle_rr": _read_float(data, 152),
        "tire_combined_slip_fl": _read_float(data, 156),
        "tire_combined_slip_fr": _read_float(data, 160),
        "tire_combined_slip_rl": _read_float(data, 164),
        "tire_combined_slip_rr": _read_float(data, 168),
        "suspension_travel_meters_fl": _read_float(data, 172),
        "suspension_travel_meters_fr": _read_float(data, 176),
        "suspension_travel_meters_rl": _read_float(data, 180),
        "suspension_travel_meters_rr": _read_float(data, 184),
        "car_ordinal": _read_i32(data, 212),
        "car_class": _read_i32(data, 216),
        "car_performance_index": _read_i32(data, 220),
        "drivetrain_type": _read_i32(data, 224),
        "num_cylinders": _read_i32(data, 228),
        "position_x": _read_float(data, offsets["position"]),
        "position_y": _read_float(data, offsets["position"] + 4),
        "position_z": _read_float(data, offsets["position"] + 8),
        "speed": _read_float(data, offsets["speed"]),
        "power": _read_float(data, offsets["power"]),
        "torque": _read_float(data, offsets["torque"]),
        "tire_temp_fl": _read_float(data, offsets["tire_temp"]),
        "tire_temp_fr": _read_float(data, offsets["tire_temp"] + 4),
        "tire_temp_rl": _read_float(data, offsets["tire_temp"] + 8),
        "tire_temp_rr": _read_float(data, offsets["tire_temp"] + 12),
        "boost": _read_float(data, offsets["boost"]),
        "fuel": _read_float(data, offsets["fuel"]),
        "distance_traveled": _read_float(data, offsets["distance"]),
        "best_lap_time": _read_float(data, offsets["best_lap"]),
        "last_lap_time": _read_float(data, offsets["last_lap"]),
        "current_lap_time": _read_float(data, offsets["current_lap"]),
        "current_race_time": _read_float(data, offsets["current_race"]),
        "lap_number": _read_u16(data, offsets["lap_number"]),
        "race_position": _read_u16(data, offsets["race_position"]),
        "accel": _read_u8(data, offsets["accel"]),
        "brake": _read_u8(data, offsets["brake"]),
        "clutch": _read_u8(data, offsets["clutch"]),
        "handbrake": _read_u8(data, offsets["handbrake"]),
        "gear": _read_u8(data, offsets["gear"]),
        "steer": _read_i8(data, offsets["steer"]),
        "normalized_driving_lane": _read_i8(data, offsets["driving_line"]),
        "normalized_ai_brake_difference": _read_i8(data, offsets["ai_brake_diff"]),
        "track": "unknown",
        "_packet_type": "telemetry",
        "_packet_format": "FH6_324",
    }
    return parsed


def parse_forza(data: bytes, get_tracks, unknown_ordinals_seen: set, log_fn) -> Optional[dict]:
    if len(data) == FM_PACKET_SIZE_FH6:
        parsed = _parse_fh6_324(data)
    elif len(data) == FM_PACKET_SIZE_FH:
        fmt = FM_FORMAT_FH
        parsed = None
    elif len(data) == FM_PACKET_SIZE:
        fmt = FM_FORMAT
        parsed = None
    else:
        return None
    try:
        if parsed is None:
            values = struct.unpack(fmt, data)
            parsed = dict(zip(FM_FIELDS, values))
        if not parsed.get("is_race_on"):
            # Race not active (menu / pause / replay / results screen).
            # Most fields are stale here, BUT Forza flips is_race_on→0 the
            # instant you cross the final line, and that same packet still
            # carries the FINAL lap's last_lap_time. Returning None dropped
            # it outright → the last lap of every race went unrecorded.
            # Emit a minimal race-over marker (never treated as telemetry)
            # so the session can recover the final lap from last_lap_time.
            return {
                "_packet_type":      "race_over",
                "is_race_on":        0,
                "last_lap_time":     parsed.get("last_lap_time"),
                "lap_number":        parsed.get("lap_number"),
                "current_race_time": parsed.get("current_race_time"),
            }
        if len(data) == FM_PACKET_SIZE_FH:
            parsed["tire_wear_fl"]  = values[len(FM_FIELDS)]
            parsed["tire_wear_fr"]  = values[len(FM_FIELDS) + 1]
            parsed["tire_wear_rl"]  = values[len(FM_FIELDS) + 2]
            parsed["tire_wear_rr"]  = values[len(FM_FIELDS) + 3]
            ord_val                 = values[len(FM_FIELDS) + 4]
            parsed["track_ordinal"] = ord_val
            track_name = get_tracks().get(ord_val)
            if ord_val and track_name is None and ord_val not in unknown_ordinals_seen:
                unknown_ordinals_seen.add(ord_val)
                log_fn.warning(f"Unknown FH5 track ordinal {ord_val} — add to FORZA_TRACKS once identified")
            parsed["track"] = track_name if track_name else (f"Track #{ord_val}" if ord_val else "unknown")
        elif len(data) != FM_PACKET_SIZE_FH6:
            parsed["track"] = "unknown"  # FM2023 doesn't broadcast track in telemetry
        else:
            parsed["track"] = "unknown"
        parsed["speed_mph"]      = parsed["speed"] * 2.237
        parsed["throttle_pct"]   = parsed["accel"] / 255 * 100
        parsed["brake_pct"]      = parsed["brake"] / 255 * 100
        parsed["clutch_pct"]     = parsed["clutch"] / 255 * 100
        parsed["rpm"]            = parsed["current_engine_rpm"]
        parsed["slip_ratio_fl"]  = abs(parsed["tire_slip_ratio_fl"])
        parsed["slip_ratio_fr"]  = abs(parsed["tire_slip_ratio_fr"])
        parsed["slip_ratio_rl"]  = abs(parsed["tire_slip_ratio_rl"])
        parsed["slip_ratio_rr"]  = abs(parsed["tire_slip_ratio_rr"])
        parsed["g_lat"]          = parsed["acceleration_x"] / 9.81
        parsed["g_lon"]          = parsed["acceleration_z"] / 9.81
        return parsed
    except struct.error:
        return None
