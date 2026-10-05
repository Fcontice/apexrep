import time

from apexrep.als.rate_limiter import Clock
from apexrep.config import Settings

MAX_TRACKED_IPS: int = 20_000


class IpRateLimiter:
    """Fixed-window request counter per visitor IP.

    In-process, so it holds for the single backend process the spec assumes.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_s: float,
        clock: Clock = time.monotonic,
        max_ips: int = MAX_TRACKED_IPS,
    ) -> None:
        self._limit: int = limit
        self._window_s: float = window_s
        self._clock: Clock = clock
        self._max_ips: int = max_ips
        self._windows: dict[str, tuple[float, int]] = {}

    def check(self, ip: str) -> float | None:
        """Count one request. Returns seconds to wait if the IP is over its limit."""
        now = self._clock()
        started_at, count = self._windows.get(ip, (now, 0))
        if now - started_at >= self._window_s:
            started_at, count = now, 0
        if count >= self._limit:
            return started_at + self._window_s - now

        if ip not in self._windows and len(self._windows) >= self._max_ips:
            self._make_room(now)
        self._windows[ip] = (started_at, count + 1)
        return None

    def _make_room(self, now: float) -> None:
        self._windows = {
            ip: window for ip, window in self._windows.items() if now - window[0] < self._window_s
        }
        # Still full of live windows: drop the oldest so memory stays bounded.
        if len(self._windows) >= self._max_ips:
            oldest_ip = min(self._windows, key=lambda ip: self._windows[ip][0])
            del self._windows[oldest_ip]


class IpLimiters:
    def __init__(self, settings: Settings, clock: Clock = time.monotonic) -> None:
        self.resolve: IpRateLimiter = IpRateLimiter(
            limit=settings.ip_limit_resolve_count,
            window_s=settings.ip_limit_resolve_window_s,
            clock=clock,
        )
        self.track: IpRateLimiter = IpRateLimiter(
            limit=settings.ip_limit_track_count,
            window_s=settings.ip_limit_track_window_s,
            clock=clock,
        )
