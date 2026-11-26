"""AppShare Control Center (runs only on the server laptop, http://127.0.0.1:7000).

It starts and stops the AppShare server as a child process, streams its logs,
finds the addresses phones can use, makes QR codes, and can open an internet
(HTTPS) tunnel with ngrok so the installed phone app works from anywhere.
"""
import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections import deque

import segno
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
DATA_DIR = os.environ.get("APPSHARE_DATA", os.path.join(ROOT, "data"))
ENV_FILE = os.path.join(ROOT, ".env")
APP_PORT = int(os.environ.get("APPSHARE_PORT", "8000"))
CONTROL_PORT = int(os.environ.get("APPSHARE_CONTROL_PORT", "7000"))
HOTSPOT_IP = "192.168.137.1"   # Windows Mobile Hotspot always gives the laptop this address
MODES = {
    "university": {"label": "University", "org": "Riverside University",
                   "blurb": "Departments, sections, faculty and students. Feedback, registrations, lab slots, polls, requests."},
    "office": {"label": "Office", "org": "Northwind Labs",
               "blurb": "Teams and managers. Leave and IT requests, expense claims, pulse surveys, workshops."},
    "general": {"label": "General", "org": "AppShare",
                "blurb": "Anyone, anywhere. RSVPs, polls, sign-ups and feedback shared by link, like a Doc."},
}


# --------------------------------------------------------------------------- helpers

def read_env_file():
    values = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def write_env_value(key, value):
    values = read_env_file()
    values[key] = value
    with open(ENV_FILE, "w", encoding="utf-8") as fh:
        fh.write("# Local settings for AppShare. Keep this file private; it is in .gitignore.\n")
        for k, v in values.items():
            fh.write(f"{k}={v}\n")


def current_mode():
    mode = (os.environ.get("APPSHARE_MODE") or read_env_file().get("APPSHARE_MODE") or "university").strip().lower()
    return mode if mode in MODES else "university"


def mode_dir(mode=None):
    return os.path.join(DATA_DIR, mode or current_mode())


def port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def ping_app(timeout=0.8):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{APP_PORT}/api/ping", headers={"X-AppShare-Control": "1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("app") == "appshare"
    except Exception:
        return False


def lan_addresses():
    """IPv4 addresses phones could use to reach this laptop."""
    found = []
    primary = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # no packet is sent; this just picks the main interface
            primary = s.getsockname()[0]
    except OSError:
        pass
    ips = set([primary] if primary else [])
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    for ip in sorted(ips, key=lambda i: (i != primary, i)):
        if ip.startswith(("127.", "169.254.")):
            continue
        if ip == HOTSPOT_IP:
            found.append({"ip": ip, "kind": "hotspot", "label": "Laptop hotspot", "fixed": True})
        else:
            found.append({"ip": ip, "kind": "lan", "label": "Wi-Fi / LAN" + ("" if ip == primary else " (other adapter)"),
                          "fixed": False})
    return found


# --------------------------------------------------------------------------- the AppShare server process

