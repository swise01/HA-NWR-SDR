#!/usr/bin/env python3

import json
import math
import os
import socket
import struct
import threading
import time
import csv
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request

OPTIONS_PATH = "/data/options.json"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAR_ORDINALS_PATH = os.path.join(BASE_DIR, "data", "car_ordinals.csv")


def load_options():
    defaults = {
        "udp_port": 5300,
        "web_port": 5310,
        "mqtt_host": "10.0.1.100",
        "mqtt_port": 1883,
        "mqtt_username": "mqtt",
        "mqtt_password": "",
        "mqtt_topic_root": "forza",
        "mqtt_discovery_prefix": "homeassistant",
        "publish_hz": 10,
        "idle_timeout_seconds": 2,
        "rewind_hold_seconds": 6,
        "redline_rpm_pct": 88,
        "game_name": "Forza Horizon 6",
        "forward_targets": "127.0.0.1:8000",
        "wled_host": "192.168.5.43",
        "wled_tach_enabled": True,
        "wled_update_hz": 8,
        "wled_watchdog_seconds": 1,
        "wled_restore_preset": 10,
        "wled_top_mode": "tach",
        "wled_bottom_mode": "tach",
        "wled_stop_bar_start_led": 104,
        "wled_stop_bar_end_led": 119,
        "wled_reverse_brake_side_leds": 10,
    }
    try:
        with open(OPTIONS_PATH, "r", encoding="utf-8") as fh:
            defaults.update(json.load(fh))
    except FileNotFoundError:
        pass
    return defaults


CONFIG = load_options()
ROOT = CONFIG["mqtt_topic_root"].strip("/")
DISCOVERY_PREFIX = CONFIG["mqtt_discovery_prefix"].strip("/")
CLIENT_ID = "forza_telemetry_bridge"
TEXT_SENSORS = {
    "current_car": ("Current Car", "mdi:car-sports"),
}
GAME_NAME_BY_KEY = {
    "fh4": "Forza Horizon 4",
    "fh5": "Forza Horizon 5",
    "fh6": "Forza Horizon 6",
    "fm8": "Forza Motorsport",
    "generic": "Forza Horizon",
}
SENSORS = {
    "speed_mph": ("Speed", "mph", "mdi:speedometer", "measurement"),
    "rpm": ("RPM", "RPM", "mdi:gauge", "measurement"),
    "rpm_pct": ("RPM Percent", "%", "mdi:gauge-full", "measurement"),
    "rpm_bar_pct": ("RPM Bar Percent", "%", "mdi:gauge-full", "measurement"),
    "gear": ("Gear", None, "mdi:car-shift-pattern", None),
    "gear_raw": ("Gear Raw", None, "mdi:code-brackets", None),
    "throttle": ("Throttle", "%", "mdi:car-speed-limiter", "measurement"),
    "brake": ("Brake", "%", "mdi:car-brake-alert", "measurement"),
    "steer": ("Steer", "%", "mdi:steering", "measurement"),
    "power_hp": ("Power", "hp", "mdi:engine", "measurement"),
    "torque_lbft": ("Torque", "lb-ft", "mdi:engine-outline", "measurement"),
    "boost_psi": ("Boost", "psi", "mdi:turbocharger", "measurement"),
    "slip": ("Slip", "%", "mdi:car-traction-control", "measurement"),
    "fuel": ("Fuel", "%", "mdi:gas-station", "measurement"),
    "distance_traveled_m": ("Distance", "m", "mdi:map-marker-distance", "measurement"),
    "current_lap_time_s": ("Current Lap", "s", "mdi:timer-outline", "measurement"),
    "last_lap_time_s": ("Last Lap", "s", "mdi:timer", "measurement"),
    "best_lap_time_s": ("Best Lap", "s", "mdi:timer-star", "measurement"),
    "current_race_time_s": ("Race Time", "s", "mdi:timer-sand", "measurement"),
    "lap_number": ("Lap", None, "mdi:counter", None),
    "race_position": ("Position", None, "mdi:trophy-award", None),
    "packet_hz": ("Packet Rate", "Hz", "mdi:chart-timeline-variant", "measurement"),
    "packet_length": ("Packet Length", "B", "mdi:package-variant", "measurement"),
}
BINARY_SENSORS = {
    "playing": ("Playing", "running"),
    "redline": ("Redline", "problem"),
    "hard_braking": ("Hard Braking", "problem"),
    "airborne": ("Airborne", "problem"),
    "impact": ("Impact", "problem"),
    "reverse": ("Reverse", None),
}


def game_key(value):
    text = str(value or "").lower()
    if "horizon 4" in text or text == "fh4":
        return "fh4"
    if "horizon 5" in text or text == "fh5":
        return "fh5"
    if "horizon 6" in text or text == "fh6":
        return "fh6"
    if "motorsport" in text or text == "fm8":
        return "fm8"
    return ""


