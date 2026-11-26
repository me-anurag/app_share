"""AppShare API server. Start it from the Control Center (python -m launcher), or directly:
    uvicorn backend.main:app --host 0.0.0.0        (APPSHARE_MODE = university | office | general)"""
import asyncio
import csv
import io
import json
import os
import re
import secrets
import time
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import access, agents, installs, limits, monitor, play, templates, trace
from .site import BACKGROUNDS as SITE_BACKGROUNDS, BLOCK_TYPES as SITE_BLOCK_TYPES, THEMES as SITE_THEMES
from .db import BASE_DIR, DB_PATH, MODE, ORG_NAME, UPLOAD_DIR, VOCAB, add_user, dumps, get_db, init_db
from .spec import (COVER_RE, LOOK_PATTERNS, LOOK_STYLES, check_file, check_value, contrast_with_white, describe_rules,
                   normalize_look, summarize, window_state)

STATIC = os.path.join(BASE_DIR, "frontend")
VERSION = "2.0"
app = FastAPI(title="AppShare")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
init_db()

class _Compress:
    """gzip responses (about 4x smaller over a phone's connection) — except the live push streams, which must
    reach the screen the moment something happens, not when a compression buffer fills."""
    def __init__(self, app):
        from starlette.middleware.gzip import GZipMiddleware
        self.app, self.gz = app, GZipMiddleware(app, minimum_size=800)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not scope.get("path", "").endswith("/stream"):
            return await self.gz(scope, receive, send)
        return await self.app(scope, receive, send)


app.add_middleware(_Compress)


@app.middleware("http")
async def _cache_assets(request: Request, call_next):
    """Files whose link carries a version stamp (?v=…) never change, so phones keep them for a year; a new version
    of the file gets a new stamp. Unstamped files are revalidated every time (cheap: 304 Not Modified)."""
    response = await call_next(request)
    p = request.url.path
    if p.startswith(("/static/", "/agents/")) and response.status_code == 200:
        response.headers["Cache-Control"] = ("public, max-age=31536000, immutable" if request.query_params.get("v")
                                             else "no-cache")
    return response


_cport = os.environ.get("APPSHARE_CONTROL_PORT", "7000")
app.add_middleware(CORSMiddleware, allow_origins=[f"http://127.0.0.1:{_cport}", f"http://localhost:{_cport}"],
                   allow_methods=["GET"], allow_headers=["*"])

QUIET_PATHS = ("/static/", "/agents/", "/sw.js", "/manifest.webmanifest", "/favicon", "/api/monitor/", "/api/ping",
               "/api/agent/progress", "/api/live", "/api/qr", "/api/client-diag", "/api/device-install")
# Requests that change data: after one succeeds, every open screen refreshes itself (see /api/live).
INSTALL_FETCHES = []
NO_LIVE_BUMP = ("/api/agent/session", "/api/login", "/api/logout", "/api/notifications/read")


def _route_name(request: Request, path: str) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return re.sub(r"/\d+", "/{id}", re.sub(r"^/a/[^/]+", "/a/{slug}", path))


@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Feed every request into the live monitor (method, route, status, time, device, user)."""
    path = request.url.path
    if path == "/manifest.webmanifest" or path.startswith("/static/icons/"):
        # who fetches the install file and icons (a browser evaluating "can this be installed?", or Google's install server)
        INSTALL_FETCHES.append({"at": time.strftime("%H:%M:%S"), "path": path, "ua": request.headers.get("user-agent", "")[:200],
                                "cookie": bool(request.cookies)})
        del INSTALL_FETCHES[:-40]
    if path.startswith(QUIET_PATHS) or (request.method == "GET" and path.endswith("/live") and path.startswith("/api/a/")):
        return await call_next(request)
    did = request.cookies.get(monitor.DEVICE_COOKIE)
    new_did = None if did else secrets.token_urlsafe(9)
    request.state.did = did or new_did
    t0 = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        if request.method != "GET" and path.startswith("/api/") and status < 400 and not path.startswith(NO_LIVE_BUMP):
            monitor.bump_live()
        if new_did:
            response.set_cookie(monitor.DEVICE_COOKIE, new_did, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
        return response
    finally:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        kind = monitor.classify(request.method, path)
        route = _route_name(request, path)
        user = None
        try:
            with get_db() as conn:
                user = monitor.user_for_token(conn, request.cookies.get("session"))
        except Exception:
            pass
        device, is_new = monitor.touch_device(request, user, did=did or new_did)
        monitor.record_request(f"{request.method} {route}", kind, status, ms)
        monitor.emit("http", method=request.method, path=path[:120], route=route, kind=kind, status=status, ms=ms,
                     user=user, device=device["id"], device_kind=device["kind"], device_label=device["label"],
                     new_device=is_new)


monitor.emit("server_start", name=monitor.SERVER_NAME, version=VERSION, org=ORG_NAME, mode=MODE)


def _parent_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x00100000, False, pid)          # SYNCHRONIZE
        if not handle:
            return False
        try:
            return k32.WaitForSingleObject(handle, 0) == 0x00000102  # WAIT_TIMEOUT: still running
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _watch_parent():
    """When started by the Control Center, stop if the Control Center disappears (window closed)."""
    import threading
    pid = int(os.environ.get("APPSHARE_PARENT_PID", "0") or 0)
    if not pid:
        return

    def loop():
        while True:
            time.sleep(2)
            if not _parent_alive(pid):
                os._exit(0)
    threading.Thread(target=loop, daemon=True).start()


_watch_parent()


# --------------------------------------------------------------------------- auth (minimal on purpose)

def optional_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?", (token,)).fetchone()
    return dict(row) if row else None


def current_user(request: Request):
    user = optional_user(request)
    if not user:
        raise HTTPException(401, "Not logged in")
    return user


def _session_response(conn, user_id, name, body):
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
    monitor.bump("logins")
    monitor.emit("login", user=name)
    resp = JSONResponse(body)
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp


class LoginIn(BaseModel):
    email: str


@app.post("/api/login")
def login(body: LoginIn):
    with get_db() as conn:
        row = conn.execute("SELECT id, name FROM users WHERE email = ?", (body.email.strip().lower(),)).fetchone()
        if not row:
            monitor.bump("failed_logins")
            local = body.email.strip().split("@")[0]
            monitor.emit("login_failed", email=(local[:2] + "•••@" + body.email.split("@")[-1]) if "@" in body.email else "•••")
            raise HTTPException(404, "No account with that email." + (" Use “Continue” to create one." if MODE == "general" else ""))
        return _session_response(conn, row["id"], row["name"], {"ok": True})


class SignupIn(BaseModel):
    name: str
    email: str


@app.post("/api/signup")
def signup(body: SignupIn):
    """Personal mode only: anyone can make an account with a name and email."""
    if MODE != "general":
        raise HTTPException(403, f"Accounts at {ORG_NAME} are created by the administrator.")
    email, name = body.email.strip().lower(), body.name.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or not name:
        raise HTTPException(400, "Enter your name and a valid email.")
    with get_db() as conn:
        row = conn.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
        uid = row["id"] if row else add_user(conn, email, name[:60], [])
        return _session_response(conn, uid, row["name"] if row else name, {"ok": True})


@app.post("/api/logout")
def logout(request: Request):
    token = request.cookies.get("session", "")
    with get_db() as conn:
        name = monitor.user_for_token(conn, token)
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    monitor.forget_token(token)
    if name:
        monitor.emit("logout", user=name)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session")
    return resp


KIND_ORDER = {"faculty": 0, "manager": 0, "staff": 1, "employee": 2, "student": 3, "member": 4}


@app.get("/api/workspace")
def workspace(request: Request = None):
    """Public: what this workspace is, and demo accounts to sign in as."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT u.name, u.email, u.title, u.kind, u.is_admin, (SELECT GROUP_CONCAT(g.name, ', ') FROM group_members gm
                      JOIN groups g ON g.id = gm.group_id WHERE gm.user_id = u.id AND g.kind NOT IN ('everyone')) AS groups
                 FROM users u""").fetchall()
    people = sorted((dict(r) for r in rows), key=lambda p: (KIND_ORDER.get(p["kind"], 5), -p["is_admin"], p["name"]))
    return {"mode": MODE, "org": ORG_NAME, "vocab": VOCAB, "people": people, **(share_info(request) if request else {})}


@app.get("/api/login-options")
def login_options():
    w = workspace()
    return {"org": w["org"], "people": w["people"]}


def _my_groups(conn, uid):
    return [dict(r) for r in conn.execute(
        "SELECT g.name, g.kind FROM group_members gm JOIN groups g ON g.id = gm.group_id WHERE gm.user_id = ? ORDER BY g.kind, g.name", (uid,))]


@app.get("/api/me")
def me(request: Request, user=Depends(current_user)):
    with get_db() as conn:
        groups = _my_groups(conn, user["id"])
    return {"id": user["id"], "name": user["name"], "email": user["email"], "title": user["title"], "kind": user["kind"],
            "is_admin": bool(user["is_admin"]), "groups": [g["name"] for g in groups if g["kind"] != "everyone"],
            "org": ORG_NAME, "mode": MODE, "vocab": VOCAB, "agents": agents.available(), **share_info(request)}


# --------------------------------------------------------------------------- the address people can actually open
# A link copied on the laptop must not say 127.0.0.1. Prefer the HTTPS tunnel (installable, works from anywhere),
# then the address the person is already using, then the laptop's Wi-Fi / hotspot address.
_BASE_CACHE = {"t": 0.0, "v": None}


def _control_center_base():
    if time.time() - _BASE_CACHE["t"] < 8:
        return _BASE_CACHE["v"]
    found = None
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{_cport}/api/status", timeout=0.6) as r:
            st = json.loads(r.read().decode())
        t = st.get("tunnel") or {}
        if t.get("state") == "online" and t.get("url"):
            found = {"url": t["url"].rstrip("/"), "https": True}
        elif st.get("lan"):
            for a in st.get("addresses", []):
                if a.get("kind") in ("hotspot", "lan"):
                    found = {"url": a["url"].rstrip("/"), "https": False}
                    break
    except Exception:
        pass
    _BASE_CACHE.update(t=time.time(), v=found)
    return found


def _lan_base(port):
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return f"http://{s.getsockname()[0]}:{port}"
    except OSError:
        return None


def share_info(request: Request):
    ctl = _control_center_base()
    here = str(request.base_url).rstrip("/")
    local = (request.url.hostname or "") in ("127.0.0.1", "localhost", "::1")
    if ctl and ctl["https"]:
        base = ctl["url"]
    elif not local:
        base = here
    else:
        base = (ctl or {}).get("url") or _lan_base(request.url.port or 8000) or here
    return {"share_base": base, "share_https": base.startswith("https://")}


@app.get("/api/live")
def live(request: Request):
    """Polled every few seconds by open screens: a version that moves when anything changes, plus my unread count."""
    out = {"v": monitor.live_version()}
    user = optional_user(request)
    if user:
        with get_db() as conn:
            out["unread"] = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL",
                                         (user["id"],)).fetchone()[0]
    return out


_DIAG = []


@app.post("/api/client-diag")
async def client_diag(request: Request):
    """Phones report whether they can install (browser, https, service worker, install offered). Kept in memory only."""
    try:
        d = await request.json()
    except Exception:
        return {"ok": False}
    row = {k: (str(d.get(k))[:300] if d.get(k) is not None else None)
           for k in ("ua", "url", "standalone", "secure", "offered", "sw", "path", "when", "installed_here", "manifest", "version",
                     "brands", "mode")}
    row["at"] = time.strftime("%H:%M:%S")
    _DIAG.append(row)
    del _DIAG[:-30]
    return {"ok": True}


@app.post("/api/device-install")
async def device_install(request: Request):
    """An installed AppShare reports itself (installed just now, or opened from the home-screen icon)."""
    try:
        d = await request.json()
    except Exception:
        return {"ok": False}
    user = optional_user(request)
    ok = installs.record(str(d.get("device") or ""), str(d.get("event") or ""), request.headers.get("user-agent", ""),
                         user=user["name"] if user else None, host=request.headers.get("host", ""))
    return {"ok": ok}


@app.get("/api/client-diag")
def client_diag_list(request: Request, token: str = ""):
    if not monitor.allowed(request, token):
        raise HTTPException(403, "Monitor token required")
    return {"items": _DIAG[::-1], "install_fetches": INSTALL_FETCHES[::-1]}


@app.get("/api/live/stream")
async def live_stream(request: Request):
    """Server-sent events: pushes {v, unread} to the screen the moment something changes (a response, a status, a
    notification, an agent's work), and a heartbeat every 15 s so proxies keep the connection open. Screens fall back
    to checking /api/live every few seconds if this stream can't be held open."""
    user = optional_user(request)
    uid = user["id"] if user else None

    def unread():
        if not uid:
            return None
        with get_db() as conn:
            return conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (uid,)).fetchone()[0]

    async def gen():
        yield "retry: 3000\n\n"
        last_v, idle = None, 0.0
        while not await request.is_disconnected():
            v = monitor.live_version()
            if v != last_v or idle >= 15:
                yield f"data: {json.dumps({'v': v, 'unread': unread()})}\n\n"
                last_v, idle = v, 0.0
            await asyncio.sleep(0.4)
            idle += 0.4
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@app.get("/api/qr")
def qr_code(data: str):
    """A QR code for a share link, to show on a projector or another phone."""
    if not data.startswith(("http://", "https://")) or len(data) > 300:
        raise HTTPException(400, "QR codes are only made for web addresses")
    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=8, border=2, dark="#1c1a17", light="#ffffff", xmldecl=False, omitsize=True)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