class ServerProcess:
    def __init__(self):
        self.proc = None
        self.state = "off"          # off | starting | online | stopping | crashed | external
        self.started_at = None
        self.lan = True
        self.token = secrets.token_urlsafe(24)
        self.logs = deque(maxlen=500)
        self.log_seq = 0
        self.exit_code = None
        self.error = None
        self.session_key = None     # API key typed into the Control Center (memory only)
        self.session_groq_key = None
        self.lock = threading.Lock()

    def log(self, line, source="server"):
        with self.lock:
            self.log_seq += 1
            self.logs.append({"seq": self.log_seq, "ts": int(time.time() * 1000), "line": line.rstrip(), "src": source})

    def api_key(self):
        if self.session_key:
            return self.session_key, "this session"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return os.environ["ANTHROPIC_API_KEY"], "environment"
        file_key = read_env_file().get("ANTHROPIC_API_KEY")
        if file_key:
            return file_key, ".env file"
        return None, None

    def start(self, lan=True):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return
        if port_open(APP_PORT):
            if ping_app():
                self.state = "external"
                raise HTTPException(409, f"An AppShare server is already running on port {APP_PORT} "
                                         "(started outside the Control Center). Stop it first.")
            raise HTTPException(409, f"Port {APP_PORT} is used by another program.")
        env = dict(os.environ)
        env.update({"APPSHARE_MONITOR_TOKEN": self.token, "PYTHONUNBUFFERED": "1",
                    "APPSHARE_CONTROL_PORT": str(CONTROL_PORT), "APPSHARE_PARENT_PID": str(os.getpid())})
        for k, v in read_env_file().items():
            env.setdefault(k, v)
        env["APPSHARE_MODE"] = current_mode()
        key, _ = self.api_key()
        if key:
            env["ANTHROPIC_API_KEY"] = key
        gkey, _ = groq_key()
        if gkey:
            env["GROQ_API_KEY"] = gkey
        cmd = [sys.executable, "-m", "uvicorn", "backend.main:app",
               "--host", "0.0.0.0" if lan else "127.0.0.1", "--port", str(APP_PORT)]
        self.lan, self.exit_code, self.error = lan, None, None
        self.log(f"$ python -m uvicorn backend.main:app --host {'0.0.0.0' if lan else '127.0.0.1'} --port {APP_PORT}",
                 "control")
        self.proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.state, self.started_at = "starting", time.time()
        threading.Thread(target=self._read_output, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._watch, args=(self.proc,), daemon=True).start()

    def _read_output(self, proc):
        for line in proc.stdout:
            self.log(line)

    def _watch(self, proc):
        while proc.poll() is None:
            if self.state == "starting" and ping_app():
                self.state = "online"
                self.log("Server is online. Phones can connect now.", "control")
            time.sleep(0.25)
        self.exit_code = proc.returncode
        if self.state == "stopping":
            self.state = "off"
            self.log("Server stopped.", "control")
        else:
            self.state = "crashed"
            self.error = f"The server stopped unexpectedly (exit code {proc.returncode}). See the log."
            self.log(self.error, "control")

    def stop(self):
        proc = self.proc
        if not proc or proc.poll() is not None:
            self.state = "off"
            return
        self.state = "stopping"
        self.log("Stopping server…", "control")
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()

    def refresh_external(self):
        if (not self.proc or self.proc.poll() is not None) and self.state in ("off", "external", "crashed"):
            if ping_app(0.4):
                self.state = "external"
            elif self.state == "external":
                self.state = "off"


# --------------------------------------------------------------------------- ngrok tunnel (optional)

