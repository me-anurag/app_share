/* AppShare Control Center — core: state, server power, live event stream, icons, connect dialog. */
"use strict";

const CC = {
  status: null,          // from the launcher (/api/status)
  snapshot: null,        // from the AppShare server (/api/monitor/snapshot)
  mode: "live",
  lastEventId: 0,
  serverStartedAt: null,
  es: null,
  selectedUrl: null,
  logSeq: 0,
  _handlers: {},

  // stack order bottom → top; validated as adjacent pairs on #181816
  KINDS: {
    page:   { label: "Pages",          color: "#3987e5" },
    data:   { label: "Data & actions", color: "#c98500" },
    submit: { label: "Submissions",    color: "#199e70" },
    agent:  { label: "Agents",         color: "#9085e9" },
  },
  STATUS: { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" },

  // ------------------------------------------------------------------ icons (24px grid, 1.6 stroke)
  ICONS: {
    power: '<path d="M12 3v8"/><path d="M6.3 6.6a8 8 0 1 0 11.4 0"/>',
    qr: '<rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1"/><rect x="14" y="3.5" width="6.5" height="6.5" rx="1"/><rect x="3.5" y="14" width="6.5" height="6.5" rx="1"/><path d="M14 14h2.5v2.5H14zM18 18h2.5v2.5H18zM14 18.5v2M18.5 14h2"/>',
    phone: '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18.5h2"/>',
    laptop: '<rect x="4.5" y="5" width="15" height="10.5" rx="1.2"/><path d="M2.5 19h19"/>',
    key: '<circle cx="8" cy="15" r="3.6"/><path d="M10.6 12.4 20 3M16.5 6.5l2.2 2.2M14 9l2 2"/>',
    door: '<path d="M14 4h5v16h-5"/><path d="M10 8l-4 4 4 4M6 12h10"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    inbox: '<path d="M4 13l2.4-7h11.2L20 13v6H4z"/><path d="M4 13h4.5a3.5 3.5 0 0 0 7 0H20"/>',
    shield: '<path d="M12 3l7 3v5c0 4.6-3 8-7 10-4-2-7-5.4-7-10V6z"/><path d="M9.5 9.5l5 5M14.5 9.5l-5 5"/>',
    block: '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
    lockx: '<rect x="5" y="11" width="14" height="9.5" rx="1.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    bot: '<rect x="5" y="8" width="14" height="11" rx="2.5"/><path d="M12 4.5V8"/><circle cx="12" cy="3.6" r=".9"/><path d="M9.5 13h.01M14.5 13h.01"/>',
    lens: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
    alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.3"/>',
    wifi: '<path d="M3 9.5a13 13 0 0 1 18 0M6.5 13a8 8 0 0 1 11 0M10 16.5a3 3 0 0 1 4 0"/><path d="M12 19.5v.2"/>',
    hotspot: '<circle cx="12" cy="11" r="1.6"/><path d="M12 12.6V21M8.4 7.4a5 5 0 0 0 0 7.2M15.6 7.4a5 5 0 0 1 0 7.2M5.6 4.6a9 9 0 0 0 0 12.8M18.4 4.6a9 9 0 0 1 0 12.8"/>',
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.4 5.3 3.4 8.5s-1 6.1-3.4 8.5c-2.4-2.4-3.4-5.3-3.4-8.5s1-6.1 3.4-8.5"/>',
    pencil: '<path d="M4 20l1.2-4.4L16 4.8l3.2 3.2L8.4 18.8z"/><path d="M14 6.8l3.2 3.2"/>',
    trash: '<path d="M5 7h14M10 7V4.5h4V7M7 7l1 13h8l1-13"/>',
    lock: '<rect x="5" y="11" width="14" height="9.5" rx="1.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    unlock: '<rect x="5" y="11" width="14" height="9.5" rx="1.5"/><path d="M8 11V8a4 4 0 0 1 7.6-1.7"/>',
    play: '<path d="M8 5.5l10 6.5-10 6.5z"/>',
    stop: '<rect x="7" y="7" width="10" height="10" rx="1"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    copy: '<rect x="8" y="8" width="11" height="11" rx="1.5"/><path d="M5 15V6a1 1 0 0 1 1-1h9"/>',
    message: '<path d="M4 5h16v11H9.5L5 19.5V16H4z"/>',
    bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5.9 1.1.9 1.9V16h5.4v-.3c0-.8.3-1.4.9-1.9A6 6 0 0 0 12 3z"/>',
    wrench: '<path d="M15 4a5 5 0 0 0-4.6 6.9L4 17.3V20h2.7l6.4-6.4A5 5 0 0 0 20 9l-3 1-2-2 1-3z"/>',
    cards: '<rect x="3" y="7" width="15" height="12" rx="1"/><path d="M6 4h15v12M3 11h15M6.5 15h5"/>',
    blueprint: '<rect x="3.5" y="3.5" width="17" height="17" rx="1"/><path d="M3.5 9h17M9 9v11.5M12 13h5M12 16.5h3"/>',
    list: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
    chart: '<path d="M4 20V4M4 20h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
    users: '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M15.5 5.3a3 3 0 0 1 0 5.6M17.5 19a5 5 0 0 0-2.6-4.4"/>',
    bell: '<path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2.5h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    server: '<rect x="4" y="4" width="16" height="6" rx="1"/><rect x="4" y="14" width="16" height="6" rx="1"/><path d="M7.5 7h.01M7.5 17h.01"/>',
    spark: '<path d="M12 3v5M12 16v5M3 12h5M16 12h5"/>',
    send: '<path d="M4 12l16-8-6 16-2.5-6.5z"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    clapper: '<rect x="3.5" y="9" width="17" height="11" rx="1"/><path d="M3.5 9l15.6-4.2.7 2.6L4.2 11.6M8 6.3l2 3M13 5l2 3"/>',
  },
  icon(name, cls = "") {
    const filled = name === "play" || name === "stop";
    return `<svg class="i ${cls}${filled ? " fill" : ""}" viewBox="0 0 24 24" aria-hidden="true">${this.ICONS[name] || ""}</svg>`;
  },
  hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach(el => {
      if (el.dataset.iconDone) return;
      el.insertAdjacentHTML("afterbegin", this.icon(el.dataset.icon, el.dataset.iconCls || ""));
      el.dataset.iconDone = "1";
    });
  },

  // ------------------------------------------------------------------ tiny event bus
  on(type, fn) { (this._handlers[type] ||= []).push(fn); },
  fire(type, ...args) { (this._handlers[type] || []).forEach(fn => { try { fn(...args); } catch (e) { console.error(type, e); } }); },

  // ------------------------------------------------------------------ helpers
  esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); },
  num(n) {
    n = Number(n) || 0;
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (Math.abs(n) >= 1e4) return (n / 1e3).toFixed(n >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
    return n.toLocaleString();
  },
  bytes(b) {
    b = Number(b) || 0;
    if (b < 1024) return b + " B";
    if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
    if (b < 1073741824) return (b / 1048576).toFixed(1) + " MB";
    return (b / 1073741824).toFixed(2) + " GB";
  },
  dur(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return h ? `${h}h ${String(m).padStart(2, "0")}m` : m ? `${m}m ${String(r).padStart(2, "0")}s` : `${r}s`;
  },
  hms(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    return [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60].map(v => String(v).padStart(2, "0")).join(":");
  },
  ago(ts) {
    const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
    if (s < 5) return "just now";
    if (s < 60) return s + "s ago";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    return Math.floor(s / 3600) + "h ago";
  },
  clock(ts) { return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }); },
  deviceIcon(kind) { return this.icon(kind === "laptop" ? "laptop" : "phone"); },
  sleep(ms) { return new Promise(r => setTimeout(r, ms)); },
  online() { return this.status && (this.status.state === "online" || this.status.state === "external"); },

  toast(msg, kind = "") {
    const t = document.createElement("div");
    t.className = "toast " + kind;
    t.textContent = msg;
    document.getElementById("toasts").appendChild(t);
    setTimeout(() => { t.style.transition = "opacity .4s"; t.style.opacity = "0"; }, 4200);
    setTimeout(() => t.remove(), 4700);
  },

  async api(path, body) {
    const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Request failed");
    return data;
  },

  appUrl(path) {
    const sep = path.includes("?") ? "&" : "?";
    return `${this.status.app_origin}${path}${sep}token=${encodeURIComponent(this.status.monitor_token || "")}`;
  },

  // ------------------------------------------------------------------ boot
  boot() {
    this.hydrateIcons();
    document.querySelectorAll(".modes button").forEach(b => b.onclick = () => this.setMode(b.dataset.mode));
    document.getElementById("powerBtn").onclick = () => this.togglePower();
    document.getElementById("bigPower").onclick = () => this.togglePower();
    document.getElementById("connectBtn").onclick = () => this.openConnect();
    document.getElementById("connectModal").addEventListener("click", e => {
      if (e.target.id === "connectModal" || e.target.closest("[data-close]")) this.closeConnect();
    });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") this.closeConnect();
      if (e.target.matches("input, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
      const m = { 1: "live", 2: "monitor", 3: "agents", 4: "flow" }[e.key];
      if (m) this.setMode(m);
    });

    this.fire("init");
    this.hydrateIcons();
    const initial = (location.hash || "").replace("#", "");
    if (["live", "monitor", "agents", "flow"].includes(initial)) this.setMode(initial);
    this.pollStatus();
    setInterval(() => this.pollStatus(), 1500);
    setInterval(() => this.tickUptime(), 1000);
    setInterval(() => { if (this.online()) this.refreshSnapshot(); }, 3000);
  },

  setMode(mode) {
    this.mode = mode;
    document.querySelectorAll(".modes button").forEach(b => { b.classList.toggle("active", b.dataset.mode === mode); b.setAttribute("aria-selected", b.dataset.mode === mode); });
    ["live", "monitor", "agents", "flow"].forEach(m => document.getElementById("view-" + m).classList.toggle("hidden", m !== mode));
    history.replaceState(null, "", "#" + mode);
    this.fire("mode", mode);
  },

  // ------------------------------------------------------------------ server status & power
  async pollStatus() {
    let st;
    try { st = await this.api("/api/status"); }
    catch { this.toastOnce("The Control Center itself stopped. Restart it with: python -m launcher", "bad"); return; }
    const prev = this.status;
    this.status = st;
    document.body.dataset.state = st.state === "external" ? "online" : st.state;
    document.getElementById("statusText").textContent =
      { off: "Off", starting: "Starting", online: "Online", stopping: "Stopping", crashed: "Error", external: "Online · ext" }[st.state];
    document.getElementById("powerBtn").setAttribute("aria-label", this.online() ? "Turn the server off" : "Turn the server on");
    this.renderOverlay();
    if (!prev || prev.mode !== st.mode || prev.state !== st.state) this.renderWorkspace();
    if (st.state === "starting" || st.state === "crashed" || st.state === "stopping") this.pullLogs();

    const wasOnline = prev && (prev.state === "online" || prev.state === "external");
    if (this.online() && !wasOnline) {
      await this.refreshSnapshot(true);
      this.openStream();
      if (prev) this.toast("Server is online. Phones can connect now.", "ok");
    }
    if (!this.online() && wasOnline) {
      this.closeStream();
      this.snapshot = null;
      this.fire("snapshot", null);
      if (st.state === "off") this.toast("Server is off.");
    }
    if (!prev || JSON.stringify(prev.addresses) !== JSON.stringify(st.addresses) || JSON.stringify(prev.tunnel) !== JSON.stringify(st.tunnel)
        || prev.state !== st.state || prev.api_key.set !== st.api_key.set) {
      this.renderConnectMini();
      this.updateConnectModal();
    }
    this.fire("status", st, prev);
  },

  toastOnce(msg, kind) {
    if (this._lastToast === msg) return;
    this._lastToast = msg;
    this.toast(msg, kind);
  },

  async togglePower() {
    const st = this.status;
    if (!st) return;
    try {
      if (st.state === "online") {
        if (!confirm("Turn the AppShare server off? Phones will lose the connection until you turn it on again.")) return;
        await this.api("/api/server/stop", {});
      } else if (st.state === "external") {
        this.toast("This server was started outside the Control Center. Stop it in its own window.", "bad");
      } else if (st.state === "off" || st.state === "crashed") {
        this.logSeq = 0;
        document.getElementById("bootLog").textContent = "";
        await this.api("/api/server/start", { lan: document.getElementById("lanToggle").checked });
      }
    } catch (e) { this.toast(e.message, "bad"); }
    this.pollStatus();
  },

  async pullLogs() {
    try {
      const d = await this.api("/api/server/logs?after=" + this.logSeq);
      const box = document.getElementById("bootLog");
      for (const l of d.lines) {
        const cls = l.src === "control" ? "c" : l.src === "tunnel" ? "t" : "";
        box.insertAdjacentHTML("beforeend", `<span class="${cls}">${this.esc(l.line)}</span>\n`);
      }
      this.logSeq = d.last;
      box.scrollTop = box.scrollHeight;
    } catch { /* ignore */ }
  },

  renderOverlay() {
    const st = this.status;
    const t = document.getElementById("poTitle"), s = document.getElementById("poSub");
    document.getElementById("lanRow").classList.toggle("hidden", !(st.state === "off" || st.state === "crashed"));
    if (st.state === "starting") { t.textContent = "Starting the server"; s.textContent = "Booting the web server, opening the database, checking the agents."; }
    else if (st.state === "stopping") { t.textContent = "Shutting down"; s.textContent = "Finishing open requests."; }
    else if (st.state === "crashed") { t.textContent = "The server stopped"; s.textContent = st.error || "Check the log below, then press power to try again."; }
    else { t.textContent = "The server is off"; s.textContent = "Press power to start AppShare on this laptop."; }
    document.getElementById("bootLog").classList.toggle("hidden", !(st.state === "starting" || st.state === "crashed" || st.state === "stopping"));
    document.getElementById("poKey").innerHTML = st.api_key.set
      ? `Agents: <b>ready</b> — key from ${this.esc(st.api_key.source)}.`
      : `Agents: <b>no API key</b>. The apps work; the agents need a key. <a href="#" id="poKeyLink">Add key</a>`;
    const link = document.getElementById("poKeyLink");
    if (link) link.onclick = e => { e.preventDefault(); this.openConnect("key"); };
  },

  // ------------------------------------------------------------------ workspace (university / office / general)
  workspace() { return this.status?.modes?.find(m => m.id === this.status.mode); },

  wsButtons(big = false) {
    return this.status.modes.map(m => `<button data-ws="${m.id}" class="${m.id === this.status.mode ? "on" : ""}" aria-pressed="${m.id === this.status.mode}">
      <span class="w-l">${this.esc(m.label)}</span><span class="w-o">${this.esc(m.org)}</span>${big ? `<span class="w-b">${this.esc(m.blurb)}</span>` : ""}</button>`).join("");
  },

  renderWorkspace() {
    const st = this.status, ws = this.workspace();
    if (!ws) return;
    document.getElementById("brandSub").innerHTML = `Server control · <b>${this.esc(ws.label)}</b>`;
    document.getElementById("poWs").classList.toggle("hidden", !(st.state === "off" || st.state === "crashed"));
    const pick = document.getElementById("wsPick");
    pick.innerHTML = this.wsButtons();
    pick.querySelectorAll("[data-ws]").forEach(b => b.onclick = () => this.setWorkspace(b.dataset.ws));
    const cm = document.getElementById("cmWs");
    if (cm) {
      cm.innerHTML = this.wsButtons(true);
      cm.querySelectorAll("[data-ws]").forEach(b => b.onclick = () => this.setWorkspace(b.dataset.ws));
    }
  },

  async setWorkspace(mode) {
    const st = this.status;
    if (!st || mode === st.mode) return;
    const m = st.modes.find(x => x.id === mode);
    if ((st.state === "online" || st.state === "starting") &&
        !confirm(`Switch to ${m.label} (${m.org})? The server restarts and phones reconnect to the ${m.label.toLowerCase()} workspace. Each workspace keeps its own apps and data.`)) return;
    try {
      const r = await this.api("/api/mode", { mode });
      this.logSeq = 0;
      document.getElementById("bootLog").textContent = "";
      this.toast(`${m.label} workspace${r.restarted ? " · restarting" : ""}`, "ok");
    } catch (e) { this.toast(e.message, "bad"); }
    this.pollStatus();
  },

  tickUptime() {
    const started = this.snapshot?.server?.started_at || this.status?.started_at;
    document.getElementById("uptime").textContent = this.online() && started ? this.hms(Date.now() - started) : "--:--:--";
    this.fire("tick");
  },

  // ------------------------------------------------------------------ monitor data from the AppShare server
  async refreshSnapshot(first = false) {
    try {
      const res = await fetch(this.appUrl("/api/monitor/snapshot"));
      if (!res.ok) throw new Error("monitor " + res.status);
      const snap = await res.json();
      const restarted = this.serverStartedAt && snap.server.started_at !== this.serverStartedAt;
      this.serverStartedAt = snap.server.started_at;
      this.snapshot = snap;
      if (first || restarted) {
        this.lastEventId = snap.latest_id;
        this.fire("history", snap.events);
        if (restarted) this.openStream();
      }
      this.fire("snapshot", snap);
    } catch (e) {
      if (first) console.warn("snapshot failed", e);
    }
  },

  openStream() {
    this.closeStream();
    if (!this.online()) return;
    const es = new EventSource(this.appUrl(`/api/monitor/stream?after=${this.lastEventId}`));
    this.es = es;
    es.onmessage = m => {
      let ev;
      try { ev = JSON.parse(m.data); } catch { return; }
      if (ev.id <= this.lastEventId) return;
      this.lastEventId = ev.id;
      this.fire("event", ev);
    };
    es.onerror = () => {
      es.close();
      if (this.es === es) this.es = null;
      setTimeout(() => { if (this.online() && !this.es) this.refreshSnapshot().then(() => this.openStream()); }, 1500);
    };
  },

  closeStream() { if (this.es) { this.es.close(); this.es = null; } },

  // ------------------------------------------------------------------ addresses & QR
  addresses() {
    const st = this.status;
    if (!st) return [];
    const list = st.addresses.map(a => ({ ...a, usable: a.kind === "local" || (st.lan && this.online()) }));
    if (st.tunnel.url) list.push({ kind: "internet", label: "Internet · HTTPS", url: st.tunnel.url, fixed: !!st.tunnel.domain, usable: this.online() });
    return list;
  },

  pickUrl() {
    const list = this.addresses();
    if (this.selectedUrl && list.some(a => a.url === this.selectedUrl)) return this.selectedUrl;
    const best = list.find(a => a.kind === "internet") || list.find(a => a.kind === "hotspot") || list.find(a => a.kind === "lan") || list[0];
    return best ? best.url : null;
  },

  // The QR leads to the install page: it gets a phone out of the camera's quick viewer and into installing.
  // https addresses lead to the Install page (it handles camera quick views, Chrome, iPhone…); plain http can't install.
  phoneUrl(url) { return url ? (url.startsWith("https") ? url + "/install" : url + "/") : ""; },
  qrSrc(url) { return "/api/qr?data=" + encodeURIComponent(this.phoneUrl(url)) + "&dark=%23141412&light=%23f1eee6"; },

  addrTag(a) {
    if (a.kind === "internet") return `<span class="tag accent"><i class="mk"></i>https</span>`;
    if (!a.usable && a.kind !== "local") return `<span class="tag muted"><i class="mk"></i>${this.online() ? "lan off" : "off"}</span>`;
    if (a.kind === "hotspot") return `<span class="tag good"><i class="mk"></i>fixed</span>`;
    return "";
  },

  addrIcon(a) { return this.icon({ local: "laptop", lan: "wifi", hotspot: "hotspot", internet: "globe" }[a.kind] || "link"); },

  renderConnectMini() {
    const box = document.getElementById("connectMini");
    if (!this.status) return;
    const url = this.pickUrl();
    const list = this.addresses().filter(a => a.kind !== "local");
    const usable = list.find(a => a.url === url)?.usable;
    box.innerHTML = `
      <div class="panel-head" style="margin-bottom:.8rem"><div><h2>Connect a phone</h2><p class="sub">Point the phone camera at the code.</p></div>
        <button class="btn sm ghost" id="miniMore">Options</button></div>
      <div class="qr-box">
        <div class="qr-paper ${usable ? "" : "off"}">${url ? `<img alt="QR code for ${this.esc(url)}" src="${this.qrSrc(url)}">` : ""}</div>
        <div>
          <div class="label" style="margin-bottom:.25rem">Address</div>
          <div class="big-url">${this.esc((url || "—").replace(/^https?:\/\//, ""))}</div>
          <div class="note ${usable ? "" : "warn"}">${usable
            ? (url.startsWith("https") ? "Works from any network. Phones can install the app." : "Phone must be on the same Wi-Fi or hotspot.")
            : (this.online() ? "Phones can't use this yet: restart with phone access on." : "Turn the server on first.")}</div>
        </div>
      </div>
      <div class="addr-list">${list.map(a => `
        <button class="addr ${a.url === url ? "sel" : ""}" data-url="${this.esc(a.url)}">
          ${this.addrIcon(a)}
          <span><div class="a-l">${this.esc(a.label)}</div><div class="a-u">${this.esc(a.url.replace(/^https?:\/\//, ""))}</div></span>
          ${this.addrTag(a)}
        </button>`).join("") || `<div class="empty-note">No network found. Connect the laptop to Wi-Fi or turn on its mobile hotspot.</div>`}
      </div>`;
    box.querySelectorAll(".addr").forEach(b => b.onclick = () => { this.selectedUrl = b.dataset.url; this.renderConnectMini(); this.updateConnectModal(); });
    document.getElementById("miniMore").onclick = () => this.openConnect();
  },

  // ------------------------------------------------------------------ connect & settings dialog
  openConnect(focus) {
    const body = document.getElementById("connectBody");
    body.innerHTML = `
      <div>
        <div class="qr-big"><img id="cmQr" alt="QR code"></div>
        <div class="big-url" id="cmUrl" style="margin-top:.8rem;text-align:center"></div>
        <div class="set-row" style="justify-content:center"><button class="btn sm" id="cmCopy" data-icon="copy">Copy address</button></div>
        <div class="note" id="cmUsable" style="text-align:center"></div>
      </div>
      <div>
        <h3>Open AppShare on a phone</h3>
        <ol class="steps" id="cmSteps"></ol>
        <div class="addr-list" id="cmAddrs"></div>

        <div class="set-sec">
          <h3>The installed app reconnects by itself</h3>
          <p class="note">It remembers its address and keeps checking for the server. Turn the server on and it reconnects, as long as the address stays the same:</p>
          <ul class="steps">
            <li><b>Tailscale Funnel</b> (recommended): one fixed HTTPS address (<span class="mono">your-pc.your-tailnet.ts.net</span>) that works from any network and lets phones install the app. It stays on even after the Control Center closes.</li>
            <li><b>Laptop hotspot</b> (Windows Settings → Network → Mobile hotspot): the laptop is always <span class="mono">192.168.137.1</span>, but plain http, so no install. <span id="cmHotspot"></span></li>
          </ul>
        </div>

        <div class="set-sec">
          <h3>Internet address (HTTPS) — needed to install the app</h3>
          <p class="note">Phones only install apps from an https address. Shared links then use it too, so they open anywhere — and in the installed app.</p>
          <div class="prov-list" id="cmProv"></div>
          <div class="set-row">
            <input class="inp" id="cmDomain" placeholder="optional: your-name.ngrok-free.app (fixed address, uses ngrok)">
            <button class="btn" id="cmTunnel" data-icon="globe"></button>
          </div>
          <div class="note" id="cmTunnelNote"></div>
        </div>

        <div class="set-sec" id="cmAiSec">
          <h3>AI provider</h3>
          <p class="note">Which AI runs the agents. Claude is the default. Groq's free tier runs open models at no cost (good for demos and
            for comparing); quality may be lower. Changes apply when the server restarts.</p>
          <div class="prov-list" id="cmAiMode"></div>
          <div class="ai-agents hidden" id="cmAiAgents"></div>
          <div class="ai-groq hidden" id="cmAiGroq">
            <div class="label" style="margin:.6rem 0 .3rem">Groq</div>
            <div class="note" id="cmGroqState"></div>
            <div class="set-row">
              <input class="inp" id="cmGroqKey" type="password" placeholder="gsk_…  (free key from console.groq.com)" autocomplete="off">
              <button class="btn" id="cmGroqKeySave">Use Groq key</button>
            </div>
            <label class="mini-switch" style="margin-top:.5rem"><input type="checkbox" id="cmGroqRemember" checked><span class="toggle"></span>Remember on this laptop (.env)</label>
            <div class="set-row">
              <select class="inp" id="cmGroqModel"></select>
              <button class="btn" id="cmGroqList">List Groq models</button>
            </div>
            <div class="note">Default model above. Optionally give agents their own model: Groq counts its free limits per model, so
              agents on different models don't share one allowance (e.g. a small fast model for Data, Design and Access).</div>
            <div class="ai-agents" id="cmGroqPer"></div>
          </div>
          <div class="set-row"><button class="btn primary" id="cmAiSave">Save AI provider</button></div>
        </div>

        <div class="set-sec" id="cmKeySec">
          <h3>Agent API key</h3>
          <div class="note" id="cmKeyState"></div>
          <div class="set-row">
            <input class="inp" id="cmKey" type="password" placeholder="sk-ant-…" autocomplete="off">
            <button class="btn primary" id="cmKeySave">Use key</button>
          </div>
          <label class="mini-switch" style="margin-top:.6rem"><input type="checkbox" id="cmKeyRemember"><span class="toggle"></span>Remember on this laptop (saved in the project's .env file)</label>
        </div>

        <div class="set-sec">
          <h3>Workspace</h3>
          <p class="note">Who the demo is for. Each workspace has its own people, groups, example apps and data. Switching restarts the server.</p>
          <div class="ws-pick big" id="cmWs"></div>
        </div>

        <div class="set-sec">
          <h3>Demo data</h3>
          <p class="note">Start fresh: deletes the apps, responses and files of the <b>${this.esc(this.workspace()?.label || "current")}</b> workspace and recreates its demo. Only while the server is off.</p>
          <div class="set-row"><button class="btn danger" id="cmReset" data-icon="trash">Reset demo data</button></div>
        </div>
      </div>`;
    this.hydrateIcons(body);
    document.getElementById("connectModal").classList.remove("hidden");
    document.getElementById("cmDomain").value = this.status?.tunnel?.domain || "";
    document.getElementById("cmCopy").onclick = async () => {
      try { await navigator.clipboard.writeText(this.phoneUrl(this.pickUrl())); this.toast("Address copied", "ok"); } catch { /* ignore */ }
    };
    document.getElementById("cmTunnel").onclick = () => this.toggleTunnel();
    document.getElementById("cmKeySave").onclick = () => this.saveKey();
    this.renderAi(true);
    document.getElementById("cmAiSave").onclick = () => this.saveAi();
    document.getElementById("cmGroqKeySave").onclick = () => this.saveGroqKey();
    document.getElementById("cmGroqList").onclick = () => this.listGroqModels();
    document.getElementById("cmReset").onclick = () => this.resetData();
    this.renderWorkspace();
    this.updateConnectModal();
    if (focus === "key") document.getElementById("cmKey").focus();
  },

  closeConnect() { document.getElementById("connectModal").classList.add("hidden"); },

  updateConnectModal() {
    if (document.getElementById("connectModal").classList.contains("hidden") || !this.status) return;
    const st = this.status, url = this.pickUrl();
    const a = this.addresses().find(x => x.url === url);
    const img = document.getElementById("cmQr");
    if (url && img.dataset.url !== url) { img.src = this.qrSrc(url); img.dataset.url = url; }
    img.style.opacity = a?.usable ? 1 : .25;
    document.getElementById("cmUrl").textContent = this.phoneUrl(url) || "—";
    document.getElementById("cmSteps").innerHTML = (url || "").startsWith("https")
      ? `<li>Scan the code with the phone camera — any network works (mobile data too).</li>
         <li>If it opens inside the camera's quick view, tap <b>Open in Chrome</b> on the page.</li>
         <li>Tap <b>Install AppShare</b>. Then open it from the home screen and sign in.</li>`
      : `<li>Connect the phone to the <b>same Wi-Fi</b> as this laptop, or to the laptop's <b>mobile hotspot</b>.</li>
         <li>Scan the code with the camera and open the link, then sign in.</li>
         <li>To <b>install</b> the app, pick the <b>Internet · HTTPS</b> address instead — phones only install from https.</li>`;
    document.getElementById("cmUsable").textContent = a?.usable ? (url.startsWith("https") ? "Works from any network. Phones can install the app." : "Works on the same network as this laptop.") : (this.online() ? "Not reachable from phones right now (phone access is off)." : "Turn the server on first.");
    document.getElementById("cmAddrs").innerHTML = this.addresses().map(x => `
      <button class="addr ${x.url === url ? "sel" : ""}" data-url="${this.esc(x.url)}">
        ${this.addrIcon(x)}<span><div class="a-l">${this.esc(x.label)}</div><div class="a-u">${this.esc(x.url.replace(/^https?:\/\//, ""))}</div></span>${this.addrTag(x)}
      </button>`).join("");
    document.querySelectorAll("#cmAddrs .addr").forEach(b => b.onclick = () => { this.selectedUrl = b.dataset.url; this.updateConnectModal(); this.renderConnectMini(); });
    document.getElementById("cmHotspot").innerHTML = st.hotspot_active ? `<span class="note ok">Hotspot is on.</span>` : `<span class="note">Hotspot is off right now.</span>`;

    const t = st.tunnel, btn = document.getElementById("cmTunnel"), note = document.getElementById("cmTunnelNote");
    btn.innerHTML = this.icon("globe") + (t.state === "online" || t.state === "starting" ? "Stop internet address" : "Get internet address");
    btn.disabled = !t.available && t.state === "off";
    note.className = "note";
    // which tunnel: Tailscale (fixed, no warning) > Cloudflare (no account) > ngrok (fixed, but a warning page that blocks Android installs)
    const ts = t.tailscale || {};
    const provs = [
      { id: "tailscale", name: "Tailscale Funnel", ok: ts.installed, tag: "recommended",
        desc: ts.signed_in ? `Fixed address <span class="mono">https://${this.esc(ts.name)}</span> · no warning page · phones can install` : ts.installed ? "Installed — sign in to Tailscale once (Start menu → Tailscale)." : "Not installed (winget install Tailscale.Tailscale)." },
      { id: "cloudflared", name: "Cloudflare quick tunnel", ok: t.has_cloudflared, tag: "no account",
        desc: t.has_cloudflared ? "No warning page · phones can install · the address changes each time it starts." : "Not installed (winget install Cloudflare.cloudflared)." },
      { id: "ngrok", name: "ngrok", ok: t.has_ngrok, tag: "",
        desc: t.has_ngrok ? "Fixed address, but the free plan shows a warning page first — Android can't install the app through it." : "Not installed." },
    ];
    const cur = t.choice || "auto";
    document.getElementById("cmProv").innerHTML = [`<label class="prov ${cur === "auto" ? "on" : ""}"><input type="radio" name="prov" value="auto" ${cur === "auto" ? "checked" : ""}><span><b>Automatic</b><span class="note">Uses the best one that's ready.</span></span></label>`,
      ...provs.map(p => `<label class="prov ${cur === p.id ? "on" : ""} ${p.ok ? "" : "off"}"><input type="radio" name="prov" value="${p.id}" ${cur === p.id ? "checked" : ""} ${p.ok ? "" : "disabled"}>
        <span><b>${p.name}</b>${p.tag ? ` <span class="tag ${p.tag === "recommended" ? "good" : "muted"}"><i class="mk"></i>${p.tag}</span>` : ""}<span class="note">${p.desc}</span></span></label>`)].join("");
    document.querySelectorAll("#cmProv input").forEach(r => r.onchange = () => { this._prov = r.value; document.querySelectorAll("#cmProv .prov").forEach(l => l.classList.toggle("on", l.contains(r))); });
    if (t.action_url) { note.className = "note warn"; note.innerHTML = `${this.esc(t.error || "One more step:")} <a href="${this.esc(t.action_url)}" target="_blank" rel="noopener">Open this link</a>`; return; }
    if (!t.available) note.innerHTML = `No tunnel tool yet. Easiest (free, no account): open a terminal and run <span class="mono">winget install Cloudflare.cloudflared</span>, then reopen this dialog. For a fixed address that never changes, use ngrok with a free static domain instead.`;
    else if (t.state === "online") { note.className = "note ok"; note.innerHTML = `Live at <span class="mono">${this.esc(t.url)}</span>${t.provider === "cloudflared" ? " — this address changes each time you start it; re-share links after a restart." : ""}${this.online() ? "" : " (turn the server on to use it)"}`; }
    else if (t.state === "starting") note.textContent = `Opening the tunnel with ${t.provider || "the tunnel tool"}…`;
    else if (t.state === "error") { note.className = "note bad"; note.textContent = t.error || "The tunnel failed."; }
    else note.textContent = t.has_cloudflared && !t.domain ? "Uses Cloudflare's free quick tunnel (no account). Enter an ngrok static domain instead for a fixed address." : "A stable HTTPS address so phones can install the app and connect from any network.";

    const ks = document.getElementById("cmKeyState");
    ks.className = "note " + (st.api_key.set ? "ok" : "warn");
    ks.textContent = st.api_key.set ? `Agents are ready (key from ${st.api_key.source}).` : "No key yet: the apps work, but the agents need a Claude API key.";
  },

  async toggleTunnel() {
    const t = this.status.tunnel;
    try {
      if (t.state === "online" || t.state === "starting") await this.api("/api/tunnel/stop", {});
      else await this.api("/api/tunnel/start", { domain: document.getElementById("cmDomain").value, provider: this._prov || t.choice || "auto" });
    } catch (e) { this.toast(e.message, "bad"); }
    this.pollStatus();
  },

  async saveKey() {
    const input = document.getElementById("cmKey");
    try {
      const r = await this.api("/api/api-key", { key: input.value, remember: document.getElementById("cmKeyRemember").checked });
      input.value = "";
      if (r.restart_needed && confirm("Key saved. Restart the server now so the agents can use it?")) {
        await this.api("/api/server/restart", { lan: this.status.lan });
      } else this.toast("Key saved.", "ok");
    } catch (e) { this.toast(e.message, "bad"); }
    this.pollStatus();
  },

  // ------------------------------------------------------------------ AI provider (Claude / Groq free tier / mixed)
  AGENT_NAMES: { builder: "Builder", data: "Data", design: "Design", access: "Access", insights: "Insights", review: "Review", reminder: "Reminder" },
  renderAi(first = false) {
    const ai = this.status?.ai;
    if (!ai || !document.getElementById("cmAiMode")) return;
    if (first || !this._ai) this._ai = { mode: ai.mode, agents: { ...ai.agents }, groq_model: ai.groq_model, groq_models: { ...(ai.groq_models || {}) } };
    const A = this._ai, opts = [
      ["claude", "Claude", "recommended", "The default: Claude Opus leads the team, Claude Haiku runs the specialists. Measured: 85.7% task success."],
      ["groq", "Free — Groq", "", "Every agent on Groq's free tier (open models). No cost; free-tier rate limits apply; quality not yet measured."],
      ["mixed", "Mixed", "", "Choose per agent, e.g. the Builder on Claude and the specialists on Groq."]];
    document.getElementById("cmAiMode").innerHTML = opts.map(([id, name, tag, desc]) => `<label class="prov ${A.mode === id ? "on" : ""}">
        <input type="radio" name="aimode" value="${id}" ${A.mode === id ? "checked" : ""}><span><b>${name}</b>${tag ? ` <span class="tag good"><i class="mk"></i>${tag}</span>` : ""}<span class="note">${desc}</span></span></label>`).join("");
    document.querySelectorAll("#cmAiMode input").forEach(r => r.onchange = () => { A.mode = r.value; this.renderAi(); });
    const ag = document.getElementById("cmAiAgents");
    ag.classList.toggle("hidden", A.mode !== "mixed");
    ag.innerHTML = Object.entries(this.AGENT_NAMES).map(([k, n]) => `<label class="ai-agent"><span>${n}</span>
        <select class="inp" data-ag="${k}"><option value="claude" ${A.agents[k] !== "groq" ? "selected" : ""}>Claude</option><option value="groq" ${A.agents[k] === "groq" ? "selected" : ""}>Groq (free)</option></select></label>`).join("");
    ag.querySelectorAll("select").forEach(s => s.onchange = () => { A.agents[s.dataset.ag] = s.value; this.renderAi(); });
    const usesGroq = A.mode === "groq" || (A.mode === "mixed" && Object.values(A.agents).includes("groq"));
    document.getElementById("cmAiGroq").classList.toggle("hidden", !usesGroq);
    const gs = document.getElementById("cmGroqState");
    gs.className = "note " + (ai.groq_key.set ? "ok" : "warn");
    gs.textContent = ai.groq_key.set ? `Groq key set (from ${ai.groq_key.source}).` : "No Groq key yet. Get one free at console.groq.com → API Keys.";
    const sel = document.getElementById("cmGroqModel");
    const models = this._groqModels || [A.groq_model];
    sel.innerHTML = [...new Set([A.groq_model, ...models])].map(m => `<option ${m === A.groq_model ? "selected" : ""}>${this.esc(m)}</option>`).join("");
    sel.onchange = () => { A.groq_model = sel.value; this.renderAi(); };
    const onGroq = Object.keys(this.AGENT_NAMES).filter(k => A.mode === "groq" || (A.mode === "mixed" && A.agents[k] === "groq"));
    const per = document.getElementById("cmGroqPer");
    const all = [...new Set([A.groq_model, ...models, ...Object.values(A.groq_models)])];
    per.innerHTML = onGroq.map(k => `<label class="ai-agent"><span>${this.AGENT_NAMES[k]}</span><select class="inp" data-gm="${k}">
        <option value="">default (${this.esc(A.groq_model)})</option>${all.map(m => `<option ${A.groq_models[k] === m ? "selected" : ""}>${this.esc(m)}</option>`).join("")}</select></label>`).join("");
    per.querySelectorAll("select").forEach(s => s.onchange = () => { if (s.value) A.groq_models[s.dataset.gm] = s.value; else delete A.groq_models[s.dataset.gm]; });
  },
  async saveAi() {
    try {
      const r = await this.api("/api/ai-settings", this._ai);
      this._ai = null;
      if (r.restart_needed && confirm("AI provider saved. Restart the server now to switch?")) await this.api("/api/server/restart", { lan: this.status.lan });
      else this.toast("AI provider saved.", "ok");
    } catch (e) { this.toast(e.message, "bad"); }
    await this.pollStatus();
    this.renderAi(true);
  },
  async saveGroqKey() {
    const input = document.getElementById("cmGroqKey");
    try {
      const r = await this.api("/api/groq-key", { key: input.value, remember: document.getElementById("cmGroqRemember").checked });
      input.value = "";
      this.toast(r.restart_needed ? "Groq key saved. Save the AI provider (or restart) to use it." : "Groq key saved.", "ok");
    } catch (e) { this.toast(e.message, "bad"); }
    await this.pollStatus();
    this.renderAi();
  },
  async listGroqModels() {
    try {
      const r = await fetch("/api/groq-models"), d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Couldn't list models");
      this._groqModels = d.models;
      this.toast(`${d.models.length} Groq models available.`, "ok");
    } catch (e) { this.toast(e.message, "bad"); }
    this.renderAi();
  },

  async resetData() {
    if (this.online() || this.status.state === "starting") { this.toast("Turn the server off first.", "bad"); return; }
    const ws = this.workspace();
    if (!confirm(`Delete all apps, responses and uploaded files in the ${ws?.label || ""} workspace, and recreate the ${ws?.org || "demo"} demo? This can't be undone.`)) return;
    try { await this.api("/api/reset-data", {}); this.toast("Demo data reset.", "ok"); } catch (e) { this.toast(e.message, "bad"); }
  },
};