# --------------------------------------------------------------------------- directory

@app.get("/api/directory")
def directory(q: str = "", user=Depends(current_user)):
    like = f"%{q.strip()}%"
    with get_db() as conn:
        groups = conn.execute(
            "SELECT g.id, g.name, g.kind, g.description, COUNT(gm.user_id) AS members FROM groups g LEFT JOIN group_members gm "
            "ON gm.group_id = g.id WHERE g.name LIKE ? OR g.description LIKE ? GROUP BY g.id ORDER BY g.kind, g.name LIMIT 30", (like, like)).fetchall()
        people = conn.execute(
            "SELECT id, name, email, title FROM users WHERE name LIKE ? OR email LIKE ? OR title LIKE ? ORDER BY name LIMIT 20",
            (like, like, like)).fetchall()
    kinds = VOCAB["group_kinds"]
    return {"groups": [{**dict(g), "kind_label": kinds.get(g["kind"], "Group")} for g in groups], "people": [dict(p) for p in people]}


@app.post("/api/admin/import")
async def import_members(request: Request, user=Depends(current_user)):
    """CSV with columns: email,name,groups[,title]   (groups separated by ';')."""
    if not user["is_admin"]:
        raise HTTPException(403, "Admins only")
    text = (await request.body()).decode("utf-8-sig")
    count = 0
    with get_db() as conn:
        for row in csv.DictReader(io.StringIO(text)):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row.get("email") or "@" not in row["email"]:
                continue
            add_user(conn, row["email"], row.get("name") or row["email"].split("@")[0],
                     [g for g in row.get("groups", "").split(";")], title=row.get("title", ""))
            count += 1
    return {"imported": count}


# --------------------------------------------------------------------------- apps

def load_app(conn, app_id=None, slug=None):
    row = conn.execute("SELECT * FROM apps WHERE slug = ?", (slug,)).fetchone() if slug else \
        conn.execute("SELECT * FROM apps WHERE id = ?", (app_id,)).fetchone()
    if not row:
        raise HTTPException(404, "App not found")
    return row


def require(conn, app_row, user, needed):
    role = access.effective_role(conn, app_row, user["id"])
    if not access.at_least(role, needed):
        monitor.bump("denied")
        monitor.emit("access_denied", user=user["name"], app=app_row["title"], needed=needed, had=role or "no access")
        raise HTTPException(403 if role else 404, "You don't have access to this app" if role else "App not found")
    return role


def _mine_filter(user_id, guest_key):
    if user_id:
        return "user_id = ?", (user_id,)
    return "user_id IS NULL AND guest_key = ?", (guest_key or "-",)


def app_summary(conn, a, user_id, guest_key=None):
    spec = json.loads(a["spec"])
    where, args = _mine_filter(user_id, guest_key)
    mine = conn.execute(f"SELECT status, updated_at FROM submissions WHERE app_id = ? AND {where} ORDER BY id DESC",
                        (a["id"], *args)).fetchall()
    owner = conn.execute("SELECT name FROM users WHERE id = ?", (a["owner_id"],)).fetchone()
    return {
        "id": a["id"], "slug": a["slug"], "title": a["title"], "kind": spec.get("kind"), "theme_color": spec.get("theme_color"),
        "description": (spec.get("description") or "")[:160], "status": a["status"], "window": window_state(spec),
        "closes_at": spec.get("closes_at"), "updated_at": a["updated_at"], "link_access": a["link_access"],
        "role": access.effective_role(conn, a, user_id) if user_id else None, "owner": owner["name"] if owner else "",
        "responses": conn.execute("SELECT COUNT(*) FROM submissions WHERE app_id = ?", (a["id"],)).fetchone()[0],
        "submitted": bool(mine), "my_count": len(mine), "my_status": mine[0]["status"] if mine else None,
        "rules": describe_rules(spec), "many": spec.get("responses_per_person") == "many",
    }


def _shared_with(conn, user_id):
    return conn.execute(
        """SELECT DISTINCT a.* FROM apps a
             LEFT JOIN permissions p ON p.app_id = a.id
             LEFT JOIN group_members gm ON p.principal_type = 'group' AND gm.group_id = p.principal_id
            WHERE a.owner_id != ? AND a.status != 'draft'
              AND ((p.principal_type = 'user' AND p.principal_id = ?) OR gm.user_id = ? OR a.link_access = 'org')
            ORDER BY a.updated_at DESC""", (user_id, user_id, user_id)).fetchall()


@app.get("/api/apps")
def my_apps(user=Depends(current_user)):
    with get_db() as conn:
        mine = conn.execute("SELECT * FROM apps WHERE owner_id = ? ORDER BY updated_at DESC", (user["id"],)).fetchall()
        others = _shared_with(conn, user["id"])
        return {"mine": [_owner_summary(conn, a, user["id"]) for a in mine],
                "shared": [app_summary(conn, a, user["id"]) for a in others]}


def _owner_summary(conn, a, user_id):
    s = app_summary(conn, a, user_id)
    s["audience"] = len(access.audience(conn, a["id"]))
    if json.loads(a["spec"]).get("statuses"):
        first = json.loads(a["spec"])["statuses"][0]
        s["waiting"] = conn.execute("SELECT COUNT(*) FROM submissions WHERE app_id = ? AND status = ?", (a["id"], first)).fetchone()[0]
    return s


@app.get("/api/home")
def home(user=Depends(current_user)):
    """Everything the Home screen needs in one call."""
    with get_db() as conn:
        shared = [app_summary(conn, a, user["id"]) for a in _shared_with(conn, user["id"])]
        mine = [_owner_summary(conn, a, user["id"]) for a in
                conn.execute("SELECT * FROM apps WHERE owner_id = ? ORDER BY updated_at DESC", (user["id"],)).fetchall()]
        unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (user["id"],)).fetchone()[0]
    todo = [s for s in shared if s["status"] == "published" and s["window"] == "open" and not s["submitted"] and not s["many"]]
    todo.sort(key=lambda s: s["closes_at"] or "9999")
    tracked = [s for s in shared if s["many"] and s["my_count"]]
    return {"todo": todo, "shared": shared, "mine": mine, "tracked": tracked, "unread": unread}