class Tunnel:
    """An HTTPS address for phones. Needed to install the app, and it makes shared links work from anywhere.
    Providers, best first:
    - tailscale: Tailscale Funnel. Free, the address never changes, no warning page. Needs a one-time sign-in.
    - cloudflared: Cloudflare quick tunnel. Free, no account, no warning page; the address changes on every start.
    - ngrok: fixed address with a free static domain, but the free plan shows a warning page first, which also
      stops Android from installing the app (Google's install server can't click "Visit Site")."""
    PROVIDERS = ("tailscale", "cloudflared", "ngrok")
    TAILSCALE_PATHS = (r"C:\Program Files\Tailscale\tailscale.exe", r"C:\Program Files (x86)\Tailscale\tailscale.exe")

    def __init__(self):
        self.proc = None
        self.url = None
        self.state = "off"      # off | starting | online | error
        self.error = None
        self.provider = None
        self.action_url = None  # a link the person must open (e.g. to sign in or enable Funnel)
        env = read_env_file()
        self.domain = env.get("APPSHARE_NGROK_DOMAIN") or os.environ.get("APPSHARE_NGROK_DOMAIN") or ""
        self.choice = env.get("APPSHARE_TUNNEL") or "auto"

    # ---------------------------------------------------------------- what is installed
    @staticmethod
    def has_ngrok():
        return shutil.which("ngrok") is not None

    @staticmethod
    def has_cloudflared():
        return shutil.which("cloudflared") is not None

    @classmethod
    def tailscale_exe(cls):
        return shutil.which("tailscale") or next((p for p in cls.TAILSCALE_PATHS if os.path.exists(p)), None)

    @classmethod
    def tailscale_status(cls):
        """{'installed', 'signed_in', 'name'} — name is this laptop's fixed Tailscale address."""
        exe = cls.tailscale_exe()
        if not exe:
            return {"installed": False, "signed_in": False, "name": None}
        try:
            out = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=6)
            st = json.loads(out.stdout or "{}")
            name = ((st.get("Self") or {}).get("DNSName") or "").rstrip(".")
            return {"installed": True, "signed_in": st.get("BackendState") == "Running" and bool(name), "name": name or None}
        except Exception:
            return {"installed": True, "signed_in": False, "name": None}

    @classmethod
    def available(cls):
        return cls.has_ngrok() or cls.has_cloudflared() or bool(cls.tailscale_exe())

    def pick(self, choice):
        if choice in self.PROVIDERS:
            return choice
        ts = self.tailscale_status()
        if ts["signed_in"]:
            return "tailscale"
        if self.has_cloudflared():
            return "cloudflared"
        if self.has_ngrok():
            return "ngrok"
        if ts["installed"]:
            return "tailscale"
        return None

    # ---------------------------------------------------------------- start / stop
    def start(self, domain="", provider=None):
        if not self.available():
            raise HTTPException(400, "No tunnel tool is installed. Easiest: run 'winget install Cloudflare.cloudflared' "
                                     "(free, no account), or install Tailscale for a fixed address.")
        self.stop()              # also clears any tunnel left over from before
        if provider:
            self.choice = provider
            write_env_value("APPSHARE_TUNNEL", provider)
        domain = (domain or self.domain or "").strip().replace("https://", "").replace("http://", "").strip("/")
        if domain:
            self.domain = domain
            write_env_value("APPSHARE_NGROK_DOMAIN", domain)
        self.provider = self.pick(self.choice)
        self.state, self.url, self.error, self.action_url = "starting", None, None, None
        if self.provider == "tailscale":
            threading.Thread(target=self._start_tailscale, daemon=True).start()
            return
        if self.provider == "ngrok":
            cmd = ["ngrok", "http", str(APP_PORT), "--log", "stdout", "--log-format", "logfmt"]
            if domain:
                cmd += ["--url", domain]
        else:
            cmd = ["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{APP_PORT}"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        if self.provider == "ngrok":
            threading.Thread(target=self._find_url, args=(self.proc,), daemon=True).start()

    def _start_tailscale(self):
        import re
        exe = self.tailscale_exe()
        ts = self.tailscale_status()
        if not ts["signed_in"]:
            self.state = "error"
            self.error = "Tailscale is installed but not signed in. Open Tailscale from the Start menu (or the tray icon) and sign in, then try again."
            self.action_url = "https://login.tailscale.com/start"
            return
        try:
            # --bg keeps Funnel running by itself; the address is this laptop's fixed name, e.g. https://laptop.tailnet.ts.net
            out = subprocess.run([exe, "funnel", "--bg", "--yes", str(APP_PORT)], capture_output=True, text=True, timeout=25)
            text = (out.stdout or "") + (out.stderr or "")
        except subprocess.TimeoutExpired as e:
            text = ((e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + \
                   ((e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""))
        link = re.search(r"https://login\.tailscale\.com/\S+", text)
        if link:          # Funnel (or HTTPS certificates) must be switched on once for this tailnet
            self.state, self.action_url = "error", link.group(0)
            self.error = "One-time step: open the link to allow Funnel (public https) for this laptop, then press the button again."
            SERVER.log("[tunnel] Tailscale needs Funnel enabled once: " + link.group(0), "tunnel")
            return
        if ts["name"] and ("Available on the internet" in text or "funnel on" in text.lower() or "https://" in text):
            self.url, self.state = f"https://{ts['name']}", "online"
            SERVER.log(f"Internet address ready: {self.url}", "tunnel")
            return
        self.state, self.error = "error", (text.strip()[:300] or "Tailscale Funnel did not start.")

    def _read(self, proc):
        if self.provider == "cloudflared":
            return self._read_cloudflared(proc)
        return self._read_ngrok(proc)

    def _read_cloudflared(self, proc):
        import re
        for line in proc.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m and not self.url:
                self.url, self.state = m.group(0), "online"
                SERVER.log(f"Internet address ready: {self.url}", "tunnel")
            elif " ERR " in line or "error=" in line.lower():
                self.error = line.strip()[:300]
        if self.state != "off":
            self.state = "error"
            self.error = self.error or "The tunnel stopped."

    def _read_ngrok(self, proc):
        for line in proc.stdout:
            if "lvl=eror" in line or "lvl=crit" in line or "ERR_NGROK" in line:
                msg = line.split("err=", 1)[-1].strip().strip('"') if "err=" in line else line.strip()
                self.error = msg[:300]
                SERVER.log(f"[tunnel] {self.error}", "tunnel")
        # Chocolatey's ngrok launcher can close its output while the real ngrok keeps running: ask ngrok itself.
        if self.state != "off" and not self._ngrok_alive():
            self.state = "error"
            self.error = self.error or "The tunnel stopped."

    @staticmethod
    def _ngrok_alive():
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as r:
                return any(t.get("public_url", "").startswith("https://") for t in json.loads(r.read().decode()).get("tunnels", []))
        except Exception:
            return False

    def _find_url(self, proc):
        for _ in range(60):
            if proc.poll() is not None and not self._ngrok_alive():
                return
            try:
                with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as r:
                    tunnels = json.loads(r.read().decode()).get("tunnels", [])
                for t in tunnels:
                    if t.get("public_url", "").startswith("https://"):
                        self.url, self.state = t["public_url"], "online"
                        SERVER.log(f"Internet address ready: {self.url}", "tunnel")
                        return
            except Exception:
                pass
            time.sleep(0.5)
        if self.state == "starting":
            self.state, self.error = "error", self.error or "Could not get the tunnel address from ngrok."

    @classmethod
    def funnel_on(cls):
        exe = cls.tailscale_exe()
        if not exe:
            return False
        try:
            out = subprocess.run([exe, "funnel", "status"], capture_output=True, text=True, timeout=6)
            return "Funnel on" in (out.stdout or "") and f"127.0.0.1:{APP_PORT}" in (out.stdout or "")
        except Exception:
            return False

    def adopt(self, ts):
        """Funnel keeps running on its own (--bg). If it's on, show it as this laptop's address — even after a restart."""
        if self.state in ("off", "error") and not self.action_url and self.choice in ("auto", "tailscale") \
                and ts.get("signed_in") and self.funnel_on():
            self.provider, self.url, self.state, self.error = "tailscale", f"https://{ts['name']}", "online", None

    def stop(self, keep_funnel=False):
        if self.proc and self.proc.poll() is None:
            self.state = "off"
            kill_tree(self.proc)
        if self.provider == "tailscale" and self.tailscale_exe() and not keep_funnel:
            subprocess.run([self.tailscale_exe(), "funnel", "reset"], capture_output=True, timeout=15)
        self.proc, self.url, self.state, self.action_url = None, None, "off", None
        # A tunnel left over from an earlier run (or a crash) blocks a new one: free ngrok allows one at a time.
        if os.name == "nt":
            for exe in ("ngrok.exe", "cloudflared.exe"):
                subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True)


def kill_tree(proc, timeout=4):
    """Stop a process and everything it started. Package-manager launchers (e.g. Chocolatey's ngrok) start the real
    program as a child; stopping only the launcher would leave the tunnel running."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


SERVER = ServerProcess()
TUNNEL = Tunnel()


def shutdown_children():
    TUNNEL.stop(keep_funnel=True)     # a Tailscale address stays reserved; installed phones just show "reconnecting"
    SERVER.stop()


# --------------------------------------------------------------------------- web API for the Control Center UI

app = FastAPI(title="AppShare Control Center")
app.mount("/ui", StaticFiles(directory=UI), name="ui")


@app.middleware("http")
async def _fresh_ui(request, call_next):
    """The Control Center's own files are always revalidated, so a reload never runs an old script."""
    response = await call_next(request)
    if request.url.path.startswith("/ui/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(os.path.join(UI, "index.html"), headers={"Cache-Control": "no-cache"})


@app.get("/api/status")
def status():
    SERVER.refresh_external()
    key, source = SERVER.api_key()
    addresses = [{"ip": "127.0.0.1", "kind": "local", "label": "This laptop", "fixed": True,
                  "url": f"http://127.0.0.1:{APP_PORT}"}]
    for a in lan_addresses():
        a["url"] = f"http://{a['ip']}:{APP_PORT}"
        a["reachable"] = SERVER.lan
        addresses.append(a)
    running = SERVER.state in ("starting", "online", "stopping")
    return {
        "state": SERVER.state,
        "pid": SERVER.proc.pid if running and SERVER.proc else None,
        "started_at": int(SERVER.started_at * 1000) if SERVER.started_at and running else None,
        "port": APP_PORT,
        "app_origin": f"http://127.0.0.1:{APP_PORT}",
        "lan": SERVER.lan,
        "monitor_token": SERVER.token if SERVER.state != "external" else "",
        "error": SERVER.error,
        "exit_code": SERVER.exit_code,
        "addresses": addresses,
        "hotspot_active": any(a["kind"] == "hotspot" for a in addresses),
        "api_key": {"set": bool(key), "source": source},
        "ai": ai_settings(),
        "tunnel": {"available": Tunnel.available(), "state": TUNNEL.state, "url": TUNNEL.url,
                   "error": TUNNEL.error, "domain": TUNNEL.domain, "provider": TUNNEL.provider, "choice": TUNNEL.choice,
                   "action_url": TUNNEL.action_url, "has_ngrok": Tunnel.has_ngrok(), "has_cloudflared": Tunnel.has_cloudflared(),
                   "tailscale": _tailscale_cached()},
        "hostname": socket.gethostname(),
        "python": sys.version.split()[0],
        "data_dir": mode_dir(),
        "has_data": os.path.exists(os.path.join(mode_dir(), "appshare.db")),
        "mode": current_mode(),
        "modes": [{"id": k, **v, "has_data": os.path.exists(os.path.join(mode_dir(k), "appshare.db"))} for k, v in MODES.items()],
    }


class ModeIn(BaseModel):
    mode: str


@app.post("/api/mode")
def set_mode(body: ModeIn):
    """Switch workspace (university / office / general). Each keeps its own data. Restarts a running server."""
    if body.mode not in MODES:
        raise HTTPException(400, "Mode must be university, office or general")
    if SERVER.state == "external":
        raise HTTPException(409, "This server was started outside the Control Center; stop it in its own window first.")
    if os.environ.get("APPSHARE_MODE") and os.environ["APPSHARE_MODE"] != body.mode:
        os.environ.pop("APPSHARE_MODE")       # the saved choice wins from now on
    write_env_value("APPSHARE_MODE", body.mode)
    was_running = SERVER.state in ("starting", "online")
    SERVER.log(f"Workspace switched to {MODES[body.mode]['label']} ({MODES[body.mode]['org']}).", "control")
    if was_running:
        SERVER.stop()
        for _ in range(40):
            if not port_open(APP_PORT):
                break
            time.sleep(0.1)
        SERVER.start(lan=SERVER.lan)
    return {"ok": True, "mode": body.mode, "restarted": was_running}


class StartIn(BaseModel):
    lan: bool = True


@app.post("/api/server/start")
def start_server(body: StartIn):
    SERVER.start(lan=body.lan)
    return {"ok": True}


@app.post("/api/server/stop")
def stop_server():
    if SERVER.state == "external":
        raise HTTPException(409, "This server was started outside the Control Center; stop it in its own window.")
    SERVER.stop()
    return {"ok": True}


@app.post("/api/server/restart")
def restart_server(body: StartIn):
    SERVER.stop()
    for _ in range(40):
        if not port_open(APP_PORT):
            break
        time.sleep(0.1)
    SERVER.start(lan=body.lan)
    return {"ok": True}


@app.get("/api/server/logs")
def server_logs(after: int = 0):
    with SERVER.lock:
        return {"lines": [l for l in SERVER.logs if l["seq"] > after][-200:], "last": SERVER.log_seq}


class KeyIn(BaseModel):
    key: str
    remember: bool = False


@app.post("/api/api-key")
def set_api_key(body: KeyIn):
    key = body.key.strip()
    if not key.startswith("sk-ant-"):
        raise HTTPException(400, "That doesn't look like a Claude API key (it should start with sk-ant-).")
    SERVER.session_key = key
    if body.remember:
        write_env_value("ANTHROPIC_API_KEY", key)
    restart_needed = SERVER.state in ("online", "starting")
    return {"ok": True, "restart_needed": restart_needed}


# --------------------------------------------------------------------------- AI provider: Claude / Groq free tier / mixed

AGENTS = ("builder", "data", "design", "access", "insights", "review", "reminder")


def groq_key():
    if SERVER.session_groq_key:
        return SERVER.session_groq_key, "this session"
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"], "environment"
    k = read_env_file().get("GROQ_API_KEY")
    return (k, ".env file") if k else (None, None)


def ai_settings():
    env = read_env_file()
    mode = (env.get("APPSHARE_AI_MODE") or os.environ.get("APPSHARE_AI_MODE") or "claude").lower()
    try:
        per = json.loads(env.get("APPSHARE_AGENT_PROVIDERS") or "{}")
    except ValueError:
        per = {}
    agents = {a: ("groq" if mode == "groq" else per.get(a, "claude") if mode == "mixed" else "claude") for a in AGENTS}
    k, src = groq_key()
    try:
        gm = json.loads(env.get("APPSHARE_GROQ_MODELS") or "{}")
    except ValueError:
        gm = {}
    return {"mode": mode, "agents": agents, "groq_model": env.get("APPSHARE_GROQ_MODEL") or "openai/gpt-oss-120b",
            "groq_models": {a: m for a, m in gm.items() if a in AGENTS}, "groq_key": {"set": bool(k), "source": src}}


class AiIn(BaseModel):
    mode: str
    agents: dict = {}
    groq_model: str = ""
    groq_models: dict = {}       # optional model per agent (Groq counts limits per model)


@app.post("/api/ai-settings")
def set_ai(body: AiIn):
    if body.mode not in ("claude", "groq", "mixed"):
        raise HTTPException(400, "mode must be claude, groq or mixed")
    write_env_value("APPSHARE_AI_MODE", body.mode)
    if body.mode == "mixed":
        per = {a: p for a, p in body.agents.items() if a in AGENTS and p in ("claude", "groq")}
        write_env_value("APPSHARE_AGENT_PROVIDERS", json.dumps(per, separators=(",", ":")))
    if body.groq_model.strip():
        write_env_value("APPSHARE_GROQ_MODEL", body.groq_model.strip())
    per_model = {a: m.strip() for a, m in body.groq_models.items() if a in AGENTS and isinstance(m, str) and m.strip()}
    write_env_value("APPSHARE_GROQ_MODELS", json.dumps(per_model, separators=(",", ":")))
    for k in ("APPSHARE_AI_MODE", "APPSHARE_AGENT_PROVIDERS", "APPSHARE_GROQ_MODEL", "APPSHARE_GROQ_MODELS"):
        os.environ.pop(k, None)              # the saved choice wins from now on
    return {"ok": True, "restart_needed": SERVER.state in ("online", "starting"), "ai": ai_settings()}


@app.post("/api/groq-key")
def set_groq_key(body: KeyIn):
    key = body.key.strip()
    if not key.startswith("gsk_"):
        raise HTTPException(400, "That doesn't look like a Groq API key (it should start with gsk_).")
    SERVER.session_groq_key = key
    if body.remember:
        write_env_value("GROQ_API_KEY", key)
    return {"ok": True, "restart_needed": SERVER.state in ("online", "starting")}


@app.get("/api/groq-models")
def groq_models():
    key, _ = groq_key()
    if not key:
        raise HTTPException(400, "Add a Groq API key first.")
    import httpx
    try:
        r = httpx.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=10)
    except httpx.HTTPError:
        raise HTTPException(502, "Couldn't reach Groq. Check the internet connection.")
    if r.status_code == 401:
        raise HTTPException(400, "Groq didn't accept that key.")
    if r.status_code >= 400:
        raise HTTPException(502, f"Groq answered {r.status_code}.")
    skip = ("whisper", "tts", "guard", "embed", "orpheus", "distil", "prompt-guard")
    return {"models": sorted(m["id"] for m in r.json().get("data", []) if m.get("active", True) and not any(s in m["id"].lower() for s in skip))}


class TunnelIn(BaseModel):
    domain: str = ""
    provider: str | None = None      # auto | tailscale | cloudflared | ngrok


_TS_CACHE = {"t": 0.0, "v": {"installed": False, "signed_in": False, "name": None}}


def _tailscale_cached():
    if time.time() - _TS_CACHE["t"] > 10:
        _TS_CACHE.update(t=time.time(), v=Tunnel.tailscale_status())
        TUNNEL.adopt(_TS_CACHE["v"])
    return _TS_CACHE["v"]


@app.post("/api/tunnel/start")
def start_tunnel(body: TunnelIn):
    if body.provider and body.provider not in ("auto",) + Tunnel.PROVIDERS:
        raise HTTPException(400, "provider must be auto, tailscale, cloudflared or ngrok")
    _TS_CACHE["t"] = 0
    TUNNEL.start(body.domain, body.provider)
    return {"ok": True}


@app.post("/api/tunnel/stop")
def stop_tunnel():
    TUNNEL.stop()
    return {"ok": True}


@app.get("/api/qr")
def qr(data: str, dark: str = "#0b1120", light: str = "#ffffff"):
    if not data.startswith(("http://", "https://")) or len(data) > 300:
        raise HTTPException(400, "QR codes are only made for web addresses")
    code = segno.make(data, error="m")
    buf = io.BytesIO()
    # Full SVG document (with xmlns) so it renders inside an <img>.
    code.save(buf, kind="svg", scale=10, border=2, dark=dark, light=light, xmldecl=False, omitsize=True)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.post("/api/reset-data")
def reset_data():
    """Start the demo fresh: only while the server is off. The UI asks for confirmation first."""
    if SERVER.state in ("starting", "online", "stopping", "external"):
        raise HTTPException(409, "Turn the server off before resetting the data.")
    m = current_mode()
    if os.path.isdir(mode_dir(m)):
        shutil.rmtree(mode_dir(m))
    SERVER.log(f"{MODES[m]['label']} demo data reset. {MODES[m]['org']} will be recreated on next start.", "control")
    return {"ok": True}
