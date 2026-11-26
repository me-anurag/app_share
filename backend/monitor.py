"""Live server monitor.

The AppShare server records what it is doing - every request, which devices are
connected, logins, shares, submissions, blocked uploads, and each step the agents
take - and streams it to the Control Center over Server-Sent Events.

Everything is in memory and resets when the server restarts. Only the laptop the
server runs on can read it (see `allowed`).
"""
import hashlib
import os
import secrets
import socket
import threading
import time
from collections import deque

TOKEN = os.environ.get("APPSHARE_MONITOR_TOKEN", "")
SERVER_NAME = os.environ.get("APPSHARE_SERVER_NAME") or socket.gethostname()
STARTED_AT = time.time()
KINDS = ("page", "data", "submit", "agent")  # traffic categories shown in charts

_lock = threading.Lock()
_events = deque(maxlen=1500)
_next_id = 1
_devices = {}                       # key -> device dict
_minutes = {}                       # minute -> {kind: count}
_endpoints = {}                     # route -> {count, ms, errors}
_counters = {
    "requests": 0, "errors": 0, "ms_total": 0.0,
    "logins": 0, "failed_logins": 0, "denied": 0, "rejected_uploads": 0,
    "submissions": 0, "shares": 0, "apps_created": 0,
    "agent_runs": 0, "agent_errors": 0, "agent_ms": 0.0, "llm_calls": 0, "tool_calls": 0,
    "tokens_in": 0, "tokens_out": 0,
}
_tools = {}
_user_cache = {}                    # session token -> (user_id, name)


def now_ms():
    return int(time.time() * 1000)


HOOKS = []          # functions called with every event (the trace store saves app lifecycle events)


def emit(type_, **data):
    """Record an event. Safe to call from any thread."""
    global _next_id
    with _lock:
        ev = {"id": _next_id, "ts": now_ms(), "type": type_, **data}
        _next_id += 1
        _events.append(ev)
    for hook in HOOKS:
        try:
            hook(ev)
        except Exception:  # noqa: BLE001 — a listener must never break the request that emitted
            pass
    return ev


_LIVE = {"v": int(time.time())}


def bump_live():
    """Something changed (a response, a status, a share, an agent's work): open screens refresh."""
    _LIVE["v"] += 1


def live_version():
    return _LIVE["v"]


def bump(name, amount=1):
    with _lock:
        _counters[name] = _counters.get(name, 0) + amount


def count_tool(name):
    with _lock:
        _tools[name] = _tools.get(name, 0) + 1
        _counters["tool_calls"] += 1


_agents = {}


def count_agent(name):
    with _lock:
        _agents[name] = _agents.get(name, 0) + 1


def events_after(after_id, limit=300):
    with _lock:
        if not _events or _events[-1]["id"] <= after_id:
            return []
        out = [e for e in _events if e["id"] > after_id]
    return out[-limit:]


def latest_id():
    with _lock:
        return _events[-1]["id"] if _events else 0


# --------------------------------------------------------------------------- devices

def describe_device(ua: str):
    ua = ua or ""
    u = ua.lower()
    if "iphone" in u:
        kind, os_name = "phone", "iPhone"
    elif "ipad" in u:
        kind, os_name = "tablet", "iPad"
    elif "android" in u:
        kind, os_name = ("phone" if "mobile" in u else "tablet"), "Android"
    elif "windows" in u:
        kind, os_name = "laptop", "Windows"
    elif "mac os" in u or "macintosh" in u:
        kind, os_name = "laptop", "Mac"
    elif "linux" in u:
        kind, os_name = "laptop", "Linux"
    else:
        kind, os_name = "laptop", "Device"
    if "edg/" in u:
        browser = "Edge"
    elif "samsungbrowser" in u:
        browser = "Samsung Internet"
    elif "chrome/" in u or "crios" in u:
        browser = "Chrome"
    elif "firefox" in u or "fxios" in u:
        browser = "Firefox"
    elif "safari" in u:
        browser = "Safari"
    elif "python" in u or "httpx" in u or "testclient" in u:
        browser, kind, os_name = "script", "laptop", "Test client"
    else:
        browser = "browser"
    return kind, os_name, browser