@app.get("/api/apps/{app_id}")
def get_app(app_id: int, user=Depends(current_user)):
    with get_db() as conn:
        a = load_app(conn, app_id)
        role = require(conn, a, user, "viewer")
        out = _owner_summary(conn, a, user["id"])
        spec = json.loads(a["spec"])
        spec["look"] = normalize_look(spec.get("look"), spec.get("kind"))
        out.update({"spec": spec, "shares": access.list_shares(conn, a["id"]),
                    "share_suggestions": json.loads(a["share_suggestions"]), "can_edit": access.at_least(role, "editor"),
                    "is_owner": role == "owner"})
        return out


class ShareEntry(BaseModel):
    type: str          # user | group
    id: int
    role: str


class ShareIn(BaseModel):
    entries: list[ShareEntry]
    link_access: str = "restricted"   # restricted | org | public
    publish: bool = True


@app.post("/api/apps/{app_id}/share")
def share_app(app_id: int, body: ShareIn, user=Depends(current_user)):
    if body.link_access not in ("restricted", "org", "public"):
        raise HTTPException(400, "link_access must be restricted, org or public")
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        before = {(r["principal_type"], r["principal_id"]) for r in conn.execute("SELECT * FROM permissions WHERE app_id = ?", (app_id,))}
        conn.execute("DELETE FROM permissions WHERE app_id = ?", (app_id,))
        for e in body.entries:
            if e.role not in access.ROLES or e.type not in ("user", "group"):
                raise HTTPException(400, f"Invalid share entry {e}")
            table = "users" if e.type == "user" else "groups"
            if not conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (e.id,)).fetchone():
                raise HTTPException(400, f"Unknown {e.type} {e.id}")
            if e.type == "user" and e.id == a["owner_id"]:
                continue
            conn.execute("INSERT OR REPLACE INTO permissions (app_id, principal_type, principal_id, role) VALUES (?, ?, ?, ?)",
                         (app_id, e.type, e.id, e.role))
        status = "published" if body.publish and a["status"] == "draft" else a["status"]
        conn.execute("UPDATE apps SET link_access = ?, status = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                     (body.link_access, status, app_id))
        # let newly added people know (once), so it shows up in their inbox
        new_users = set()
        for e in body.entries:
            if (e.type, e.id) in before:
                continue
            if e.type == "user":
                new_users.add(e.id)
            else:
                new_users |= {r[0] for r in conn.execute("SELECT user_id FROM group_members WHERE group_id = ?", (e.id,))}
        new_users.discard(a["owner_id"])
        for uid in new_users:
            conn.execute("INSERT INTO notifications (user_id, app_id, kind, title, body) VALUES (?, ?, 'shared', ?, ?)",
                         (uid, app_id, a["title"], f"{user['name']} shared this with you."))
        shares = access.list_shares(conn, app_id)
        audience = len(access.audience(conn, app_id))
        monitor.bump("shares")
        monitor.emit("app_shared", app_id=app_id, title=a["title"], user=user["name"], audience=audience,
                     targets=[f"{s['name']} ({s['role']})" for s in shares][:8] + (["anyone with the link"] if body.link_access == "public" else []),
                     link_access=body.link_access, published=status == "published" and a["status"] == "draft")
        return {"ok": True, "status": status, "link": f"/a/{a['slug']}", "shares": shares, "audience": audience,
                "link_access": body.link_access}


class StatusIn(BaseModel):
    status: str


@app.post("/api/apps/{app_id}/status")
def set_status(app_id: int, body: StatusIn, user=Depends(current_user)):
    if body.status not in ("published", "closed"):
        raise HTTPException(400, "status must be published or closed")
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        conn.execute("UPDATE apps SET status = ?, updated_at = datetime('now','localtime') WHERE id = ?", (body.status, app_id))
    monitor.emit("app_status", app_id=app_id, title=a["title"], user=user["name"], status=body.status)
    return {"ok": True}


@app.delete("/api/apps/{app_id}")
def delete_app(app_id: int, user=Depends(current_user)):
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "owner")
        paths = [r[0] for r in conn.execute("SELECT stored_path FROM files WHERE app_id = ?", (app_id,))]
        conn.execute("DELETE FROM apps WHERE id = ?", (app_id,))
    monitor.emit("app_deleted", app_id=app_id, title=a["title"], user=user["name"])
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
    return {"ok": True}


# --------------------------------------------------------------------------- play: quizzes, live games, party lights

def _player(conn, slug, request):
    """Who is playing: (app, spec, user, player key, is_host). Same access rules as opening the app."""
    user = optional_user(request)
    a = load_app(conn, slug=slug)
    role = None
    if user:
        role = access.effective_role(conn, a, user["id"])
        if not role and a["link_access"] == "public" and a["status"] != "draft":
            role = "submitter"
        if not role:
            require(conn, a, user, "submitter")
    elif a["link_access"] != "public" or a["status"] == "draft":
        raise HTTPException(401, "Sign in to open this app")
    is_host = bool(role) and access.at_least(role, "editor")
    if a["status"] == "draft" and not is_host:
        raise HTTPException(400, "This app is a draft preview.")
    did = getattr(request.state, "did", None) or request.cookies.get(monitor.DEVICE_COOKIE)
    pkey = f"u{user['id']}" if user else (f"d{did}" if did else None)
    return a, json.loads(a["spec"]), user, pkey, is_host


def _is_live(spec):
    return spec.get("kind") == "party" or (spec.get("quiz") or {}).get("mode") == "host"


@app.get("/api/a/{slug}/live")
def play_view(slug: str, request: Request, host: int = 0):
    with get_db() as conn:
        a, spec, user, pkey, is_host = _player(conn, slug, request)
        if not _is_live(spec):
            raise HTTPException(400, "This app has no live game.")
        if spec.get("kind") == "party" and pkey and not host:
            play.join(conn, a["id"], pkey, "")          # a phone in the room counts and gets a place in the wave
        return play.view(conn, a, spec, None if host else pkey, is_host and bool(host))


class JoinIn(BaseModel):
    name: str


@app.post("/api/a/{slug}/live/join")
def play_join(slug: str, body: JoinIn, request: Request):
    with get_db() as conn:
        a, spec, user, pkey, _ = _player(conn, slug, request)
        if not pkey:
            raise HTTPException(400, "Your browser blocked cookies; allow them to play.")
        name = body.name.strip() or (user["name"].split(" ")[0] if user else "")
        if not name:
            raise HTTPException(400, "Type a nickname to join.")
        if spec.get("anonymous") and user:
            pass                                            # a nickname is all anyone sees
        play.join(conn, a["id"], pkey, name)
    return {"ok": True}


class AnswerIn(BaseModel):
    q: int
    answer: str | list[str]


@app.post("/api/a/{slug}/live/answer")
def play_answer(slug: str, body: AnswerIn, request: Request):
    with get_db() as conn:
        a, spec, user, pkey, _ = _player(conn, slug, request)
        row = conn.execute("SELECT id, name FROM players WHERE app_id = ? AND pkey = ?", (a["id"], pkey)).fetchone() if pkey else None
        if not row or not row["name"]:
            raise HTTPException(400, "Join with a nickname first.")
        try:
            pts = play.answer(conn, a, spec, row["id"], body.q, body.answer)
        except ValueError as e:
            raise HTTPException(400, str(e))
    monitor.emit("quiz_answer", app_id=a["id"], title=a["title"], q=body.q + 1)
    return {"ok": True, "locked": True}          # right or wrong is shown at the reveal, not now


class ControlIn(BaseModel):
    action: str
    scene: str | None = None
    colors: list[str] | None = None
    bpm: int | None = None
    message: str | None = None
    on: bool | None = None


@app.post("/api/apps/{app_id}/live")
def play_control(app_id: int, body: ControlIn, user=Depends(current_user)):
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        spec = json.loads(a["spec"])
        try:
            st = play.control(conn, a, spec, body.action, body.model_dump(exclude_none=True))
        except ValueError as e:
            raise HTTPException(400, str(e))
    monitor.emit("live_control", app_id=app_id, title=a["title"], user=user["name"], action=body.action)
    return {"ok": True, "state": st}


@app.get("/api/a/{slug}/leaderboard")
def quiz_leaderboard(slug: str, request: Request):
    with get_db() as conn:
        a, spec, user, pkey, is_host = _player(conn, slug, request)
        if not spec.get("quiz") or spec["quiz"]["mode"] != "self":
            raise HTTPException(400, "This app has no leaderboard.")
        if not spec["quiz"]["leaderboard"] and not is_host:
            raise HTTPException(403, "The leaderboard is private.")
        return {"leaderboard": [{k: v for k, v in r.items() if k != "sid"} for r in play.leaderboard(conn, a, spec)]}


@app.get("/a/{slug}/host")
def host_page(slug: str):
    return page("host.html")


# --------------------------------------------------------------------------- sites: the owner is in control
# Theme, background, footer and the badge change by tapping (no AI). A suggested extra is written by one small
# AI call only when the owner switches it on; switching it off removes that block. Nothing is ever added unasked.

class SiteLookIn(BaseModel):
    theme: str | None = None
    background: str | None = None
    accent: str | None = None
    footer: str | None = None
    show_badge: bool | None = None


def _site_of(conn, app_id, user):
    a = load_app(conn, app_id)
    require(conn, a, user, "editor")
    spec = json.loads(a["spec"])
    if spec.get("kind") != "site" or not spec.get("site"):
        raise HTTPException(400, "This app isn't a site.")
    return a, spec


