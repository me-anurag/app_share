/* AppShare Control Center — Monitor: what the server tracks. */
"use strict";

const Monitor = (() => {
  const LOG_MAX = 300;
  let log = [], security = [];
  let filter = "all", paused = false, chartMode = "chart";
  const $ = id => document.getElementById(id);
  const ORDER = ["page", "data", "submit", "agent"];    // stack order bottom → top (validated adjacent pairs)

  function skeleton() {
    $("view-monitor").innerHTML = `
      <div class="offline-note hidden" id="monOffline">${CC.icon("power")}
        <span>The server is off, so there is nothing to measure. Turn it on with the power switch; numbers start counting immediately.</span></div>
      <div class="mon-alerts" id="monAlerts"></div>

      <div class="kpi-strip">
        <div class="kpi hero"><div class="k-l">Devices connected now</div><div class="k-v" id="kDevices">0</div><div class="k-list" id="kDevKinds"></div></div>
        <div class="kpi"><div class="k-l">Uptime</div><div class="k-v num" id="kUptime">—</div><div class="k-s" id="kStarted">&nbsp;</div></div>
        <div class="kpi"><div class="k-l">Requests served</div><div class="k-v" id="kReq">0</div><div class="k-s" id="kRpm">&nbsp;</div></div>
        <div class="kpi"><div class="k-l">Avg response time</div><div class="k-v" id="kMs">—</div><div class="k-s" id="kErr">&nbsp;</div></div>
        <div class="kpi"><div class="k-l">People signed in</div><div class="k-v" id="kUsers">0</div><div class="k-s" id="kLogins">&nbsp;</div></div>
      </div>
      <div class="kpi-strip">
        <div class="kpi"><div class="k-l">Apps</div><div class="k-v" id="kApps">0</div><div class="k-s" id="kAppsS">&nbsp;</div></div>
        <div class="kpi"><div class="k-l">Responses collected</div><div class="k-v" id="kSubs">0</div><div class="k-s" id="kSubsS">&nbsp;</div></div>
        <div class="kpi"><div class="k-l">Files stored</div><div class="k-v" id="kFiles">0</div><div class="k-s" id="kFilesS">&nbsp;</div></div>
        <div class="kpi"><div class="k-l">Agent runs</div><div class="k-v" id="kAgent">0</div><div class="k-s" id="kAgentS">&nbsp;</div></div>
        <div class="kpi"><div class="k-l">App installed on</div><div class="k-v" id="kInst">0</div><div class="k-list" id="kInstS"></div></div>
      </div>

      <div class="mon-grid">
        <div class="panel span-8">
          <div class="panel-head">
            <div><h2>Traffic</h2><p class="sub">Requests per minute by type, last 30 minutes</p></div>
            <div class="chart-tools">
              <div class="legend" id="trafficLegend"></div>
              <div class="seg" role="group" aria-label="View"><button data-cm="chart" class="on">Chart</button><button data-cm="table">Table</button></div>
            </div>
          </div>
          <div class="chart-box" id="trafficBox"></div>
        </div>
        <div class="panel span-4">
          <div class="panel-head"><div><h2>Connected devices</h2><p class="sub">Each browser that has talked to the server</p></div></div>
          <div class="tbl-wrap" id="devTable"></div>
        </div>
        <div class="panel span-7">
          <div class="panel-head"><div><h2>Apps on this server</h2><p class="sub">Status, audience, and how many have responded</p></div></div>
          <div class="tbl-wrap" id="appsTable"></div>
        </div>
        <div class="panel span-5">
          <div class="panel-head"><div><h2>Security & validation</h2><p class="sub">Everything the server refused, and why</p></div></div>
          <div class="sec-counts" id="secCounts"></div>
          <div class="sec-list" id="secList"></div>
        </div>
        <div class="panel span-6">
          <div class="panel-head"><div><h2>Agents</h2><p class="sub">Calls to Claude, tool use and tokens</p></div></div>
          <div class="sec-counts counts6" id="agentCounts"></div>
          <div class="label" style="margin:.3rem 0 .7rem">Runs by agent</div>
          <div class="bars" id="agentBars" style="margin-bottom:1rem"></div>
          <div class="label" style="margin:.3rem 0 .7rem">Tool calls</div>
          <div class="bars" id="toolBars"></div>
        </div>
        <div class="panel span-6">
          <div class="panel-head"><div><h2>Busiest endpoints</h2><p class="sub">Requests per route, with average time</p></div></div>
          <div class="bars" id="epBars"></div>
        </div>
        <div class="panel span-12">
          <div class="panel-head">
            <div><h2>Request log</h2><p class="sub">Every request as it happens</p></div>
            <div class="log-tools">
              <div class="seg" id="logFilters" role="group" aria-label="Filter"></div>
              <button class="btn sm" id="logPause">Pause</button>
            </div>
          </div>
          <div class="log-box" id="logBox"></div>
        </div>
      </div>`;

    $("trafficLegend").innerHTML = ORDER.map(k => `<span><i class="sw" style="background:${CC.KINDS[k].color}"></i>${CC.KINDS[k].label}</span>`).join("");
    document.querySelectorAll("[data-cm]").forEach(b => b.onclick = () => {
      chartMode = b.dataset.cm;
      document.querySelectorAll("[data-cm]").forEach(x => x.classList.toggle("on", x === b));
      renderTraffic();
    });
    const filters = [["all", "All"], ["page", "Pages"], ["data", "Data"], ["submit", "Submissions"], ["agent", "Agents"], ["errors", "Errors"]];
    $("logFilters").innerHTML = filters.map(([k, l]) => `<button class="${k === filter ? "on" : ""}" data-f="${k}">${l}</button>`).join("");
    document.querySelectorAll("[data-f]").forEach(b => b.onclick = () => {
      filter = b.dataset.f;
      document.querySelectorAll("[data-f]").forEach(x => x.classList.toggle("on", x === b));
      renderLog();
    });
    $("logPause").onclick = () => { paused = !paused; $("logPause").textContent = paused ? "Resume" : "Pause"; if (!paused) renderLog(); };
    window.addEventListener("resize", () => { if (CC.mode === "monitor") renderTraffic(); });
    renderAll();
  }

  const tag = (cls, text, shape = "") => `<span class="tag ${cls}"><i class="mk ${shape}"></i>${text}</span>`;

  // -------------------------------------------------------------- KPI strip
  function renderTiles() {
    const snap = CC.snapshot, on = CC.online();
    $("monOffline").classList.toggle("hidden", on);
    if (!snap) {
      ["kDevices", "kReq", "kUsers", "kApps", "kSubs", "kFiles", "kAgent"].forEach(id => $(id).textContent = "0");
      ["kUptime", "kMs"].forEach(id => $(id).textContent = "—");
      ["kStarted", "kRpm", "kErr", "kLogins", "kAppsS", "kSubsS", "kFilesS", "kAgentS"].forEach(id => $(id).innerHTML = "&nbsp;");
      $("kDevKinds").innerHTML = "";
      $("kInst").textContent = "—"; $("kInstS").innerHTML = "";
      return;
    }
    renderAlerts(snap);
    const c = snap.counters, db = snap.db, now = Date.now();
    const live = snap.devices.filter(d => now - d.last_seen < 30000);
    $("kDevices").textContent = live.length;
    const kinds = {};
    live.forEach(d => { kinds[d.os] = (kinds[d.os] || 0) + 1; });
    $("kDevKinds").innerHTML = Object.entries(kinds).map(([k, n]) => tag("", `${n} ${CC.esc(k)}`)).join("") || `<span class="k-s">Waiting for phones</span>`;
    $("kUptime").textContent = CC.hms(now - snap.server.started_at);
    $("kStarted").textContent = "since " + new Date(snap.server.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    $("kReq").textContent = CC.num(c.requests);
    const last = snap.series[snap.series.length - 1] || {};
    $("kRpm").textContent = `${ORDER.reduce((s, k) => s + (last[k] || 0), 0)} this minute`;
    $("kMs").textContent = c.requests ? c.avg_ms + " ms" : "—";
    $("kErr").innerHTML = c.errors ? `<span class="st" style="color:#f08a7f">${CC.icon("alert")}${c.errors} server errors</span>` : `<span class="st" style="color:#7fcf80">${CC.icon("check")}no server errors</span>`;
    $("kUsers").textContent = new Set(snap.devices.filter(d => d.user && now - d.last_seen < 300000).map(d => d.user)).size;
    $("kLogins").textContent = `${c.logins} sign-ins · ${db.users} members`;
    $("kApps").textContent = db.apps_total;
    const bs = db.apps_by_status;
    $("kAppsS").textContent = `${bs.published || 0} live · ${bs.draft || 0} draft · ${bs.closed || 0} closed`;
    $("kSubs").textContent = CC.num(db.submissions);
    $("kSubsS").textContent = `${c.submissions} since start`;
    $("kFiles").textContent = CC.num(db.files);
    $("kFilesS").textContent = `${CC.bytes(db.files_bytes)} · database ${CC.bytes(db.db_bytes)}`;
    $("kAgent").textContent = c.agent_runs;
    $("kAgentS").textContent = `${CC.num(c.tokens_in + c.tokens_out)} tokens · ${c.tool_calls} tool calls`;
    // Installs: a device counts once it reported an install or opened AppShare from its home-screen icon.
    const inst = snap.installs || { count: 0, devices: [] };
    $("kInst").textContent = `${inst.count} ${inst.count === 1 ? "device" : "devices"}`;
    $("kInstS").innerHTML = inst.devices.slice(0, 6).map(d => {
      const who = d.user || [d.model, d.os].filter(Boolean).join(" ") || "Device";
      const when = d.last_open || d.installed_at || d.last_seen;
      return `<span title="${CC.esc(`${d.os} · ${d.browser}${d.model ? " · " + d.model : ""} · last opened ${CC.ago(when)} · opened ${d.opens || 0}× from the icon`)}">${tag("", CC.esc(who))}</span>`;
    }).join("") + (inst.count > 6 ? tag("muted", `+${inst.count - 6} more`) : "") || `<span class="k-s">Counted when opened from the home-screen icon</span>`;
  }

  // -------------------------------------------------------------- alerts + AI budget (limits are enforced on the server)
  function renderAlerts(snap) {
    const box = $("monAlerts");
    if (!box) return;
    const L = snap.limits, A = snap.alerts || [];
    const col = { critical: CC.STATUS.critical, serious: CC.STATUS.serious, warning: CC.STATUS.warning };
    const usd = v => "$" + v.toFixed(v < 1 ? 3 : 2);
    const bar = L ? `<div class="budget"><span class="label">AI budget today</span>
        <span class="bud-bar" role="img" aria-label="${L.used_pct}% used"><i style="width:${Math.min(100, L.used_pct)}%;background:${L.used_pct >= 100 ? CC.STATUS.critical : L.used_pct >= 80 ? CC.STATUS.warning : CC.STATUS.good}"></i></span>
        <b class="mono">${usd(L.spent_today_usd)} of ${usd(L.budget_usd)}</b>
        <span class="cell-sub">· limit ${L.per_user_per_hour} AI requests per person per hour · refused: ${L.refused.budget} over budget, ${L.refused.rate} over the hourly limit</span></div>` : "";
    box.innerHTML = bar + A.map(a => `<div class="alert-row" style="border-left-color:${col[a.level] || CC.STATUS.warning}">
        <span class="st" style="color:${col[a.level] || CC.STATUS.warning}">${CC.icon("alert")}${a.level}</span><span>${CC.esc(a.text)}</span></div>`).join("");
  }

  // -------------------------------------------------------------- traffic chart
  function niceMax(v) {
    if (v <= 4) return 4;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }
  const hhmm = t => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

  function renderTraffic() {
    const box = $("trafficBox");
    const series = CC.snapshot?.series || [];
    if (chartMode === "table") {
      box.innerHTML = `<div class="tbl-wrap" style="max-height:260px;overflow:auto"><table class="tbl"><thead><tr><th>Minute</th>${ORDER.map(k => `<th class="r">${CC.KINDS[k].label}</th>`).join("")}<th class="r">Total</th></tr></thead><tbody>
        ${[...series].reverse().map(m => `<tr><td class="mono">${hhmm(m.t)}</td>${ORDER.map(k => `<td class="r">${m[k]}</td>`).join("")}<td class="r"><b>${ORDER.reduce((s, k) => s + m[k], 0)}</b></td></tr>`).join("") || `<tr><td colspan="6" class="empty-note">No data yet.</td></tr>`}
      </tbody></table></div>`;
      return;
    }
    const W = Math.max(320, box.clientWidth || 700), H = 260;
    const m = { l: 40, r: 8, t: 12, b: 28 };
    const pw = W - m.l - m.r, ph = H - m.t - m.b;
    const totals = series.map(s => ORDER.reduce((a, k) => a + s[k], 0));
    const max = niceMax(Math.max(0, ...totals));
    const n = Math.max(series.length, 1);
    const slot = pw / n, bw = Math.min(24, Math.max(4, slot * .62)), GAP = 2;
    const y = v => m.t + ph - (v / max) * ph;
    let g = "";
    for (let i = 0; i <= 4; i++) {
      const v = (max / 4) * i, yy = y(v);
      g += `<line class="${i ? "gridline" : "baseline"}" x1="${m.l}" x2="${W - m.r}" y1="${yy}" y2="${yy}"/>`;
      g += `<text class="axis-t" x="${m.l - 8}" y="${yy + 4}" text-anchor="end">${CC.num(v)}</text>`;
    }
    series.forEach((s, i) => {
      const cx = m.l + slot * i + slot / 2;
      const parts = ORDER.filter(k => s[k] > 0);
      let base = y(0);
      parts.forEach((k, j) => {
        const h = (s[k] / max) * ph, gap = j > 0 ? GAP : 0;
        const y0 = base - gap, hh = Math.max(1, h - gap), x0 = cx - bw / 2, y1 = y0 - hh;
        if (j === parts.length - 1) {
          const r = Math.min(4, hh, bw / 2);
          g += `<path fill="${CC.KINDS[k].color}" d="M${x0},${y0} V${y1 + r} Q${x0},${y1} ${x0 + r},${y1} H${x0 + bw - r} Q${x0 + bw},${y1} ${x0 + bw},${y1 + r} V${y0} Z"/>`;
        } else {
          g += `<rect fill="${CC.KINDS[k].color}" x="${x0}" y="${y1}" width="${bw}" height="${hh}"/>`;
        }
        base = y1;
      });
      if (i % 5 === (series.length - 1) % 5) g += `<text class="axis-t" x="${cx}" y="${H - 8}" text-anchor="middle">${i === series.length - 1 ? "now" : hhmm(s.t)}</text>`;
      g += `<rect class="hit" data-i="${i}" x="${m.l + slot * i}" y="${m.t}" width="${slot}" height="${ph}"/>`;
    });
    const empty = !totals.some(Boolean);
    box.innerHTML = `<svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Stacked columns: requests per minute by type">${g}
      ${empty ? `<text class="axis-t" x="${m.l + pw / 2}" y="${m.t + ph / 2}" text-anchor="middle">${CC.online() ? "No requests yet. Open AppShare on a phone." : "Server is off"}</text>` : ""}</svg>
      <div class="tooltip hidden" id="trafficTip"></div>`;
    const tip = $("trafficTip");
    box.querySelectorAll(".hit").forEach(r => {
      r.addEventListener("mouseenter", () => {
        const s = series[+r.dataset.i];
        const total = ORDER.reduce((a, k) => a + s[k], 0);
        tip.innerHTML = `<div class="tt-h">${hhmm(s.t)}</div>
          ${[...ORDER].reverse().map(k => `<div class="tt-r"><span><i class="sw" style="background:${CC.KINDS[k].color}"></i>${CC.KINDS[k].label}</span><b>${s[k]}</b></div>`).join("")}
          <div class="tt-r tt-t"><span>Total</span><b>${total}</b></div>`;
        tip.classList.remove("hidden");
        const bx = box.getBoundingClientRect(), rx = r.getBoundingClientRect();
        let left = rx.left - bx.left + rx.width + 8;
        if (left + 200 > bx.width) left = rx.left - bx.left - 200;
        tip.style.left = left + "px";
        tip.style.top = "10px";
      });
      r.addEventListener("mouseleave", () => tip.classList.add("hidden"));
    });
  }

  // -------------------------------------------------------------- tables
  function renderDevices() {
    const list = (CC.snapshot?.devices || []).slice(0, 12);
    if (!list.length) { $("devTable").innerHTML = `<div class="empty-note">${CC.online() ? "No devices yet. Scan the QR code on a phone." : "Server is off."}</div>`; return; }
    const now = Date.now();
    $("devTable").innerHTML = `<table class="tbl"><thead><tr><th>Device</th><th>Seen</th><th class="r">Req</th></tr></thead><tbody>
      ${list.map(d => {
        const on = now - d.last_seen < 30000, idle = !on && now - d.last_seen < 300000;
        const st = on ? `<span class="st"><i class="mk" style="background:${CC.STATUS.good}"></i>Online</span>`
          : idle ? `<span class="st"><i class="mk" style="background:#8c8a7f;border-radius:50%"></i>Idle</span>`
          : `<span class="st" style="color:#8c8a7f"><i class="mk" style="border:1px solid #8c8a7f"></i>Away</span>`;
        return `<tr><td><div class="dev-cell"><span class="dev-ico">${CC.deviceIcon(d.kind)}</span><div>
            <div><b>${CC.esc(d.user || "Not signed in")}</b></div>
            <div class="cell-sub">${CC.esc(d.label)} · ${CC.esc(d.browser)} · <span class="mono">${CC.esc(d.ip)}</span></div></div></div></td>
          <td>${st}<div class="cell-sub">${CC.ago(d.last_seen)} · ${CC.esc(d.via)}</div></td>
          <td class="r mono">${CC.num(d.requests)}</td></tr>`;
      }).join("")}</tbody></table>`;
  }

  function deadline(a) {
    if (!a.closes_at) return `<span class="cell-sub">No deadline</span>`;
    const ms = new Date(a.closes_at).getTime() - Date.now();
    if (ms <= 0) return `<span class="cell-sub">Closed ${new Date(a.closes_at).toLocaleDateString([], { day: "numeric", month: "short" })}</span>`;
    const d = Math.floor(ms / 86400000), h = Math.floor((ms % 86400000) / 3600000), mi = Math.floor((ms % 3600000) / 60000);
    return `<span class="mono">${d ? `${d}d ${h}h` : h ? `${h}h ${mi}m` : `${mi}m`}</span> <span class="cell-sub">left</span>`;
  }

  function statusTag(a) {
    if (a.status === "draft") return tag("warn", "Draft", "tri");
    if (a.status === "closed" || a.window === "closed") return tag("bad", "Closed");
    if (a.window === "not_open") return tag("muted", "Opens later");
    return tag("good", "Open", "circle");
  }

  function renderApps() {
    const apps = CC.snapshot?.db?.apps || [];
    if (!apps.length) { $("appsTable").innerHTML = `<div class="empty-note">${CC.online() ? "No apps yet. Ask the Builder agent to make one." : "Server is off."}</div>`; return; }
    $("appsTable").innerHTML = `<table class="tbl"><thead><tr><th>App</th><th>Status</th><th>Responses</th><th>Deadline</th></tr></thead><tbody>
      ${apps.map(a => {
        const pct = a.audience ? Math.min(100, Math.round(a.responses / a.audience * 100)) : 0;
        return `<tr><td><b>${CC.esc(a.title)}</b><div class="cell-sub">by ${CC.esc(a.owner)} · ${a.shares.length ? "shared with " + a.shares.map(CC.esc).join(", ") : "not shared"}</div></td>
          <td>${statusTag(a)}</td>
          <td style="min-width:140px"><div class="mono" style="font-size:.8rem">${a.responses}${a.audience ? ` / ${a.audience}` : ""}${a.files ? ` <span class="cell-sub">· ${a.files} files</span>` : ""}</div>
            ${a.audience ? `<div class="meter ${pct >= 100 ? "done" : ""}" role="img" aria-label="${pct}% responded"><i style="width:${pct}%"></i></div>` : ""}</td>
          <td>${deadline(a)}</td></tr>`;
      }).join("")}</tbody></table>`;
  }

  // -------------------------------------------------------------- security
  const SEC_TYPES = { submission_rejected: 1, access_denied: 1, login_failed: 1, review_done: 1 };
  function secItem(ev) {
    const E = CC.esc;
    if (ev.type === "review_done") {
      return { c: ev.verdict === "problem" ? CC.STATUS.critical : CC.STATUS.warning, i: "lens",
        t: `Review agent flagged <b>${E(ev.user)}</b>'s submission to “${E(ev.title)}”`, s: E(ev.summary) };
    }
    if (ev.type === "submission_rejected") {
      return ev.blocked_file
        ? { c: CC.STATUS.critical, i: "shield", t: `Blocked a file from <b>${E(ev.user)}</b> on “${E(ev.title)}”`, s: E((ev.reasons || []).join(" · ")) }
        : { c: CC.STATUS.warning, i: "alert", t: `Rejected a response from <b>${E(ev.user)}</b> on “${E(ev.title)}”`, s: E((ev.reasons || []).join(" · ")) };
    }
    if (ev.type === "access_denied") return { c: CC.STATUS.serious, i: "block", t: `<b>${E(ev.user)}</b> tried to open “${E(ev.app)}”`, s: `needed ${E(ev.needed)}, had ${E(ev.had)}` };
    return { c: CC.STATUS.critical, i: "key", t: `Sign-in refused for <span class="mono">${E(ev.email)}</span>`, s: "not a member of the organization" };
  }
  function renderSecurity() {
    const c = CC.snapshot?.counters;
    const count = (n, l, col, i) => `<div class="sec-count"><div class="n">${n}</div><div class="l"><span style="color:${col}">${CC.icon(i)}</span>${l}</div></div>`;
    $("secCounts").innerHTML = count(c?.rejected_uploads || 0, "Files blocked", CC.STATUS.critical, "shield") + count(c?.denied || 0, "Access denied", CC.STATUS.serious, "block") + count(c?.failed_logins || 0, "Sign-ins refused", CC.STATUS.critical, "key");
    $("secList").innerHTML = security.length ? security.slice(0, 30).map(ev => {
      const it = secItem(ev);
      return `<div class="sec-item"><span class="si-i" style="color:${it.c}">${CC.icon(it.i)}</span><div><div class="si-t">${it.t}</div><div class="si-s">${it.s}</div></div><span class="si-m">${CC.clock(ev.ts)}</span></div>`;
    }).join("") : `<div class="empty-note">Nothing blocked yet. Try uploading a renamed file, or opening an app you don't have access to.</div>`;
  }

  // -------------------------------------------------------------- agents + endpoints
  function bars(rows, color) {
    const max = Math.max(1, ...rows.map(r => r.v));
    return rows.map(r => `<div class="bar-row"><span class="bl" title="${CC.esc(r.l)}">${CC.esc(r.l)}</span>
      <span class="bt"><i style="width:${(r.v / max) * 100}%;background:${color}"></i></span>
      <span class="bv">${CC.num(r.v)}${r.s ? `<small>${r.s}</small>` : ""}</span></div>`).join("");
  }

  function renderAgents() {
    const c = CC.snapshot?.counters, s = CC.snapshot?.server;
    const box = (n, l) => `<div class="sec-count"><div class="n">${n}</div><div class="l">${l}</div></div>`;
    $("agentCounts").innerHTML = c
      ? box(c.agent_runs, "Runs") + box(c.agent_avg_ms ? (c.agent_avg_ms / 1000).toFixed(1) + " s" : "—", "Avg time per run") + box(c.llm_calls, "Claude calls")
        + box(CC.num(c.tokens_in), "Tokens read") + box(CC.num(c.tokens_out), "Tokens written") + box(c.agent_errors, "Errors")
      : box("—", "Runs") + box("—", "Avg time per run") + box("—", "Claude calls") + box("—", "Tokens read") + box("—", "Tokens written") + box("—", "Errors");
    const order = ["builder", "data", "design", "access", "insights", "review", "reminder"];
    const runsBy = order.map(k => ({ l: k, v: (c?.agents || {})[k] || 0 }));
    $("agentBars").innerHTML = c && runsBy.some(r => r.v) ? bars(runsBy, CC.KINDS.agent.color) : `<div class="empty-note">No agent has run yet.</div>`;
    const tools = Object.entries(c?.tools || {}).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([l, v]) => ({ l, v }));
    $("toolBars").innerHTML = tools.length ? bars(tools, CC.KINDS.agent.color)
      : `<div class="empty-note">${s ? (s.api_key ? "No agent runs yet. Ask the Builder agent for an app." : "No API key, so the agents are off. Add one under Connect phones → Agent API key.") : "Server is off."}</div>`;
  }

  function renderEndpoints() {
    const eps = CC.snapshot?.counters?.endpoints || [];
    $("epBars").innerHTML = eps.length ? bars(eps.slice(0, 9).map(e => ({ l: e.route, v: e.count, s: `${(e.ms / e.count).toFixed(0)} ms` })), CC.KINDS.page.color)
      : `<div class="empty-note">No requests yet.</div>`;
  }

  // -------------------------------------------------------------- request log
  function rowHtml(ev, fresh) {
    const sc = ev.status >= 500 ? "bad" : ev.status >= 400 ? "warn" : "ok";
    return `<div class="log-row${fresh ? " fresh" : ""}"><span class="lt">${CC.clock(ev.ts)}</span><i class="sw" style="background:${CC.KINDS[ev.kind]?.color || "#8c8a7f"}" title="${CC.KINDS[ev.kind]?.label || ""}"></i>
      <span class="lm">${CC.esc(ev.method)}</span><span class="lp" title="${CC.esc(ev.path)}">${CC.esc(ev.path)}</span>
      <span class="ls ${sc}">${ev.status}</span><span class="lms">${ev.ms} ms</span><span class="lu">${CC.esc(ev.user || ev.device_label || "")}</span></div>`;
  }
  const visible = ev => filter === "all" ? true : filter === "errors" ? ev.status >= 400 : ev.kind === filter;
  function renderLog() {
    const rows = log.filter(visible).slice(0, 150);
    $("logBox").innerHTML = `<div class="log-row log-head"><span>Time</span><span></span><span>Method</span><span>Path</span><span>Status</span><span style="text-align:right">Duration</span><span>Who</span></div>` +
      (rows.map(r => rowHtml(r)).join("") || `<div class="empty-note" style="padding:1rem">No requests ${filter === "all" ? "yet" : "of this type yet"}.</div>`);
  }

  function renderAll() { renderTiles(); renderTraffic(); renderDevices(); renderApps(); renderSecurity(); renderAgents(); renderEndpoints(); renderLog(); }

  // -------------------------------------------------------------- wiring
  CC.on("init", skeleton);
  CC.on("snapshot", () => { if (CC.mode === "monitor") { renderTiles(); renderTraffic(); renderDevices(); renderApps(); renderSecurity(); renderAgents(); renderEndpoints(); } });
  CC.on("tick", () => { if (CC.mode === "monitor" && CC.snapshot) $("kUptime").textContent = CC.hms(Date.now() - CC.snapshot.server.started_at); });
  CC.on("mode", m => { if (m === "monitor") renderAll(); });
  CC.on("history", events => {
    log = events.filter(e => e.type === "http").reverse().slice(0, LOG_MAX);
    security = events.filter(e => SEC_TYPES[e.type] && !(e.type === "review_done" && e.verdict === "ok")).reverse();
    if (CC.mode === "monitor") { renderLog(); renderSecurity(); }
  });
  CC.on("event", ev => {
    if (ev.sim) return;
    if (ev.type === "http") {
      log.unshift(ev);
      if (log.length > LOG_MAX) log.length = LOG_MAX;
      if (CC.mode === "monitor" && !paused && visible(ev)) {
        const box = $("logBox");
        box.querySelector(".empty-note")?.remove();
        box.firstElementChild.insertAdjacentHTML("afterend", rowHtml(ev, true));
        while (box.children.length > 151) box.lastElementChild.remove();
      }
    } else if (SEC_TYPES[ev.type] && !(ev.type === "review_done" && ev.verdict === "ok")) {
      security.unshift(ev);
      if (CC.mode === "monitor") renderSecurity();
    }
  });
  CC.on("status", (st, prev) => { if (CC.mode === "monitor" && (!prev || prev.state !== st.state)) renderAll(); });

  return { renderAll };
})();
