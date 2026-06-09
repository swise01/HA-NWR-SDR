import struct
from typing import Optional

# Codemasters F1 UDP format (F1 2023/2024)
# Header: packetFormat(H), gameYear(B), gameMajorVersion(B), gameMinorVersion(B),
#         packetVersion(B), packetId(B), sessionUID(Q), sessionTime(f),
#         frameIdentifier(I), playerCarIndex(B), secondaryPlayerCarIndex(B)
# Packet IDs: 0=Motion, 1=Session, 6=CarTelemetry, 7=CarStatus

F1_HEADER_SIZE = 29  # F1 2023/2024 header

# Track names by F1 track ID (F1 2023)
F1_TRACKS = {
    0: "Melbourne", 1: "Paul Ricard", 2: "Shanghai", 3: "Sakhir (Bahrain)",
    4: "Catalunya", 5: "Monaco", 6: "Montreal", 7: "Silverstone",
    8: "Hockenheim", 9: "Hungaroring", 10: "Spa", 11: "Monza",
    12: "Singapore", 13: "Suzuka", 14: "Abu Dhabi", 15: "Texas",
    16: "Brazil", 17: "Austria", 18: "Sochi", 19: "Mexico",
    20: "Baku (Azerbaijan)", 21: "Sakhir Short", 22: "Silverstone Short",
    23: "Texas Short", 24: "Suzuka Short", 25: "Hanoi", 26: "Zandvoort",
    27: "Imola", 28: "Portimão", 29: "Jeddah", 30: "Miami",
    31: "Las Vegas", 32: "Losail",
}

# Per-session F1 state (track, session type) populated from packet ID 1
_f1_session_meta: dict = {}