@app.post("/api/apps/{app_id}/site/look")
def set_site_look(app_id: int, body: SiteLookIn, user=Depends(current_user)):
    with get_db() as conn:
        a, spec = _site_of(conn, app_id, user)
        site = spec["site"]
        if body.theme is not None:
            if body.theme not in SITE_THEMES:
                raise HTTPException(400, f"theme must be one of {', '.join(SITE_THEMES)}")
            site["theme"] = body.theme
        if body.background is not None:
            if body.background not in SITE_BACKGROUNDS:
                raise HTTPException(400, f"background must be one of {', '.join(SITE_BACKGROUNDS)}")
            site["background"] = body.background
        if body.accent is not None:
            if body.accent and not re.fullmatch(r"#[0-9a-fA-F]{6}", body.accent):
                raise HTTPException(400, "colour must look like #1f5f7a")
            site["accent"] = body.accent
        if body.footer is not None:
            site["footer"] = body.footer.strip()[:200]
        if body.show_badge is not None:
            site["show_badge"] = body.show_badge
        _save_spec(conn, app_id, spec)
    monitor.emit("app_updated", app_id=app_id, title=a["title"], user=user["name"])
    return {"ok": True, "site": site}


class SiteExtraIn(BaseModel):
    type: str
    on: bool
    note: str = ""


@app.post("/api/apps/{app_id}/site/extra")
def toggle_site_extra(app_id: int, body: SiteExtraIn, user=Depends(current_user)):
    with get_db() as conn:
        a, spec = _site_of(conn, app_id, user)
    site = spec["site"]
    first = site["pages"][0]
    if not body.on:                                  # off: remove the extra block(s) of this type — free
        before = sum(len(p["blocks"]) for p in site["pages"])
        for p in site["pages"]:
            p["blocks"] = [b for b in p["blocks"] if not (b.get("extra") and b["type"] == body.type)]
        removed = before - sum(len(p["blocks"]) for p in site["pages"])
    else:
        if body.type not in SITE_BLOCK_TYPES or body.type == "form":
            raise HTTPException(400, "That kind of block can't be added.")
        if any(b.get("extra") and b["type"] == body.type for p in site["pages"] for b in p["blocks"]):
            return {"ok": True, "site": site, "added": None}
        try:
            agents._limit(user["id"], user["name"])
            block = agents.write_site_extra(site, spec["title"], body.type, body.note.strip()[:300], user["name"],
                                            any(f["type"] != "info" for f in spec["fields"]))
        except agents.AgentError as e:
            raise HTTPException(503, str(e))
        blocks = first["blocks"]
        at = next((i for i, b in enumerate(blocks) if b["type"] == "form"), len(blocks))   # extras go above the form
        blocks.insert(at, block)
        removed = 0
    with get_db() as conn:
        a, fresh = _site_of(conn, app_id, user)
        fresh["site"] = site
        _save_spec(conn, app_id, fresh)
    monitor.emit("app_updated", app_id=app_id, title=a["title"], user=user["name"])
    return {"ok": True, "site": site, "added": body.type if body.on else None, "removed": removed}


# --------------------------------------------------------------------------- look: style, pattern, colour, cover
# Changing the design by hand costs no tokens: the owner taps a style, the engine renders it.

class LookIn(BaseModel):
    style: str | None = None
    pattern: str | None = None
    theme_color: str | None = None


def _save_spec(conn, app_id, spec):
    conn.execute("UPDATE apps SET spec = ?, updated_at = datetime('now','localtime') WHERE id = ?", (dumps(spec), app_id))


@app.post("/api/apps/{app_id}/look")
def set_look(app_id: int, body: LookIn, user=Depends(current_user)):
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        spec = json.loads(a["spec"])
        look = normalize_look(spec.get("look"), spec.get("kind"))
        if body.style is not None:
            if body.style not in LOOK_STYLES:
                raise HTTPException(400, f"style must be one of {', '.join(LOOK_STYLES)}")
            look["style"] = body.style
        if body.pattern is not None:
            if body.pattern not in LOOK_PATTERNS:
                raise HTTPException(400, f"pattern must be one of {', '.join(LOOK_PATTERNS)}")
            look["pattern"] = body.pattern
        if body.theme_color is not None:
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", body.theme_color):
                raise HTTPException(400, "colour must look like #1f5f7a")
            if contrast_with_white(body.theme_color) < 4.5:
                raise HTTPException(400, "White text isn't readable on that colour. Pick a darker one.")
            spec["theme_color"] = body.theme_color
        spec["look"] = look
        _save_spec(conn, app_id, spec)
    monitor.emit("app_updated", app_id=app_id, title=a["title"], user=user["name"])
    return {"ok": True, "look": look, "theme_color": spec.get("theme_color")}


