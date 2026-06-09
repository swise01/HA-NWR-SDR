import urllib.request, sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.1.3:8000"

CHECKS = [
    ("/",                                    ["Throttle", "Brake", "Rear Slip"]),
    ("/sessions",                            ["Pacefinder", "Sessions", "Circuit"]),
    ("/sessions/game?name=forza_motorsport", ["Forza", "circuit"]),
    ("/status",                              ["status"]),
    ("/health",                              ["OK"]),
    ("/setup",                               ["Storage", "port"]),
]

failed = 0
for path, keywords in CHECKS:
    try:
        body = urllib.request.urlopen(BASE + path, timeout=5).read().decode()
        for kw in keywords:
            if kw not in body:
                print(f"✗ {path} — missing '{kw}'"); failed += 1
            else:
                print(f"✓ {path} — '{kw}'")
    except Exception as e:
        print(f"✗ {path} — {e}"); failed += 1

sys.exit(failed)
