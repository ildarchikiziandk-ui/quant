"""Простой in-memory лимитер запросов (на процесс). Защищает вход, регистрацию и спам."""
import time
from collections import defaultdict, deque
from threading import Lock

_hits = defaultdict(deque)
_lock = Lock()


def hit(key: str, limit: int, window: int) -> bool:
    """Регистрирует попытку. Возвращает False, если лимит превышен."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reset(key: str = None):
    with _lock:
        if key is None:
            _hits.clear()
        else:
            _hits.pop(key, None)