COVER_TYPES = {".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".png": [b"\x89PNG"], ".webp": [b"RIFF"]}
COVER_MAX = 5 * 1024 * 1024


def _cover_path(app_id, name):
    return os.path.join(UPLOAD_DIR, str(app_id), name)


@app.post("/api/apps/{app_id}/cover")
async def set_cover(app_id: int, request: Request, user=Depends(current_user)):
    form = await request.form()
    f = form.get("file")
    if f is None or not getattr(f, "filename", ""):
        raise HTTPException(400, "Choose a picture to upload.")
    ext = os.path.splitext(f.filename)[1].lower()
    content = await f.read()
    if ext not in COVER_TYPES:
        raise HTTPException(400, "Use a JPG, PNG or WEBP picture.")
    if len(content) > COVER_MAX:
        raise HTTPException(400, "That picture is larger than 5 MB.")
    if not any(content.startswith(m) for m in COVER_TYPES[ext]) or (ext == ".webp" and content[8:12] != b"WEBP"):
        raise HTTPException(400, "That file doesn't look like a real picture.")
    name = f"cover-{secrets.token_hex(4)}.{'jpg' if ext == '.jpeg' else ext[1:]}"
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        spec = json.loads(a["spec"])
        look = normalize_look(spec.get("look"), spec.get("kind"))
        old = look.get("cover")
        os.makedirs(os.path.dirname(_cover_path(app_id, name)), exist_ok=True)
        with open(_cover_path(app_id, name), "wb") as fh:
            fh.write(content)
        look["cover"] = name
        spec["look"] = look
        _save_spec(conn, app_id, spec)
    if old:
        try:
            os.remove(_cover_path(app_id, old))
        except OSError:
            pass
    monitor.emit("app_updated", app_id=app_id, title=a["title"], user=user["name"])
    return {"ok": True, "look": look}


@app.delete("/api/apps/{app_id}/cover")
def remove_cover(app_id: int, user=Depends(current_user)):
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        spec = json.loads(a["spec"])
        look = normalize_look(spec.get("look"), spec.get("kind"))
        old = look.pop("cover", None)
        spec["look"] = look
        _save_spec(conn, app_id, spec)
    if old:
        try:
            os.remove(_cover_path(app_id, old))
        except OSError:
            pass
    return {"ok": True, "look": look}


@app.get("/api/a/{slug}/cover")
def get_cover(slug: str, request: Request):
    """The cover picture, for exactly the people who may open the app."""
    user = optional_user(request)
    with get_db() as conn:
        a = load_app(conn, slug=slug)
        if user:
            if not access.effective_role(conn, a, user["id"]) and not (a["link_access"] == "public" and a["status"] != "draft"):
                raise HTTPException(404, "Not found")
        elif a["link_access"] != "public" or a["status"] == "draft":
            raise HTTPException(404, "Not found")
        cover = normalize_look(json.loads(a["spec"]).get("look")).get("cover")
    path = _cover_path(a["id"], cover) if cover else None
    if not path or not COVER_RE.fullmatch(cover) or not os.path.exists(path):
        raise HTTPException(404, "No cover picture")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


# --------------------------------------------------------------------------- templates

@app.get("/api/templates")
def list_templates(user=Depends(current_user)):
    out = []
    for t in templates.for_mode():
        spec = t["spec"]
        out.append({"id": t["id"], "name": t["name"], "icon": t["icon"], "blurb": t["blurb"], "prompt": t["prompt"],
                    "kind": spec.get("kind"), "fields": [f["label"] for f in spec["fields"]][:6],
                    "rules": describe_rules({**spec, "show_results": spec.get("show_results", "never")})})
    return {"mode": MODE, "templates": out}


@app.post("/api/templates/{tid}/use")
def use_template(tid: str, user=Depends(current_user)):
    t = templates.find(tid)
    if not t:
        raise HTTPException(404, "Template not found")
    spec, errors = templates.build_spec(t)
    if errors:
        raise HTTPException(500, "; ".join(errors))
    slug = secrets.token_urlsafe(6).replace("_", "x").replace("-", "y")
    link = VOCAB["default_access"]
    with get_db() as conn:
        app_id = conn.execute("INSERT INTO apps (slug, owner_id, title, spec, link_access) VALUES (?, ?, ?, ?, ?)",
                              (slug, user["id"], spec["title"], dumps(spec), link)).lastrowid
        monitor.bump("apps_created")
        monitor.emit("app_created", app_id=app_id, title=spec["title"], user=user["name"], fields=len(spec["fields"]),
                     closes_at=spec["closes_at"], template=tid)
        return get_app_inline(conn, app_id, user)


# --------------------------------------------------------------------------- filling an app

def _capacity(conn, a, spec, exclude_sid=None):
    """Seats left overall and per option (e.g. time slots)."""
    ex = exclude_sid or -1
    total = conn.execute("SELECT COUNT(*) FROM submissions WHERE app_id = ? AND id != ?", (a["id"], ex)).fetchone()[0]
    out = {"taken": total, "max": spec.get("max_responses"),
           "left": (spec["max_responses"] - total) if spec.get("max_responses") else None, "options": {}}
    limited = [f for f in spec["fields"] if f.get("limits")]
    if limited:
        rows = [json.loads(r[0]) for r in conn.execute("SELECT data FROM submissions WHERE app_id = ? AND id != ?", (a["id"], ex))]
        for f in limited:
            counts = {o: 0 for o in f["limits"]}
            for r in rows:
                if r.get(f["id"]) in counts:
                    counts[r[f["id"]]] += 1
            out["options"][f["id"]] = {o: max(0, f["limits"][o] - counts[o]) for o in f["limits"]}
    return out


def _results_allowed(spec, role, has_submitted):
    if role and access.at_least(role, "viewer"):
        return True
    return spec.get("show_results") == "always" or (spec.get("show_results") == "after_submit" and has_submitted)


def _all_data(conn, app_id):
    return [json.loads(r[0]) for r in conn.execute("SELECT data FROM submissions WHERE app_id = ?", (app_id,))]


@app.get("/api/a/{slug}")
def open_app(slug: str, request: Request):
    user = optional_user(request)
    guest_key = getattr(request.state, "did", None) or request.cookies.get(monitor.DEVICE_COOKIE)
    with get_db() as conn:
        a = load_app(conn, slug=slug)
        if user:
            role = access.effective_role(conn, a, user["id"])
            if not role and a["link_access"] == "public":
                role = "submitter"
            if not role:
                require(conn, a, user, "submitter")
        else:
            if a["link_access"] != "public" or a["status"] == "draft":
                raise HTTPException(401, "Sign in to open this app")
            role = "guest"
        spec = json.loads(a["spec"])
        spec["look"] = normalize_look(spec.get("look"), spec.get("kind"))
        editor = bool(user) and access.at_least(access.effective_role(conn, a, user["id"]), "editor")
        full_spec = spec
        spec = play.public_spec(spec, editor)              # quiz answers stay on the server until the reveal
        where, args = _mine_filter(user["id"] if user else None, guest_key)
        mine = conn.execute(f"SELECT * FROM submissions WHERE app_id = ? AND {where} ORDER BY id DESC", (a["id"], *args)).fetchall()
        many = spec.get("responses_per_person") == "many"
        cap = _capacity(conn, a, spec, None if many or not mine else mine[0]["id"])
        state = window_state(spec)
        reason = None
        if a["status"] == "draft":
            reason = "draft"
        elif a["status"] == "closed":
            reason = "closed"
        elif state != "open":
            reason = state
        elif mine and not many and (not spec.get("allow_edit_after_submit", True) or spec.get("quiz")):
            reason = "already"
        elif cap["left"] is not None and cap["left"] <= 0 and (many or not mine):
            reason = "full"
        owner = conn.execute("SELECT name FROM users WHERE id = ?", (a["owner_id"],)).fetchone()
        out = {
            "id": a["id"], "slug": a["slug"], "title": a["title"], "spec": spec, "status": a["status"], "role": role,
            "window": state, "can_manage": bool(user) and access.at_least(access.effective_role(conn, a, user["id"]), "viewer"),
            "owner": owner["name"] if owner else "", "rules": describe_rules(spec), "capacity": cap,
            "can_submit": reason is None, "blocked": reason, "guest": not user, "many": many,
            "my_submission": {"data": json.loads(mine[0]["data"]), "updated_at": mine[0]["updated_at"], "status": mine[0]["status"],
                              "status_note": mine[0]["status_note"]} if mine and not many else None,
            "my_submissions": [{"id": m["id"], "data": json.loads(m["data"]), "created_at": m["created_at"], "status": m["status"],
                                "status_note": m["status_note"]} for m in mine][:20] if many else [],
            "results": summarize(spec, _all_data(conn, a["id"])) if _results_allowed(spec, role if role != "guest" else None, bool(mine)) and not spec.get("quiz") else None,
            "quiz": _quiz_result(conn, a, full_spec, json.loads(mine[0]["data"]), editor, mine[0]["id"]) if mine and not many and full_spec.get("quiz", {}).get("mode") == "self" else None,
            "can_host": editor,
            "org": ORG_NAME, "mode": MODE,
            # questions their account answers (filled in and hidden on the page; filled on the server too)
            "auto": _auto_identity(spec, dict(user) if user else None),
            # transparency for the person answering: is an AI going to read this, and is it anonymous?
            "ai_review": agents.available() and spec.get("ai_review", True) and any(f["type"] in ("file", "long_text") for f in spec["fields"]),
            "anonymous": bool(spec.get("anonymous")),
        }
        return out


def _quiz_result(conn, a, spec, data, editor, sid):
    """A self-paced quiz after playing: score, rank, the leaderboard and (if the owner allows) the right answers."""
    pts, best, _ = play.score(spec, data)
    q = spec["quiz"]
    board = play.leaderboard(conn, a, spec, None)
    mine = next((b for b in board if b["sid"] == sid), None)
    reveal = editor or q["reveal"] == "after_submit" or (q["reveal"] == "end" and window_state(spec) == "closed")
    return {"points": pts, "max": best, "rank": mine["rank"] if mine else None, "players": len(board),
            "leaderboard": [{k: v for k, v in b.items() if k != "sid"} for b in board[:10]] if q["leaderboard"] or editor else None,
            "review": play.review(spec, data) if reveal else None,
            "reveal_later": q["reveal"] == "end" and not reveal}


_NAME_Q = re.compile(r"\bname\b", re.I)
_NOT_PERSON = re.compile(r"\b(team|company|club|project|group|event|organi[sz]ation|school|college|product|app|file|pet|book|"
                        r"song|place|venue|business|brand|course|subject|topic|item|dish|game|nick ?name)\b", re.I)


def _auto_identity(spec, user):
    """Questions the signed-in person's account already answers: {field_id: value}. Their name for a "your name"
    question (not "team name" etc.) and their email for an email question. Never for anonymous apps or guests."""
    if not user or spec.get("anonymous"):
        return {}
    out = {}
    for f in spec["fields"]:
        text = f"{f.get('label', '')} {f.get('id', '').replace('_', ' ')}"
        if f["type"] == "email" and user.get("email"):
            out[f["id"]] = user["email"]
        elif f["type"] == "short_text" and _NAME_Q.search(text) and not _NOT_PERSON.search(text):
            out[f["id"]] = user["name"]
    return out


def _guess_identity(spec, data):
    name = email = None
    for f in spec["fields"]:
        v = data.get(f["id"])
        if not v or not isinstance(v, str):
            continue
        if f["type"] == "email" and not email:
            email = v
        if f["type"] == "short_text" and not name and ("name" in f["id"] or "name" in f["label"].lower()):
            name = v
    return name, email


def _notify_owner(conn, a, name):
    """Tell the owner someone responded — one running note per app, so 60 sign-ups don't mean 60 messages."""
    row = conn.execute("SELECT id, title FROM notifications WHERE user_id = ? AND app_id = ? AND kind = 'response' AND read_at IS NULL "
                       "ORDER BY id DESC LIMIT 1", (a["owner_id"], a["id"])).fetchone()
    latest = f"Latest: {name}." if name else "Open the app to see them."
    if row:
        m = re.match(r"(\d+) new responses", row["title"])
        n = int(m.group(1)) + 1 if m else 2
        conn.execute("UPDATE notifications SET title = ?, body = ?, created_at = datetime('now','localtime') WHERE id = ?",
                     (f"{n} new responses · {a['title']}", latest, row["id"]))
    else:
        conn.execute("INSERT INTO notifications (user_id, app_id, kind, title, body) VALUES (?, ?, 'response', ?, ?)",
                     (a["owner_id"], a["id"], f"New response · {a['title']}", f"{name} responded." if name else "Someone responded."))


@app.post("/api/a/{slug}/submit")
async def submit(slug: str, request: Request):
    user = optional_user(request)
    guest_key = getattr(request.state, "did", None) or request.cookies.get(monitor.DEVICE_COOKIE)
    form = await request.form()
    who = user["name"] if user else "Guest"
    with get_db() as conn:
        a = load_app(conn, slug=slug)
        if user:
            if not (a["link_access"] == "public" and a["status"] != "draft"):
                require(conn, a, user, "submitter")
        elif a["link_access"] != "public":
            raise HTTPException(401, "Sign in to respond")
        spec = json.loads(a["spec"])
        if a["status"] == "draft":
            raise HTTPException(400, "This app is a draft preview. Share it to start collecting responses.")
        if a["status"] == "closed":
            raise HTTPException(400, "This app is closed and no longer accepts responses.")
        state = window_state(spec)
        if state != "open":
            raise HTTPException(400, "The deadline has passed." if state == "closed" else "This app is not open yet.")
        many = spec.get("responses_per_person") == "many"
        where, args = _mine_filter(user["id"] if user else None, guest_key)
        existing = None if many else conn.execute(
            f"SELECT * FROM submissions WHERE app_id = ? AND {where} ORDER BY id DESC", (a["id"], *args)).fetchone()
        if existing and not spec.get("allow_edit_after_submit", True):
            raise HTTPException(400, "You have already responded.")
        if (spec.get("quiz") or {}).get("mode") == "host" or spec.get("kind") == "party":
            raise HTTPException(400, "This is a live game: join it from the app page.")
        if existing and spec.get("quiz"):
            raise HTTPException(400, "You've already played this quiz.")
        old = json.loads(existing["data"]) if existing else {}

        data, errors, uploads, file_errors = {}, [], [], []
        auto = _auto_identity(spec, dict(user) if user else None)
        for f in spec["fields"]:
            if f["type"] == "info":
                continue
            if f["type"] == "file":
                up = form.get(f["id"])
                if up is not None and hasattr(up, "filename") and up.filename:
                    content = await up.read()
                    err = check_file(f, up.filename, content[:8], len(content))
                    if err:
                        errors.append(err)
                        file_errors.append(err)
                    else:
                        uploads.append((f, up.filename, content))
                elif f["id"] in old:
                    data[f["id"]] = old[f["id"]]
                elif f["required"]:
                    errors.append(f"{f['label']} is required")
                continue
            raw = form.getlist(f["id"]) if f["type"] == "checkbox" else form.get(f["id"])
            if f["id"] in auto and not (raw or "").strip():
                raw = auto[f["id"]]                     # the account answers "your name" / "your email"
            value, err = check_value(f, raw)
            if err:
                errors.append(err)
            else:
                data[f["id"]] = value
        cap = _capacity(conn, a, spec, existing["id"] if existing else None)
        if cap["left"] is not None and cap["left"] <= 0:
            errors.append("Sorry, this is full — there are no places left.")
        for fid, left in cap["options"].items():
            choice = data.get(fid)
            if choice in left and left[choice] <= 0:
                errors.append(f"“{choice}” is full. Please choose another option.")
        if errors:
            if file_errors:
                monitor.bump("rejected_uploads")
            monitor.emit("submission_rejected", app_id=a["id"], title=a["title"], user="Someone" if spec.get("anonymous") else who,
                         reasons=errors[:5], blocked_file=bool(file_errors))
            raise HTTPException(422, {"errors": errors})

        gname, gemail = (None, None) if user else _guess_identity(spec, data)
        if existing:
            sub_id = existing["id"]
        else:
            sub_id = conn.execute(
                "INSERT INTO submissions (app_id, user_id, guest_key, guest_name, guest_email, data, status) VALUES (?, ?, ?, ?, ?, '{}', ?)",
                (a["id"], user["id"] if user else None, None if user else guest_key, gname, gemail,
                 spec["statuses"][0] if spec.get("statuses") else None)).lastrowid
            if not user or user["id"] != a["owner_id"]:
                _notify_owner(conn, a, None if spec.get("anonymous") else (user["name"] if user else gname))
        folder = os.path.join(UPLOAD_DIR, str(a["id"]), str(sub_id))
        os.makedirs(folder, exist_ok=True)
        replaced = []
        for f, name, content in uploads:
            safe = "".join(c for c in os.path.basename(name) if c.isalnum() or c in "._- ")[:120] or "file"
            path = os.path.join(folder, f"{secrets.token_hex(4)}_{safe}")
            with open(path, "wb") as fh:
                fh.write(content)
            fid = conn.execute("INSERT INTO files (app_id, submission_id, user_id, field_id, original_name, stored_path, size) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (a["id"], sub_id, user["id"] if user else None, f["id"], name, path, len(content))).lastrowid
            if f["id"] in old:
                replaced.append(old[f["id"]]["file_id"])
            data[f["id"]] = {"file_id": fid, "name": name, "size": len(content)}
        conn.execute("UPDATE submissions SET data = ?, guest_name = COALESCE(?, guest_name), guest_email = COALESCE(?, guest_email), "
                     "updated_at = datetime('now','localtime') WHERE id = ?", (dumps(data), gname, gemail, sub_id))
        for fid in replaced:
            row = conn.execute("SELECT stored_path FROM files WHERE id = ?", (fid,)).fetchone()
            conn.execute("DELETE FROM files WHERE id = ?", (fid,))
            if row:
                try:
                    os.remove(row["stored_path"])
                except OSError:
                    pass
        results = summarize(spec, _all_data(conn, a["id"])) if spec.get("show_results") in ("after_submit", "always") and not spec.get("quiz") else None
        quiz = _quiz_result(conn, a, spec, data, False, sub_id) if spec.get("quiz") else None
    monitor.bump("submissions")
    monitor.emit("submission", app_id=a["id"], title=a["title"], user=who if not spec.get("anonymous") else "Someone",
                 updated=bool(existing), files=[{"name": n, "size": len(c)} for _, n, c in uploads])
    if spec.get("ai_review", True) and any(f["type"] in ("file", "long_text") for f in spec["fields"]):
        agents.review_async(sub_id)      # only where there is something to read (not every poll vote)
    return {"ok": True, "message": spec.get("confirmation_message"), "updated": bool(existing), "results": results, "quiz": quiz,
            "status": spec["statuses"][0] if spec.get("statuses") and not existing else None}


@app.get("/api/files/{file_id}")
def download(file_id: int, user=Depends(current_user)):
    with get_db() as conn:
        f = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not f:
            raise HTTPException(404, "File not found")
        name = f["original_name"]
        if f["user_id"] != user["id"]:
            a = load_app(conn, f["app_id"])
            require(conn, a, user, "viewer")
            if json.loads(a["spec"]).get("anonymous"):          # the name could identify the author
                name = agents.generic_file_name(name)
    return FileResponse(f["stored_path"], filename=name)


# --------------------------------------------------------------------------- responses (owner side)

def _responses(conn, a):
    spec = json.loads(a["spec"])
    anon = spec.get("anonymous")
    rows = conn.execute(
        """SELECT s.*, u.name, u.email, u.title, r.verdict AS review_verdict, r.summary AS review_summary, r.flags AS review_flags,
                  r.evidence AS review_evidence, r.guard AS review_guard, r.decision AS review_decision, r.decided_by AS review_decided_by
             FROM submissions s LEFT JOIN users u ON u.id = s.user_id
             LEFT JOIN reviews r ON r.submission_id = s.id
            WHERE s.app_id = ? ORDER BY s.created_at DESC""", (a["id"],)).fetchall()
    out = []
    for i, r in enumerate(rows):
        if anon:
            name, email, sub = f"Response {len(rows) - i}", "", "anonymous"
        elif r["user_id"]:
            name, email, sub = r["name"], r["email"], r["title"]
        else:
            name, email, sub = r["guest_name"] or "Guest", r["guest_email"] or "", "via public link"
        # anonymous: the day only, never the exact time (in a small group a timestamp can identify who answered)
        when = (lambda t: (t or "")[:10]) if anon else (lambda t: t)
        data = json.loads(r["data"])
        if anon:          # file names can identify the author: keep only the type
            data = {k: ({**v, "name": agents.generic_file_name(v.get("name"))} if isinstance(v, dict) and "file_id" in v else v) for k, v in data.items()}
        out.append({"id": r["id"], "name": name, "email": email, "subtitle": sub, "guest": not r["user_id"],
                    "created_at": when(r["created_at"]), "updated_at": when(r["updated_at"]), "data": data,
                    "status": r["status"], "status_note": r["status_note"],
                    "review": {"verdict": r["review_verdict"], "summary": r["review_summary"],
                               "flags": json.loads(r["review_flags"] or "[]"), "evidence": json.loads(r["review_evidence"] or "null"),
                               "guard": r["review_guard"], "decision": r["review_decision"], "decided_by": r["review_decided_by"]}
                    if r["review_verdict"] else None})
    return out


@app.get("/api/apps/{app_id}/responses")
def responses(app_id: int, user=Depends(current_user)):
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "viewer")
        spec = json.loads(a["spec"])
        done = {r[0] for r in conn.execute("SELECT user_id FROM submissions WHERE app_id = ? AND user_id IS NOT NULL", (app_id,))}
        missing = [p for p in access.audience(conn, app_id) if p["id"] not in done]
        reminders = [dict(r) for r in conn.execute(
            "SELECT stage, sent, created_at FROM reminder_log WHERE app_id = ? ORDER BY created_at DESC LIMIT 5", (app_id,))]
        return {"fields": spec["fields"], "statuses": spec.get("statuses") or [], "anonymous": spec.get("anonymous"),
                "responses": _responses(conn, a), "missing": [{"name": m["name"], "email": m["email"]} for m in missing],
                "reminders": reminders, "agents_available": agents.available()}


@app.get("/api/apps/{app_id}/summary")
def app_summary_tab(app_id: int, user=Depends(current_user)):
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "viewer")
        spec = json.loads(a["spec"])
        rows = conn.execute("SELECT data, status, created_at FROM submissions WHERE app_id = ?", (app_id,)).fetchall()
        by_status = {}
        for r in rows:
            if r["status"]:
                by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_day = {}
        for r in rows:
            by_day[r["created_at"][:10]] = by_day.get(r["created_at"][:10], 0) + 1
        return {"total": len(rows), "audience": len(access.audience(conn, app_id)), "capacity": _capacity(conn, a, spec),
                "questions": summarize(spec, [json.loads(r["data"]) for r in rows]),
                "statuses": [{"name": s, "count": by_status.get(s, 0)} for s in spec.get("statuses") or []],
                "by_day": sorted(by_day.items())[-14:], "anonymous": spec.get("anonymous")}