def load_car_ordinals():
    by_game = {}
    any_game = {}
    try:
        with open(CAR_ORDINALS_PATH, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    ordinal = int(row.get("ordinal") or 0)
                except ValueError:
                    continue
                name = " ".join(str(row.get("display_name") or "").split())
                key = game_key(row.get("game"))
                if not ordinal or not name or not key:
                    continue
                by_game.setdefault(key, {})[ordinal] = name
                any_game.setdefault(ordinal, []).append((key, name))
    except FileNotFoundError:
        print(f"Car ordinal map not found: {CAR_ORDINALS_PATH}", flush=True)
    return by_game, any_game


CAR_ORDINALS_BY_GAME, CAR_ORDINALS_ANY = load_car_ordinals()


def resolve_car(ordinal, game_name):
    ordinal = int(ordinal or 0)
    if not ordinal:
        return "Unknown Car", False, ""
    key = game_key(game_name)
    if key and ordinal in CAR_ORDINALS_BY_GAME.get(key, {}):
        return CAR_ORDINALS_BY_GAME[key][ordinal], True, key
    for fallback in ("fh6", "fh5", "fh4", "fm8"):
        if fallback in CAR_ORDINALS_BY_GAME and ordinal in CAR_ORDINALS_BY_GAME[fallback]:
            return CAR_ORDINALS_BY_GAME[fallback][ordinal], True, fallback
    matches = CAR_ORDINALS_ANY.get(ordinal) or []
    if matches:
        return matches[0][1], True, matches[0][0]
    return f"Unknown #{ordinal}", False, key


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clamp(value, low, high):
    return max(low, min(high, value))


def read_float(data, offset):
    if offset + 4 > len(data):
        return None
    value = struct.unpack_from("<f", data, offset)[0]
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def read_i32(data, offset):
    if offset + 4 > len(data):
        return None
    return struct.unpack_from("<i", data, offset)[0]


def read_u32(data, offset):
    if offset + 4 > len(data):
        return None
    return struct.unpack_from("<I", data, offset)[0]


def read_u16(data, offset):
    if offset + 2 > len(data):
        return None
    return struct.unpack_from("<H", data, offset)[0]


def read_u8(data, offset):
    if offset + 1 > len(data):
        return None
    return data[offset]


def read_i8(data, offset):
    if offset + 1 > len(data):
        return None
    return struct.unpack_from("<b", data, offset)[0]


def first_reasonable(candidates, low, high):
    for value in candidates:
        if value is not None and low <= value <= high:
            return value
    return None


def parse_packet(data, source, packet_hz):
    if len(data) in (323, 324):
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
            "hand_brake": 318,
            "gear": 319,
            "steer": 320,
            "driving_line": 321,
            "ai_brake_diff": 322,
        }
    else:
        offsets = {
            "position": 232,
            "speed": 244,
            "power": 248,
            "torque": 252,
            "tire_temp": 256,
            "boost": 272,
            "fuel": 276,
            "distance": 280,
            "best_lap": 284,
            "last_lap": 288,
            "current_lap": 292,
            "current_race": 296,
            "lap_number": 300,
            "race_position": 302,
            "accel": 303,
            "brake": 304,
            "clutch": 305,
            "hand_brake": 306,
            "gear": 307,
            "steer": 308,
            "driving_line": 309,
            "ai_brake_diff": 310,
        }
    speed_ms = first_reasonable([read_float(data, offsets["speed"])], -20, 250)
    max_rpm = first_reasonable([read_float(data, 8)], 1000, 20000)
    idle_rpm = first_reasonable([read_float(data, 12)], 200, 3000)
    rpm = first_reasonable([read_float(data, 16)], 0, 22000)
    accel_x = read_float(data, 20) or 0
    accel_y = read_float(data, 24) or 0
    accel_z = read_float(data, 28) or 0
    velocity_x = read_float(data, 32) or 0
    velocity_y = read_float(data, 36) or 0
    velocity_z = read_float(data, 40) or 0
    angular_velocity_x = read_float(data, 44) or 0
    angular_velocity_y = read_float(data, 48) or 0
    angular_velocity_z = read_float(data, 52) or 0
    yaw = read_float(data, 56) or 0
    pitch = read_float(data, 60) or 0
    roll = read_float(data, 64) or 0
    suspension_norm = [
        read_float(data, 68),
        read_float(data, 72),
        read_float(data, 76),
        read_float(data, 80),
    ]
    tire_slip_ratio = [
        read_float(data, 84),
        read_float(data, 88),
        read_float(data, 92),
        read_float(data, 96),
    ]
    wheel_rotation_speed = [
        read_float(data, 100),
        read_float(data, 104),
        read_float(data, 108),
        read_float(data, 112),
    ]
    wheel_on_rumble_strip = [
        read_u8(data, 116),
        read_u8(data, 117),
        read_u8(data, 118),
        read_u8(data, 119),
    ]
    wheel_in_puddle = [
        read_u8(data, 120),
        read_u8(data, 121),
        read_u8(data, 122),
        read_u8(data, 123),
    ]
    surface_rumble = [
        read_float(data, 124),
        read_float(data, 128),
        read_float(data, 132),
        read_float(data, 136),
    ]
    tire_slip_angle = [
        read_float(data, 140),
        read_float(data, 144),
        read_float(data, 148),
        read_float(data, 152),
    ]
    tire_combined_slip = [
        read_float(data, 156),
        read_float(data, 160),
        read_float(data, 164),
        read_float(data, 168),
    ]
    suspension_m = [
        read_float(data, 172),
        read_float(data, 176),
        read_float(data, 180),
        read_float(data, 184),
    ]
    car_ordinal = read_i32(data, 212)
    car_class = read_i32(data, 216)
    car_pi = read_i32(data, 220)
    drivetrain_type = read_i32(data, 224)
    num_cylinders = read_i32(data, 228)
    position_x = read_float(data, offsets["position"]) or 0
    position_y = read_float(data, offsets["position"] + 4) or 0
    position_z = read_float(data, offsets["position"] + 8) or 0
    power_w = read_float(data, offsets["power"])
    torque_nm = read_float(data, offsets["torque"])
    tire_temp_fl = read_float(data, offsets["tire_temp"])
    tire_temp_fr = read_float(data, offsets["tire_temp"] + 4)
    tire_temp_rl = read_float(data, offsets["tire_temp"] + 8)
    tire_temp_rr = read_float(data, offsets["tire_temp"] + 12)
    boost_psi = read_float(data, offsets["boost"])
    fuel_raw = read_float(data, offsets["fuel"]) or 0
    fuel_pct = (fuel_raw * 100) if fuel_raw <= 1.5 else fuel_raw
    fuel_pct = clamp(fuel_pct, 0, 100)
    distance_traveled_m = read_float(data, offsets["distance"])
    best_lap_time_s = read_float(data, offsets["best_lap"])
    last_lap_time_s = read_float(data, offsets["last_lap"])
    current_lap_time_s = read_float(data, offsets["current_lap"])
    current_race_time_s = read_float(data, offsets["current_race"])
    lap_number = int(read_u16(data, offsets["lap_number"]) or 0)
    race_position = int(read_u8(data, offsets["race_position"]) or 0)
    race_fields_valid = bool(lap_number or race_position or best_lap_time_s or last_lap_time_s or current_lap_time_s)
    accel = read_u8(data, offsets["accel"])
    brake = read_u8(data, offsets["brake"])
    clutch = read_u8(data, offsets["clutch"])
    hand_brake = read_u8(data, offsets["hand_brake"])
    gear_raw = read_u8(data, offsets["gear"])
    steer = read_i8(data, offsets["steer"])
    normalized_driving_line = read_i8(data, offsets["driving_line"])
    normalized_ai_brake_difference = read_i8(data, offsets["ai_brake_diff"])
    engine_telemetry_alive = bool(max_rpm and idle_rpm and rpm)
    paused_or_loading = bool(gear_raw == 0 and not engine_telemetry_alive)
    reverse = bool(gear_raw == 0 and not paused_or_loading)
    on_ground = sum(1 for item in suspension_norm if item is not None and item < 0.98)
    if rpm and max_rpm and max_rpm > idle_rpm:
        rpm_pct = round(((rpm - idle_rpm) / (max_rpm - idle_rpm)) * 100, 1)
    else:
        rpm_pct = round((rpm / max_rpm) * 100, 1) if rpm and max_rpm else 0
    rpm_pct = clamp(rpm_pct, 0, 100)
    rpm_bar_pct = round((rpm / max_rpm) * 100, 1) if rpm and max_rpm else rpm_pct
    rpm_bar_pct = clamp(rpm_bar_pct, 0, 100)
    redline_threshold_pct = clamp(float(CONFIG.get("redline_rpm_pct", 88)), 50, 98)
    speed_mph = round((speed_ms or 0) * 2.2369362921, 1)
    slip_ratio = [abs(value or 0) for value in tire_slip_ratio]
    combined_slip = [abs(value or 0) for value in tire_combined_slip]
    slip_angle = [abs(value or 0) for value in tire_slip_angle]
    gear_int = int(gear_raw or 0)
    if paused_or_loading:
        gear_display = "N"
    elif reverse:
        gear_display = "R"
    else:
        gear_display = str(max(0, gear_int))
    mode = "paused" if paused_or_loading else ("race" if race_fields_valid else "freeroam")
    current_car, car_known, car_lookup_game = resolve_car(car_ordinal, CONFIG["game_name"])

    payload = {
        "game": CONFIG["game_name"],
        "received_utc": utc_now(),
        "source_ip": source[0],
        "source_port": source[1],
        "packet_length": len(data),
        "packet_hz": round(packet_hz, 1),
        "is_race_on": read_i32(data, 0) == 1,
        "timestamp_ms": read_u32(data, 4),
        "position_x": round(position_x, 3),
        "position_y": round(position_y, 3),
        "position_z": round(position_z, 3),
        "acceleration_x": round(accel_x, 3),
        "acceleration_y": round(accel_y, 3),
        "acceleration_z": round(accel_z, 3),
        "velocity_x": round(velocity_x, 3),
        "velocity_y": round(velocity_y, 3),
        "velocity_z": round(velocity_z, 3),
        "angular_velocity_x": round(angular_velocity_x, 3),
        "angular_velocity_y": round(angular_velocity_y, 3),
        "angular_velocity_z": round(angular_velocity_z, 3),
        "yaw": round(yaw, 3),
        "pitch": round(pitch, 3),
        "roll": round(roll, 3),
        "normalized_suspension_travel_fl": round(suspension_norm[0] or 0, 3),
        "normalized_suspension_travel_fr": round(suspension_norm[1] or 0, 3),
        "normalized_suspension_travel_rl": round(suspension_norm[2] or 0, 3),
        "normalized_suspension_travel_rr": round(suspension_norm[3] or 0, 3),
        "tire_slip_ratio_fl": round(slip_ratio[0], 3),
        "tire_slip_ratio_fr": round(slip_ratio[1], 3),
        "tire_slip_ratio_rl": round(slip_ratio[2], 3),
        "tire_slip_ratio_rr": round(slip_ratio[3], 3),
        "wheel_rotation_speed_fl": round(wheel_rotation_speed[0] or 0, 3),
        "wheel_rotation_speed_fr": round(wheel_rotation_speed[1] or 0, 3),
        "wheel_rotation_speed_rl": round(wheel_rotation_speed[2] or 0, 3),
        "wheel_rotation_speed_rr": round(wheel_rotation_speed[3] or 0, 3),
        "wheel_on_rumble_strip_fl": int(wheel_on_rumble_strip[0] or 0),
        "wheel_on_rumble_strip_fr": int(wheel_on_rumble_strip[1] or 0),
        "wheel_on_rumble_strip_rl": int(wheel_on_rumble_strip[2] or 0),
        "wheel_on_rumble_strip_rr": int(wheel_on_rumble_strip[3] or 0),
        "wheel_in_puddle_fl": int(wheel_in_puddle[0] or 0),
        "wheel_in_puddle_fr": int(wheel_in_puddle[1] or 0),
        "wheel_in_puddle_rl": int(wheel_in_puddle[2] or 0),
        "wheel_in_puddle_rr": int(wheel_in_puddle[3] or 0),
        "surface_rumble_fl": round(surface_rumble[0] or 0, 3),
        "surface_rumble_fr": round(surface_rumble[1] or 0, 3),
        "surface_rumble_rl": round(surface_rumble[2] or 0, 3),
        "surface_rumble_rr": round(surface_rumble[3] or 0, 3),
        "tire_slip_angle_fl": round(slip_angle[0], 3),
        "tire_slip_angle_fr": round(slip_angle[1], 3),
        "tire_slip_angle_rl": round(slip_angle[2], 3),
        "tire_slip_angle_rr": round(slip_angle[3], 3),
        "tire_combined_slip_fl": round(combined_slip[0], 3),
        "tire_combined_slip_fr": round(combined_slip[1], 3),
        "tire_combined_slip_rl": round(combined_slip[2], 3),
        "tire_combined_slip_rr": round(combined_slip[3], 3),
        "suspension_travel_meters_fl": round(suspension_m[0] or 0, 3),
        "suspension_travel_meters_fr": round(suspension_m[1] or 0, 3),
        "suspension_travel_meters_rl": round(suspension_m[2] or 0, 3),
        "suspension_travel_meters_rr": round(suspension_m[3] or 0, 3),
        "car_ordinal": int(car_ordinal or 0),
        "current_car": current_car,
        "car_name": current_car,
        "car_known": car_known,
        "car_lookup_game": car_lookup_game,
        "car_class": int(car_class or 0),
        "car_performance_index": int(car_pi or 0),
        "drivetrain_type": int(drivetrain_type or 0),
        "num_cylinders": int(num_cylinders or 0),
        "speed_mph": speed_mph,
        "speed_kmh": round((speed_ms or 0) * 3.6, 1),
        "rpm": round(rpm or 0),
        "rpm_pct": rpm_pct,
        "rpm_bar_pct": rpm_bar_pct,
        "engine_max_rpm": round(max_rpm or 0),
        "engine_idle_rpm": round(idle_rpm or 0),
        "gear": gear_int,
        "gear_raw": gear_int,
        "gear_display": gear_display,
        "throttle": round(((accel or 0) / 255) * 100, 1),
        "brake": round(((brake or 0) / 255) * 100, 1),
        "clutch": round(((clutch or 0) / 255) * 100, 1),
        "handbrake": round(((hand_brake or 0) / 255) * 100, 1),
        "steer": round(((steer or 0) / 127) * 100, 1),
        "power_hp": round((power_w or 0) / 745.7, 1),
        "torque_lbft": round((torque_nm or 0) * 0.737562, 1),
        "boost_psi": round(boost_psi or 0, 1),
        "fuel": round(fuel_pct, 1),
        "fuel_raw": round(fuel_raw, 3),
        "tire_temp_fl": round(tire_temp_fl or 0, 1),
        "tire_temp_fr": round(tire_temp_fr or 0, 1),
        "tire_temp_rl": round(tire_temp_rl or 0, 1),
        "tire_temp_rr": round(tire_temp_rr or 0, 1),
        "distance_traveled_m": round(distance_traveled_m or 0, 1),
        "best_lap_time_s": round(best_lap_time_s or 0, 3),
        "last_lap_time_s": round(last_lap_time_s or 0, 3),
        "current_lap_time_s": round(current_lap_time_s or 0, 3),
        "current_race_time_s": round(current_race_time_s or 0, 3),
        "lap_number": lap_number,
        "race_position": race_position,
        "race_fields_valid": race_fields_valid,
        "mode": mode,
        "normalized_driving_line": int(normalized_driving_line or 0),
        "normalized_ai_brake_difference": int(normalized_ai_brake_difference or 0),
        "slip": round(clamp(max(slip_ratio) * 100, 0, 300), 1),
        "hard_braking": (brake or 0) > 210 and speed_mph > 25,
        "impact": False,
        "redline": rpm_bar_pct >= redline_threshold_pct,
        "redline_threshold_pct": redline_threshold_pct,
        "airborne": on_ground <= 1 and abs(accel_y) < 0.4 and speed_mph > 20,
        "wheelspin": ((accel or 0) > 160 and speed_mph < 90 and max(slip_ratio) > 0.15) or max(combined_slip) > 0.35,
        "wet": sum(1 for value in wheel_in_puddle if value) > 0,
        "on_rumble": sum(1 for value in wheel_on_rumble_strip if value) > 0,
        "reverse": reverse,
        "paused_or_loading": paused_or_loading,
    }
    payload["playing"] = False if payload["paused_or_loading"] else payload["is_race_on"] or payload["reverse"] or payload["speed_mph"] > 1 or payload["rpm"] > max(1200, payload["engine_idle_rpm"] + 300)
    payload["event"] = "paused" if payload["paused_or_loading"] else "idle"
    effect = "off" if payload["paused_or_loading"] else "idle"
    if payload["playing"]:
        if payload["redline"]:
            effect = "redline"
            payload["event"] = "redline"
        elif payload["hard_braking"]:
            effect = "brake"
            payload["event"] = "hard_braking"
        elif payload["reverse"]:
            effect = "reverse"
            payload["event"] = "reverse"
        elif payload["slip"] > 80 or payload["wheelspin"]:
            effect = "drive"
            payload["event"] = "wheelspin"
        elif payload["airborne"]:
            effect = "airborne"
            payload["event"] = "airborne"
        else:
            effect = "drive"
            payload["event"] = "drive"
    payload["effect"] = effect
    return payload


