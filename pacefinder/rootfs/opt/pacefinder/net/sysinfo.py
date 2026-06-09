"""Pi/Linux system metrics via /proc and /sys.

All readers fail gracefully on non-Linux dev boxes (Mac/Windows) so the same
endpoint works locally for development — fields just come back as None.

Surfaced through GET /system/load and rendered in the Debug panel.
"""
import os
import time


_last_cpu = {"idle": 0, "total": 0}


def _cpu_pct():
    """% CPU busy since last call. Returns None on first call or non-Linux."""
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()[1:]
        vals = [int(x) for x in parts]
        idle = vals[3] + vals[4]   # idle + iowait
        total = sum(vals)
        d_idle = idle - _last_cpu["idle"]
        d_total = total - _last_cpu["total"]
        _last_cpu["idle"], _last_cpu["total"] = idle, total
        if d_total <= 0:
            return None
        return round(100.0 * (1 - d_idle / d_total), 1)
    except (OSError, IndexError, ValueError):
        return None


def _meminfo():
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k] = int(v.strip().split()[0])  # kB
        total = info["MemTotal"]
        avail = info.get("MemAvailable", info["MemFree"])
        used = total - avail
        return {
            "total_mb": round(total / 1024),
            "used_mb":  round(used / 1024),
            "used_pct": round(100 * used / total, 1),
        }
    except (OSError, KeyError, ValueError):
        return None


def _loadavg():
    try:
        return [round(v, 2) for v in os.getloadavg()]   # 1m, 5m, 15m
    except (OSError, AttributeError):
        return None


def _cpu_temp():
    # Pi exposes CPU temp here (milli-°C). Mac/Windows: returns None.
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (OSError, ValueError):
        return None


def _disk_pct(path: str):
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        if total <= 0:
            return None
        return round(100 * (total - free) / total, 1)
    except OSError:
        return None


def snapshot(storage_path: str = "/"):
    """Single-call dict of current system state. Cheap — call from a 2s poll."""
    return {
        "ts":            time.time(),
        "cpu_pct":       _cpu_pct(),
        "load":          _loadavg(),
        "mem":           _meminfo(),
        "cpu_temp_c":    _cpu_temp(),
        "disk_used_pct": _disk_pct(storage_path),
    }
