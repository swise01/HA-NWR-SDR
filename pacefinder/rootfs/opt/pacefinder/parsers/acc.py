import struct
from typing import Optional

# ACC UDP plugin physics packet
# Full struct reference: https://www.assettocorsa.net/forum/index.php?threads/acc-udp-remote-telemetry-port.59734/

ACC_PHYSICS_SIZE = 328  # v1.7+ physics packet size

_ACC_SESSION_TYPES = {
    0: "unknown", 1: "practice", 2: "qualifying", 3: "qualifying",
    4: "race", 5: "time_trial", 6: "time_trial",
    7: "unknown", 8: "unknown", 9: "practice", 10: "qualifying",
}


def parse_acc(data: bytes) -> Optional[dict]:
    """Parse ACC physics (packetId=0) or graphics (packetId=1) packet."""
    if len(data) < 4:
        return None
    try:
        packet_id = struct.unpack_from("<i", data, 0)[0]
        if packet_id == 1:
            # Graphics packet: session type at offset 8, race position at offset 136
            if len(data) < 140:
                return None
            session_int = struct.unpack_from("<i", data, 8)[0]
            position    = struct.unpack_from("<i", data, 136)[0]
            result: dict = {
                "_packet_type": "graphics",
                "session_type": _ACC_SESSION_TYPES.get(session_int, "unknown"),
                "race_position": position if position > 0 else None,
            }
            # rainIntensity enum at offset 1552 (added in ACC 1.8 shared memory)
            if len(data) >= 1556:
                rain_int = struct.unpack_from("<i", data, 1552)[0]
                _ACC_RAIN = {0: "Clear", 1: "LightCloud", 2: "LightRain",
                             3: "Rain", 4: "HeavyRain", 5: "Thunderstorm"}
                w = _ACC_RAIN.get(rain_int)
                if w is not None:
                    result["weather_condition"] = w
            return result
        if packet_id != 0:
            return None  # Static or unknown packet — ignore
    except struct.error:
        return None
    try:
        o = 0
        def ri(fmt):
            nonlocal o
            val = struct.unpack_from(fmt, data, o)
            o += struct.calcsize(fmt)
            return val[0] if len(val) == 1 else val

        packet_id = ri("<i")
        gas       = ri("<f")
        brake     = ri("<f")
        fuel      = ri("<f")
        gear      = ri("<i")
        rpm       = ri("<i")
        steer     = ri("<f")
        speed_kmh = ri("<f")
        vel_x, vel_y, vel_z = ri("<fff")
        acc_x, acc_y, acc_z = ri("<fff")  # G-forces (m/s²)
        slip_fl, slip_fr, slip_rl, slip_rr = ri("<ffff")

        # wheelSlip done — continue with more fields if packet is large enough
        result = {
            "packet_id":    packet_id,
            "throttle_pct": round(gas * 100, 1),
            "brake_pct":    round(brake * 100, 1),
            "fuel":         round(fuel, 2),
            "gear":         gear,
            "rpm":          rpm,
            "steer":        round(steer, 3),
            "speed_mph":    round(speed_kmh * 0.621371, 1),
            "velocity_x":   round(vel_x, 3),
            "velocity_y":   round(vel_y, 3),
            "velocity_z":   round(vel_z, 3),
            "g_lat":        round(acc_x / 9.81, 3),
            "g_lon":        round(acc_z / 9.81, 3),
            "g_vert":       round(acc_y / 9.81, 3),
            "slip_ratio_fl": round(abs(slip_fl), 4),
            "slip_ratio_fr": round(abs(slip_fr), 4),
            "slip_ratio_rl": round(abs(slip_rl), 4),
            "slip_ratio_rr": round(abs(slip_rr), 4),
        }

        # Extended fields: wheelsPressure(4f), brakeTemp(4f), tyreCoreTemp(4f)
        if len(data) >= o + 48:
            slip_angle_fl, slip_angle_fr, slip_angle_rl, slip_angle_rr = ri("<ffff")
            slip_speed_fl, slip_speed_fr, slip_speed_rl, slip_speed_rr = ri("<ffff")
            slip_speed2_fl, slip_speed2_fr, slip_speed2_rl, slip_speed2_rr = ri("<ffff")

        if len(data) >= o + 32:
            p_fl, p_fr, p_rl, p_rr = ri("<ffff")
            b_fl, b_fr, b_rl, b_rr = ri("<ffff")
            result["tyre_pressure_fl"] = round(p_fl, 2)
            result["tyre_pressure_fr"] = round(p_fr, 2)
            result["tyre_pressure_rl"] = round(p_rl, 2)
            result["tyre_pressure_rr"] = round(p_rr, 2)
            result["brake_temp_fl"]    = round(b_fl, 1)
            result["brake_temp_fr"]    = round(b_fr, 1)
            result["brake_temp_rl"]    = round(b_rl, 1)
            result["brake_temp_rr"]    = round(b_rr, 1)

        if len(data) >= o + 16:
            t_fl, t_fr, t_rl, t_rr = ri("<ffff")
            result["tyre_core_temp_fl"] = round(t_fl, 1)
            result["tyre_core_temp_fr"] = round(t_fr, 1)
            result["tyre_core_temp_rl"] = round(t_rl, 1)
            result["tyre_core_temp_rr"] = round(t_rr, 1)

        # airTemp at byte 288, roadTemp at byte 292 (fixed offsets in SPageFilePhysics)
        if len(data) >= 296:
            air_t  = struct.unpack_from("<f", data, 288)[0]
            road_t = struct.unpack_from("<f", data, 292)[0]
            if -50 < air_t < 80:   # sanity range
                result["air_temp_c"]   = round(air_t, 1)
            if -10 < road_t < 100:
                result["track_temp_c"] = round(road_t, 1)

        return result
    except struct.error:
        return None
