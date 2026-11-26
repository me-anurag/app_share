"""Which devices have AppShare installed.

Browsers never tell a site how often it was installed (or uninstalled), so each browser keeps a random device id
and reports two things: "installed" (the browser's appinstalled event) and "app_open" (AppShare opened from its
home-screen icon, i.e. in standalone mode). Either one counts the device as installed. The second also catches
devices that installed before this existed. Kept in one small JSON file shared by all workspaces, because an
install belongs to the address, not to a workspace.
"""
import json
import os
import re
import threading
import time

from .db import DATA_ROOT
from .monitor import describe_device

PATH = os.path.join(DATA_ROOT, "installs.json")
_LOCK = threading.Lock()
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(DATA_ROOT, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def _model(ua):
    """The phone model from the user agent, e.g. 'V2437' or 'SM-S918B' (Chrome hides it as 'K' on newer Android)."""
    m = re.search(r"Android [\d.]+; ([^;)]+?)(?: Build/[^;)]*)?[;)]", ua or "")
    model = m.group(1).strip() if m else ""
    return "" if model in ("K", "wv") else model


def record(device_id, event, ua, user=None, host=""):
    if not ID_RE.match(device_id or "") or event not in ("installed", "app_open"):
        return False
    kind, os_name, browser = describe_device(ua)
    now = int(time.time() * 1000)
    with _LOCK:
        data = _load()
        d = data.get(device_id) or {"first_seen": now, "opens": 0}
        d.update(kind=kind, os=os_name, browser=browser, model=_model(ua) or d.get("model", ""), last_seen=now)
        if user:
            d["user"] = user
        if host:
            d["host"] = host
        if event == "installed":
            d["installed_at"] = now
        else:
            d["opens"] = d.get("opens", 0) + 1
            d["last_open"] = now
        data[device_id] = d
        _save(data)
    return True


def summary():
    with _LOCK:
        data = _load()
    items = sorted(({"id": k[:6], **v} for k, v in data.items()), key=lambda d: -d.get("last_seen", 0))
    return {"count": len(items), "devices": items}
