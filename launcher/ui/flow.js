/* AppShare Control Center — Flow: every app's journey, from the request typed to sharing and responses.
   Everything shown is read from the server's trace store (measured, never simulated). Click any node for its details. */
"use strict";

const Flow = (() => {
  const $ = id => document.getElementById(id);
  const E = s => CC.esc(s);
  let journeys = [], sel = null, J = null, round = null, node = null, follow = true;
  let refreshTimer = null, loading = false;

  // -------------------------------------------------------------- formatting
  const ms = v => v == null ? "—" : v < 1000 ? `${v} ms` : v < 60000 ? `${(v / 1000).toFixed(1)} s` : CC.dur(v);
  const usd = v => v == null ? "—" : v === 0 ? "$0" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`;
  const tok = (i, o) => `${CC.num(i)} in · ${CC.num(o)} out`;
  const json = v => `<pre class="fl-json">${E(JSON.stringify(v, null, 2))}</pre>`;
  const AGENT = { builder: "Builder", data: "Data agent", design: "Design agent", access: "Access agent",
                  review: "Review agent", reminder: "Reminder agent", insights: "Insights agent", site: "Site agent" };

  // -------------------------------------------------------------- skeleton
  function skeleton() {
    $("view-flow").innerHTML = `
      <div class="offline-note hidden" id="flOffline">${CC.icon("power")}<span>The server is off. Journeys are saved, so they show again as soon as it's on.</span></div>
      <div class="fl-grid">
        <aside class="panel fl-side">
          <div class="panel-head"><div><h2>Journeys</h2><p class="sub">One per app · newest activity first</p></div>
            <label class="mini-switch" title="Jump to the app that's being worked on right now"><input type="checkbox" id="flFollow" checked><span class="toggle"></span>Follow live</label></div>
          <div id="flList" class="fl-list"></div>
          <div class="note" id="flHealth"></div>
        </aside>
        <section class="fl-main">
          <div class="panel" id="flHead"></div>
          <div class="panel fl-canvas-panel">
            <div class="panel-head"><div><h2>Flow</h2><p class="sub">From the request to sharing and responses. Click any step for its details.</p></div>
              <div class="fl-tools"><button class="btn sm fl-replay" id="flReplay" title="Play this round again on its real timeline. Nothing is re-run and nothing costs anything."></button><div class="fl-rounds" id="flRounds"></div></div></div>
            <div class="fl-canvas-wrap" id="flWrap"><div class="fl-canvas" id="flCanvas"></div></div>
            <div class="fl-legend">
              <span><i class="fl-dot ok"></i>Done</span><span><i class="fl-dot run"></i>Working now</span>
              <span><i class="fl-dot warn"></i>Needed a fix</span><span><i class="fl-dot err"></i>Failed</span><span><i class="fl-dot idle"></i>Not yet / not used</span>
            </div>
          </div>
          <div class="panel" id="flTiming"></div>
        </section>
      </div>
      <aside class="fl-drawer hidden" id="flDrawer" aria-label="Step details">
        <div class="fl-dh"><div id="flDTitle"></div><button class="icon-btn" id="flDClose" aria-label="Close" data-icon="x"></button></div>
        <div class="fl-db" id="flDBody"></div>
      </aside>`;
    $("flFollow").onchange = e => { follow = e.target.checked; };
    $("flDClose").onclick = closeDrawer;
    document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
    window.addEventListener("resize", () => { if (CC.mode === "flow") fit(); });
    CC.hydrateIcons($("view-flow"));
    render();
  }

  // -------------------------------------------------------------- data
  async function load(full = true) {
    if (!CC.online() || !CC.status || loading || replay) return;
    loading = true;
    try {
      const r = await fetch(CC.appUrl("/api/trace/journeys?limit=80"));
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      const newest = d.journeys[0];
      if (follow && newest && (newest.running || !sel) && newest.id !== sel) { sel = newest.id; round = null; node = null; }
      if (!sel && newest) sel = newest.id;
      journeys = d.journeys;
      $("flHealth").textContent = d.health.failures ? `Tracing skipped ${d.health.failures} write(s): ${d.health.last_failure}` : "";
      const mine = journeys.find(j => j.id === sel);
      if (sel && (full || !J || J.id !== sel || (mine && mine.updated_at !== J.updated_at))) {
        const jr = await fetch(CC.appUrl(`/api/trace/journeys/${encodeURIComponent(sel)}`));
        J = jr.ok ? await jr.json() : null;
      }
    } catch (e) { console.warn("flow", e); }
    loading = false;
    render();
  }

  function schedule(delay = 600) {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => load(true), delay);
  }

  // -------------------------------------------------------------- journey list
  function renderList() {
    const box = $("flList");
    if (!journeys.length) {
      box.innerHTML = `<div class="empty-note">${CC.online() ? "No journeys yet. Create an app on a phone (describe it, or use a template) and its journey appears here live." : "Server is off."}</div>`;
      return;
    }
    box.innerHTML = journeys.map(j => {
      const t = j.totals, ev = j.events || {};
      const state = j.running ? "run" : j.run_errors ? "err" : "ok";
      return `<button class="fl-item ${j.id === sel ? "sel" : ""}" data-j="${E(j.id)}">
        <div class="fl-it"><i class="fl-dot ${state}"></i><b>${E(j.title || "New app")}</b></div>
        <div class="cell-sub">${E(j.owner || "")} · ${E(originLabel(j.origin))} · ${CC.ago(j.updated_at)}</div>
        <div class="fl-im mono">${t.llm_calls ? `${t.llm_calls} calls · ${usd(t.cost)}` : "no agent calls"}${ev.app_shared ? ` · shared` : ""}${ev.submission ? ` · ${ev.submission} resp` : ""}</div>
      </button>`;
    }).join("");
    box.querySelectorAll("[data-j]").forEach(b => b.onclick = () => { stopReplay(); sel = b.dataset.j; round = null; closeDrawer(); follow = false; $("flFollow").checked = false; load(true); });
  }
  const originLabel = o => ({ agent: "built by agents", template: "from a template", blank: "created", edit: "edited by agents", existing: "earlier app" }[o] || o || "");

  // -------------------------------------------------------------- model of one journey
  function model() {
    const runs = J.runs || [];
    const builders = runs.filter(r => r.agent === "builder").sort((a, b) => a.started_at - b.started_at);
    if (round == null && builders.length) round = builders[builders.length - 1].round;
    const b = builders.find(r => r.round === round) || null;
    const kids = b ? runs.filter(r => r.parent_id === b.id) : [];
    const spec = a => kids.filter(r => r.agent === a);
    const roundRuns = b ? [b, ...kids] : [];
    const validator = roundRuns.flatMap(r => r.steps.filter(s => s.kind === "validator").map(s => ({ ...s, agent: r.agent })));
    const ev = t => (J.events || []).filter(e => e.type === t);
    return { runs, builders, b, kids, spec, roundRuns, validator, ev,
             review: runs.filter(r => r.agent === "review"), reminder: runs.filter(r => r.agent === "reminder"),
             insights: runs.filter(r => r.agent === "insights") };
  }

  const sumRuns = list => list.reduce((a, r) => {
    const t = r.totals; a.ms += r.ms || 0; a.llm += t.llm_calls; a.tools += t.tool_calls; a.tin += t.tokens_in + t.cache_read + t.cache_write;
    a.tout += t.tokens_out; a.cost += t.cost || 0; a.retries += t.retries; a.err += r.status === "error" || r.status === "interrupted" ? 1 : 0;
    a.run += r.status === "running" ? 1 : 0; return a;
  }, { ms: 0, llm: 0, tools: 0, tin: 0, tout: 0, cost: 0, retries: 0, err: 0, run: 0 });

  const runState = list => !list.length ? "idle" : list.some(r => r.status === "running") ? "run"
    : list.some(r => r.status === "error" || r.status === "interrupted") ? "err"
    : list.some(r => r.totals.rejected || r.totals.retries || r.totals.tool_errors) ? "warn" : "ok";

  // -------------------------------------------------------------- header (journey totals)
  function renderHead(M) {
    const t = J.totals, now = J.app_now, p = J.params;
    const firstShare = M.ev("app_shared")[0];
    const created = M.ev("app_created")[0];
    const build = M.builders[0];
    const vTotal = t.valid + t.rejected;
    const kpi = (l, v, s = "") => `<div class="fl-k"><div class="label">${l}</div><div class="fl-kv">${v}</div><div class="cell-sub">${s}</div></div>`;
    $("flHead").innerHTML = `
      <div class="panel-head" style="margin-bottom:.6rem"><div>
        <h2>${E(J.title || "New app")}</h2>
        <p class="sub">${E(J.owner || "")} · ${E(originLabel(J.origin))} · started ${new Date(J.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}${J.app_id ? ` · app #${J.app_id}` : ""}${now ? ` · <span class="mono">${E(now.link)}</span>` : ""}</p></div>
        <div class="fl-tags">${replay ? `<span class="tag accent"><i class="mk circle"></i>Replay of the recording · nothing is re-run</span>` : now ?`<span class="tag ${now.status === "published" ? "good" : now.status === "closed" ? "muted" : "warn"}">${E(now.status)}</span>` : J.app_id ? `<span class="tag bad">deleted</span>` : `<span class="tag warn">not saved yet</span>`}
          <span class="tag muted" title="${E(J.cost_note)}">cost calculated</span></div></div>
      <div class="fl-kpis">
        ${kpi("Build time", build ? ms(build.ms) : "—", build ? "request → app ready" : "no agent build")}
        ${kpi("Model calls", t.llm_calls, `${t.tool_calls} tool calls`)}
        ${kpi("Tokens", CC.num(t.tokens_in + t.cache_read + t.cache_write), `${CC.num(t.tokens_out)} written · ${CC.num(t.cache_read)} from cache`)}
        ${kpi("Cost", usd(t.cost), "all agents, all rounds")}
        ${kpi("Validator", vTotal ? `${t.valid}/${vTotal}` : "—", !vTotal ? "no checks yet" : t.rejected ? `${t.rejected} rejected, then fixed` : "no rejections")}
        ${kpi("Retries · errors", `${t.retries} · ${t.tool_errors}`, "API retries · tool errors")}
        ${kpi("App", p ? `${p.fields} fields` : "—", p ? `${p.active_rules} rules · ${p.required} required` : "")}
        ${kpi("Responses", now ? `${now.responders}${now.audience ? "/" + now.audience : ""}` : "—", now ? (firstShare && created ? `shared ${ms(firstShare.ts - created.ts)} after creating` : now.audience ? "people responded / audience" : "people responded") : "")}
      </div>`;
  }

  // -------------------------------------------------------------- the flow graph
  // Agents are drawn as robots: their head sits above the box (HEAD px), the box is the robot's body.
  const W = 186, H = 104, HEAD = 40, CX = [0, 236, 472, 708, 944];
  const Y3 = [HEAD, HEAD + 146, HEAD + 292];   // three stacked nodes
  const ROW_B = HEAD + 292 + H + 90;
  const ROBOT = new Set(["builder", "data", "design", "access", "review", "reminder", "insights"]);
  function nodesFor(M) {
    const now = J.app_now, p = J.params, b = M.b;
    const ns = [];
    const add = (id, x, y, kind, title, state, lines, sub = "") => ns.push({ id, x, y, kind, title, state, lines, sub });
    const tmpl = !M.builders.length;
    // row A: building
    add("request", CX[0], Y3[1], "user", "Request", b || J.request ? "ok" : J.origin === "template" ? "ok" : "idle",
      b ? [`“${short(b.input, 64)}”`, `${words(b.input)} words · ${E(b.trigger)}`] : J.origin === "template" ? ["Started from a template", "no agents needed"] : ["—"], J.owner || "");
    if (b) {
      const bt = b.totals;
      add("builder", CX[1], Y3[1], "agent", "Builder", runState([b]),
        [`${ms(b.ms)} · ${bt.llm_calls} calls`, `${tok(bt.tokens_in + bt.cache_read + bt.cache_write, bt.tokens_out)}`, `${usd(bt.cost)} · ${bt.tool_calls} tools${bt.retries ? ` · ${bt.retries} retry` : ""}`], modelName(b.model));
    } else add("builder", CX[1], Y3[1], "agent", "Builder", "idle", [tmpl ? "not used (template)" : "—"]);
    ["data", "design", "access"].forEach((a, i) => {
      const rs = M.spec(a), s = sumRuns(rs);
      add(a, CX[2], Y3[i], "agent", AGENT[a], runState(rs),
        rs.length ? [`${ms(s.ms)} · ${s.llm} calls`, `${tok(s.tin, s.tout)}`, `${usd(s.cost)} · ${s.tools} tools${rs.length > 1 ? ` · ${rs.length}×` : ""}`]
          : b ? ["not needed in this round:", "the Builder made this", "change by itself"] : [tmpl ? "not used (template)" : "—"],
        rs[0] ? modelName(rs[0].model) : "");
    });
    const v = M.validator, vOk = v.filter(s => s.ok).length, vNo = v.length - vOk;
    add("validator", CX[3], Y3[1], "check", "Validator", !v.length ? "idle" : v[v.length - 1].ok ? (vNo ? "warn" : "ok") : "err",
      v.length ? [`${v.length} checks · ${vOk} valid`, vNo ? `${vNo} rejected → fixed` : "no rejections", `last: ${v[v.length - 1].ok ? "VALID" : "REJECTED"}`] : [tmpl ? "template is pre-validated" : "no checks this round"], "code");
    add("app", CX[4], Y3[1], "app", "App saved", p ? "ok" : "idle",
      p ? [`${p.fields} fields · ${p.required} required`, `${p.choice_options} options · ${p.file_fields} file${p.file_fields === 1 ? "" : "s"}`, `${p.active_rules} rules · ${E(p.look || "classic")}`] : ["not saved yet"], J.app_id ? `app #${J.app_id}` : "");
    // row B: after sharing
    const sh = M.ev("app_shared"), last = sh[sh.length - 1];
    add("shared", CX[0], ROW_B + Y3[1], "app", "Shared", sh.length ? "ok" : "idle",
      sh.length ? [`${last.detail.audience ?? "?"} people · ${E(last.detail.link_access)}`, short((last.detail.targets || []).join(", "), 40) || "—", `${sh.length} share change${sh.length > 1 ? "s" : ""}`] : ["not shared yet"]);
    const subs = M.ev("submission"), rej = M.ev("submission_rejected");
    add("responses", CX[1], ROW_B + Y3[1], "people", "Responses", now?.responses ? (rej.length ? "warn" : "ok") : "idle",
      now ? [`${now.responders} people${now.audience ? ` of ${now.audience}` : ""}`, `${subs.length} live · ${rej.length} refused`, now.audience ? pctBar(now.responders / now.audience) : `${now.responses} total`] : ["—"]);
    const rv = M.review, rs = sumRuns(rv), verdicts = now?.reviews || {};
    add("review", CX[2], ROW_B + Y3[0], "agent", "Review agent", runState(rv),
      rv.length ? [`${rv.length} reviewed · ${ms(Math.round(rs.ms / rv.length))} each`, `ok ${verdicts.ok || 0} · check ${verdicts.check || 0} · problem ${verdicts.problem || 0}`, usd(rs.cost)] : ["no reviews yet"]);
    const rm = M.reminder, rms = sumRuns(rm);
    add("reminder", CX[2], ROW_B + Y3[1], "agent", "Reminder agent", runState(rm),
      rm.length ? [`${rm.length} run${rm.length > 1 ? "s" : ""} · ${now?.reminded || 0} reminded`, `${tok(rms.tin, rms.tout)}`, usd(rms.cost)] : ["no reminders yet"]);
    const ins = M.insights, is = sumRuns(ins);
    add("insights", CX[2], ROW_B + Y3[2], "agent", "Insights agent", runState(ins),
      ins.length ? [`${ins.length} question${ins.length > 1 ? "s" : ""} answered`, `${ms(Math.round(is.ms / ins.length))} avg`, usd(is.cost)] : ["no questions yet"]);
    return ns;
  }
  const short = (s, n) => { s = String(s || "").replace(/\s+/g, " ").trim(); return E(s.length > n ? s.slice(0, n - 1) + "…" : s); };
  const modelName = m => E(String(m || "").replace(/^claude-/, ""));
  const words = s => String(s || "").trim().split(/\s+/).filter(Boolean).length;
  const pctBar = f => `<span class="fl-bar"><i style="width:${Math.round(Math.min(1, f) * 100)}%"></i></span> ${Math.round(f * 100)}%`;

  const EDGES = [["request", "builder"], ["builder", "data"], ["builder", "design"], ["builder", "access"], ["data", "design", "dep"],
                 ["data", "validator"], ["design", "validator"], ["access", "validator"], ["validator", "app"], ["app", "shared", "wrap"],
                 ["shared", "responses"], ["responses", "review"], ["responses", "reminder"], ["responses", "insights"]];

  /** An agent's box: the usual box (so arrows stay clear) with the agent itself standing small on its top edge. */
  function robotHtml(n) {
    const pose = n.state === "run" ? "think" : "idle";
    return `<button class="fl-node fl-agent ag-${n.id} s-${n.state} ${node === n.id ? "sel" : ""}" data-n="${n.id}" style="left:${n.x}px;top:${n.y}px;width:${W}px;height:${H}px" title="${E(n.title)} — an AI agent">
      <span class="fl-fig char ${n.id} ${pose}" aria-hidden="true">${CHAR.svg(n.id)}</span>
      <div class="fl-nh"><i class="fl-dot ${n.state}"></i><b>${E(n.title)}</b><span class="fl-ai">AI</span><span class="fl-ns">${n.sub}</span></div>
      ${n.lines.map(l => `<div class="fl-nl">${l}</div>`).join("")}
    </button>`;
  }

  function renderCanvas(M) {
    const ns = nodesFor(M), byId = Object.fromEntries(ns.map(n => [n.id, n]));
    const cw = CX[4] + W + 8, ch = ROW_B + Y3[2] + H + 26;
    // Orthogonal connectors with rounded corners: fan-outs read as a branching tree, fan-ins as a clean merge.
    // Each ends in a small arrowhead that stops just short of the box, and starts at a small port dot.
    const GAP = 4, R = 9, HEADL = 7, HEADW = 4;
    const elbow = (x0, y0, x1, y1) => {
      if (Math.abs(y1 - y0) < 1) return `M${x0},${y0} H${x1}`;
      const mx = Math.round((x0 + x1) / 2), dy = Math.sign(y1 - y0), r = Math.min(R, Math.abs(y1 - y0) / 2, (x1 - x0) / 2);
      return `M${x0},${y0} H${mx - r} Q${mx},${y0} ${mx},${y0 + dy * r} V${y1 - dy * r} Q${mx},${y1} ${mx + r},${y1} H${x1}`;
    };
    const layers = { idle: [], live: [], flowing: [] };
    EDGES.forEach(([a, b, how]) => {
      const A = byId[a], B = byId[b];
      const live = A.state !== "idle" && B.state !== "idle";
      const st = B.state === "run" && A.state !== "idle" ? "flowing" : live ? "live" : "idle";
      let d, head, x0, y0;
      if (how === "wrap") {                         // App saved → down → left → down into Shared
        x0 = A.x + W - 40; y0 = A.y + H;
        const ym = ROW_B - 14, x1 = B.x + 40, y1 = B.y - GAP;
        d = `M${x0},${y0} V${ym - R} Q${x0},${ym} ${x0 - R},${ym} H${x1 + R} Q${x1},${ym} ${x1},${ym + R} V${y1 - HEADL}`;
        head = `${x1 - HEADW},${y1 - HEADL} ${x1},${y1} ${x1 + HEADW},${y1 - HEADL}`;
      } else if (how === "dep") {                   // Data → Design: Design waits for Data's fields
        x0 = A.x + W / 2 - 24; y0 = A.y + H;
        const y1 = B.y - GAP;
        d = `M${x0},${y0} V${y1 - HEADL}`;
        head = `${x0 - HEADW},${y1 - HEADL} ${x0},${y1} ${x0 + HEADW},${y1 - HEADL}`;
      } else {
        x0 = A.x + W; y0 = A.y + H / 2;
        const x1 = B.x - GAP, y1 = B.y + H / 2;
        d = elbow(x0, y0, x1 - HEADL, y1);
        head = `${x1 - HEADL},${y1 - HEADW} ${x1},${y1} ${x1 - HEADL},${y1 + HEADW}`;
      }
      layers[st].push(`<g class="fl-edge s-${st} ${how || ""}"><path d="${d}"/><polygon points="${head}"/><circle cx="${x0}" cy="${y0}" r="2.6"/></g>`);
    });
    const paths = layers.idle.join("") + layers.live.join("") + layers.flowing.join("");
    $("flCanvas").style.width = cw + "px";
    $("flCanvas").style.height = ch + "px";
    $("flCanvas").innerHTML = `
      <svg class="fl-svg" width="${cw}" height="${ch}" aria-hidden="true">
        <text class="fl-row-l" x="0" y="${ROW_B - 26}">AFTER SHARING</text>
        ${paths}
      </svg>
      ${ns.map(n => ROBOT.has(n.id) ? robotHtml(n) : `<button class="fl-node k-${n.kind} s-${n.state} ${node === n.id ? "sel" : ""}" data-n="${n.id}" style="left:${n.x}px;top:${n.y}px;width:${W}px;height:${H}px">
        <div class="fl-nh"><i class="fl-dot ${n.state}"></i><b>${E(n.title)}</b><span class="fl-ns">${n.sub}</span></div>
        ${n.lines.map(l => `<div class="fl-nl">${l}</div>`).join("")}
      </button>`).join("")}`;
    $("flCanvas").querySelectorAll("[data-n]").forEach(b => b.onclick = () => openNode(b.dataset.n));
    fit();
  }

  function fit() {
    const wrap = $("flWrap"), cv = $("flCanvas");
    if (!wrap || !cv.style.width) return;
    const cw = parseFloat(cv.style.width), ch = parseFloat(cv.style.height);
    const s = Math.min(1, (wrap.clientWidth - 4) / cw);
    cv.style.transform = `scale(${s})`;
    wrap.style.height = Math.ceil(ch * s) + "px";
  }

  function renderRounds(M) {
    const box = $("flRounds");
    if (M.builders.length < 2) { box.innerHTML = M.builders.length ? `<span class="cell-sub">1 build round</span>` : ""; return; }
    box.innerHTML = `<div class="seg" role="group" aria-label="Round">${M.builders.map(r => `<button class="${r.round === round ? "on" : ""}" data-r="${r.round}" title="${E(r.input)}">${r.round === 1 ? "Built" : "Edit " + (r.round - 1)}</button>`).join("")}</div>`;
    box.querySelectorAll("[data-r]").forEach(b => b.onclick = () => { if (replay) stopReplay(); round = +b.dataset.r; render(); });
  }

  // -------------------------------------------------------------- replay: play a recorded round again on its real timeline
  // Nothing is re-run and nothing is called: the saved trace is shown as it was at each moment.
  let replay = null;
  const stepTotals = steps => {
    const t = { steps: steps.length, llm_calls: 0, tool_calls: 0, retries: 0, valid: 0, rejected: 0, tool_errors: 0, tokens_in: 0, tokens_out: 0,
                cache_read: 0, cache_write: 0, cost: 0, model_ms: 0, tool_ms: 0 };
    for (const s of steps) {
      if (s.kind === "llm") { t.llm_calls++; t.model_ms += s.ms || 0; }
      if (s.kind === "tool") { t.tool_calls++; t.tool_ms += s.ms || 0; if (!s.ok) t.tool_errors++; }
      if (s.kind === "retry") t.retries++;
      if (s.kind === "validator") s.ok ? t.valid++ : t.rejected++;
      t.tokens_in += s.tokens_in || 0; t.tokens_out += s.tokens_out || 0; t.cache_read += s.cache_read || 0; t.cache_write += s.cache_write || 0;
      t.cost += s.cost || 0;
    }
    return t;
  };
  function clockAt(F, vt) {
    const c = JSON.parse(JSON.stringify(F));
    c.runs = c.runs.filter(r => r.started_at <= vt).map(r => {
      // a step counts once it has finished (so tokens appear when each model call returns)
      const steps = r.steps.filter(s => s.started_at + (s.ms || 0) <= vt);
      const live = !r.ended_at || r.ended_at > vt;
      return { ...r, steps, status: live ? "running" : r.status, ms: live ? vt - r.started_at : r.ms, ended_at: live ? null : r.ended_at,
               output: live ? "" : r.output, totals: stepTotals(steps) };
    });
    c.events = c.events.filter(e => e.ts <= vt);
    c.totals = stepTotals(c.runs.flatMap(r => r.steps));
    const created = F.events.find(e => e.type === "app_created");
    if (created && created.ts > vt) c.params = null;
    if (vt < replay.t1) c.app_now = null;
    return c;
  }
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("appshare-replay") : null;
  async function startReplay() {
    const M = model();
    if (!M.b) return;
    const runs = [M.b, ...M.kids];
    const t0 = M.b.started_at - 600, t1 = Math.max(...runs.map(r => r.ended_at || r.started_at)) + 800;
    closeDrawer();
    // the Agent theater plays the same recorded events in step (this window, and any other Control Center window)
    let evs = null;
    try {
      const r = await fetch(CC.appUrl(`/api/trace/journeys/${encodeURIComponent(J.id)}/events?round=${M.b.round}`));
      if (r.ok) evs = await r.json();
    } catch { /* the Flow replay works on its own */ }
    const startAt = Date.now() + 600;               // the moment the Builder started, on the wall clock
    if (evs) {
      const msg = { type: "start", events: evs.events, t0: evs.t0, startAt, title: evs.title };
      // the theater joins in when it can; the Flow replay never depends on it
      try { if (typeof Theater !== "undefined" && typeof Theater.playRecorded === "function") Theater.playRecorded(msg); } catch (e) { console.warn("theater replay", e); }
      try { channel?.postMessage(msg); } catch { /* no other windows */ }
    }
    replay = { full: J, t0, t1, start: performance.now(), keepRound: round, vt: t0, synced: !!evs,
               rows: runs.map(r => ({ id: r.id, agent: r.agent })), rows0: M.b.started_at,
               rowsEnd: Math.max(...runs.map(r => r.ended_at || r.started_at)) };
    replay.timer = setInterval(tickReplay, 100);
    tickReplay();
  }
  function tickReplay() {
    if (!replay) return;
    const vt = replay.t0 + (performance.now() - replay.start);
    replay.vt = Math.min(vt, replay.t1);
    J = clockAt(replay.full, replay.vt);
    round = replay.keepRound;
    render();
    if (vt >= replay.t1) stopReplay(false);
  }
  function stopReplay(early = true) {
    if (!replay) return;
    clearInterval(replay.timer);
    if (early && replay.synced) {
      try { if (typeof Theater !== "undefined" && typeof Theater.stopRecorded === "function") Theater.stopRecorded(); } catch { /* ignore */ }
      try { channel?.postMessage({ type: "stop" }); } catch { /* ignore */ }
    }
    J = replay.full;
    replay = null;
    render();
  }
  function replayControl(M) {
    const el = $("flReplay");
    if (!el) return;
    el.disabled = !replay && !(M && M.b);
    if (!replay && !(M && M.b)) {
      el.innerHTML = "No agent build to replay";
      el.title = J && J.origin === "template" ? "This app was made from a template: no agents built it." : "No build was recorded for this app (it was made before tracing, or only reviews/reminders ran).";
      el.onclick = null;
      return;
    }
    el.title = "Play this round again on its real timeline. Nothing is re-run and nothing costs anything.";
    if (replay) {
      const done = Math.max(0, Math.min(replay.t1, replay.t0 + (performance.now() - replay.start)) - replay.t0 - 600);
      el.innerHTML = `<span class="fl-rp-live"></span>Replaying · ${(done / 1000).toFixed(1)} s of ${((replay.t1 - replay.t0 - 1400) / 1000).toFixed(1)} s${replay.synced ? " · also in Agent theater" : ""} · <u>stop</u>`;
      el.onclick = stopReplay;
    } else {
      el.innerHTML = `▶ Replay this round`;
      el.onclick = startReplay;
    }
  }

  // -------------------------------------------------------------- timing (who ran when: shows the parallel team)
  function renderTiming(M) {
    const box = $("flTiming");
    const now = replay ? replay.vt : Date.now();
    // during a replay every agent of the round keeps its row (even before it starts) and the axis is the whole round
    const order = replay ? replay.rows : M.roundRuns.map(r => ({ id: r.id, agent: r.agent }));
    const byId = Object.fromEntries(M.roundRuns.map(r => [r.id, r]));
    if (!order.length) { box.innerHTML = `<h2>Timing</h2><p class="sub">Appears when agents build or edit this app.</p>`; return; }
    const started = M.roundRuns;
    const t0 = replay ? replay.rows0 : Math.min(...started.map(r => r.started_at));
    const lastStep = r => Math.max(r.started_at, ...r.steps.map(s => s.started_at + (s.ms || 0)));
    const endOf = r => r.ended_at || (r.status === "running" ? now : lastStep(r));
    const running = started.some(r => r.status === "running");
    const t1 = replay ? replay.rowsEnd : Math.max(...started.map(endOf), running ? now : 0);
    const span = Math.max(1, t1 - t0), Wd = 900, L = 120, R = 70, rowH = 26, Hh = order.length * rowH;
    const x = t => L + (Math.min(Math.max(t, t0), t1) - t0) / span * (Wd - L - R);
    const ticks = [0, .25, .5, .75, 1].map(f => `<line class="gridline" x1="${x(t0 + f * span)}" x2="${x(t0 + f * span)}" y1="0" y2="${Hh}"/><text class="axis-t" x="${x(t0 + f * span)}" y="${Hh + 14}" text-anchor="middle">${ms(Math.round(f * span))}</text>`).join("");
    const bars = order.map((o, i) => {
      const y = i * rowH + 5, r = byId[o.id];
      const label = `<text class="fl-gl ${r ? "" : "wait"}" x="${L - 10}" y="${y + 12}" text-anchor="end">${E(AGENT[o.agent] || o.agent)}</text>`;
      if (!r) return label;
      const end = endOf(r), live = r.status === "running";
      const segs = r.steps.filter(s => s.kind === "llm" || s.kind === "tool").map(s => `<rect class="fl-seg ${s.kind}" x="${x(s.started_at)}" y="${y + 3}" width="${Math.max(1.5, x(s.started_at + (s.ms || 0)) - x(s.started_at))}" height="10"><title>${E(s.kind === "llm" ? "Model call" : s.name)} · ${ms(s.ms)}</title></rect>`).join("");
      return `${label}<rect class="fl-run ${live ? "running" : r.status}" x="${x(r.started_at)}" y="${y}" width="${Math.max(2, x(end) - x(r.started_at))}" height="16" rx="2"><title>${E(AGENT[r.agent])} · ${ms(end - r.started_at)}</title></rect>${segs}
        ${live ? `<rect class="fl-run-tip" x="${x(end) - 3}" y="${y}" width="3" height="16"/>` : ""}
        <text class="fl-gv ${live ? "live" : ""}" x="${x(end) + 6}" y="${y + 12}">${ms(end - r.started_at)}${live ? " …" : ""}</text>`;
    }).join("");
    const cursor = (replay || running) && now < t1 + 1 ? `<line class="fl-now" x1="${x(now)}" x2="${x(now)}" y1="-2" y2="${Hh + 2}"/><text class="fl-now-t" x="${x(now)}" y="-6" text-anchor="middle">${ms(Math.max(0, now - t0))}</text>` : "";
    const kids = started.slice(1), par = kids.length > 1 ? overlap(kids, now) : 0;
    box.innerHTML = `<div class="panel-head"><div><h2>Timing</h2><p class="sub">Who worked when in this round: bars are agent runs; darker marks are model calls, light marks tool calls.${replay || running ? " The line is now." : ""}</p></div>
        <div class="cell-sub">${kids.length > 1 ? `Specialists overlapped for <b>${ms(par)}</b> (parallel work)` : ""}</div></div>
      <svg class="chart-svg fl-timing" viewBox="0 -18 ${Wd} ${Hh + 38}" role="img" aria-label="Timeline of agent runs">${ticks}${bars}${cursor}</svg>`;
  }
  function overlap(rs, now = Date.now()) {
    // time during which at least two specialist runs were active
    const pts = rs.flatMap(r => [[r.started_at, 1], [r.ended_at || now, -1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let n = 0, last = 0, total = 0;
    for (const [t, d] of pts) { if (n >= 2) total += t - last; n += d; last = t; }
    return total;
  }

  // -------------------------------------------------------------- details drawer
  function openNode(id) { node = id; renderDrawer(); renderCanvas(model()); }
  function closeDrawer() { node = null; const d = $("flDrawer"); if (d) d.classList.add("hidden"); document.querySelectorAll(".fl-node.sel").forEach(n => n.classList.remove("sel")); }

  function renderDrawer() {
    if (!node || !J) return;
    const M = model();
    const d = $("flDrawer"); d.classList.remove("hidden");
    const kv = rows => `<table class="fl-kv">${rows.filter(Boolean).map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("")}</table>`;
    const sec = (t, html) => `<section class="fl-sec"><div class="label">${t}</div>${html}</section>`;
    let title = "", body = "";
    const runsBlock = rs => rs.length ? rs.map(r => runHtml(r, kv, sec)).join("") : `<div class="empty-note">Nothing recorded for this step yet.</div>`;

    if (node === "request") {
      title = "Request";
      body = M.b ? sec("What the person typed", `<blockquote class="fl-quote">${E(M.b.input)}</blockquote>`)
        + kv([["By", E(J.owner)], ["When", new Date(M.b.started_at).toLocaleString()], ["Words", words(M.b.input)], ["Round", M.b.round === 1 ? "first build" : `edit ${M.b.round - 1}`], ["Journey", `<span class="mono">${E(J.id)}</span>`]])
        + (M.builders.length > 1 ? sec("All requests on this app", `<ol class="fl-ol">${M.builders.map(r => `<li>${E(r.input)} <span class="cell-sub">· ${ms(r.ms)}</span></li>`).join("")}</ol>`) : "")
        : sec("Origin", J.origin === "template" ? "Created from a ready-made template: no agents were involved." : "No request recorded (the app existed before tracing started).");
    } else if (["builder", "data", "design", "access", "review", "reminder", "insights"].includes(node)) {
      const rs = node === "builder" ? (M.b ? [M.b] : []) : ["data", "design", "access"].includes(node) ? M.spec(node) : M[node];
      title = AGENT[node];
      body = (["review", "reminder", "insights"].includes(node) && rs.length > 1 ? sec("Across all runs", kvTotals(sumRuns(rs), rs.length, kv)) : "") + runsBlock([...rs].reverse());
    } else if (node === "validator") {
      title = "Validator";
      body = sec("What it is", `<p class="fl-p">Plain code (not AI) that checks every app before it's saved: field types, options, file rules, dates, places, statuses. The agents' own check tools call it too.</p>`)
        + (M.validator.length ? M.validator.map(s => `<div class="fl-step ${s.ok ? "" : "bad"}"><div class="fl-sl"><i class="fl-dot ${s.ok ? "ok" : "err"}"></i><b>${s.ok ? "VALID" : "REJECTED"}</b> <span class="cell-sub">${E(s.name.replace("validator · ", ""))} · ${E(AGENT[s.agent])} · ${CC.clock(s.started_at)}</span></div>
            ${(s.detail.problems || []).length ? `<ul class="fl-ul">${s.detail.problems.map(p => `<li>${E(p)}</li>`).join("")}</ul>` : ""}</div>`).join("")
          : `<div class="empty-note">No Validator checks in this round.</div>`);
    } else if (node === "app") {
      const p = J.params;
      title = "App saved";
      body = p ? kv([["Title", E(p.title)], ["Fields", `${p.fields} (${p.required} required)`], ["By type", Object.entries(p.by_type).map(([k, v]) => `${E(k)} ${v}`).join(" · ")],
          ["Choice options", p.choice_options], ["File fields", p.file_fields], ["Active rules", p.active_rules], ["Look", E(p.look || "classic")]])
        + sec("Rules", kv(Object.entries(p.rules).map(([k, v]) => [E(k.replace(/_/g, " ")), v === true ? "yes" : v === false ? "no" : E(v)])))
        + (J.app_now ? sec("Now", kv([["Status", E(J.app_now.status)], ["Link", `<span class="mono">${E(J.app_now.link)}</span>`], ["Access", E(J.app_now.link_access)]])) : "")
        : `<div class="empty-note">The app hasn't been saved yet.</div>`;
    } else if (node === "shared") {
      title = "Shared";
      const sh = M.ev("app_shared");
      body = sh.length ? sh.map(e => `<div class="fl-step"><div class="fl-sl"><i class="fl-dot ok"></i><b>${E(e.detail.audience ?? "?")} people</b> <span class="cell-sub">${CC.clock(e.ts)} · ${new Date(e.ts).toLocaleDateString()}</span></div>
          ${kv([["With", E((e.detail.targets || []).join(", ") || "—")], ["Link access", E(e.detail.link_access)], ["Published now", e.detail.published ? "yes" : "no"], ["By", E(e.detail.by)]])}</div>`).join("")
        : `<div class="empty-note">Not shared yet. Sharing only happens when the owner presses Share and confirms.</div>`;
    } else if (node === "responses") {
      title = "Responses";
      const now = J.app_now, subs = M.ev("submission"), rej = M.ev("submission_rejected");
      body = (now ? kv([["People responded", `${now.responders}${now.audience ? ` of ${now.audience} (${Math.round(now.responders / now.audience * 100)}%)` : ""}`], ["Responses in total", now.responses],
          ["Received while traced", `${subs.length} (${subs.filter(e => e.detail.updated).length} edits)`], ["Refused by the server", rej.length], ["Files", `${subs.reduce((a, e) => a + (e.detail.files || 0), 0)} · ${CC.bytes(subs.reduce((a, e) => a + (e.detail.file_bytes || 0), 0))}`]]) : "")
        + sec("Privacy", `<p class="fl-p">Answers are never stored in traces — only that a response arrived, when, and its size. ${J.params?.rules?.anonymous ? "This app is <b>anonymous</b>: no names either." : ""}</p>`)
        + (rej.length ? sec("Refused (and why)", rej.map(e => `<div class="fl-step bad"><div class="fl-sl"><b>${E(e.detail.by || "Someone")}</b> <span class="cell-sub">${CC.clock(e.ts)}</span></div><ul class="fl-ul">${(e.detail.reasons || []).map(r => `<li>${E(r)}</li>`).join("")}</ul></div>`).join("")) : "")
        + (subs.length ? sec("Arrivals", `<ol class="fl-ol">${subs.slice(-30).reverse().map(e => `<li>${E(e.detail.by || "Someone")} · ${CC.clock(e.ts)}${e.detail.updated ? " · edited" : ""}${e.detail.files ? ` · ${e.detail.files} file` : ""}</li>`).join("")}</ol>`) : "");
    }
    // Redraw only when something changed, and keep what the person opened: expanded sections, open instructions, scroll.
    const box = $("flDBody"), sameNode = box.dataset.node === node;
    if (sameNode && box.dataset.sig === body) return;
    const open = sameNode ? new Set([...box.querySelectorAll("details[open][data-k]")].map(x => x.dataset.k)) : new Set();
    const prompts = sameNode ? new Set([...box.querySelectorAll("[data-prompt]")].filter(b => b.nextElementSibling?.innerHTML).map(b => b.dataset.prompt)) : new Set();
    const scroll = sameNode ? box.scrollTop : 0;
    $("flDTitle").innerHTML = `<div class="label">Step</div><h2>${E(title)}</h2>`;
    box.innerHTML = body;
    box.dataset.sig = body; box.dataset.node = node;
    box.querySelectorAll("details[data-k]").forEach(x => { if (open.has(x.dataset.k)) x.open = true; });
    box.querySelectorAll("[data-prompt]").forEach(b => { b.onclick = () => showPrompt(b); if (prompts.has(b.dataset.prompt)) showPrompt(b); });
    box.querySelectorAll("[data-go]").forEach(b => b.onclick = () => openNode(b.dataset.go));
    CC.hydrateIcons(d);
    box.scrollTop = scroll;
  }

  // -------------------------------------------------------------- the handover: from whom, what in, what it did, what out, to whom
  const SPEC_AGENT = { ask_data_agent: "data", ask_design_agent: "design", ask_access_agent: "access", ask_site_agent: "site" };
  const FINAL = { data: "submit_fields", design: "submit_design", access: "submit_access", site: "submit_site", review: "submit_review",
                  reminder: "send_reminders" };
  const chip = (id, label) => ["builder", "data", "design", "access", "review", "reminder", "insights", "validator", "app", "request", "responses", "shared"].includes(id)
    ? `<button class="fl-go" data-go="${id}">${E(label)}</button>` : `<b>${E(label)}</b>`;
  const clip = (v, n = 160) => { const t = typeof v === "string" ? v : JSON.stringify(v); return t && t.length > n ? t.slice(0, n - 1) + "…" : (t || ""); };
  const names = list => (list || []).map(x => x && (x.name || x.label || x.title || x.type) || x).filter(Boolean);

  /** One tool call in plain words: what the agent did, and what came back. */
  function action(s) {
    const a = (s.detail || {}).args || {}, r = (s.detail || {}).result, err = r && typeof r === "object" && r.error;
    const res = err ? `error: ${clip(r.error, 140)}${r.problems ? ` (${r.problems.length} problems)` : ""}` : "";
    const A = AGENT[SPEC_AGENT[s.name]] || "";
    switch (s.name) {
      case "ask_data_agent": case "ask_design_agent": case "ask_access_agent": case "ask_site_agent":
        return [`Gave the ${A} a brief`, `“${clip(a.brief, 400)}”`,
          res || (r && (r.fields ? `got back ${r.fields.length} fields${r.closes_at ? ", deadline " + r.closes_at : ""}` : r.title ? `got back “${r.title}” in ${r.theme_color || "a colour"}`
            : r.share_suggestions ? `got back: ${names(r.share_suggestions).join(", ") || "no audience"}` : r.site ? `got back a ${r.site.theme} site` : "got its answer")), SPEC_AGENT[s.name]];
      case "check_fields": return [`Checked ${(a.fields || []).length} fields with the Validator`, names(a.fields).join(", "), res || (r?.ok ? "all valid" : `${(r?.problems || []).length} problems: ${clip((r?.problems || []).join("; "), 200)}`)];
      case "submit_fields": return [`Handed over ${(a.fields || []).length} fields${a.closes_at ? ", deadline " + a.closes_at : ""}`, names(a.fields).join(", "), res || "accepted"];
      case "get_fields": return ["Read the Data agent's fields", "", res || `${(r?.fields || []).length} fields`];
      case "check_color": return [`Checked that white text is readable on ${a.hex}`, "", r?.contrast ? `contrast ${r.contrast}:1 — ${r.readable ? "readable" : "too light"}` : res];
      case "submit_design": return [`Handed over the design: “${a.title}”`, `${a.theme_color || ""} · ${a.style || ""} ${a.pattern || ""}`.trim(), res || "accepted"];
      case "list_groups": return ["Read the list of groups", "", res || `${(r?.groups || []).length} groups`];
      case "search_people": return [`Searched the directory for “${a.query}”`, "", res || `${(r?.people || []).length} found: ${names(r?.people).slice(0, 5).join(", ")}`];
      case "submit_access": return ["Handed over who should get the app", (a.share_suggestions || []).map(x => `${x.name || x.type} (${x.role})`).join(", "), res || "accepted"];
      case "check_site": return ["Checked the site layout", "", res || (r?.ok ? `valid: ${(r.blocks || []).join(", ")}` : `${(r?.problems || []).length} problems`)];
      case "submit_site": return [`Handed over a ${a.site?.theme || ""} site`, `${(a.site?.pages || []).length} page(s)`, res || "accepted"];
      case "get_current_app": return ["Opened the current app", "", res || (r?.spec ? `“${r.spec.title}”` : "no app yet")];
      case "save_app": return [a.use_team_draft ? "Saved the team's draft" + (a.spec && Object.keys(a.spec).length ? " with changes" : "") : "Saved the app it wrote itself",
        a.spec && Object.keys(a.spec).length ? clip(a.spec, 300) : "", res || (r?.link ? `Validator: valid · saved as ${r.link}` : "")];
      case "get_overview": return ["Read the app's overview", "", res || `${r?.responses ?? "?"} responses of ${r?.expected_audience ?? "?"}`];
      case "list_responses": return ["Read the responses", "", res || `${(r?.responses || []).length} read`];
      case "list_missing": return ["Found who hasn't responded", "", res || `${(r?.missing || r?.people || []).length} people`];
      case "get_assignment": return ["Read what the assignment asks", "", res || "ok"];
      case "read_submission": return ["Read the submission (files fenced as data)", "", res || (r?.guard ? `scanner: ${clip(r.guard, 100)}` : "ok")];
      case "compare_with_others": return ["Compared it with the other submissions", "", res || clip(r, 160)];
      case "submit_review": return [`Gave its verdict: ${a.verdict}`, a.summary || "", res || "recorded as a suggestion"];
      case "send_reminders": return [`Sent ${(a.people || a.emails || []).length} reminders`, `“${a.title || ""}” — ${clip(a.message, 200)}`, res || "sent"];
      case "submit_block": return [`Wrote one ${a.block?.type || ""} block`, "", res || "added"];
    }
    return [s.name, clip(a, 200), res || clip(r, 160)];
  }

  function handover(r) {
    const parent = r.parent_id ? (J.runs || []).find(x => x.id === r.parent_id) : null;
    const steps = r.steps || [];
    const tools = steps.filter(s => s.kind === "tool");
    const fin = FINAL[r.agent] ? [...tools].reverse().find(s => s.name === FINAL[r.agent] && s.ok) : null;
    const saved = r.agent === "builder" ? [...tools].reverse().find(s => s.name === "save_app" && s.ok) : null;
    let from, to;
    if (parent) from = chip(parent.agent, `${AGENT[parent.agent] || parent.agent}`) + ` <span class="cell-sub">asked it to do this part</span>`;
    else if (r.agent === "builder") from = chip("request", J.owner ? `${J.owner} (the request)` : "the person's request");
    else if (r.agent === "review") from = chip("responses", "a new submission") + ` <span class="cell-sub">started automatically</span>`;
    else if (r.agent === "reminder") from = `<b>${r.trigger === "schedule" ? "the reminder schedule" : "the owner"}</b>`;
    else from = `<b>the owner</b> <span class="cell-sub">asked a question</span>`;
    if (parent) to = chip(parent.agent, AGENT[parent.agent]) + ` <span class="cell-sub">as the answer to its brief</span>`;
    else if (r.agent === "builder") to = chip("validator", "Validator") + " → " + chip("app", "the saved app") + ` <span class="cell-sub">and the reply</span> → ` + chip("request", J.owner || "the person");
    else if (r.agent === "review") to = chip("responses", "the owner's Responses tab") + ` <span class="cell-sub">as a suggestion — a person decides</span>`;
    else if (r.agent === "reminder") to = `<b>${(fin?.detail?.args?.people || fin?.detail?.args?.emails || []).length || "the"} people who hadn't responded</b> <span class="cell-sub">as notifications</span>`;
    else to = `<b>the owner</b> <span class="cell-sub">as the chat reply</span>`;
    const did = tools.map((s, i) => {
      const [what, detail, result, go] = action(s);
      return `<li class="${s.ok ? "" : "bad"}"><span class="fl-hn">${i + 1}</span><div><b>${E(what)}</b>${go ? " " + chip(go, "open") : ""}
        ${detail ? `<div class="fl-hd">${E(detail)}</div>` : ""}${result ? `<div class="fl-hr">→ ${E(result)}</div>` : ""}</div></li>`;
    }).join("");
    const outObj = fin?.detail?.args;
    let output = "";
    if (r.agent === "builder") {
      output = (saved ? `<div class="fl-p">Saved the app — ${E(action(saved)[2])}</div>` : "") + `<blockquote class="fl-quote">${E(r.output || (r.status === "running" ? "…still working" : "—"))}</blockquote>`;
    } else if (outObj) {
      const { reason, ...rest } = outObj;
      output = `<div class="fl-p">${E(action(fin)[0])}</div><details class="fl-step" data-k="${E(r.id)}:out"><summary><b>The exact output it handed over</b> <span class="cell-sub">${Object.keys(rest).length} parts</span></summary><div class="fl-si">${json(rest)}</div></details>`
        + (reason ? `<div class="label">Why (its own words)</div><blockquote class="fl-quote fl-why">${E(reason)}</blockquote>` : "");
    } else {
      output = `<blockquote class="fl-quote">${E(r.output || (r.status === "running" ? "…still working" : "—"))}</blockquote>`;
    }
    return `<div class="fl-hand">
      <div class="fl-hrow"><div class="label">From</div><div>${from}</div></div>
      <div class="fl-hrow"><div class="label">Input</div><div><blockquote class="fl-quote">${E(r.input || "—")}</blockquote></div></div>
      <div class="fl-hrow"><div class="label">What it did</div><div>${did ? `<ol class="fl-did">${did}</ol>` : `<span class="cell-sub">${r.status === "running" ? "working…" : "answered directly, no tools"}</span>`}</div></div>
      <div class="fl-hrow"><div class="label">Output</div><div>${output}</div></div>
      <div class="fl-hrow"><div class="label">Passed to</div><div>${to}</div></div>
    </div>`;
  }

  function kvTotals(s, n, kv) {
    return kv([["Runs", n], ["Total time", ms(s.ms)], ["Model calls", s.llm], ["Tool calls", s.tools], ["Tokens", tok(s.tin, s.tout)], ["Cost", usd(s.cost)], ["Retries", s.retries], ["Failed runs", s.err]]);
  }

  function runHtml(r, kv, sec) {
    const t = r.totals;
    const st = r.status === "ok" ? `<span class="tag good">done</span>` : r.status === "running" ? `<span class="tag accent">working</span>` : `<span class="tag bad">${E(r.status)}</span>`;
    return `<div class="fl-run-card">
      <div class="fl-sl">${st} <span class="cell-sub">${new Date(r.started_at).toLocaleString([], { dateStyle: "short", timeStyle: "medium" })} · ${ms(r.ms)} · ${usd(t.cost)}</span></div>
      ${handover(r)}
      <details class="fl-step" data-k="${E(r.id)}:numbers"><summary><b>Numbers</b> <span class="cell-sub">time, model, calls, tokens, cost</span></summary><div class="fl-si">
      ${kv([["Time", ms(r.ms)], ["Model", `<span class="mono">${E(r.model || "—")}</span>`], ["Model calls", t.llm_calls], ["Tool calls", `${t.tool_calls}${t.tool_errors ? ` (${t.tool_errors} returned an error)` : ""}`],
        ["Tokens", `${CC.num(t.tokens_in)} in · ${CC.num(t.cache_read)} cached · ${CC.num(t.cache_write)} cache write · ${CC.num(t.tokens_out)} out`], ["Cost", `${usd(t.cost)} <span class="cell-sub">calculated</span>`],
        t.retries ? ["Retries", t.retries] : null, (t.valid + t.rejected) ? ["Validator", `${t.valid} valid · ${t.rejected} rejected`] : null, ["Started by", E(r.trigger)]])}</div></details>
      ${(() => { const why = r.steps.filter(s => s.detail && s.detail.reason); return why.length ? sec("Stated reasons (the agent's own words)", why.map(s => `<blockquote class="fl-quote fl-why"><span class="mono">${E(s.name)}</span>${E(s.detail.reason)}</blockquote>`).join("")) : ""; })()}
      ${r.error ? sec("Error", `<div class="note bad">${E(r.error)}</div>`) : ""}
      ${r.prompt_sha ? `<button class="btn sm" data-prompt="${E(r.prompt_sha)}">Show its instructions</button><div class="fl-prompt"></div>` : ""}
      ${sec(`Every step, raw (${r.steps.length})`, r.steps.map(s => stepHtml(s, r.id)).join("") || `<div class="empty-note">No steps.</div>`)}
    </div>`;
  }

  function stepHtml(s, runId = "") {
    const d = s.detail || {};
    let head = "", inner = "";
    if (s.kind === "llm") {
      head = `<i class="fl-k-ic llm"></i><b>Model call</b> <span class="cell-sub">${ms(s.ms)} · ${CC.num(s.tokens_in + s.cache_read + s.cache_write)} in / ${CC.num(s.tokens_out)} out · ${usd(s.cost)} · ${E(s.stop_reason)}</span>`;
      inner = (d.tool_calls?.length ? `<div class="fl-p">Decided to call: ${d.tool_calls.map(c => `<span class="mono">${E(c)}</span>`).join(", ")}</div>` : "")
        + (d.text ? `<div class="label">Said</div><blockquote class="fl-quote">${E(d.text)}</blockquote>` : "")
        + (d.thinking ? `<div class="label">Its thinking (as returned by the API)</div><blockquote class="fl-quote dim">${E(d.thinking)}</blockquote>` : d.thinking_withheld ? `<div class="cell-sub">Thinking not stored: ${E(d.thinking_withheld)}</div>` : "")
        + (d.fallback_model ? `<div class="note warn">Answered by fallback model ${E(d.fallback_model)}</div>` : "")
        + `<div class="cell-sub">Cache: ${CC.num(s.cache_read)} read · ${CC.num(s.cache_write)} written · step ${s.loop_step}</div>`;
    } else if (s.kind === "tool") {
      head = `<i class="fl-k-ic tool"></i><b class="mono">${E(s.name)}</b> <span class="cell-sub">${ms(s.ms)} · ${s.ok ? "ok" : "returned an error"}</span>`;
      inner = (d.reason ? `<div class="label">Stated reason</div><blockquote class="fl-quote fl-why">${E(d.reason)}</blockquote>` : "")
        + `<div class="label">Arguments</div>${json(d.args)}<div class="label">Result</div>${json(d.result)}`;
    } else if (s.kind === "validator") {
      head = `<i class="fl-k-ic ${s.ok ? "ok" : "bad"}"></i><b>Validator: ${s.ok ? "VALID" : "REJECTED"}</b> <span class="cell-sub">${E(s.name.replace("validator · ", "on "))}</span>`;
      inner = (d.problems || []).length ? `<ul class="fl-ul">${d.problems.map(p => `<li>${E(p)}</li>`).join("")}</ul>` : `<div class="cell-sub">No problems.</div>`;
    } else if (s.kind === "retry") {
      head = `<i class="fl-k-ic bad"></i><b>${E(s.name)}</b> <span class="cell-sub">waited ${ms(s.ms)}</span>`;
      inner = `<div class="note bad">${E(d.error)}</div>`;
    }
    return `<details class="fl-step ${s.ok === 0 ? "bad" : ""}" data-k="${E(runId)}:${E(s.seq ?? s.started_at)}"><summary>${head}</summary><div class="fl-si">${inner}</div></details>`;
  }

  async function showPrompt(btn) {
    const box = btn.nextElementSibling;
    if (box.innerHTML) { box.innerHTML = ""; btn.textContent = "Show its instructions"; return; }
    try {
      const r = await fetch(CC.appUrl(`/api/trace/prompts/${encodeURIComponent(btn.dataset.prompt)}`));
      const p = await r.json();
      box.innerHTML = `<div class="label">System prompt</div><pre class="fl-json">${E(p.text)}</pre><div class="label">Tools it could use</div><div class="fl-p mono">${E(JSON.parse(p.tools || "[]").join(", "))}</div>`;
      btn.textContent = "Hide instructions";
    } catch { box.innerHTML = `<div class="note bad">Couldn't load the instructions.</div>`; }
  }

  // -------------------------------------------------------------- render
  function render() {
    if (!$("flList")) return;
    $("flOffline").classList.toggle("hidden", CC.online());
    renderList();
    if (!J || J.id !== sel) {
      $("flHead").innerHTML = `<h2>Flow</h2><p class="sub">${journeys.length ? "Pick a journey on the left." : "Every app gets a journey: the request, each agent's work, the Validator, the saved app, sharing and responses — measured, not simulated."}</p>`;
      $("flCanvas").innerHTML = ""; $("flCanvas").style.width = ""; $("flWrap").style.height = "120px"; $("flRounds").innerHTML = ""; $("flTiming").innerHTML = "";
      return;
    }
    const M = model();
    renderHead(M);
    renderRounds(M);
    replayControl(M);
    renderCanvas(M);
    renderTiming(M);
    if (node) renderDrawer();
  }

  // -------------------------------------------------------------- wiring
  const LIVE = new Set(["agent_start", "agent_reply", "agent_error", "agent_llm_end", "agent_tool_result", "app_created", "app_updated",
                        "app_shared", "app_status", "app_deleted", "submission", "submission_rejected", "status_changed", "review_done", "reminders_sent"]);
  CC.on("init", skeleton);
  CC.on("mode", m => { if (m === "flow") load(true); });
  CC.on("event", ev => { if (!ev.sim && LIVE.has(ev.type) && CC.mode === "flow") schedule(ev.type === "agent_start" ? 150 : 600); });
  CC.on("status", (st, prev) => { if (CC.mode === "flow" && (!prev || prev.state !== st.state)) { if (CC.online()) load(true); else render(); } });
  // while an agent is working live, the timing chart moves on its own (several times a second)
  setInterval(() => {
    if (CC.mode === "flow" && !replay && J && J.runs.some(r => r.status === "running")) renderTiming(model());
  }, 250);
  setInterval(() => {
    if (CC.mode !== "flow" || !CC.online()) return;
    const running = J && J.runs.some(r => r.status === "running");
    if (running) load(true); else load(false);
  }, 4000);

  return { load };
})();