class RespStatusIn(BaseModel):
    status: str
    note: str = ""


@app.post("/api/apps/{app_id}/responses/{sid}/status")
def set_response_status(app_id: int, sid: int, body: RespStatusIn, user=Depends(current_user)):
    """Move a request along (e.g. Pending -> Approved). The person who sent it is notified."""
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        spec = json.loads(a["spec"])
        if body.status not in (spec.get("statuses") or []):
            raise HTTPException(400, f"Status must be one of: {', '.join(spec.get('statuses') or [])}")
        s = conn.execute("SELECT * FROM submissions WHERE id = ? AND app_id = ?", (sid, app_id)).fetchone()
        if not s:
            raise HTTPException(404, "Response not found")
        conn.execute("UPDATE submissions SET status = ?, status_note = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                     (body.status, body.note.strip()[:300] or None, sid))
        if s["user_id"]:
            conn.execute("INSERT INTO notifications (user_id, app_id, kind, title, body) VALUES (?, ?, 'status', ?, ?)",
                         (s["user_id"], app_id, f"{a['title']}: {body.status}",
                          (body.note.strip() or f"{user['name']} marked your request as {body.status}.")[:300]))
        monitor.emit("status_changed", app_id=app_id, title=a["title"], user=user["name"], status=body.status)
    return {"ok": True}


class DecisionIn(BaseModel):
    decision: str          # confirmed | dismissed


@app.post("/api/apps/{app_id}/responses/{sid}/review-decision")
def review_decision(app_id: int, sid: int, body: DecisionIn, user=Depends(current_user)):
    """An AI flag is never a decision: a person confirms or dismisses it, and that is recorded with their name."""
    if body.decision not in ("confirmed", "dismissed"):
        raise HTTPException(400, "decision must be confirmed or dismissed")
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        if not conn.execute("SELECT 1 FROM reviews WHERE submission_id = ? AND app_id = ?", (sid, app_id)).fetchone():
            raise HTTPException(404, "No review for this response")
        conn.execute("UPDATE reviews SET decision = ?, decided_by = ?, decided_at = datetime('now','localtime') WHERE submission_id = ?",
                     (body.decision, user["name"], sid))
    monitor.emit("review_decided", app_id=app_id, title=a["title"], user=user["name"], decision=body.decision)
    return {"ok": True}


@app.post("/api/apps/{app_id}/remind")
def remind_now(app_id: int, user=Depends(current_user)):
    """The Reminder agent nudges everyone who hasn't responded yet."""
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "editor")
        if a["status"] != "published":
            raise HTTPException(400, "Share the app first; reminders go to the people it is shared with.")
    if not agents.available():
        return {"error": "The Reminder agent needs a Claude API key. Add one in the Control Center."}
    try:
        out = agents.run_reminder(app_id, f"manual-{int(time.time())}", triggered_by=user["name"])
    except agents.AgentError as e:
        return {"error": str(e)}
    return {"reply": out["reply"], "sent": out["sent"]}


