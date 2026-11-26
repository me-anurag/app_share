"""Cost and abuse limits for the AI agents, checked in code before any model call, plus alerts for the Monitor.

  APPSHARE_DAILY_BUDGET_USD           calculated AI spend allowed per day (default 3.00). Measured from the trace
                                      store (tokens x prices), so it survives restarts. 0 disables the agents.
  APPSHARE_USER_AGENT_RUNS_PER_HOUR   AI requests one person may make per hour (default 30): Builder and Insights.
Background agents (Review, Reminder) count towards the budget but not towards anyone's hourly limit.
"""
import os
import threading
import time
from collections import defaultdict, deque

from . import monitor, trace

BUDGET = float(os.environ.get("APPSHARE_DAILY_BUDGET_USD", "3.00"))
PER_HOUR = int(os.environ.get("APPSHARE_USER_AGENT_RUNS_PER_HOUR", "30"))
_recent = defaultdict(deque)          # user id -> times of their recent AI requests (in memory: resets on restart)
_lock = threading.Lock()
_refused = {"budget": 0, "rate": 0}


class LimitReached(Exception):
    pass


def _midnight_ms():
    t = time.localtime()
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)) * 1000)


def spent_today():
    with trace._lock:
        try:
            v = trace._db().execute("SELECT COALESCE(SUM(cost), 0) FROM steps WHERE started_at >= ?", (_midnight_ms(),)).fetchone()[0]
        except Exception:  # noqa: BLE001
            v = 0.0
    return round(v or 0.0, 6)


def check(user_id=None, user_name=None):
    """Raise LimitReached (with a message for the person) if the budget or their hourly limit is used up."""
    spent = spent_today()
    if spent >= BUDGET:
        _refused["budget"] += 1
        monitor.emit("limit_hit", kind="budget", user=user_name, spent=spent, budget=BUDGET)
        raise LimitReached(f"Today's AI budget (${BUDGET:.2f}) is used up, so the AI agents are paused until tomorrow. "
                           "Everything else in AppShare keeps working.")
    if user_id is None:
        return
    now = time.time()
    with _lock:
        q = _recent[user_id]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= PER_HOUR:
            _refused["rate"] += 1
            wait = int((3600 - (now - q[0])) / 60) + 1
            monitor.emit("limit_hit", kind="rate", user=user_name, limit=PER_HOUR)
            raise LimitReached(f"You've asked the AI {PER_HOUR} times in the last hour. Please try again in about {wait} minutes.")
        q.append(now)


def status():
    spent = spent_today()
    return {"budget_usd": BUDGET, "spent_today_usd": spent, "used_pct": round(spent / BUDGET * 100, 1) if BUDGET else 100.0,
            "per_user_per_hour": PER_HOUR, "refused": dict(_refused)}


def alerts():
    """What the server laptop should be told about, most serious first."""
    out = []
    st = status()
    if st["used_pct"] >= 100:
        out.append({"level": "critical", "text": f"AI budget used up today (${st['spent_today_usd']:.2f} of ${st['budget_usd']:.2f}); agents are paused."})
    elif st["used_pct"] >= 80:
        out.append({"level": "warning", "text": f"AI budget {st['used_pct']:.0f}% used today (${st['spent_today_usd']:.2f} of ${st['budget_usd']:.2f})."})
    hour_ago = int(time.time() * 1000) - 3600_000
    with trace._lock:
        try:
            bad = trace._db().execute("SELECT COUNT(*) FROM runs WHERE status IN ('error', 'interrupted') AND started_at >= ?", (hour_ago,)).fetchone()[0]
        except Exception:  # noqa: BLE001
            bad = 0
    if bad >= 3:
        out.append({"level": "serious", "text": f"{bad} agent runs failed in the last hour — check the API key, the internet connection, or the Flow tab."})
    c = monitor.counters()
    if c.get("errors", 0) >= 5:
        out.append({"level": "serious", "text": f"{c['errors']} server errors since start — see the Monitor's request log."})
    if _refused["rate"]:
        out.append({"level": "warning", "text": f"{_refused['rate']} AI request(s) refused by the per-person hourly limit."})
    return out
