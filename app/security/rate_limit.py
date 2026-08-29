import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 10, window_s: int = 60):
        self.limit = limit
        self.window_s = window_s
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= current - self.window_s:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(current)
            return True