def encode_remaining_length(length):
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length:
            digit |= 0x80
        out.append(digit)
        if not length:
            return bytes(out)


def mqtt_string(value):
    encoded = str(value).encode("utf-8")
    return struct.pack("!H", len(encoded)) + encoded


class MqttClient:
    def __init__(self):
        self.sock = None
        self.last_io = 0
        self.lock = threading.Lock()

    def connect(self):
        self.close()
        sock = socket.create_connection((CONFIG["mqtt_host"], int(CONFIG["mqtt_port"])), timeout=10)
        variable = mqtt_string("MQTT") + bytes([4])
        flags = 0x02
        payload = mqtt_string(CLIENT_ID)
        password = CONFIG.get("mqtt_password") or ""
        username = CONFIG.get("mqtt_username") or ""
        if username:
            flags |= 0x80
            payload += mqtt_string(username)
        if password:
            flags |= 0x40
            payload += mqtt_string(password)
        variable += bytes([flags]) + struct.pack("!H", 30)
        packet = bytes([0x10]) + encode_remaining_length(len(variable) + len(payload)) + variable + payload
        sock.sendall(packet)
        response = sock.recv(4)
        if len(response) < 4 or response[0] != 0x20 or response[3] != 0:
            raise RuntimeError(f"MQTT connect failed: {response!r}")
        self.sock = sock
        self.last_io = time.monotonic()
        print(f"MQTT connected to {CONFIG['mqtt_host']}:{CONFIG['mqtt_port']}", flush=True)

    def ensure(self):
        if self.sock is None:
            self.connect()

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def publish(self, topic, payload, retain=False):
        if not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")
        fixed = 0x30 | (0x01 if retain else 0)
        body = mqtt_string(topic) + payload
        packet = bytes([fixed]) + encode_remaining_length(len(body)) + body
        with self.lock:
            for attempt in range(2):
                try:
                    self.ensure()
                    self.sock.sendall(packet)
                    self.last_io = time.monotonic()
                    return
                except OSError:
                    self.close()
                    if attempt:
                        raise

    def ping_if_idle(self):
        with self.lock:
            if self.sock and time.monotonic() - self.last_io > 20:
                try:
                    self.sock.sendall(b"\xc0\x00")
                    self.last_io = time.monotonic()
                except OSError:
                    self.close()


state = {
    "latest": {},
    "events": deque(maxlen=40),
    "last_packet_at": 0,
    "last_publish_at": 0,
    "packet_times": deque(maxlen=120),
    "packets": 0,
    "lighting_enabled": False,
}
state_lock = threading.Lock()
mqtt = MqttClient()
subscribe_callbacks = {}
WLED_BAR_MODES = {"tach", "speed", "brake", "slip", "off"}
WLED_CONTROL_KEYS = {
    "game_name",
    "rewind_hold_seconds",
    "wled_top_mode",
    "wled_bottom_mode",
    "wled_stop_bar_start_led",
    "wled_stop_bar_end_led",
    "wled_reverse_brake_side_leds",
}


def current_lighting_controls():
    return {key: CONFIG.get(key) for key in sorted(WLED_CONTROL_KEYS)}


def apply_lighting_control(key, value, publish=False):
    if key not in WLED_CONTROL_KEYS:
        return False
    if key == "game_name":
        raw_value = str(value).strip()
        normalized = game_key(raw_value) or raw_value.lower()
        value = GAME_NAME_BY_KEY.get(normalized, raw_value)
        if game_key(value) == "" and value.lower() != "forza horizon":
            return False
    elif key in ("wled_top_mode", "wled_bottom_mode"):
        value = str(value).strip().lower()
        if value not in WLED_BAR_MODES:
            return False
    elif key in ("wled_stop_bar_start_led", "wled_stop_bar_end_led"):
        value = int(clamp(int(value), 86, 140))
    elif key == "wled_reverse_brake_side_leds":
        value = int(clamp(int(value), 1, 20))
    elif key == "rewind_hold_seconds":
        value = int(clamp(int(value), 0, 15))
    CONFIG[key] = value
    if publish:
        mqtt.publish(f"{ROOT}/control/{key}", value, retain=True)
    print(f"Forza lighting control {key}={value}", flush=True)
    return True


class MqttSubscriber:
    def __init__(self, client_id):
        self.client_id = client_id

    def connect(self):
        sock = socket.create_connection((CONFIG["mqtt_host"], int(CONFIG["mqtt_port"])), timeout=10)
        variable = mqtt_string("MQTT") + bytes([4])
        flags = 0x02
        payload = mqtt_string(self.client_id)
        password = CONFIG.get("mqtt_password") or ""
        username = CONFIG.get("mqtt_username") or ""
        if username:
            flags |= 0x80
            payload += mqtt_string(username)
        if password:
            flags |= 0x40
            payload += mqtt_string(password)
        variable += bytes([flags]) + struct.pack("!H", 30)
        packet = bytes([0x10]) + encode_remaining_length(len(variable) + len(payload)) + variable + payload
        sock.sendall(packet)
        response = sock.recv(4)
        if len(response) < 4 or response[0] != 0x20 or response[3] != 0:
            raise RuntimeError(f"MQTT subscriber connect failed: {response!r}")
        sock.settimeout(None)
        return sock

    def run(self, subscriptions):
        while True:
            sock = None
            try:
                sock = self.connect()
                for idx, topic in enumerate(subscriptions, start=1):
                    body = struct.pack("!H", idx) + mqtt_string(topic) + b"\x00"
                    sock.sendall(b"\x82" + encode_remaining_length(len(body)) + body)
                print(f"MQTT subscriber connected to {CONFIG['mqtt_host']}:{CONFIG['mqtt_port']}", flush=True)
                while True:
                    header = sock.recv(1)
                    if not header:
                        raise OSError("MQTT subscriber socket closed")
                    remaining = 0
                    multiplier = 1
                    while True:
                        digit = sock.recv(1)[0]
                        remaining += (digit & 127) * multiplier
                        if not digit & 128:
                            break
                        multiplier *= 128
                    body = sock.recv(remaining)
                    if header[0] >> 4 != 3 or len(body) < 2:
                        continue
                    topic_len = struct.unpack("!H", body[:2])[0]
                    topic = body[2:2 + topic_len].decode("utf-8", "replace")
                    payload = body[2 + topic_len:].decode("utf-8", "replace")
                    callback = subscriptions.get(topic)
                    if callback:
                        callback(payload)
            except Exception as exc:
                print(f"MQTT subscriber reconnecting: {exc}", flush=True)
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass
                time.sleep(2)


def parse_forward_targets(value):
    targets = []
    for item in str(value or "").split(","):
        item = item.strip()
        if not item:
            continue
        host, sep, port = item.rpartition(":")
        if not sep or not host or not port.isdigit():
            print(f"Ignoring invalid forward target: {item}", flush=True)
            continue
        targets.append((host, int(port)))
    return targets


FORWARD_TARGETS = parse_forward_targets(CONFIG.get("forward_targets", ""))