def client_ip(request):
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


DEVICE_COOKIE = "appshare_did"


def touch_device(request, user=None, count_request=True, did=None):
    """Register or refresh the device behind a request. Returns (device, is_new).
    A device is one browser: identified by its device cookie, or by IP + browser if it has none yet."""
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")
    did = did or request.cookies.get(DEVICE_COOKIE)
    key = hashlib.sha1((did or f"{ip}|{ua}").encode()).hexdigest()[:10]
    kind, os_name, browser = describe_device(ua)
    t = now_ms()
    with _lock:
        d = _devices.get(key)
        is_new = d is None
        if is_new:
            d = _devices[key] = {"id": key, "ip": ip, "kind": kind, "os": os_name, "browser": browser,
                                 "label": os_name if os_name in ("iPhone", "iPad", "Mac", "Device", "Test client")
                                          else f"{os_name} {kind}",
                                 "first_seen": t, "last_seen": t, "requests": 0, "user": None,
                                 "via": "internet" if request.headers.get("x-forwarded-for") else
                                        ("this laptop" if ip in ("127.0.0.1", "::1") else "local network")}
        d["last_seen"] = t
        if count_request:
            d["requests"] += 1
        if user:
            d["user"] = user
        snapshot = dict(d)
    return snapshot, is_new


def devices():
    with _lock:
        return sorted((dict(d) for d in _devices.values()), key=lambda d: -d["last_seen"])


# --------------------------------------------------------------------------- requests

def classify(method, path):
    if not path.startswith("/api/"):
        return "page"
    if path.startswith("/api/agent/"):
        return "agent"
    if path.endswith("/submit") or path.startswith("/api/files/"):
        return "submit"
    return "data"


def record_request(route, kind, status, ms):
    minute = int(time.time() // 60)
    with _lock:
        _counters["requests"] += 1
        _counters["ms_total"] += ms
        if status >= 500:
            _counters["errors"] += 1
        bucket = _minutes.setdefault(minute, {k: 0 for k in KINDS})
        bucket[kind] = bucket.get(kind, 0) + 1
        for m in [m for m in _minutes if m < minute - 60]:
            del _minutes[m]
        ep = _endpoints.setdefault(route, {"route": route, "count": 0, "ms": 0.0, "errors": 0})
        ep["count"] += 1
        ep["ms"] += ms
        if status >= 400:
            ep["errors"] += 1


def series(minutes=30):
    now_min = int(time.time() // 60)
    with _lock:
        return [{"t": (m * 60) * 1000, **_minutes.get(m, {k: 0 for k in KINDS})}
                for m in range(now_min - minutes + 1, now_min + 1)]


def user_for_token(conn, token):
    if not token:
        return None
    if token in _user_cache:
        return _user_cache[token]
    row = conn.execute("SELECT u.id, u.name FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
                       (token,)).fetchone()
    if row:
        _user_cache[token] = row["name"]
        return row["name"]
    return None


def forget_token(token):
    _user_cache.pop(token, None)


# --------------------------------------------------------------------------- access

def allowed(request, token_param: str):
    """Monitor data is for the laptop only: loopback, not forwarded by a tunnel, right token."""
    host = (request.client.host if request.client else "")
    if host not in ("127.0.0.1", "::1"):
        return False
    if request.headers.get("x-forwarded-for") or request.headers.get("x-forwarded-host"):
        return False
    hosthdr = request.headers.get("host", "")
    if not (hosthdr.startswith("127.0.0.1") or hosthdr.startswith("localhost")):
        return False
    return (not TOKEN) or secrets.compare_digest(token_param or "", TOKEN)


def counters():
    with _lock:
        c = dict(_counters)
        c["tools"] = dict(_tools)
        c["agents"] = dict(_agents)
        c["endpoints"] = sorted((dict(e) for e in _endpoints.values()), key=lambda e: -e["count"])[:12]
    c["avg_ms"] = round(c["ms_total"] / c["requests"], 1) if c["requests"] else 0
    c["agent_avg_ms"] = round(c["agent_ms"] / c["agent_runs"]) if c["agent_runs"] else 0
    return c