@app.post("/api/apps/{app_id}/review-pending")
def review_pending(app_id: int, user=Depends(current_user)):
    """Ask the Review agent to read every response that has no review yet."""
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "viewer")
        ids = [r[0] for r in conn.execute("SELECT s.id FROM submissions s LEFT JOIN reviews r ON r.submission_id = s.id "
                                          "WHERE s.app_id = ? AND r.submission_id IS NULL", (app_id,))]
    if not agents.available():
        raise HTTPException(400, "The agents need a Claude API key. Add one in the Control Center.")
    for sid in ids:
        agents.review_async(sid)
    return {"queued": len(ids)}


@app.get("/api/apps/{app_id}/export.csv")
def export_csv(app_id: int, user=Depends(current_user)):
    with get_db() as conn:
        a = load_app(conn, app_id)
        require(conn, a, user, "viewer")
        spec = json.loads(a["spec"])
        fields = [f for f in spec["fields"] if f["type"] != "info"]
        rows = _responses(conn, a)
    buf = io.StringIO()
    w = csv.writer(buf)
    head = (["Response"] if spec.get("anonymous") else ["Name", "Email"]) + ["Submitted", "Last updated"] + \
        (["Status", "Note"] if spec.get("statuses") else []) + [f["label"] for f in fields]
    w.writerow(head)
    for r in rows:
        vals = []
        for f in fields:
            v = r["data"].get(f["id"], "")
            vals.append(v.get("name", "") if isinstance(v, dict) else "; ".join(v) if isinstance(v, list) else v)
        who = [r["name"]] if spec.get("anonymous") else [r["name"], r["email"]]
        w.writerow(who + [r["created_at"], r["updated_at"]] + ([r["status"] or "", r["status_note"] or ""] if spec.get("statuses") else []) + vals)
    name = "".join(c for c in a["title"] if c.isalnum() or c in " -_").strip() or "responses"
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


# --------------------------------------------------------------------------- notifications

@app.get("/api/notifications")
def notifications(user=Depends(current_user)):
    with get_db() as conn:
        rows = conn.execute("""SELECT n.*, a.slug, a.owner_id FROM notifications n LEFT JOIN apps a ON a.id = n.app_id
                                WHERE n.user_id = ? ORDER BY n.id DESC LIMIT 40""", (user["id"],)).fetchall()
        unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (user["id"],)).fetchone()[0]
    return {"unread": unread, "items": [{**dict(r), "mine": r["owner_id"] == user["id"]} for r in rows]}


@app.post("/api/notifications/read")
def notifications_read(user=Depends(current_user)):
    with get_db() as conn:
        conn.execute("UPDATE notifications SET read_at = datetime('now','localtime') WHERE user_id = ? AND read_at IS NULL", (user["id"],))
    return {"ok": True}


def _reminder_scheduler():
    """Every minute: remind people 24 hours and 2 hours before each open deadline (once per stage)."""
    import threading

    def loop():
        while True:
            time.sleep(60)
            if not agents.available():
                continue
            try:
                due = []
                with get_db() as conn:
                    for a in conn.execute("SELECT id, spec FROM apps WHERE status = 'published'").fetchall():
                        spec = json.loads(a["spec"])
                        if not spec.get("closes_at") or window_state(spec) != "open":
                            continue
                        hours = (datetime.strptime(spec["closes_at"], "%Y-%m-%dT%H:%M") - datetime.now()).total_seconds() / 3600
                        stage = "hour" if hours <= 2 else "day" if hours <= 24 else None
                        if stage and not conn.execute("SELECT 1 FROM reminder_log WHERE app_id = ? AND stage = ?", (a["id"], stage)).fetchone():
                            conn.execute("INSERT INTO reminder_log (app_id, stage) VALUES (?, ?)", (a["id"], stage))
                            due.append((a["id"], stage))
                for app_id, stage in due:
                    try:
                        agents.run_reminder(app_id, stage)
                    except agents.AgentError:
                        pass
            except Exception as e:  # the scheduler must never die
                print("reminder scheduler:", e)

    threading.Thread(target=loop, daemon=True, name="reminders").start()


_reminder_scheduler()


# --------------------------------------------------------------------------- agents

class AgentIn(BaseModel):
    message: str
    session_id: int | None = None
    app_id: int | None = None


@app.post("/api/agent/session")
def agent_session(body: dict | None = None, user=Depends(current_user)):
    """Create a builder conversation first, so the phone can follow its progress while the team works."""
    app_id = (body or {}).get("app_id")
    with get_db() as conn:
        if app_id:
            require(conn, load_app(conn, app_id), user, "editor")
        s = agents.load_session(conn, None, user["id"], "builder", app_id)
    return {"session_id": s["id"], "cursor": monitor.latest_id()}


@app.get("/api/agent/progress")
def agent_progress(session_id: int, after: int = 0, user=Depends(current_user)):
    """The live steps of the agent team for one conversation (Builder + its specialists)."""
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM agent_sessions WHERE id = ? AND user_id = ?", (session_id, user["id"])).fetchone():
            raise HTTPException(404, "Unknown session")
    return agents.progress(session_id, after)


@app.post("/api/agent/build")
def agent_build(body: AgentIn, user=Depends(current_user)):
    with get_db() as conn:
        if body.app_id and not body.session_id:
            require(conn, load_app(conn, body.app_id), user, "editor")
        session = agents.load_session(conn, body.session_id, user["id"], "builder", body.app_id)
        if body.app_id and not session["app_id"]:
            session["app_id"] = body.app_id
        try:
            reply, error = agents.run_builder(conn, user, session, body.message), None
        except agents.AgentError as e:
            agents.store_session(conn, session)
            reply, error = None, str(e)
        app_out = get_app_inline(conn, session["app_id"], user) if session["app_id"] else None
    return {"session_id": session["id"], "reply": reply, "error": error, "app": app_out, "app_changed": session["saved"]}


def get_app_inline(conn, app_id, user):
    a = load_app(conn, app_id)
    out = _owner_summary(conn, a, user["id"])
    out.update({"spec": json.loads(a["spec"]), "share_suggestions": json.loads(a["share_suggestions"]),
                "shares": access.list_shares(conn, a["id"])})
    return out


@app.post("/api/agent/insights")
def agent_insights(body: AgentIn, user=Depends(current_user)):
    if not body.app_id:
        raise HTTPException(400, "app_id is required")
    with get_db() as conn:
        a = load_app(conn, body.app_id)
        require(conn, a, user, "viewer")
        session = agents.load_session(conn, body.session_id, user["id"], "insights", a["id"])
        if session["app_id"] != a["id"]:
            session = agents.load_session(conn, None, user["id"], "insights", a["id"])
        try:
            reply, error = agents.run_insights(conn, a, session, body.message, user["name"], user["id"]), None
        except agents.AgentError as e:
            agents.store_session(conn, session)
            reply, error = None, str(e)
    return {"session_id": session["id"], "reply": reply, "error": error}


# --------------------------------------------------------------------------- heartbeat + monitor

@app.get("/api/ping")
def ping(request: Request):
    """Phones call this every few seconds: keeps them 'online' in the monitor and lets them auto-reconnect."""
    body = {"ok": True, "app": "appshare", "server": monitor.SERVER_NAME, "version": VERSION, "time": int(time.time() * 1000)}
    if request.headers.get("x-appshare-control"):      # the Control Center's own health check
        return body
    with get_db() as conn:
        user = monitor.user_for_token(conn, request.cookies.get("session"))
    did = request.cookies.get(monitor.DEVICE_COOKIE)
    new_did = None if did else secrets.token_urlsafe(9)
    device, is_new = monitor.touch_device(request, user, count_request=False, did=did or new_did)
    if is_new:
        monitor.emit("device_new", device=device["id"], device_kind=device["kind"], device_label=device["label"], user=user, via=device["via"])
    resp = JSONResponse(body)
    if new_did:
        resp.set_cookie(monitor.DEVICE_COOKIE, new_did, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
    return resp


def _db_stats(conn):
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]   # noqa: E731
    by_status = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM apps GROUP BY status")}
    apps = []
    for a in conn.execute("SELECT a.*, u.name AS owner FROM apps a JOIN users u ON u.id = a.owner_id ORDER BY a.updated_at DESC LIMIT 30").fetchall():
        spec = json.loads(a["spec"])
        apps.append({"id": a["id"], "title": a["title"], "owner": a["owner"], "status": a["status"], "kind": spec.get("kind"),
                     "window": window_state(spec), "closes_at": spec.get("closes_at"), "slug": a["slug"],
                     "responses": one("SELECT COUNT(*) FROM submissions WHERE app_id = ?", a["id"]),
                     "audience": len(access.audience(conn, a["id"])), "files": one("SELECT COUNT(*) FROM files WHERE app_id = ?", a["id"]),
                     "shares": [s["name"] for s in access.list_shares(conn, a["id"])][:5] + (["anyone with the link"] if a["link_access"] == "public" else [])})
    return {"users": one("SELECT COUNT(*) FROM users"), "groups": one("SELECT COUNT(*) FROM groups"),
            "apps_total": sum(by_status.values()), "apps_by_status": by_status, "submissions": one("SELECT COUNT(*) FROM submissions"),
            "files": one("SELECT COUNT(*) FROM files"), "files_bytes": one("SELECT COALESCE(SUM(size), 0) FROM files"),
            "db_bytes": os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0, "sessions": one("SELECT COUNT(*) FROM sessions"), "apps": apps}