def parse_f1(data: bytes) -> Optional[dict]:
    """Dispatch F1 packets by ID; return unified dict for telemetry packets."""
    if len(data) < 24:  # minimum valid header (F1 2023)
        return None
    try:
        # Detect game year from packetFormat field (uint16 @ 0): 2023 or 2024
        packet_format = struct.unpack_from("<H", data, 0)[0]
        is_2024 = (packet_format >= 2024)
        # F1 2023: 24-byte header, playerCarIndex @ 23
        # F1 2024: 29-byte header, playerCarIndex @ 27
        hdr      = 29 if is_2024 else 24
        pidx_off = 27 if is_2024 else 23

        packet_id   = struct.unpack_from("<B", data, 6)[0]
        session_uid = struct.unpack_from("<Q", data, 7)[0]

        if packet_id == 1:
            # Session — extract track, session type, weather, temperatures
            # layout: weather(B) trackTemp(b) airTemp(b) totalLaps(B) trackLength(H) sessionType(B) trackId(b)
            base = hdr
            if len(data) >= base + 8:
                weather_val  = struct.unpack_from("<B", data, base + 0)[0]
                track_temp   = struct.unpack_from("<b", data, base + 1)[0]
                air_temp     = struct.unpack_from("<b", data, base + 2)[0]
                session_type = struct.unpack_from("<B", data, base + 6)[0]
                track_id     = struct.unpack_from("<b", data, base + 7)[0]
                session_types = {
                    0: "unknown",
                    1: "practice", 2: "practice", 3: "practice", 4: "practice",
                    5: "qualifying", 6: "qualifying", 7: "qualifying",
                    8: "qualifying", 9: "qualifying",
                    10: "race", 11: "race", 12: "race",
                    13: "time_trial",
                }
                _F1_WEATHER = {0: "Clear", 1: "LightCloud", 2: "Overcast",
                               3: "LightRain", 4: "HeavyRain", 5: "Thunderstorm"}
                _f1_session_meta[session_uid] = {
                    "track":             F1_TRACKS.get(track_id, f"track_{track_id}"),
                    "session_type":      session_types.get(session_type, "unknown"),
                    "weather_condition": _F1_WEATHER.get(weather_val),
                    "track_temp_c":      float(track_temp) if -10 <= track_temp <= 100 else None,
                    "air_temp_c":        float(air_temp)   if -50 <= air_temp <= 80  else None,
                }
            return None

        if packet_id == 2:
            # LapData — lap number, times, position
            # F1 2024 per-car: 50 bytes  |  F1 2023 per-car: 43 bytes
            if is_2024:
                car_size     = 50
                off_last_lap = 0   # uint32 lastLapTimeInMS
                off_cur_lap  = 4   # uint32 currentLapTimeInMS
                off_pos      = 30  # uint8 carPosition
                off_lap_num  = 31  # uint8 currentLapNum
                off_grid_pos = 41  # uint8 gridPosition
            else:
                car_size     = 43
                off_last_lap = 0
                off_cur_lap  = 4
                off_pos      = 24
                off_lap_num  = 25
                off_grid_pos = 34
            player_idx = struct.unpack_from("<B", data, pidx_off)[0]
            base = hdr + player_idx * car_size
            if len(data) < base + car_size:
                return None
            last_lap_ms = struct.unpack_from("<I", data, base + off_last_lap)[0]
            cur_lap_ms  = struct.unpack_from("<I", data, base + off_cur_lap)[0]
            car_pos     = struct.unpack_from("<B", data, base + off_pos)[0]
            cur_lap_num = struct.unpack_from("<B", data, base + off_lap_num)[0]
            grid_pos    = struct.unpack_from("<B", data, base + off_grid_pos)[0]
            return {
                "_packet_type":     "lap_data",
                "_session_uid":     session_uid,
                "lap_number":       cur_lap_num,
                "current_lap_time": round(cur_lap_ms / 1000, 3) if cur_lap_ms < 600_000 else None,
                "last_lap_time":    round(last_lap_ms / 1000, 3) if 0 < last_lap_ms < 600_000 else None,
                "race_position":    car_pos,
                "grid_position":    grid_pos,
            }

        if packet_id == 0:
            # Motion — g-forces and velocity for player car
            # per-car: worldPos(3f) worldVel(3f) worldForwardDir(3H) worldRightDir(3H)
            #          gForceLateral(f) gForceLongitudinal(f) gForceVertical(f) yaw(f) pitch(f) roll(f)
            player_idx = struct.unpack_from("<B", data, pidx_off)[0]
            car_size = 60
            base = hdr + player_idx * car_size
            if len(data) < base + car_size:
                return None
            pos_x, pos_y, pos_z = struct.unpack_from("<fff", data, base)
            vel_x, vel_y, vel_z = struct.unpack_from("<fff", data, base + 12)
            g_lat  = struct.unpack_from("<f", data, base + 36)[0]
            g_lon  = struct.unpack_from("<f", data, base + 40)[0]
            g_vert = struct.unpack_from("<f", data, base + 44)[0]
            result = {
                "_packet_type": "motion",
                "_session_uid": session_uid,
                "position_x": round(pos_x, 2),
                "position_y": round(pos_y, 2),
                "position_z": round(pos_z, 2),
                "velocity_x": round(vel_x, 2),
                "velocity_y": round(vel_y, 2),
                "velocity_z": round(vel_z, 2),
                "g_lat":  round(g_lat, 3),
                "g_lon":  round(g_lon, 3),
                "g_vert": round(g_vert, 3),
            }
            # F1 2023: wheelSlip appended at end of Motion packet after all 22 cars
            # layout at tail: suspPos(4f) suspVel(4f) suspAcc(4f) wheelSpeed(4f) wheelSlip(4f) ...
            if not is_2024:
                slip_base = hdr + 22 * car_size + 64  # 64 = 4×4f before wheelSlip
                if len(data) >= slip_base + 16:
                    s_fl, s_fr, s_rl, s_rr = struct.unpack_from("<ffff", data, slip_base)
                    result["slip_ratio_fl"] = round(abs(s_fl), 4)
                    result["slip_ratio_fr"] = round(abs(s_fr), 4)
                    result["slip_ratio_rl"] = round(abs(s_rl), 4)
                    result["slip_ratio_rr"] = round(abs(s_rr), 4)
            return result

        if packet_id == 13:
            # MotionEx (F1 2024 only) — per-player extra motion including wheelSlip
            # layout: suspPos(4f) suspVel(4f) suspAcc(4f) wheelSpeed(4f) wheelSlip(4f) ...
            # wheelSlip order: FL=0, FR=1, RL=2, RR=3
            slip_base = hdr + 64  # 4 × 16 bytes before wheelSlip
            if len(data) < slip_base + 16:
                return None
            s_fl, s_fr, s_rl, s_rr = struct.unpack_from("<ffff", data, slip_base)
            return {
                "_packet_type":  "motion",
                "_session_uid":  session_uid,
                "slip_ratio_fl": round(abs(s_fl), 4),
                "slip_ratio_fr": round(abs(s_fr), 4),
                "slip_ratio_rl": round(abs(s_rl), 4),
                "slip_ratio_rr": round(abs(s_rr), 4),
            }

        if packet_id == 6:
            # CarTelemetry — speed, inputs, tyres, engine
            # per-car (60 bytes): speed(H) throttle(f) steer(f) brake(f) clutch(B)
            #   gear(b) engineRPM(H) drs(B) revLightsPercent(B) revLightsBitValue(H)
            #   brakesTemp(4H) tyresSurfaceTemp(4B) tyresInnerTemp(4B)
            #   engineTemp(H) tyresPressure(4f) surfaceType(4B)
            player_idx = struct.unpack_from("<B", data, pidx_off)[0]
            car_size = 60
            base = hdr + player_idx * car_size
            if len(data) < base + car_size:
                return None
            speed    = struct.unpack_from("<H", data, base)[0]
            throttle = struct.unpack_from("<f", data, base + 2)[0]
            steer    = struct.unpack_from("<f", data, base + 6)[0]
            brake    = struct.unpack_from("<f", data, base + 10)[0]
            clutch   = struct.unpack_from("<B", data, base + 14)[0]
            gear     = struct.unpack_from("<b", data, base + 15)[0]
            rpm      = struct.unpack_from("<H", data, base + 16)[0]
            drs      = struct.unpack_from("<B", data, base + 18)[0]
            # drs@18 + revLightsPercent(B)@19 + revLightsBitValue(H)@20 → brake temps at +22
            bt_rl, bt_rr, bt_fl, bt_fr = struct.unpack_from("<HHHH", data, base + 22)
            ts_rl, ts_rr, ts_fl, ts_fr = struct.unpack_from("<BBBB", data, base + 30)
            ti_rl, ti_rr, ti_fl, ti_fr = struct.unpack_from("<BBBB", data, base + 34)
            engine_temp = struct.unpack_from("<H", data, base + 38)[0]
            tp_rl, tp_rr, tp_fl, tp_fr = struct.unpack_from("<ffff", data, base + 40)
            meta = _f1_session_meta.get(session_uid, {})
            ret: dict = {
                "_packet_type":         "telemetry",
                "_session_uid":         session_uid,
                "track":                meta.get("track", "unknown"),
                "session_type":         meta.get("session_type", "unknown"),
                "speed_mph":            round(speed * 0.621371, 1),
                "throttle_pct":         round(throttle * 100, 1),
                "brake_pct":            round(brake * 100, 1),
                "clutch_pct":           round(clutch / 255 * 100, 1),
                "steer":                round(steer, 3),
                "gear":                 gear,
                "rpm":                  rpm,
                "drs":                  bool(drs),
                "brake_temp_fl":        bt_fl,
                "brake_temp_fr":        bt_fr,
                "brake_temp_rl":        bt_rl,
                "brake_temp_rr":        bt_rr,
                "tyre_surface_temp_fl": ts_fl,
                "tyre_surface_temp_fr": ts_fr,
                "tyre_surface_temp_rl": ts_rl,
                "tyre_surface_temp_rr": ts_rr,
                "tyre_inner_temp_fl":   ti_fl,
                "tyre_inner_temp_fr":   ti_fr,
                "tyre_inner_temp_rl":   ti_rl,
                "tyre_inner_temp_rr":   ti_rr,
                "tyre_pressure_fl":     round(tp_fl, 2),
                "tyre_pressure_fr":     round(tp_fr, 2),
                "tyre_pressure_rl":     round(tp_rl, 2),
                "tyre_pressure_rr":     round(tp_rr, 2),
                "engine_temp":          engine_temp,
            }
            # Carry weather/temp from session packet into each telemetry sample
            for k in ("weather_condition", "track_temp_c", "air_temp_c"):
                v = meta.get(k)
                if v is not None:
                    ret[k] = v
            return ret

        if packet_id == 7:
            # CarStatus — fuel, tyre compound
            # per-car (47 bytes): tractionControl(B) antiLockBrakes(B) fuelMix(B)
            #   frontBrakeBias(B) pitLimiterStatus(B) fuelInTank(f) fuelCapacity(f)
            #   fuelRemainingLaps(f) maxRPM(H) idleRPM(H) maxGears(B) drsAllowed(B)
            #   drsActivationDistance(H) actualTyreCompound(B) visualTyreCompound(B) tyresAgeLaps(B)
            player_idx = struct.unpack_from("<B", data, pidx_off)[0]
            car_size = 47
            base = hdr + player_idx * car_size
            if len(data) < base + car_size:
                return None
            fuel_in_tank        = struct.unpack_from("<f", data, base + 5)[0]
            fuel_remaining_laps = struct.unpack_from("<f", data, base + 13)[0]
            tyre_compound       = struct.unpack_from("<B", data, base + 23)[0]
            tyre_age_laps       = struct.unpack_from("<B", data, base + 25)[0]
            compounds = {16: "C5", 17: "C4", 18: "C3", 19: "C2", 20: "C1",
                         21: "C0", 7: "Inter", 8: "Wet", 9: "Wet"}
            return {
                "_packet_type":        "car_status",
                "_session_uid":        session_uid,
                "fuel_in_tank":        round(fuel_in_tank, 2),
                "fuel_remaining_laps": round(fuel_remaining_laps, 1),
                "tyre_compound":       compounds.get(tyre_compound, f"compound_{tyre_compound}"),
                "tyre_age_laps":       tyre_age_laps,
            }

        return None
    except struct.error:
        return None