class WledTach:
    def __init__(self, host):
        self.host = str(host or "").strip()
        self.original = None
        self.active = False
        self.last_update = 0
        self.last_bucket = None
        self.redline_phase = 0
        self.restored = False
        self.last_watchdog_at = 0

    def call(self, path, payload=None):
        if not self.host:
            return None
        url = f"http://{self.host}{path}"
        data = None
        headers = {}
        method = "GET"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        req = request.Request(url, data=data, headers=headers, method=method)
        with request.urlopen(req, timeout=0.4) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else None

    def snapshot(self):
        if self.original is None:
            current = self.call("/json/state")
            if current and not self.is_forza_state(current):
                self.original = current
            self.restored = False

    def restore(self):
        if self.restored:
            return
        if self.original is not None:
            self.call("/json/state", self.original)
        else:
            self.restore_default()
        self.original = None
        self.active = False
        self.last_bucket = None
        self.redline_phase = 0
        self.restored = True

    def restore_default(self):
        preset = int(CONFIG.get("wled_restore_preset", 10) or 10)
        self.call(
            "/json/state",
            {
                "seg": [{"id": 0, "frz": False}, {"id": 1, "frz": False}],
                "ps": preset,
                "transition": 7,
            },
        )

    def is_forza_state(self, current):
        segments = current.get("seg", []) if isinstance(current, dict) else []
        names = {str(seg.get("n", "")) for seg in segments if isinstance(seg, dict)}
        return any(name.startswith("Forza ") for name in names)

    def watchdog_reclaim_needed(self, now):
        interval = float(CONFIG.get("wled_watchdog_seconds", 1) or 0)
        if interval <= 0 or now - self.last_watchdog_at < interval:
            return False
        self.last_watchdog_at = now
        current = self.call("/json/state")
        if current and not self.is_forza_state(current):
            self.original = current
            self.last_bucket = None
            print("WLED preset changed during gameplay; reclaiming Forza lighting", flush=True)
            return True
        return False

    def update(self, telemetry):
        if not self.host or not CONFIG.get("wled_tach_enabled", True):
            return
        now = time.monotonic()
        enabled = state.get("lighting_enabled")
        if not enabled or not telemetry.get("playing") or telemetry.get("effect") == "off":
            if self.active or self.original is not None or not self.restored:
                self.restore()
            self.last_update = now
            return
        update_hz = min(max(4, int(CONFIG.get("wled_update_hz", 8))), 8)
        if now - self.last_update < 1 / update_hz:
            return
        self.last_update = now
        rpm_pct = clamp(float(telemetry.get("rpm_pct") or 0), 0, 100)
        rpm_bar_pct = clamp(float(telemetry.get("rpm_bar_pct") or rpm_pct), 0, 100)
        brake_pct = clamp(float(telemetry.get("brake") or 0), 0, 100)
        rpm_leds = int(clamp(round(55 * rpm_bar_pct / 100), 0, 55))
        engine_alive = bool(telemetry.get("rpm") and telemetry.get("engine_max_rpm"))
        if engine_alive:
            rpm_leds = max(2, rpm_leds)
        effect = telemetry.get("effect")
        event = telemetry.get("event")
        if telemetry.get("reverse"):
            effect = "reverse"
        elif effect != "redline" and brake_pct >= 1:
            effect = "brake"
        elif effect == "slip":
            effect = "drive"
        reclaim = self.watchdog_reclaim_needed(now)
        bucket = (int(rpm_bar_pct // 2), int(brake_pct // 5), effect, event)
        idle_flicker = engine_alive and rpm_leds <= 8 and effect in ("idle", "drive")
        if not reclaim and bucket == self.last_bucket and not idle_flicker and effect not in ("redline", "brake", "airborne", "lap_complete"):
            return
        self.last_bucket = bucket
        self.snapshot()
        self.active = True
        self.restored = False
        if effect == "redline":
            self.redline_phase = (self.redline_phase + 1) % 6
            top_pixels = []
            bottom_pixels = []
            for index in range(55):
                phase = (index + self.redline_phase) % 6
                color = [255, 0, 0] if phase < 3 else [135, 0, 0]
                top_pixels.extend([index, color])
                bottom_pixels.extend([index, color])
            payload = {
                "on": True,
                "bri": 255,
                "transition": 0,
                "mainseg": 0,
                "seg": [
                    {"id": 0, "start": 86, "stop": 141, "n": "Forza Top Redline", "on": True, "bri": 255, "fx": 0, "rev": False, "i": top_pixels},
                    {"id": 1, "start": 2, "stop": 57, "n": "Forza Bottom Redline", "on": True, "bri": 255, "fx": 0, "rev": True, "i": bottom_pixels},
                    {"id": 2, "start": 0, "stop": 0},
                    {"id": 3, "start": 0, "stop": 0},
                ],
            }
            self.call("/json/state", payload)
            return
        if effect == "lap_complete":
            payload = {
                "on": True,
                "bri": 255,
                "transition": 0,
                "seg": [
                    {"id": 0, "start": 86, "stop": 141, "n": "Forza Top Speed", "on": True, "bri": 255, "fx": 0, "sx": 128, "ix": 128, "rev": False, "col": [[255, 196, 64], [0, 0, 0], [0, 0, 0]]},
                    {"id": 1, "start": 2, "stop": 57, "n": "Forza Bottom Tach", "on": True, "bri": 255, "fx": 0, "sx": 128, "ix": 128, "rev": True, "col": [[255, 196, 64], [0, 0, 0], [0, 0, 0]]},
                    {"id": 2, "start": 0, "stop": 0},
                    {"id": 3, "start": 0, "stop": 0},
                ],
            }
            self.call("/json/state", payload)
            return
        dim = [0, 0, 0]
        flicker_phase = int(time.monotonic() * 12) % 4
        speed_pct = clamp((float(telemetry.get("speed_mph") or 0) / 180) * 100, 0, 100)
        speed_leds = int(clamp(round(55 * speed_pct / 100), 0, 55))
        slip_pct = clamp(float(telemetry.get("slip") or 0), 0, 100)
        slip_leds = int(clamp(round(55 * slip_pct / 100), 0, 55))
        brake_leds = int(clamp(round(55 * brake_pct / 100), 0, 55))
        def tach_color(index):
            pct = ((index + 1) / 55) * 100
            if pct >= 84:
                return [255, 0, 0]
            if pct >= 60:
                return [255, 170, 0]
            if idle_flicker and index >= max(0, rpm_leds - 2):
                return [0, 140 + (flicker_phase * 32), 18]
            return [0, 255, 35]
        def mode_pixels(mode):
            pixels = []
            mode = mode if mode in WLED_BAR_MODES else "tach"
            for index in range(55):
                color = dim
                if mode == "tach" and index < rpm_leds:
                    color = tach_color(index)
                elif mode == "speed" and index < speed_leds:
                    color = [0, 170, 255] if speed_pct < 75 else [255, 176, 0]
                elif mode == "brake" and index < brake_leds:
                    color = [255, 0, 0]
                elif mode == "slip" and index < slip_leds:
                    color = [255, 0, 90] if slip_pct > 35 else [0, 220, 255]
                pixels.extend([index, color])
            return pixels
        top_mode = str(CONFIG.get("wled_top_mode", "tach")).strip().lower()
        bottom_mode = str(CONFIG.get("wled_bottom_mode", "tach")).strip().lower()
        top_pixels = mode_pixels(top_mode)
        bottom_pixels = mode_pixels(bottom_mode)
        brake_color = [255, 0, 0]
        def add_top_center_stop_bar():
            start_led = clamp(int(CONFIG.get("wled_stop_bar_start_led", 104)), 86, 140)
            end_led = clamp(int(CONFIG.get("wled_stop_bar_end_led", 119)), start_led, 140)
            for led in range(int(start_led), int(end_led) + 1):
                top_pixels[(led - 86) * 2 + 1] = brake_color
        if effect == "reverse":
            reverse_pixels = []
            reverse_brake = brake_pct >= 1
            if reverse_brake:
                add_top_center_stop_bar()
            side_leds = int(clamp(int(CONFIG.get("wled_reverse_brake_side_leds", 10)), 1, 20))
            for index in range(55):
                color = [255, 255, 255]
                if reverse_brake and (index < side_leds or index >= 55 - side_leds):
                    color = brake_color
                reverse_pixels.extend([index, color])
            payload = {
                "on": True,
                "bri": 255,
                "transition": 0,
                "mainseg": 0,
                "seg": [
                    {
                        "id": 0,
                        "start": 86,
                        "stop": 141,
                        "n": "Forza Top Tach",
                        "on": True,
                        "bri": 255,
                        "fx": 0,
                        "rev": False,
                        "i": top_pixels,
                    },
                    {
                        "id": 1,
                        "start": 2,
                        "stop": 57,
                        "n": "Forza Bottom Reverse",
                        "on": True,
                        "bri": 255,
                        "fx": 0,
                        "sx": 128,
                        "ix": 128,
                        "rev": True,
                        "col": [[255, 255, 255], [0, 0, 0], [0, 0, 0]],
                        "i": reverse_pixels,
                    },
                    {"id": 2, "start": 0, "stop": 0},
                    {"id": 3, "start": 0, "stop": 0},
                ],
            }
            self.call("/json/state", payload)
            return
        if effect == "brake":
            add_top_center_stop_bar()
            bottom_pixels = []
            for index in range(55):
                bottom_pixels.extend([index, brake_color])
        elif effect == "airborne":
            bottom_pixels = []
            top_pixels = []
            for index in range(55):
                color = [0, 220, 255] if index < max(1, rpm_leds) else dim
                bottom_pixels.extend([index, color])
                top_pixels.extend([index, color])
        payload = {
            "on": True,
            "bri": 255,
            "transition": 0,
            "mainseg": 0,
            "seg": [
                {
                    "id": 0,
                    "start": 86,
                    "stop": 141,
                    "n": "Forza Top Speed",
                    "on": True,
                    "bri": 255,
                    "fx": 0,
                    "ix": 128,
                    "sx": 128,
                    "pal": 0,
                    "rev": False,
                    "i": top_pixels,
                },
                {
                    "id": 1,
                    "start": 2,
                    "stop": 57,
                    "n": "Forza Bottom Tach",
                    "on": True,
                    "bri": 255,
                    "fx": 0,
                    "ix": 128,
                    "sx": 128,
                    "pal": 0,
                    "rev": True,
                    "i": bottom_pixels,
                },
                {"id": 2, "start": 0, "stop": 0},
                {"id": 3, "start": 0, "stop": 0},
            ],
        }
        self.call("/json/state", payload)


wled_tach = WledTach(CONFIG.get("wled_host", ""))


def lighting_enabled_changed(payload):
    enabled = str(payload).strip().lower() in ("1", "true", "on", "yes")
    with state_lock:
        state["lighting_enabled"] = enabled
    print(f"Forza lighting enabled={enabled}", flush=True)
    if not enabled:
        try:
            wled_tach.restore()
        except Exception as exc:
            print(f"WLED restore failed: {exc}", flush=True)


def make_lighting_control_changed(key):
    def changed(payload):
        try:
            apply_lighting_control(key, payload)
        except (TypeError, ValueError) as exc:
            print(f"Ignored invalid lighting control {key}={payload!r}: {exc}", flush=True)
    return changed


def publish_discovery():
    device = {
        "identifiers": ["forza_telemetry"],
        "name": "Forza Telemetry",
        "manufacturer": "Wise Homelab",
        "model": CONFIG["game_name"],
    }
    availability = {"topic": f"{ROOT}/status"}
    for key, meta in SENSORS.items():
        name, unit, icon, state_class = meta
        cfg = {
            "name": f"Forza {name}",
            "unique_id": f"forza_{key}",
            "state_topic": f"{ROOT}/state",
            "value_template": f"{{{{ value_json.{key} }}}}",
            "availability": availability,
            "device": device,
            "icon": icon,
        }
        if unit:
            cfg["unit_of_measurement"] = unit
        if state_class:
            cfg["state_class"] = state_class
        mqtt.publish(f"{DISCOVERY_PREFIX}/sensor/forza/{key}/config", json.dumps(cfg), retain=True)
    for key, meta in TEXT_SENSORS.items():
        name, icon = meta
        cfg = {
            "name": f"Forza {name}",
            "unique_id": f"forza_{key}",
            "state_topic": f"{ROOT}/state",
            "value_template": f"{{{{ value_json.{key} }}}}",
            "availability": availability,
            "device": device,
            "icon": icon,
        }
        mqtt.publish(f"{DISCOVERY_PREFIX}/sensor/forza/{key}/config", json.dumps(cfg), retain=True)
    for key, meta in BINARY_SENSORS.items():
        name, device_class = meta
        cfg = {
            "name": f"Forza {name}",
            "unique_id": f"forza_{key}",
            "state_topic": f"{ROOT}/state",
            "value_template": f"{{{{ value_json.{key} }}}}",
            "payload_on": "True",
            "payload_off": "False",
            "availability": availability,
            "device": device,
        }
        if device_class:
            cfg["device_class"] = device_class
        mqtt.publish(f"{DISCOVERY_PREFIX}/binary_sensor/forza/{key}/config", json.dumps(cfg), retain=True)
    text_cfg = {
        "name": "Forza Lighting Effect",
        "unique_id": "forza_lighting_effect",
        "state_topic": f"{ROOT}/effect",
        "availability": availability,
        "device": device,
        "icon": "mdi:led-strip-variant",
    }
    mqtt.publish(f"{DISCOVERY_PREFIX}/sensor/forza/effect/config", json.dumps(text_cfg), retain=True)
    snapshot_cfg = {
        "name": "Forza Snapshot",
        "unique_id": "forza_snapshot",
        "state_topic": f"{ROOT}/state",
        "value_template": "{{ value_json.speed_mph }}",
        "json_attributes_topic": f"{ROOT}/state",
        "availability": availability,
        "device": device,
        "icon": "mdi:chart-box",
        "unit_of_measurement": "mph",
        "state_class": "measurement",
    }
    mqtt.publish(f"{DISCOVERY_PREFIX}/sensor/forza/snapshot/config", json.dumps(snapshot_cfg), retain=True)
    event_cfg = {
        "name": "Forza Event",
        "unique_id": "forza_event",
        "state_topic": f"{ROOT}/state",
        "value_template": "{{ value_json.event }}",
        "availability": availability,
        "device": device,
        "icon": "mdi:message-flash",
    }
    mqtt.publish(f"{DISCOVERY_PREFIX}/sensor/forza/event/config", json.dumps(event_cfg), retain=True)
    subscriber = MqttSubscriber("forza_telemetry_control")
    subscriptions = {f"{ROOT}/control/lighting_enabled": lighting_enabled_changed}
    for key in WLED_CONTROL_KEYS:
        subscriptions[f"{ROOT}/control/{key}"] = make_lighting_control_changed(key)
    threading.Thread(
        target=subscriber.run,
        args=(subscriptions,),
        daemon=True,
    ).start()


def publish_state(payload, force=False):
    now = time.monotonic()
    interval = 1 / max(1, int(CONFIG["publish_hz"]))
    if not force and now - state["last_publish_at"] < interval:
        return
    state["last_publish_at"] = now
    mqtt.publish(f"{ROOT}/state", json.dumps(payload), retain=False)
    mqtt.publish(f"{ROOT}/effect", payload["effect"], retain=False)
    mqtt.publish(f"{ROOT}/status", "online", retain=True)


def telemetry_loop():
    publish_discovery()
    mqtt.publish(f"{ROOT}/status", "online", retain=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", int(CONFIG["udp_port"])))
    sock.settimeout(1.0)
    print(f"Listening for Forza UDP on 0.0.0.0:{CONFIG['udp_port']}", flush=True)
    if FORWARD_TARGETS:
        print(f"Forwarding raw UDP packets to {FORWARD_TARGETS}", flush=True)
    last_speed = 0.0
    last_lap_number = 0
    last_current_lap_time = 0.0
    last_valid_gameplay_at = 0
    last_valid_payload = {}
    reported_recent_off = False
    last_debug_at = 0
    while True:
        try:
            data, source = sock.recvfrom(2048)
        except socket.timeout:
            with state_lock:
                latest = dict(state["latest"])
                stale_timeout = min(int(CONFIG["idle_timeout_seconds"]), 2)
                stale = state["last_packet_at"] and time.monotonic() - state["last_packet_at"] > stale_timeout
            if stale and latest.get("playing"):
                latest["playing"] = False
                latest["effect"] = "off"
                latest["received_utc"] = utc_now()
                with state_lock:
                    state["latest"] = latest
                try:
                    wled_tach.update(latest)
                except Exception as exc:
                    print(f"WLED tach update failed: {exc}", flush=True)
                publish_state(latest, force=True)
                mqtt.publish(f"{ROOT}/effect", "off", retain=False)
            mqtt.ping_if_idle()
            continue
        now = time.monotonic()
        for target in FORWARD_TARGETS:
            try:
                sock.sendto(data, target)
            except OSError as exc:
                print(f"UDP forward failed for {target}: {exc}", flush=True)
        with state_lock:
            state["packet_times"].append(now)
            recent = [item for item in state["packet_times"] if now - item <= 1]
            packet_hz = len(recent)
            payload = parse_packet(data, source, packet_hz)
            valid_gameplay = not payload.get("paused_or_loading") and (
                payload.get("fuel", 0) > 0
                or payload.get("speed_mph", 0) > 1
                or payload.get("rpm", 0) > 0
                or payload.get("is_race_on")
            )
            if valid_gameplay:
                last_valid_gameplay_at = now
                last_valid_payload = dict(payload)
                reported_recent_off = False
            elif payload.get("paused_or_loading") and last_valid_payload and last_valid_gameplay_at and now - last_valid_gameplay_at < int(CONFIG.get("rewind_hold_seconds", 6)):
                held_for = round(now - last_valid_gameplay_at, 2)
                payload = dict(last_valid_payload)
                payload["received_utc"] = utc_now()
                payload["rewind_hold"] = True
                payload["rewind_hold_seconds"] = int(CONFIG.get("rewind_hold_seconds", 6))
                payload["rewind_hold_for_s"] = held_for
                payload["event"] = "rewind_hold"
            elif payload.get("paused_or_loading") and last_valid_payload and not reported_recent_off:
                print(
                    "gameplay_to_off "
                    f"after={now - last_valid_gameplay_at:.1f}s "
                    f"last_speed={last_valid_payload.get('speed_mph')} "
                    f"last_gear={last_valid_payload.get('gear_display')} "
                    f"last_lap={last_valid_payload.get('lap_number')} "
                    f"last_current_lap={last_valid_payload.get('current_lap_time_s')} "
                    f"last_last_lap={last_valid_payload.get('last_lap_time_s')} "
                    f"last_best_lap={last_valid_payload.get('best_lap_time_s')} "
                    f"last_race_time={last_valid_payload.get('current_race_time_s')} "
                    f"last_position={last_valid_payload.get('race_position')} "
                    f"last_is_race_on={last_valid_payload.get('is_race_on')}",
                    flush=True,
                )
                reported_recent_off = True
            if last_speed > 30 and (last_speed - payload["speed_mph"]) > 20 and payload["speed_mph"] < (last_speed * 0.65):
                payload["impact"] = True
            payload["reverse"] = bool(payload.get("reverse"))
            current_lap_time = float(payload.get("current_lap_time_s") or 0)
            if payload["lap_number"] and payload["lap_number"] > last_lap_number:
                payload["event"] = "lap_complete"
                payload["lap_complete"] = True
                if payload["effect"] in ("drive", "idle"):
                    payload["effect"] = "lap_complete"
            elif last_current_lap_time > 10 and 0 < current_lap_time < 5 and current_lap_time < last_current_lap_time and payload["playing"]:
                payload["event"] = "lap_complete"
                payload["lap_complete"] = True
                if payload["effect"] in ("drive", "idle"):
                    payload["effect"] = "lap_complete"
            if payload["impact"]:
                payload["event"] = "impact"
            if now - last_debug_at > 2:
                print(
                    "telemetry "
                    f"gear_raw={payload.get('gear_raw')} "
                    f"gear_display={payload.get('gear_display')} "
                    f"reverse={payload.get('reverse')} "
                    f"effect={payload.get('effect')} "
                    f"speed={payload.get('speed_mph')} "
                    f"throttle={payload.get('throttle')} "
                    f"brake={payload.get('brake')} "
                    f"fuel={payload.get('fuel')} "
                    f"slip={payload.get('slip')} "
                    f"lap={payload.get('lap_number')} "
                    f"current_lap={payload.get('current_lap_time_s')} "
                    f"last_lap={payload.get('last_lap_time_s')} "
                    f"best_lap={payload.get('best_lap_time_s')} "
                    f"race_time={payload.get('current_race_time_s')} "
                    f"position={payload.get('race_position')} "
                    f"car={payload.get('current_car')} "
                    f"car_ordinal={payload.get('car_ordinal')} "
                    f"is_race_on={payload.get('is_race_on')} "
                    f"event={payload.get('event')}",
                    flush=True,
                )
                last_debug_at = now
            last_speed = payload["speed_mph"]
            last_lap_number = int(payload.get("lap_number") or last_lap_number)
            last_current_lap_time = current_lap_time
            previous = state["latest"]
            if payload["effect"] != previous.get("effect"):
                state["events"].appendleft({"at": payload["received_utc"], "effect": payload["effect"]})
            if payload.get("event") != previous.get("event"):
                state["events"].appendleft({"at": payload["received_utc"], "event": payload["event"]})
            state["latest"] = payload
            state["last_packet_at"] = now
            state["packets"] += 1
        try:
            wled_tach.update(payload)
        except Exception as exc:
            print(f"WLED tach update failed: {exc}", flush=True)
        publish_state(payload)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forza Telemetry</title>
<style>
	:root{color-scheme:dark;--bg:#08090b;--panel:#111419;--panel2:#171b22;--line:#252b34;--line2:#323946;--text:#f5f7fb;--muted:#9aa4b2;--dim:#697381;--red:#ff385c;--amber:#ffb000;--green:#33d17a;--blue:#4dabf7;--cyan:#35d7ff;--mag:#ff4fd8}
	*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:12px/1.25 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-variant-numeric:tabular-nums;overflow:hidden}
	main{width:100vw;height:100vh;padding:8px;display:grid;grid-template-rows:30px auto;gap:8px}.rail{min-height:0;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--line);padding-bottom:6px}
	.dot{width:10px;height:10px;border-radius:50%;background:var(--dim)}.dot.on{background:var(--green);box-shadow:0 0 18px #33d17a88}.dot.red{background:var(--red);box-shadow:0 0 18px #ff385caa}
	.title{font-size:12px;letter-spacing:.14em;text-transform:uppercase;white-space:nowrap}.pill{border:1px solid var(--line);border-radius:999px;padding:2px 7px;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}.carPill{max-width:300px;overflow:hidden;text-overflow:ellipsis;color:var(--text);border-color:var(--line2)}.spacer{flex:1}.muted{color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
	.lightControls{display:flex;align-items:center;gap:5px;min-width:0}.lightControls label{display:flex;align-items:center;gap:3px;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}.lightControls select,.lightControls input{height:22px;background:var(--panel2);border:1px solid var(--line);border-radius:4px;color:var(--text);font:10px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.lightControls select{width:66px}.lightControls input{width:44px;padding:0 4px}
		.dashboard{min-height:0;display:grid;grid-template-columns:1.15fr .9fr 1fr 1fr;grid-template-rows:178px minmax(0,1fr) minmax(0,1.05fr);grid-template-areas:"hero hero hero hero" "inputs timing state chassis" "susp susp raw raw";gap:8px}.tile,.wideGauge,.steerGauge{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px;min-width:0;min-height:0;overflow:hidden}.lbl{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.08em}.sub{color:var(--dim);font-size:10px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
		.hero{grid-area:hero;display:grid;grid-template-columns:1.1fr .55fr 1fr;grid-template-rows:minmax(0,1fr) 30px;gap:8px}.heroSteer{grid-column:1/-1;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:5px 8px;display:grid;grid-template-columns:auto 1fr auto;gap:8px;align-items:center}.hero .tile{display:grid;grid-template-rows:auto minmax(0,1fr) auto}.speed{font-size:60px;line-height:.9;font-weight:760;letter-spacing:0}.gear{align-self:center;justify-self:center;font-size:112px;line-height:.82;font-weight:850;text-align:center}.unit{font-size:14px;color:var(--muted);margin-left:4px}.rpmNum{font-size:54px;line-height:.95;font-weight:760;letter-spacing:0}.bar,.hbar{height:7px;background:#252b34;border-radius:2px;overflow:hidden;margin-top:5px}.fill,.hfill{height:100%;width:0;background:var(--blue);transition:width 80ms linear}.rpmfill{background:linear-gradient(90deg,var(--green) 0 60%,var(--amber) 72%,var(--red) 88%)}.redline .rpmfill,.redline .rpmWide{background:var(--red);animation:pulse .22s steps(2,end) infinite}
	@keyframes pulse{50%{filter:brightness(.35)}}.wideBar{height:9px;background:#252b34;border-radius:2px;overflow:hidden;margin-top:5px}.wideFill{height:100%;width:0;transition:width 70ms linear}.speedWide{background:linear-gradient(90deg,#2f80ff 0%,var(--cyan) 45%,var(--green) 72%,var(--amber) 90%,var(--red) 100%)}.rpmWide{background:var(--rpmc,var(--green))}.readoutGauge{position:relative;display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:3px;isolation:isolate}.readoutGauge .wideBar{position:absolute;inset:0;height:auto;margin:0;border-radius:6px;background:#111722;z-index:-1}.readoutGauge .wideFill{opacity:.36}.readoutValue{align-self:center;justify-self:end;font-size:80px;line-height:.88;font-weight:850;letter-spacing:0;color:#f8fbff;text-shadow:0 1px 9px #000;white-space:nowrap}.readoutValue .readoutUnit{font-size:28px;color:#dbe6f4;margin-left:6px}.speedDisplay{color:#eaf7ff}.rpmDisplay{color:#f8fbff}
		.compactGauges{display:none}.gaugeTop,.hmetricTop{display:grid;grid-template-columns:1fr auto;gap:6px;align-items:baseline}.gaugeVal,.hmetricVal{font-size:12px;font-weight:700}.inputs{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.inputMetric{position:relative;min-height:68px;background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:6px;overflow:hidden}.inputMetric .lbl,.inputMetric .num{position:relative;z-index:2}.inputMetric .num{font-size:18px;font-weight:720}.vbarFill{position:absolute;left:0;right:0;bottom:0;height:0;width:100%;background:var(--green);opacity:.34;transition:height 80ms linear;z-index:1}.brake .vbarFill{background:var(--red)}.slip .vbarFill{background:linear-gradient(0deg,var(--cyan),var(--mag))}
	.metricBars{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.hmetric{position:relative;min-height:120px;background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:6px;overflow:hidden}.hmetricTop{position:relative;z-index:2;display:block}.hmetricVal{font-size:16px;margin-top:4px}.hmetric .hbar{position:absolute;inset:0;height:auto;margin:0;border-radius:5px;background:transparent;z-index:1}.hmetric .hfill{position:absolute;left:0;right:0;bottom:0;width:100%;height:0;opacity:.34;transition:height 80ms linear}.powerfill{background:linear-gradient(0deg,var(--blue),var(--cyan))}.torquefill{background:linear-gradient(0deg,var(--green),var(--amber))}.boostfill{background:linear-gradient(0deg,var(--mag),var(--red))}
	.steerTrack{position:relative;height:9px;background:#252b34;border-radius:2px;overflow:hidden;margin-top:5px}.steerTrack:after{content:"";position:absolute;top:0;bottom:0;left:50%;width:1px;background:#f5f7fb66}.steerFill{position:absolute;top:0;bottom:0;width:0;transition:width 70ms linear}.steerLeft{right:50%;background:linear-gradient(90deg,#6f42c1,var(--mag))}.steerRight{left:50%;background:linear-gradient(90deg,var(--cyan),var(--blue))}
		.stack{display:grid;gap:8px;min-height:0}.inputsStack{grid-area:inputs}.timingStack{grid-area:timing}.stateStack{grid-area:state}.chassisPanel{grid-area:chassis}.suspensionPanel{grid-area:susp}.rawPanel{grid-area:raw}.timing,.raw,.events{display:grid;gap:5px}.raw{grid-template-rows:auto repeat(7,24px);gap:4px}.row{position:relative;height:24px;display:grid;grid-template-columns:minmax(0,1fr) minmax(54px,auto);gap:6px;align-items:center;border:1px solid #202630;border-radius:4px;padding:0 8px 0 12px;overflow:hidden;background:var(--panel2);line-height:1}.row:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,var(--c,var(--blue)),color-mix(in srgb,var(--c,var(--blue)) 30%,transparent));opacity:calc(.06 + var(--p,0) * .28);z-index:0}.row:before{content:"";position:absolute;left:4px;top:5px;bottom:5px;width:3px;border-radius:2px;background:var(--c,var(--blue));opacity:calc(.35 + var(--p,0) * .65);z-index:1}.row span{position:relative;z-index:2}.row span:first-child{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.row span:last-child{font-size:12px;font-weight:650;white-space:nowrap;text-align:right;overflow:hidden;text-overflow:ellipsis}.matrix{display:grid;grid-template-columns:repeat(4,1fr);gap:5px}.cell{position:relative;background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:5px 5px 9px;text-align:center;overflow:hidden}.cell:before{content:"";position:absolute;inset:0;background:var(--c,var(--blue));opacity:calc(.05 + var(--p,0) * .24);z-index:0}.cell:after{content:"";position:absolute;left:4px;bottom:3px;width:calc((100% - 8px) * var(--p,0));height:3px;border-radius:2px;background:var(--c,var(--blue));box-shadow:0 0 10px color-mix(in srgb,var(--c,var(--blue)) 55%,transparent)}.cell .lbl,.cell .v{position:relative;z-index:1}.cell .v{font-size:15px;font-weight:650;margin-top:2px;white-space:nowrap}.eventList{max-height:122px;overflow:hidden;color:var(--muted);font-size:10px}.eventList div{border-bottom:1px solid #202630;padding:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.rawJson{height:calc(100% - 26px);overflow:hidden;margin:0;background:#080b10;border:1px solid var(--line);border-radius:5px;padding:6px;color:#cbd5e1;font:9px/1.25 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap}
	.carGrid{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:5px}.wheel{position:relative;background:var(--panel2);border:1px solid var(--line);border-radius:5px;padding:5px;overflow:hidden}.wheel:before{content:"";position:absolute;inset:0;background:var(--tc,var(--green));opacity:calc(.05 + var(--tp,0) * .22);z-index:0}.wheel>*{position:relative;z-index:1}.wheelHead{display:grid;grid-template-columns:1fr auto;gap:5px;align-items:baseline;margin-bottom:4px}.wheelName{font-size:10px;font-weight:700}.wheelVals{color:var(--muted);font-size:10px}.wheelStat{display:grid;grid-template-columns:28px 1fr 34px;gap:5px;align-items:center;margin-top:3px}.wheelStat .lbl{letter-spacing:.04em}.tempfill{background:var(--green)}.slipfill{background:linear-gradient(90deg,var(--cyan),var(--mag),var(--red))}
		@media(max-width:1100px){body{overflow:auto}main{height:auto}.dashboard{grid-template-columns:1fr;grid-template-rows:auto;grid-template-areas:"hero" "gauges" "inputs" "timing" "state" "chassis" "susp" "raw"}.speed,.gear{font-size:54px}}
	</style>
</head>
<body><main>
	<div class="rail"><div class="dot" id="dot"></div><div class="title">Forza Telemetry</div><div class="pill">dense v2</div><div class="pill" id="status">waiting</div><div class="pill" id="effect">idle</div><div class="pill" id="event">idle</div><div class="pill carPill" id="currentCarPill">car unknown</div><div class="lightControls">
	  <label>Game <select id="gameName"><option value="fh6">FH6</option><option value="fh5">FH5</option><option value="fh4">FH4</option><option value="fm8">FM8</option><option value="generic">FH</option></select></label>
	  <label>Top <select id="wledTopMode"><option>tach</option><option>speed</option><option>brake</option><option>slip</option><option>off</option></select></label>
	  <label>Bottom <select id="wledBottomMode"><option>tach</option><option>speed</option><option>brake</option><option>slip</option><option>off</option></select></label>
	  <label>Stop <input id="wledStopStart" type="number" min="86" max="140">-<input id="wledStopEnd" type="number" min="86" max="140"></label>
	  <label>Sides <input id="wledSides" type="number" min="1" max="20"></label>
	  <label>Rewind <input id="rewindHold" type="number" min="0" max="15">s</label>
	</div><div class="spacer"></div><div class="muted" id="source"></div></div>
	<div class="dashboard">
	  <section class="hero">
	    <div class="tile readoutGauge"><div class="lbl">Speed</div><div class="readoutValue speedDisplay"><span id="speed">000</span><span class="readoutUnit">MPH</span></div><div class="sub">pkt <span id="hz">0</span> Hz | <span id="coords">0, 0, 0</span></div><div class="wideBar"><div class="wideFill speedWide" id="speedWide"></div></div></div>
	    <div class="tile"><div class="lbl">Gear</div><div class="gear" id="gear">0</div><div class="sub"><span id="gearCar">Unknown Car</span></div><div class="sub">raw <span id="gearraw">0</span> | rev <span id="reverse">false</span></div></div>
	    <div class="tile readoutGauge" id="rpmTile"><div class="lbl">RPM</div><div class="readoutValue rpmDisplay"><span id="rpm">0</span><span class="readoutUnit">RPM</span></div><div class="sub"><span id="rpmpct">0%</span> | max <span id="maxrpm">0</span> | idle <span id="idlerpm">0</span></div><div class="wideBar"><div class="wideFill rpmWide" id="rpmWide"></div></div></div>
	    <div class="heroSteer"><div class="lbl">Steering</div><div class="steerTrack"><div class="steerFill steerLeft" id="steerLeft"></div><div class="steerFill steerRight" id="steerRight"></div></div><div class="gaugeVal"><span id="steerWide">0</span>%</div></div>
	  </section>
		  <div class="stack inputsStack">
	    <div class="tile">
	      <div class="inputs">
	        <div class="inputMetric"><div class="lbl">Throttle</div><div class="num"><span id="throttle">0</span>%</div><div class="vbarFill" id="throttlebar"></div></div>
	        <div class="inputMetric brake"><div class="lbl">Brake</div><div class="num"><span id="brake">0</span>%</div><div class="vbarFill" id="brakebar"></div></div>
	        <div class="inputMetric slip"><div class="lbl">Slip</div><div class="num"><span id="slip">0</span>%</div><div class="vbarFill" id="slipbar"></div></div>
	      </div>
	    </div>
	    <div class="tile">
	      <div class="lbl">Powertrain</div>
	      <div class="metricBars">
        <div class="hmetric"><div class="hmetricTop"><div class="lbl">Power</div><div class="hmetricVal"><span id="power">0</span> hp</div></div><div class="hbar"><div class="hfill powerfill" id="powerbar"></div></div></div>
        <div class="hmetric"><div class="hmetricTop"><div class="lbl">Torque</div><div class="hmetricVal"><span id="torque">0</span> lb-ft</div></div><div class="hbar"><div class="hfill torquefill" id="torquebar"></div></div></div>
        <div class="hmetric"><div class="hmetricTop"><div class="lbl">Boost</div><div class="hmetricVal"><span id="boost">0</span> psi</div></div><div class="hbar"><div class="hfill boostfill" id="boostbar"></div></div></div>
      </div>
    </div>
	  </div>
		  <div class="stack timingStack">
    <div class="tile timing">
      <div class="lbl">Timing</div>
      <div class="matrix">
        <div class="cell"><div class="lbl">Current</div><div class="v" id="laptime">0.00</div></div>
        <div class="cell"><div class="lbl">Last</div><div class="v" id="lastlap">0.00</div></div>
        <div class="cell"><div class="lbl">Best</div><div class="v" id="bestlap">0.00</div></div>
        <div class="cell"><div class="lbl">Lap</div><div class="v" id="lap">0</div></div>
        <div class="cell"><div class="lbl">Position</div><div class="v" id="pos">0</div></div>
        <div class="cell"><div class="lbl">Fuel</div><div class="v" id="fuel">0</div></div>
        <div class="cell"><div class="lbl">Class</div><div class="v" id="carclass">0</div></div>
        <div class="cell"><div class="lbl">PI</div><div class="v" id="pi">0</div></div>
      </div>
    </div>
    <div class="tile">
      <div class="lbl">Tires</div>
      <div class="carGrid">
        <div class="wheel"><div class="wheelHead"><div class="wheelName">Front Left</div><div class="wheelVals"><span id="tempfl">0</span> F | <span id="slipfl">0</span></div></div><div class="wheelStat"><div class="lbl">Temp</div><div class="hbar"><div class="hfill tempfill" id="tempflbar"></div></div><div id="tempflpct">0%</div></div><div class="wheelStat"><div class="lbl">Slip</div><div class="hbar"><div class="hfill slipfill" id="slipflbar"></div></div><div id="slipflpct">0%</div></div></div>
        <div class="wheel"><div class="wheelHead"><div class="wheelName">Front Right</div><div class="wheelVals"><span id="tempfr">0</span> F | <span id="slipfr">0</span></div></div><div class="wheelStat"><div class="lbl">Temp</div><div class="hbar"><div class="hfill tempfill" id="tempfrbar"></div></div><div id="tempfrpct">0%</div></div><div class="wheelStat"><div class="lbl">Slip</div><div class="hbar"><div class="hfill slipfill" id="slipfrbar"></div></div><div id="slipfrpct">0%</div></div></div>
        <div class="wheel"><div class="wheelHead"><div class="wheelName">Rear Left</div><div class="wheelVals"><span id="temprl">0</span> F | <span id="sliprl">0</span></div></div><div class="wheelStat"><div class="lbl">Temp</div><div class="hbar"><div class="hfill tempfill" id="temprlbar"></div></div><div id="temprlpct">0%</div></div><div class="wheelStat"><div class="lbl">Slip</div><div class="hbar"><div class="hfill slipfill" id="sliprlbar"></div></div><div id="sliprlpct">0%</div></div></div>
        <div class="wheel"><div class="wheelHead"><div class="wheelName">Rear Right</div><div class="wheelVals"><span id="temprr">0</span> F | <span id="sliprr">0</span></div></div><div class="wheelStat"><div class="lbl">Temp</div><div class="hbar"><div class="hfill tempfill" id="temprrbar"></div></div><div id="temprrpct">0%</div></div><div class="wheelStat"><div class="lbl">Slip</div><div class="hbar"><div class="hfill slipfill" id="sliprrbar"></div></div><div id="sliprrpct">0%</div></div></div>
      </div>
    </div>
	  </div>
		  <div class="stack stateStack">
    <div class="tile raw">
      <div class="lbl">State</div>
      <div class="row"><span>Steer</span><span id="steer">0%</span></div>
      <div class="row"><span>Lat G</span><span id="glat">0.00</span></div>
      <div class="row"><span>Lon G</span><span id="glon">0.00</span></div>
      <div class="row"><span>Wheelspin</span><span id="wheelspin">false</span></div>
      <div class="row"><span>Rumble</span><span id="rumble">false</span></div>
      <div class="row"><span>Puddle</span><span id="wet">false</span></div>
      <div class="row"><span>Current Car</span><span id="car">Unknown</span></div>
    </div>
    <div class="tile events"><div class="lbl">Events</div><div class="eventList" id="events"></div></div>
	  </div>
		<section class="wideGauge chassisPanel">
  <div class="gaugeTop"><div class="lbl">Chassis & Motion</div><div class="gaugeVal">G force | attitude | velocity</div></div>
  <div class="matrix">
    <div class="cell"><div class="lbl">Accel X</div><div class="v" id="accx">0</div></div>
    <div class="cell"><div class="lbl">Accel Y</div><div class="v" id="accy">0</div></div>
    <div class="cell"><div class="lbl">Accel Z</div><div class="v" id="accz">0</div></div>
    <div class="cell"><div class="lbl">Lat/Lon G</div><div class="v"><span id="glat2">0</span> / <span id="glon2">0</span></div></div>
    <div class="cell"><div class="lbl">Yaw</div><div class="v" id="yaw">0</div></div>
    <div class="cell"><div class="lbl">Pitch</div><div class="v" id="pitch">0</div></div>
    <div class="cell"><div class="lbl">Roll</div><div class="v" id="roll">0</div></div>
    <div class="cell"><div class="lbl">Angular Y</div><div class="v" id="angy">0</div></div>
    <div class="cell"><div class="lbl">Velocity X</div><div class="v" id="velx">0</div></div>
    <div class="cell"><div class="lbl">Velocity Y</div><div class="v" id="vely">0</div></div>
    <div class="cell"><div class="lbl">Velocity Z</div><div class="v" id="velz">0</div></div>
    <div class="cell"><div class="lbl">Distance</div><div class="v" id="distance">0</div></div>
  </div>
	</section>
		<section class="wideGauge suspensionPanel">
  <div class="gaugeTop"><div class="lbl">Suspension, Wheels & Surface</div><div class="gaugeVal">FL | FR | RL | RR</div></div>
  <div class="matrix">
    <div class="cell"><div class="lbl">Susp Norm</div><div class="v" id="suspnormfl">0</div></div>
    <div class="cell"><div class="lbl">Susp Norm</div><div class="v" id="suspnormfr">0</div></div>
    <div class="cell"><div class="lbl">Susp Norm</div><div class="v" id="suspnormrl">0</div></div>
    <div class="cell"><div class="lbl">Susp Norm</div><div class="v" id="suspnormrr">0</div></div>
    <div class="cell"><div class="lbl">Susp m</div><div class="v" id="suspmfl">0</div></div>
    <div class="cell"><div class="lbl">Susp m</div><div class="v" id="suspmfr">0</div></div>
    <div class="cell"><div class="lbl">Susp m</div><div class="v" id="suspmrl">0</div></div>
    <div class="cell"><div class="lbl">Susp m</div><div class="v" id="suspmrr">0</div></div>
    <div class="cell"><div class="lbl">Wheel Speed</div><div class="v" id="wspfl">0</div></div>
    <div class="cell"><div class="lbl">Wheel Speed</div><div class="v" id="wspfr">0</div></div>
    <div class="cell"><div class="lbl">Wheel Speed</div><div class="v" id="wsprl">0</div></div>
    <div class="cell"><div class="lbl">Wheel Speed</div><div class="v" id="wsprr">0</div></div>
    <div class="cell"><div class="lbl">Rumble/Puddle</div><div class="v" id="surfFL">0/0</div></div>
    <div class="cell"><div class="lbl">Rumble/Puddle</div><div class="v" id="surfFR">0/0</div></div>
    <div class="cell"><div class="lbl">Rumble/Puddle</div><div class="v" id="surfRL">0/0</div></div>
    <div class="cell"><div class="lbl">Rumble/Puddle</div><div class="v" id="surfRR">0/0</div></div>
  </div>
	</section>
		<section class="wideGauge rawPanel">
  <div class="gaugeTop"><div class="lbl">Full Parsed Telemetry</div><div class="gaugeVal"><span id="fieldCount">0</span> fields</div></div>
  <pre class="rawJson" id="rawJson">{}</pre>
	</section>
	</div>
	</main>
<script>
const $=id=>document.getElementById(id);
function set(id,value){const el=$(id); if(el) el.textContent=value}
	function pct(id,value){const el=$(id); if(el) el.style.width=Math.max(0,Math.min(100,value))+"%"}
	function hpct(id,value){const el=$(id); if(el) el.style.height=Math.max(0,Math.min(100,value))+"%"}
	function steerbar(value){const v=Math.max(-100,Math.min(100,Number(value||0)));pct("steerLeft",v<0?Math.abs(v):0);pct("steerRight",v>0?v:0);set("steerWide",Math.round(v))}
	function n(value,d=0){return Number(value||0).toFixed(d)}
	function clamp01(value){return Math.max(0,Math.min(1,Number(value||0)))}
	function hue(p){const v=clamp01(p);return `hsl(${Math.round(130-(130*v))} 90% 58%)`}
	function gauge(id,p,c){const el=$(id)?.closest(".cell,.row");if(!el)return;const v=clamp01(p);el.style.setProperty("--p",v);el.style.setProperty("--c",c||hue(v))}
	function rpmColor(p){const v=Number(p||0);if(v>=88)return"#ff385c";if(v>=72)return"#ff6a00";if(v>=60)return"#ffb000";return"#33d17a"}
	function signedGauge(id,value,max){const p=Math.min(1,Math.abs(Number(value||0))/max);gauge(id,p,value<0?"#ff4fd8":"#35d7ff")}
	function boolGauge(id,on){gauge(id,on?1:.04,on?"#33d17a":"#697381")}
	function tempColor(f){if(f<205)return"#33d17a";if(f<240)return"#ffb000";return"#ff385c"}
function wheel(pos,temp,slip){const tp=Math.max(0,Math.min(100,(temp-70)/190*100));const sp=Math.max(0,Math.min(100,Math.abs(slip)*100));pct("temp"+pos+"bar",tp);pct("slip"+pos+"bar",sp);set("temp"+pos+"pct",`${Math.round(temp)}F`);set("slip"+pos+"pct",`${Math.round(sp)}%`);const c=tempColor(temp);const tf=$("temp"+pos+"bar");if(tf){tf.style.background=c;const box=tf.closest(".wheel");if(box){box.style.setProperty("--tc",c);box.style.setProperty("--tp",tp/100)}}}
let shownGear="0",pendingGear=null,pendingGearAt=0,observedSpeedMax=120;
function gearText(t){const raw=Number(t.gear_raw ?? t.gear ?? 0);const label=String(t.gear_display||raw||0);if(label==="R"){shownGear="R";pendingGear=null;return label}const shown=Number(shownGear);if(Number.isFinite(raw)&&Number.isFinite(shown)&&Math.abs(raw-shown)>2){const now=performance.now();if(pendingGear!==label){pendingGear=label;pendingGearAt=now;return shownGear}if(now-pendingGearAt<250)return shownGear}shownGear=label;pendingGear=null;return label}
let controlsReady=false;
function applyControls(c){
  if(!c||controlsReady)return;
  const g=String(c.game_name||"").toLowerCase(); $("gameName").value=g.includes("horizon 6")?"fh6":g.includes("horizon 5")?"fh5":g.includes("horizon 4")?"fh4":g.includes("motorsport")?"fm8":"generic";
  $("wledTopMode").value=c.wled_top_mode||"tach";
  $("wledBottomMode").value=c.wled_bottom_mode||"tach";
  $("wledStopStart").value=c.wled_stop_bar_start_led ?? 104;
  $("wledStopEnd").value=c.wled_stop_bar_end_led ?? 119;
  $("wledSides").value=c.wled_reverse_brake_side_leds ?? 10;
  $("rewindHold").value=c.rewind_hold_seconds ?? 6;
  controlsReady=true;
}
async function sendControl(key,value){
  await fetch("/api/control",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({[key]:value})});
}
function bindControl(id,key){
  const el=$(id);
  if(!el)return;
  el.addEventListener("change",()=>sendControl(key,el.value).catch(()=>{}));
}
bindControl("wledTopMode","wled_top_mode");
bindControl("gameName","game_name");
bindControl("wledBottomMode","wled_bottom_mode");
bindControl("wledStopStart","wled_stop_bar_start_led");
bindControl("wledStopEnd","wled_stop_bar_end_led");
bindControl("wledSides","wled_reverse_brake_side_leds");
bindControl("rewindHold","rewind_hold_seconds");
async function tick(){
  const res=await fetch("/api/state",{cache:"no-store"}); const data=await res.json(); const t=data.latest||{};
  applyControls(data.controls);
  $("dot").className="dot"+(t.redline?" red":(t.playing?" on":""));
  $("rpmTile").classList.toggle("redline",!!t.redline);
  set("status",t.playing?"playing":"waiting"); set("source",t.source_ip?`${t.source_ip}:${t.source_port} | ${t.packet_length} B`:"");
  set("effect",t.effect||"idle"); set("event",t.event||"idle"); set("hz",t.packet_hz||0);
  const carLabel=t.current_car||t.car_name||(t.car_ordinal?`Unknown #${t.car_ordinal}`:"Unknown Car");set("currentCarPill",`car ${carLabel}`);set("gearCar",carLabel);
  set("speed",String(Math.round(t.speed_mph||0)).padStart(3,"0")); set("gear",gearText(t)); set("gearraw",t.gear_raw ?? t.gear ?? 0); set("reverse",String(!!t.reverse));
  const rpmVisual = t.rpm_bar_pct ?? t.rpm_pct ?? 0;
  set("rpm",Math.round(t.rpm||0)); set("rpmpct",`${n(rpmVisual,1)}%`); set("maxrpm",Math.round(t.engine_max_rpm||0)); set("idlerpm",Math.round(t.engine_idle_rpm||0)); pct("rpmbar",rpmVisual); $("rpmTile").style.setProperty("--rpmc",rpmColor(rpmVisual)); $("rpmTile").classList.toggle("redline",!!t.redline);
  observedSpeedMax=Math.max(observedSpeedMax,Math.ceil((t.speed_mph||0)/20)*20); pct("speedWide",((t.speed_mph||0)/observedSpeedMax)*100);
  pct("rpmWide",rpmVisual);
	  set("throttle",Math.round(t.throttle||0)); set("brake",Math.round(t.brake||0)); set("slip",Math.round(t.slip||0)); hpct("throttlebar",t.throttle||0); hpct("brakebar",t.brake||0); hpct("slipbar",(t.slip||0)/3);
	  set("power",Math.round(t.power_hp||0)); set("torque",Math.round(t.torque_lbft||0)); set("boost",n(t.boost_psi,1)); hpct("powerbar",(t.power_hp||0)/15); hpct("torquebar",(t.torque_lbft||0)/12); hpct("boostbar",(t.boost_psi||0)*2);
	  set("laptime",n(t.current_lap_time_s,2)); set("lastlap",n(t.last_lap_time_s,2)); set("bestlap",n(t.best_lap_time_s,2)); set("lap",t.lap_number||0); set("pos",t.race_position||0); set("fuel",n(t.fuel,0)); set("carclass",t.car_class||0); set("pi",t.car_performance_index||0);
	  gauge("laptime",((t.current_lap_time_s||0)%180)/180,"#4dabf7"); gauge("lastlap",((t.last_lap_time_s||0)%180)/180,"#35d7ff"); gauge("bestlap",((t.best_lap_time_s||0)%180)/180,"#33d17a"); gauge("lap",Math.min((t.lap_number||0)/10,1),"#ffb000");
	  gauge("pos",t.race_position?Math.max(0,1-(t.race_position-1)/12):0,"#ffb000"); gauge("fuel",(t.fuel||0)/100,hue(1-(t.fuel||0)/100)); gauge("carclass",(t.car_class||0)/7,"#ff4fd8"); gauge("pi",(t.car_performance_index||0)/1000,"#35d7ff");
	  set("slipfl",n(t.tire_slip_ratio_fl,2)); set("slipfr",n(t.tire_slip_ratio_fr,2)); set("sliprl",n(t.tire_slip_ratio_rl,2)); set("sliprr",n(t.tire_slip_ratio_rr,2));
  set("tempfl",n(t.tire_temp_fl,0)); set("tempfr",n(t.tire_temp_fr,0)); set("temprl",n(t.tire_temp_rl,0)); set("temprr",n(t.tire_temp_rr,0));
  wheel("fl",t.tire_temp_fl||0,t.tire_slip_ratio_fl||0); wheel("fr",t.tire_temp_fr||0,t.tire_slip_ratio_fr||0); wheel("rl",t.tire_temp_rl||0,t.tire_slip_ratio_rl||0); wheel("rr",t.tire_temp_rr||0,t.tire_slip_ratio_rr||0);
	  set("steer",`${Math.round(t.steer||0)}%`); steerbar(t.steer||0); set("glat",n((t.acceleration_x||0)/9.81,2)); set("glon",n((t.acceleration_z||0)/9.81,2)); set("wheelspin",String(!!t.wheelspin)); set("rumble",String(!!t.on_rumble)); set("wet",String(!!t.wet)); set("car",carLabel);
	  signedGauge("steer",t.steer||0,100); signedGauge("glat",(t.acceleration_x||0)/9.81,2.5); signedGauge("glon",(t.acceleration_z||0)/9.81,2.5); boolGauge("wheelspin",!!t.wheelspin); boolGauge("rumble",!!t.on_rumble); boolGauge("wet",!!t.wet); gauge("car",t.car_ordinal?1:.04,"#697381");
	  set("coords",`${n(t.position_x,1)}, ${n(t.position_y,1)}, ${n(t.position_z,1)}`);
	  set("accx",n(t.acceleration_x,2)); set("accy",n(t.acceleration_y,2)); set("accz",n(t.acceleration_z,2)); set("glat2",n((t.acceleration_x||0)/9.81,2)); set("glon2",n((t.acceleration_z||0)/9.81,2));
	  set("yaw",n(t.yaw,2)); set("pitch",n(t.pitch,2)); set("roll",n(t.roll,2)); set("angy",n(t.angular_velocity_y,2)); set("velx",n(t.velocity_x,1)); set("vely",n(t.velocity_y,1)); set("velz",n(t.velocity_z,1)); set("distance",n(t.distance_traveled_m,0));
	  signedGauge("accx",t.acceleration_x||0,20); signedGauge("accy",t.acceleration_y||0,20); signedGauge("accz",t.acceleration_z||0,20); signedGauge("glat2",(t.acceleration_x||0)/9.81,2.5); signedGauge("glon2",(t.acceleration_z||0)/9.81,2.5);
	  signedGauge("yaw",t.yaw||0,3.2); signedGauge("pitch",t.pitch||0,1); signedGauge("roll",t.roll||0,1); signedGauge("angy",t.angular_velocity_y||0,4); signedGauge("velx",t.velocity_x||0,90); signedGauge("vely",t.velocity_y||0,20); signedGauge("velz",t.velocity_z||0,90); gauge("distance",((t.distance_traveled_m||0)%5000)/5000,"#ffb000");
	  set("suspnormfl",n(t.normalized_suspension_travel_fl,2)); set("suspnormfr",n(t.normalized_suspension_travel_fr,2)); set("suspnormrl",n(t.normalized_suspension_travel_rl,2)); set("suspnormrr",n(t.normalized_suspension_travel_rr,2));
	  set("suspmfl",n(t.suspension_travel_meters_fl,2)); set("suspmfr",n(t.suspension_travel_meters_fr,2)); set("suspmrl",n(t.suspension_travel_meters_rl,2)); set("suspmrr",n(t.suspension_travel_meters_rr,2));
	  set("wspfl",n(t.wheel_rotation_speed_fl,1)); set("wspfr",n(t.wheel_rotation_speed_fr,1)); set("wsprl",n(t.wheel_rotation_speed_rl,1)); set("wsprr",n(t.wheel_rotation_speed_rr,1));
	  set("surfFL",`${t.wheel_on_rumble_strip_fl||0}/${t.wheel_in_puddle_fl||0}`); set("surfFR",`${t.wheel_on_rumble_strip_fr||0}/${t.wheel_in_puddle_fr||0}`); set("surfRL",`${t.wheel_on_rumble_strip_rl||0}/${t.wheel_in_puddle_rl||0}`); set("surfRR",`${t.wheel_on_rumble_strip_rr||0}/${t.wheel_in_puddle_rr||0}`);
	  gauge("suspnormfl",t.normalized_suspension_travel_fl||0,"#4dabf7"); gauge("suspnormfr",t.normalized_suspension_travel_fr||0,"#4dabf7"); gauge("suspnormrl",t.normalized_suspension_travel_rl||0,"#35d7ff"); gauge("suspnormrr",t.normalized_suspension_travel_rr||0,"#35d7ff");
	  gauge("suspmfl",Math.abs(t.suspension_travel_meters_fl||0)/.35,"#33d17a"); gauge("suspmfr",Math.abs(t.suspension_travel_meters_fr||0)/.35,"#33d17a"); gauge("suspmrl",Math.abs(t.suspension_travel_meters_rl||0)/.35,"#ffb000"); gauge("suspmrr",Math.abs(t.suspension_travel_meters_rr||0)/.35,"#ffb000");
	  gauge("wspfl",Math.abs(t.wheel_rotation_speed_fl||0)/220,"#ff4fd8"); gauge("wspfr",Math.abs(t.wheel_rotation_speed_fr||0)/220,"#ff4fd8"); gauge("wsprl",Math.abs(t.wheel_rotation_speed_rl||0)/220,"#ff385c"); gauge("wsprr",Math.abs(t.wheel_rotation_speed_rr||0)/220,"#ff385c");
	  boolGauge("surfFL",(t.wheel_on_rumble_strip_fl||t.wheel_in_puddle_fl)); boolGauge("surfFR",(t.wheel_on_rumble_strip_fr||t.wheel_in_puddle_fr)); boolGauge("surfRL",(t.wheel_on_rumble_strip_rl||t.wheel_in_puddle_rl)); boolGauge("surfRR",(t.wheel_on_rumble_strip_rr||t.wheel_in_puddle_rr));
  $("events").innerHTML=(data.events||[]).slice(0,24).map(e=>`<div>${e.at} - ${e.effect||e.event}</div>`).join("");
  set("fieldCount",Object.keys(t).length); $("rawJson").textContent=JSON.stringify(t,null,2);
}
setInterval(tick,100); tick().catch(()=>{});
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path.startswith("/api/state"):
            with state_lock:
                body = json.dumps({"latest": state["latest"], "events": list(state["events"]), "packets": state["packets"], "controls": current_lighting_controls()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.path.startswith("/api/control"):
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            changed = {}
            for key, value in data.items():
                if apply_lighting_control(key, value, publish=True):
                    changed[key] = CONFIG.get(key)
            body = json.dumps({"ok": True, "changed": changed, "controls": current_lighting_controls()}).encode("utf-8")
            self.send_response(200)
        except Exception as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def web_loop():
    server = ThreadingHTTPServer(("0.0.0.0", int(CONFIG["web_port"])), Handler)
    print(f"Dashboard listening on 0.0.0.0:{CONFIG['web_port']}", flush=True)
    server.serve_forever()


def web_loop_supervisor():
    while True:
        try:
            web_loop()
        except Exception as exc:
            print(f"Dashboard server restarting: {exc}", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    threading.Thread(target=web_loop_supervisor, daemon=True).start()
    while True:
        try:
            telemetry_loop()
        except Exception as exc:
            print(f"Bridge error: {exc}", flush=True)
            time.sleep(5)
            mqtt.close()