@app.get("/api/monitor/snapshot")
def monitor_snapshot(request: Request, token: str = ""):
    if not monitor.allowed(request, token):
        raise HTTPException(403, "Monitor is only available on the server laptop")
    with get_db() as conn:
        db = _db_stats(conn)
    return {"server": {"name": monitor.SERVER_NAME, "version": VERSION, "org": ORG_NAME, "mode": MODE, "pid": os.getpid(),
                       "started_at": int(monitor.STARTED_AT * 1000), "now": int(time.time() * 1000),
                       "agent_model": agents.MODEL, "agent_effort": agents.EFFORT, "api_key": agents.available(),
                       "ai": agents.providers.describe()},
            "counters": monitor.counters(), "series": monitor.series(30), "devices": monitor.devices(), "db": db,
            "installs": installs.summary(),
            "events": monitor.events_after(0, 200), "latest_id": monitor.latest_id(),
            "limits": limits.status(), "alerts": limits.alerts()}


@app.get("/api/trace/journeys")
def trace_journeys(request: Request, token: str = "", limit: int = 50):
    """Every app's journey (newest activity first) with measured totals: the Flow dashboard's list."""
    if not monitor.allowed(request, token):
        raise HTTPException(403, "Traces are only available on the server laptop")
    return {"journeys": trace.list_journeys(max(1, min(limit, 200))), "health": trace.health()}


@app.get("/api/trace/journeys/{jid}")
def trace_journey(jid: str, request: Request, token: str = ""):
    """One journey in full: runs, every step (model calls, tools, Validator, retries), app events and parameters."""
    if not monitor.allowed(request, token):
        raise HTTPException(403, "Traces are only available on the server laptop")
    j = trace.get_journey(jid)
    if not j:
        raise HTTPException(404, "No such journey")
    j["app_now"] = None
    if j.get("app_id"):
        with get_db() as conn:
            a = conn.execute("SELECT id, slug, status, link_access FROM apps WHERE id = ?", (j["app_id"],)).fetchone()
            if a:
                one = lambda q: conn.execute(q, (a["id"],)).fetchone()[0]
                verdicts = {r[0]: r[1] for r in conn.execute("SELECT verdict, COUNT(*) FROM reviews WHERE app_id = ? GROUP BY verdict", (a["id"],))}
                j["app_now"] = {"status": a["status"], "link_access": a["link_access"], "link": f"/a/{a['slug']}",
                                "responses": one("SELECT COUNT(*) FROM submissions WHERE app_id = ?"),
                                "responders": one("SELECT COUNT(DISTINCT COALESCE(user_id, -id)) FROM submissions WHERE app_id = ?"),
                                "audience": len(access.audience(conn, a["id"])), "reviews": verdicts,
                                "reminded": one("SELECT COALESCE(SUM(sent), 0) FROM reminder_log WHERE app_id = ?")}
    return j


@app.get("/api/apps/{app_id}/story")
def app_story(app_id: int, user=Depends(current_user)):
    """'How this app was built' for the people who can edit it: what each agent decided and its stated reason."""
    with get_db() as conn:
        require(conn, load_app(conn, app_id), user, "editor")
    return trace.story(app_id)


@app.get("/api/trace/journeys/{jid}/events")
def trace_round_events(jid: str, request: Request, round: int = 1, token: str = ""):
    """A saved build round turned back into the live events the Agent theater animates (same describe_* functions,
    real timestamps), so a Flow replay can play in the theater in step. Nothing is re-run."""
    if not monitor.allowed(request, token):
        raise HTTPException(403, "Traces are only available on the server laptop")
    j = trace.get_journey(jid)
    if not j:
        raise HTTPException(404, "No such journey")
    b = next((r for r in j["runs"] if r["agent"] == "builder" and r["round"] == round), None)
    if not b:
        raise HTTPException(404, "No such round")
    runs = [b] + [r for r in j["runs"] if r["parent_id"] == b["id"]]
    evs = []
    for r in runs:
        tag = {"run_id": r["id"], "agent": r["agent"], "replay": True, "recorded": True}
        evs.append({"ts": r["started_at"], "type": "agent_start", **tag, "user": j["owner"], "message": r["input"],
                    "app": j["title"], "parent": r["parent_id"]})
        for s in r["steps"]:
            d = s["detail"] or {}
            if s["kind"] == "llm":
                evs.append({"ts": s["started_at"], "type": "agent_llm_start", **tag, "step": s["loop_step"], "model": s["model"]})
                evs.append({"ts": s["started_at"] + (s["ms"] or 0), "type": "agent_llm_end", **tag, "step": s["loop_step"], "ms": s["ms"],
                            "tokens_in": (s["tokens_in"] or 0) + (s["cache_read"] or 0) + (s["cache_write"] or 0),
                            "tokens_out": s["tokens_out"] or 0, "stop_reason": s["stop_reason"], "model": s["model"]})
            elif s["kind"] == "tool":
                args, res = d.get("args") or {}, d.get("result") or {}
                evs.append({"ts": s["started_at"], "type": "agent_tool", **tag, "step": s["loop_step"], "tool": s["name"],
                            **agents.describe_call(s["name"], args)})
                try:
                    out = agents.describe_result(s["name"], res, not s["ok"])
                except Exception:  # noqa: BLE001 — a redacted result may lack a field: show it plainly
                    out = {"ok": bool(s["ok"]), "summary": "done" if s["ok"] else "returned an error"}
                evs.append({"ts": s["started_at"] + (s["ms"] or 0), "type": "agent_tool_result", **tag, "step": s["loop_step"],
                            "tool": s["name"], **out})
        end = r["ended_at"] or r["started_at"]
        if r["status"] == "ok":
            evs.append({"ts": end, "type": "agent_reply", **tag, "text": r["output"], "ms": r["ms"], "parent": r["parent_id"]})
        else:
            evs.append({"ts": end, "type": "agent_error", **tag, "error": r["error"] or r["status"]})
    evs.sort(key=lambda e: e["ts"])
    return {"t0": b["started_at"], "title": j["title"], "round": round, "events": evs}


@app.get("/api/trace/prompts/{sha}")
def trace_prompt(sha: str, request: Request, token: str = ""):
    """The exact instructions and tool list an agent run had."""
    if not monitor.allowed(request, token):
        raise HTTPException(403, "Traces are only available on the server laptop")
    p = trace.get_prompt(sha)
    if not p:
        raise HTTPException(404, "No such prompt")
    return p


@app.get("/api/monitor/stream")
async def monitor_stream(request: Request, token: str = "", after: int = -1):
    """Server-Sent Events: every monitor event as it happens."""
    if not monitor.allowed(request, token):
        raise HTTPException(403, "Monitor is only available on the server laptop")

    async def gen():
        last = monitor.latest_id() if after < 0 else after
        idle = 0.0
        yield "retry: 1500\n\n"
        while not await request.is_disconnected():
            batch = monitor.events_after(last)
            for ev in batch:
                last = ev["id"]
                yield f"id: {ev['id']}\ndata: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
            if batch:
                idle = 0.0
            else:
                idle += 0.2
                if idle >= 15:
                    idle = 0.0
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- pages

_FP = {}     # path -> (mtime, fingerprint)


def _fingerprint(url_path):
    """A short hash of the file behind /static/… or /agents/…, recomputed only when the file changes."""
    fs = os.path.join(STATIC, url_path[len("/static/"):]) if url_path.startswith("/static/") else \
        os.path.join(BASE_DIR, "launcher", "ui", url_path[len("/agents/"):])
    try:
        m = os.path.getmtime(fs)
    except OSError:
        return None
    hit = _FP.get(url_path)
    if hit and hit[0] == m:
        return hit[1]
    import hashlib
    with open(fs, "rb") as f:
        fp = hashlib.sha1(f.read()).hexdigest()[:10]
    _FP[url_path] = (m, fp)
    return fp


def page(name):
    """Serve a page with every script/stylesheet link stamped with its file's fingerprint, so a phone downloads a file
    once and keeps it until it really changes (and gets the new one immediately when it does)."""
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        html_text = f.read()

    def stamp(m):
        fp = _fingerprint(m.group(2))
        return f'{m.group(1)}="{m.group(2)}?v={fp}"' if fp else m.group(0)
    html_text = re.sub(r'(src|href)="(/(?:static|agents)/[^"?#]+\.(?:js|css))"', stamp, html_text)
    return Response(html_text, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


@app.get("/")
def index_page(request: Request):
    if not request.cookies.get("session"):
        return RedirectResponse("/login")
    return page("index.html")


@app.get("/login")
def login_page():
    return page("login.html")


@app.get("/install")
def install_page():
    """Where the Control Center's QR code leads: gets any phone from 'scanned it' to 'installed' in one or two taps."""
    return page("install.html")


@app.get("/manifest.webmanifest")
def manifest(request: Request):
    """The install file. Built per request so it can name its own address (lets the page detect an installed app)."""
    with open(os.path.join(STATIC, "manifest.webmanifest"), encoding="utf-8") as fh:
        data = json.load(fh)
    here = str(request.base_url).rstrip("/")
    data["related_applications"] = [{"platform": "webapp", "url": here + "/manifest.webmanifest"}]
    return JSONResponse(data, media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def service_worker():
    return FileResponse(os.path.join(STATIC, "sw.js"), media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/agents/characters.js")
def characters_js():
    """The agents' portraits are shared with the Control Center."""
    return FileResponse(os.path.join(BASE_DIR, "launcher", "ui", "characters.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/a/{slug}")
def app_page(slug: str):
    return page("app.html")


@app.get("/manage/{app_id}")
def manage_page(app_id: int):
    return page("manage.html")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse(f"/login?next={request.url.path}")
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
