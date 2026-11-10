"""Local per-tier health, the pre-check before a call. Rolling window of recent failures; nothing is ever removed,
an unhealthy tier simply loses priority until its failures age out (same idea as OpenRouter's 30 s provider check)."""
import time
from collections import deque
from config import HEALTH_WINDOW_S, HEALTH_FAIL_THRESHOLD

_failures: dict[str, deque] = {}


def record(tier: str, ok: bool):
    q = _failures.setdefault(tier, deque())
    now = time.time()
    while q and now - q[0] > HEALTH_WINDOW_S:
        q.popleft()
    if not ok:
        q.append(now)


def recent_failures(tier: str) -> int:
    q = _failures.get(tier)
    if not q:
        return 0
    now = time.time()
    while q and now - q[0] > HEALTH_WINDOW_S:
        q.popleft()
    return len(q)


def is_unhealthy(tier: str) -> bool:
    return recent_failures(tier) >= HEALTH_FAIL_THRESHOLD


def reset():
    _failures.clear()
