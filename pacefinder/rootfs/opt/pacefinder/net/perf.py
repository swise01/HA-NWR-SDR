"""Per-request perf instrumentation primitives.

Lives outside net/router.py so db/store.py can import _TimedLock to wrap its
own _db_lock without creating a circular import. See:
docs/specs/perf-audit-and-instrument.md
"""
import contextvars
import time
from collections import deque

# Per-request context — populated by the router for each incoming request
# and consulted by _TimedLock to attribute DB time. Outside a request (the
# listener thread, the watchdog), get() returns None and timing is skipped.
_perf_ctx: contextvars.ContextVar = contextvars.ContextVar("perf_ctx", default=None)

# Bounded ring buffers shared between the recording sites (router) and the
# /debug/perf endpoint (router). Bounded so memory stays flat over time.
_perf_ring: deque = deque(maxlen=200)
_perf_client_ring: deque = deque(maxlen=200)

_PERF_LOG_THRESHOLD_MS = 50.0


class _TimedLock:
    """Wraps a threading.Lock so acquire+held time is added to _perf_ctx
    when used inside an HTTP request, and is a no-op everywhere else."""
    __slots__ = ("_lock", "_t0")

    def __init__(self, lock):
        self._lock = lock

    def __enter__(self):
        self._t0 = time.perf_counter()
        self._lock.acquire()
        return self

    def __exit__(self, *exc):
        elapsed_ms = (time.perf_counter() - self._t0) * 1000
        ctx = _perf_ctx.get()
        if ctx is not None:
            ctx["db_ms"] += elapsed_ms
        self._lock.release()
        return False
