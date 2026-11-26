/* AppShare Control Center — Agent theater, drawn as an assembly line.
   Every run is a line of stations in workflow order. The work item travels along the conveyor,
   each station shows who is working, whether it is asking Claude, and what it produced, and the
   bench underneath shows the result being assembled. Driven by the server's real agent events,
   or by a clearly labelled recorded example. */
"use strict";

const Theater = (() => {
  const $ = id => document.getElementById(id);
  const esc = s => CC.esc(s);
  const NAME = { builder: "Builder", data: "Data", design: "Design", access: "Access", insights: "Insights", review: "Review", reminder: "Reminder" };
  const FIELD_ICON = { file: "inbox", short_text: "pencil", long_text: "list", number: "chart", email: "message", date: "list", select: "list", radio: "check", checkbox: "check", rating: "spark", info: "message" };

  // -------------------------------------------------------------- the lines (one per kind of run)
  const LINES = {
    builder: {
      cls: "build", title: "Build line", sub: "One request becomes a working app: brief → specialists → assembly → check → live.",
      stations: [
        { id: "req", kind: "person", icon: "phone", name: "Request", job: "What the person asked for", span: true },
        { id: "brief", agent: "builder", name: "Brief", job: "Builder plans it and writes one brief for the team", span: true },
        { id: "data", agent: "data", name: "Data", job: "Fields, file rules, deadline" },
        { id: "design", agent: "design", name: "Design", job: "Title, wording, colour — starts once Data's fields exist" },
        { id: "access", agent: "access", name: "Access", job: "Real groups and people, with roles" },
        { id: "assemble", agent: "builder", name: "Assembly", job: "Builder puts the three parts together", span: true },
        { id: "valid", kind: "validator", name: "Validator", job: "Checks every rule — plain code, not AI", span: true },
        { id: "app", kind: "app", icon: "server", name: "App created", job: "Database, screens and link — automatic", span: true },
      ],
      edges: [["req", "brief"], ["brief", "data"], ["brief", "access"], ["data", "design"], ["data", "assemble", "over"],
              ["design", "assemble"], ["access", "assemble"], ["assemble", "valid"], ["valid", "app"], ["valid", "assemble", "reject"]],
    },
    review: {
      cls: "single", title: "Review line", sub: "Every new submission is read before the owner opens it.",
      stations: [
        { id: "req", kind: "person", icon: "inbox", name: "Submission", job: "Someone submitted a file" },
        { id: "agent", agent: "review", name: "Review agent", job: "Reads with Claude, decides what to check" },
        { id: "get_assignment", tool: true, icon: "blueprint", name: "Read the task", job: "What was asked for" },
        { id: "read_submission", tool: true, icon: "lens", name: "Read the file", job: "Text of the PDF / DOCX" },
        { id: "compare_with_others", tool: true, icon: "copy", name: "Compare", job: "Against everyone else's files" },
        { id: "submit_review", tool: true, icon: "check", name: "Verdict", job: "Looks fine / check this / problem" },
        { id: "out", kind: "app", icon: "bell", name: "Owner sees it", job: "Shown on the response card" },
      ],
    },
    reminder: {
      cls: "single", title: "Reminder line", sub: "Before a deadline, only the people who haven't responded get a nudge.",
      stations: [
        { id: "req", kind: "person", icon: "bell", name: "Trigger", job: "24 h / 2 h before, or Remind now" },
        { id: "agent", agent: "reminder", name: "Reminder agent", job: "Decides who and what to send" },
        { id: "get_overview", tool: true, icon: "chart", name: "Check progress", job: "Responses so far vs expected" },
        { id: "list_missing", tool: true, icon: "list", name: "Find who's missing", job: "Audience minus responses" },
        { id: "send_reminders", tool: true, icon: "send", name: "Send reminders", job: "In-app notification to each" },
        { id: "out", kind: "app", icon: "check", name: "Done", job: "Logged so nobody is nagged twice" },
      ],
    },
    insights: {
      cls: "single", title: "Insights line", sub: "A question about responses is answered from the real data, not guessed.",
      stations: [
        { id: "req", kind: "person", icon: "message", name: "Question", job: "Asked by the app's owner" },
        { id: "agent", agent: "insights", name: "Insights agent", job: "Decides what to look up" },
        { id: "get_overview", tool: true, icon: "chart", name: "Overview", job: "Deadline, counts, audience" },
        { id: "list_responses", tool: true, icon: "list", name: "Read responses", job: "The answers people gave" },
        { id: "list_missing", tool: true, icon: "users", name: "Who's missing", job: "Audience minus responses" },
        { id: "out", kind: "app", icon: "message", name: "Answer", job: "Sent back to the owner" },
      ],
    },
  };

  // what travels on each conveyor (shown as a label on the arrow and on the moving card)
  const BUILD_LABELS = { "req>brief": "request", "brief>data": "brief", "brief>access": "brief", "data>design": "fields", "data>assemble": "fields",
    "design>assemble": "look", "access>assemble": "audience", "assemble>valid": "draft", "valid>app": "approved", "valid>assemble": "fix it" };
  const FIRST_LABEL = { review: "file", reminder: "deadline", insights: "question" };
  const CARD_ICON = { request: "message", brief: "send", fields: "list", look: "spark", audience: "users", draft: "blueprint", approved: "check",
    "fix it": "alert", "fix this": "alert", change: "pencil", file: "inbox", deadline: "bell", question: "message", answer: "message", done: "check" };

  // -------------------------------------------------------------- state
  const queue = [];
  let playing = false, demoRunning = false, demoAbort = false, pace = 1;
  let paused = false, replaying = false, filterAt = null, rec = null, lastRec = null;
  let edgeState = {};
  const runs = new Map();
  let top = null, line = null, lineKey = null;
  const thinking = new Set();
  const history = [];

  // -------------------------------------------------------------- small drawings
  function stampSvg() {
    return `<svg viewBox="0 0 80 110" aria-hidden="true">
      <ellipse cx="40" cy="18" rx="20" ry="16" fill="#8a5a3a"/><ellipse cx="34" cy="12" rx="7" ry="5" fill="#a8744f"/>
      <rect x="33" y="30" width="14" height="26" fill="#6e4730"/>
      <rect x="10" y="56" width="60" height="30" rx="3" fill="#3a3328"/><rect x="10" y="56" width="60" height="6" rx="2" fill="#4a4134"/>
      <rect x="12" y="86" width="56" height="9" fill="#5a2a22"/></svg>`;
  }
  let inkId = 0;
  function markSvg(word, col) {
    const id = "ink" + (++inkId);
    return `<svg viewBox="0 0 220 80" aria-hidden="true">
      <defs><filter id="${id}" x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency=".8" numOctaves="2" seed="${inkId}" result="n"/>
        <feDisplacementMap in="SourceGraphic" in2="n" scale="3" result="d"/>
        <feComponentTransfer in="n" result="m"><feFuncA type="discrete" tableValues="0 1 1 1 1 1 1"/></feComponentTransfer>
        <feComposite in="d" in2="m" operator="in"/></filter></defs>
      <g filter="url(#${id})" transform="rotate(-7 110 40)" fill="none" stroke="${col}">
        <rect x="8" y="10" width="204" height="60" rx="6" stroke-width="5"/><rect x="16" y="18" width="188" height="44" rx="3" stroke-width="1.5"/>
        <text x="110" y="52" text-anchor="middle" fill="${col}" stroke="none" font-family="ui-monospace, Consolas, monospace" font-weight="800" font-size="${word.length > 9 ? 22 : 27}" letter-spacing="4">${word}</text>
      </g></svg>`;
  }
  const head = k => `<span class="mini-face">${CHAR.svg(k, { crop: "head" })}</span>`;

  // -------------------------------------------------------------- page skeleton
  function skeleton() {
    $("view-agents").innerHTML = `
      <div class="narration"><span class="n-i" id="nIco">${CC.icon("clapper", "lg")}</span><span class="n-t" id="nText">Waiting for someone to ask an agent.</span><span id="thMode"></span></div>
      <div class="panel line-panel">
        <div class="line-head">
          <div><h2 id="lineTitle">Build line</h2><p class="sub" id="lineSub"></p></div>
          <div class="st-legend">
            <span><i></i>waiting</span><span><i class="q"></i>has its brief</span><span><i class="a"></i>working</span>
            <span><i class="t"></i>asking Claude</span><span><i class="d"></i>done</span><span><i class="x"></i>problem</span>
          </div>
          <div class="claude-meter" id="claude"><span class="bulb"></span><span id="claudeText">Claude · idle</span></div>
          <div class="th-play">
            <button class="btn sm ghost" id="thPause" title="Pause / resume (Space)">${CC.icon("stop")}Pause</button>
            <button class="btn sm ghost" id="thReplay" title="Play the last run again, step by step" disabled>${CC.icon("play")}Replay last run</button>
          </div>
        </div>
        <div class="line-wrap"><div class="line" id="line"></div></div>
      </div>
      <div class="th-grid" style="margin-top:1.25rem">
        <div class="bench2" id="bench" style="margin-top:0"></div>
        <aside style="display:flex;flex-direction:column;gap:1.25rem">
          <div class="panel">
            <div class="run-head"><h2 id="runTitle">Workflow</h2><span id="runState"></span></div>
            <div class="run-meta" id="runMeta">Each step appears here, in order, as the agents work.</div>
            <ol class="flow-steps" id="steps"></ol>
            <div id="runSum"></div>
          </div>
          <div class="panel">
            <h2>Rehearse</h2>
            <p class="sub">Replays a recorded run so you can show the workflow without a phone or an API key. Labelled as a simulation.</p>
            <div class="th-controls">
              <button class="btn primary" data-demo="builder">${CC.icon("play")}Build (team)</button>
              <button class="btn" data-demo="review">${CC.icon("play")}Review</button>
              <button class="btn" data-demo="reminder">${CC.icon("play")}Reminder</button>
              <button class="btn" data-demo="insights">${CC.icon("play")}Insights</button>
              <button class="btn ghost hidden" id="demoStop">${CC.icon("stop")}Stop</button>
            </div>
            <div class="speed-row">Pace <button data-pace="1.6">slow</button><button data-pace="1" class="on">normal</button><button data-pace=".55">fast</button></div>
          </div>
          <div class="panel">
            <h2>Recent runs</h2>
            <div class="history" id="history"><div class="empty-note">None yet.</div></div>
          </div>
        </aside>
      </div>`;
    document.querySelectorAll("[data-demo]").forEach(b => b.onclick = () => playDemo(b.dataset.demo));
    document.querySelectorAll("[data-pace]").forEach(b => b.onclick = () => {
      pace = +b.dataset.pace;
      document.querySelectorAll("[data-pace]").forEach(x => x.classList.toggle("on", x === b));
    });
    $("demoStop").onclick = stopDemo;
    $("thPause").onclick = togglePause;
    $("thReplay").onclick = replayLast;
    document.addEventListener("keydown", e => {
      if (CC.mode !== "agents" || e.code !== "Space" || e.target.matches("input, textarea, button")) return;
      e.preventDefault(); togglePause();
    });
    buildLine("builder");
    benchIdle();
    renderMode();
    new ResizeObserver(() => drawEdges()).observe($("line"));
    setInterval(glance, 2300);
  }

  // -------------------------------------------------------------- presenting: pause, replay
  function togglePause() {
    paused = !paused;
    $("thPause").innerHTML = paused ? `${CC.icon("play")}Resume` : `${CC.icon("stop")}Pause`;
    $("thPause").classList.toggle("primary", paused);
    $("line").classList.toggle("paused", paused);
    renderMode();
  }
  async function replayLast() {
    if (!lastRec || playing || demoRunning) return;
    replaying = true; renderMode(); $("thReplay").disabled = true;
    const ids = {};
    lastRec.forEach(ev => enqueue({ ...ev, run_id: ids[ev.run_id] ||= "rp-" + Math.random().toString(36).slice(2, 8),
      parent: ev.parent ? (ids[ev.parent] ||= "rp-" + Math.random().toString(36).slice(2, 8)) : undefined, replay: true }));
    while (playing || queue.length) await sleep(200);
    replaying = false; renderMode(); $("thReplay").disabled = !lastRec;
  }

  // -------------------------------------------------------------- characters: speech, glances, give and catch
  function say(id, text, kind = "", ms = 2600) {
    const b = $("bub-" + id);
    if (!b || !speed()) return;
    b.className = "bub on " + kind;
    b.textContent = text;
    clearTimeout(b._t);
    b._t = setTimeout(() => b.classList.remove("on"), ms * Math.max(1, pace));
  }
  function glance() {
    document.querySelectorAll("#line .st").forEach(el => {
      const c = el.querySelector(".char");
      if (!c) return;
      c.classList.remove("look-l", "look-r", "look-u");
      const s = el.dataset.state;
      if (s === "queued") c.classList.add("look-l");                       // watching for the work to arrive
      else if (s === "done" || s === "skip") { const r = Math.random(); if (r < .3) c.classList.add("look-l"); else if (r < .6) c.classList.add("look-r"); else if (r < .75) c.classList.add("look-u"); }
    });
  }
  function pose(id, cls, ms) {
    const c = $("st-" + id)?.querySelector(".char");
    if (!c) return;
    c.classList.remove(cls); void c.offsetWidth; c.classList.add(cls);
    setTimeout(() => c.classList.remove(cls), ms);
  }

  // -------------------------------------------------------------- building a line
  function stationHtml(s, i, n) {
    const fig = s.agent ? `<div class="char ${s.agent} idle">${CHAR.svg(s.agent)}</div>`
      : s.kind === "validator" ? `<div class="prop stamp">${stampSvg()}</div>`
      : `<div class="prop ${s.tool ? "tool" : ""}">${CC.icon(s.icon || "wrench")}</div>`;
    return `<div class="st ${s.span && lineKey === "builder" ? "span2" : ""}" id="st-${s.id}" data-state="wait" style="${lineKey === "builder" ? `grid-area:${s.id}` : ""}">
      <span class="st-claude">CLAUDE</span>
      <div class="st-top"><span class="st-n">${n}</span><span class="st-name">${esc(s.name)}</span><span class="st-light"></span></div>
      <div class="st-fig">${fig}<span class="tdots"><i></i><i></i><i></i></span><span class="okb">${CC.icon("check")}</span></div>
      <div class="bub" id="bub-${s.id}"></div>
      <div class="st-job">${esc(s.job)}</div>
      ${s.tool ? `<div class="st-tool">${esc(s.id)}()</div>` : ""}
      <div class="st-status" id="ss-${s.id}">${s.tool ? "Not used yet" : "Waiting"}</div>
      <div class="st-out" id="so-${s.id}"></div>
    </div>`;
  }

  function buildLine(key) {
    lineKey = key;
    line = LINES[key];
    const el = $("line");
    el.className = "line " + line.cls;
    if (line.cls === "single") el.style.setProperty("--n", line.stations.length);
    // order numbers: build line counts parallel stations as one step
    const order = key === "builder" ? { req: 1, brief: 2, data: 3, access: 3, design: 4, assemble: 5, valid: 6, app: 7 } : null;
    el.innerHTML = `<svg class="edges" id="edges"></svg>` + line.stations.map((s, i) => stationHtml(s, i, order ? order[s.id] : i + 1)).join("");
    if (!line.edges) line.edges = line.stations.slice(1).map((s, i) => [line.stations[i].id, s.id]);
    line.labels = key === "builder" ? BUILD_LABELS : {
      [`req>agent`]: FIRST_LABEL[key], [`${line.stations[line.stations.length - 2].id}>out`]: key === "insights" ? "answer" : "result" };
    edgeState = {};
    line.edges.forEach(([a, b, how]) => { edgeState[`${a}>${b}`] = how === "reject" ? "hidden-edge" : ""; });
    filterAt = null;
    $("lineTitle").textContent = line.title;
    $("lineSub").textContent = line.sub;
    thinking.clear(); renderClaude();
    // hovering a station lights up its conveyors; clicking it filters the workflow to its steps
    el.querySelectorAll(".st").forEach(s => {
      const id = s.id.slice(3);
      s.onmouseenter = () => { hover = id; paintEdges(); };
      s.onmouseleave = () => { hover = null; paintEdges(); };
      s.onclick = () => {
        filterAt = filterAt === id ? null : id;
        el.querySelectorAll(".st").forEach(x => x.classList.toggle("sel", x.id === "st-" + filterAt));
        renderSteps();
      };
      s.title = "Click to see only this station's steps";
    });
    requestAnimationFrame(drawEdges);
  }
  let hover = null;

  /** Conveyor arrows between station cards (recomputed on resize). */
  function drawEdges() {
    const svg = $("edges"), box = $("line");
    if (!svg || !line) return;
    const B = box.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${B.width} ${B.height}`);
    const R = id => { const r = $("st-" + id).getBoundingClientRect(); return { l: r.left - B.left, r: r.right - B.left, t: r.top - B.top, b: r.bottom - B.top, cx: r.left - B.left + r.width / 2, cy: r.top - B.top + r.height / 2 }; };
    const marker = (id, col) => `<marker id="arr-${id}" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto">
      <path d="M0,1 L10,5 L0,9 z" style="fill:${col};stroke:none"/></marker>`;   // inline style: the .edges path rule must not blank it
    // Orthogonal routing: a straight line where two stations overlap vertically, otherwise right angles with
    // rounded corners through the gaps between stations — never behind a station.
    const RAD = 10, PAD = 22, END = 7;        // END: the arrowhead stops this far short of the station, in the open
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    const rounded = pts => {            // polyline -> path with rounded corners
      let d = `M${pts[0][0]},${pts[0][1]}`;
      for (let i = 1; i < pts.length - 1; i++) {
        const [px, py] = pts[i - 1], [x, y] = pts[i], [nx, ny] = pts[i + 1];
        const r = Math.min(RAD, Math.hypot(x - px, y - py) / 2, Math.hypot(nx - x, ny - y) / 2);
        const ax = x - Math.sign(x - px) * r, ay = y - Math.sign(y - py) * r, bx = x + Math.sign(nx - x) * r, by = y + Math.sign(ny - y) * r;
        d += ` L${ax},${ay} Q${x},${y} ${bx},${by}`;
      }
      const [lx, ly] = pts[pts.length - 1];
      return d + ` L${lx},${ly}`;
    };
    svg.innerHTML = `<defs>${marker("idle", "#5a5850")}${marker("flow", "#e8572a")}${marker("done", "#3f8a56")}${marker("bad", "#e0483f")}${marker("hl", "#b9b7ac")}</defs>` + line.edges.map(([a, b, how]) => {
      const A = R(a), Bb = R(b);
      let d;
      if (how === "over") {                 // Data → Assembly: up over the Design station, down into Assembly
        const top = Math.min(...line.stations.map(x => R(x.id).t));       // above the highest station, so it never crosses one
        const y = Math.max(6, top - 14), xg = Bb.l - 16;
        d = rounded([[A.r - 26, A.t], [A.r - 26, y], [xg, y], [xg, Bb.t + PAD], [Bb.l - END, Bb.t + PAD]]);
      } else if (how === "reject") {        // Validator → Assembly: down, back along the bottom, up into Assembly
        const y = Math.max(A.b, Bb.b) + 16;
        d = rounded([[A.cx, A.b], [A.cx, y], [Bb.cx, y], [Bb.cx, Bb.b + END]]);
      } else {
        const lo = Math.max(A.t, Bb.t) + PAD, hi = Math.min(A.b, Bb.b) - PAD;
        if (lo <= hi) {                     // they overlap vertically: one straight line at a shared height
          const y = clamp(Bb.cy, lo, hi);
          d = `M${A.r},${y} L${Bb.l - END},${y}`;
        } else {                            // step through the gap between the two stations
          const y1 = clamp(Bb.cy, A.t + PAD, A.b - PAD), y2 = Bb.cy, xm = Math.round((A.r + Bb.l) / 2);
          d = rounded([[A.r, y1], [xm, y1], [xm, y2], [Bb.l - END, y2]]);
        }
      }
      const key = `${a}>${b}`, s = edgeState[key] || "";      // render with the current state so redraws never flash
      return `<g data-g="${key}"><path class="trk ${s}" d="${d}"/><path class="belt ${s}" data-e="${key}" d="${d}"/>
        ${line.labels[key] ? `<text class="elab ${s}" text-anchor="middle">${esc(line.labels[key])}</text>` : ""}</g>`;
    }).join("");
    // labels sit just above the middle of their conveyor
    svg.querySelectorAll("g[data-g]").forEach(g => {
      const t = g.querySelector("text"), p = g.querySelector(".belt");
      if (!t) return;
      const m = p.getPointAtLength(p.getTotalLength() / 2);
      t.setAttribute("x", m.x); t.setAttribute("y", m.y - 9);
    });
    paintEdges();
  }
  function paintEdges() {
    const svg = $("edges");
    if (!svg) return;
    svg.querySelectorAll("g[data-g]").forEach(g => {
      const key = g.dataset.g, s = edgeState[key] || "";
      const hl = hover && key.split(">").includes(hover) && s !== "hidden-edge" ? " hl" : "";
      g.querySelector(".trk").setAttribute("class", `trk ${s}${hl}`);
      const belt = g.querySelector(".belt");
      belt.setAttribute("class", `belt ${s}${hl}`);
      const m = ["flow", "done", "bad"].includes(s) ? s : hl ? "hl" : "idle";
      if (s === "hidden-edge" || s === "skip") belt.removeAttribute("marker-end"); else belt.setAttribute("marker-end", `url(#arr-${m})`);
      g.querySelector("text")?.setAttribute("class", `elab ${s}`);
    });
  }
  function edge(a, b, cls) {
    const key = `${a}>${b}`;
    if (!(key in edgeState)) return null;
    edgeState[key] = cls;
    paintEdges();
    return $("edges")?.querySelector(`.belt[data-e="${key}"]`);
  }

  /** A labelled work item rides the conveyor: the sender hands it over, the receiver catches it. */
  function carry(a, b, label, kind = "") {
    const p = edge(a, b, kind === "bad" ? "bad" : "flow");
    if (!p || !speed()) { if (p) edge(a, b, kind === "bad" ? "bad" : "done"); return Promise.resolve(); }
    const box = $("line"), len = p.getTotalLength(), dur = Math.max(650, Math.min(1300, len * 3.2)) * speed();
    const name = line.labels[`${a}>${b}`] || label;
    const pk = document.createElement("div");
    pk.className = "pkt " + kind;
    pk.innerHTML = `${CC.icon(CARD_ICON[name] || CARD_ICON[label] || "cards")}<span>${esc(label)}</span>`;
    box.appendChild(pk);
    pose(a, "give", 520);
    return new Promise(res => {
      let t0 = performance.now(), last = t0;
      const step = now => {
        if (paused) { t0 += now - last; last = now; requestAnimationFrame(step); return; }
        last = now;
        const k = Math.min(1, (now - t0) / dur), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        const pt = p.getPointAtLength(e * len);
        pk.style.transform = `translate(${pt.x}px, ${pt.y}px) translate(-50%, -50%)`;
        if (k < 1) requestAnimationFrame(step);
        else { pk.remove(); edge(a, b, kind === "bad" ? "bad" : "done"); pose(b, "catch", 520); res(); }
      };
      requestAnimationFrame(step);
    });
  }

  // -------------------------------------------------------------- station helpers
  function st(id, state, status, err = false) {
    const el = $("st-" + id);
    if (!el) return;
    if (state) {
      el.dataset.state = state;
      const c = el.querySelector(".char");
      if (c) {
        const pose = { wait: "idle", queued: "listen", active: "work", think: "think", done: "happy", bad: "sad", skip: "idle" }[state];
        ["idle", "listen", "think", "work", "happy", "sad"].forEach(x => c.classList.toggle(x, x === pose));
        if (state === "done") setTimeout(() => { if (el.dataset.state === "done") { c.classList.remove("happy"); c.classList.add("idle"); } }, 1600);
      }
    }
    if (status !== undefined) { const s = $("ss-" + id); s.innerHTML = status; s.classList.toggle("err", err); }
  }
  function out(id, html, append = false) { const o = $("so-" + id); if (!o) return; if (append) o.insertAdjacentHTML("beforeend", html); else o.innerHTML = html; }
  const chip = (t, cls = "") => `<span class="chip-o ${cls}" title="${esc(t)}">${esc(t)}</span>`;
  const stateOf = id => $("st-" + id)?.dataset.state;

  function renderClaude() {
    const m = $("claude");
    if (!m) return;
    m.classList.toggle("on", thinking.size > 0);
    $("claudeText").innerHTML = thinking.size
      ? `Claude · thinking for <b>${[...thinking].map(k => NAME[k] || k).join(", ")}</b>${thinking.size > 1 ? " — at the same time" : ""}`
      : "Claude · idle";
  }

  function narrate(icon, html) {
    $("nIco").innerHTML = CC.icon(icon, "lg");
    const t = $("nText");
    t.innerHTML = html;
    t.classList.remove("fade"); void t.offsetWidth; t.classList.add("fade");
  }
  function renderMode() {
    const m = $("thMode");
    if (!m) return;
    m.innerHTML = paused ? `<span class="tag accent"><i class="mk"></i>Paused · Space to resume</span>`
      : recTitle ? `<span class="tag accent"><i class="mk tri"></i>Replay · recorded run, in step with Flow</span>`
      : replaying ? `<span class="tag accent"><i class="mk tri"></i>Replay</span>`
      : demoRunning ? `<span class="tag warn"><i class="mk tri"></i>Simulation · recorded</span>`
      : CC.online() ? `<span class="tag good"><i class="mk circle"></i>Live</span>` : `<span class="tag muted"><i class="mk"></i>Server off</span>`;
  }

  // -------------------------------------------------------------- workflow steps (right panel)
  function step({ who, icon, text, sub = "", cls = "", par = false, at = null }) {
    const run = runs.get(top);
    if (!run) return null;
    const s = { who, icon, text, sub, cls, par, t: Date.now(), at: at || (who ? home(run, who) : null) };
    run.steps.push(s);
    renderSteps();
    return s;
  }
  function renderSteps() {
    const run = runs.get(top);
    if (!run) return;
    $("runTitle").textContent = `${line.title}${run.sim ? " · simulation" : ""}`;
    $("runMeta").textContent = `For ${run.user || "someone"} · started ${CC.clock(run.started)}`;
    $("runState").innerHTML = run.state === "done" ? `<span class="tag good"><i class="mk circle"></i>Done</span>`
      : run.state === "error" ? `<span class="tag bad"><i class="mk"></i>Failed</span>` : `<span class="tag accent"><i class="mk"></i>Working</span>`;
    const shown = run.steps.map((s, i) => ({ ...s, n: i + 1 })).filter(s => !filterAt || s.at === filterAt);
    const fname = filterAt ? line.stations.find(s => s.id === filterAt)?.name : "";
    $("steps").innerHTML = (filterAt ? `<li class="filter-row"><span>Only <b>${esc(fname)}</b> · ${shown.length} of ${run.steps.length} steps</span><button id="clearFilter">Show all</button></li>` : "") +
      (shown.length ? shown.map(s => `
      <li class="${s.cls} ${s.par ? "par" : ""}">
        <span class="fs-n">${s.n}</span>
        <span class="fs-i">${s.who ? CHAR.svg(s.who, { crop: "head" }) : CC.icon(s.icon || "check")}</span>
        <div><div class="fs-t">${s.text}</div>${s.sub ? `<div class="fs-s">${s.sub}</div>` : ""}</div>
        <span class="fs-m">+${((s.t - run.t0) / 1000).toFixed(1)}s</span>
      </li>`).join("") : `<li class="filter-row"><span>Nothing has happened at this station yet.</span></li>`);
    const cf = $("clearFilter");
    if (cf) cf.onclick = () => { filterAt = null; document.querySelectorAll("#line .st.sel").forEach(x => x.classList.remove("sel")); renderSteps(); };
    const box = $("steps");
    if (!filterAt) box.scrollTop = box.scrollHeight;
    $("runSum").innerHTML = run.calls ? `<div class="run-sum">
      <div><b>${run.calls}</b><span>Claude calls</span></div>
      <div><b>${CC.num(run.tin)}</b><span>tokens read</span></div>
      <div><b>${run.state === "done" ? ((run.ms || 0) / 1000).toFixed(1) + " s" : CC.num(run.tout)}</b><span>${run.state === "done" ? "total time" : "tokens written"}</span></div></div>` : "";
  }
  function renderHistory() {
    $("history").innerHTML = history.length ? history.slice(0, 10).map(h => `
      <div class="h-item">${head(h.agent)}
        <span class="h-t" title="${esc(h.message)}">${h.sim ? "sim · " : ""}${esc(h.message)}</span>
        <span class="h-m">${h.state === "done" ? (h.ms / 1000).toFixed(1) + " s" : "failed"}</span></div>`).join("") : `<div class="empty-note">None yet.</div>`;
  }

  // -------------------------------------------------------------- the bench
  function benchIdle() {
    $("bench").className = "bench2";
    $("bench").innerHTML = `<div class="bx"><div class="bx-h"><span>Bench</span></div>
      <div class="bx-empty">When an agent starts, what it is making appears here: the app being assembled, a submission being read, reminders going out, or an answer being worked out.
      Ask the Builder for an app on a phone, or play a recorded run.</div></div>`;
  }

  function benchBuild(run) {
    $("bench").className = "bench2 build";
    $("bench").innerHTML = `
      <div class="bx"><div class="bx-h"><span>On the bench · <b>the app being assembled</b></span><span id="draftState">parts arriving</span></div>
        <div class="draft" id="draft">
          <div class="band" id="dBand"></div>
          <div class="sec" id="dLook"><div><div class="d-ph">title and instructions — from Design</div></div><span class="from design">Design</span></div>
          <div class="sec" id="dFields"><div><div class="d-ph">fields — from Data</div></div><span class="from data">Data</span></div>
          <div class="sec" id="dMeta"><div class="d-meta"><div><span>Deadline</span><b id="dDue">—</b></div><div><span>Audience</span><b id="dAud">— from Access</b></div></div><span class="from access">Access</span></div>
          <div class="stamp-zone" id="dStamp"></div>
        </div>
        <div id="dProblems"></div>
      </div>
      <div class="bx"><div class="bx-h"><span>Created automatically</span><span id="madeState">after the Validator approves</span></div>
        <div class="made pending" id="made">
          <div class="mk-row"><span class="mk-i">${CC.icon("server")}</span><div><div class="mk-t">Database table</div><div class="mk-s">One column per field; every response is a row.</div><div class="dbt" id="mkDb"><div><span>who</span><span>…</span><span>submitted</span></div><div><span></span><span></span><span></span></div></div></div></div>
          <div class="mk-row"><span class="mk-i">${CC.icon("phone")}</span><div><div class="mk-t">Screens</div><div class="mk-s">The form people fill in, the results page, the owner's page.</div><div class="mini-phone" id="mkPhone"><i class="t"></i><i></i><i></i><i class="btn"></i></div></div></div>
          <div class="mk-row"><span class="mk-i">${CC.icon("link")}</span><div><div class="mk-t">Its own link</div><div class="mk-s link-out" id="mkLink">/a/……</div></div></div>
        </div>
      </div>`;
  }
  function dFields(fields, pencil = false, problems = []) {
    if (!fields || !fields.length) return;
    const s = $("dFields");
    if (!s) return;
    s.innerHTML = `<div><div class="d-fields">${fields.map((f, i) => `<div class="d-field ${pencil ? "pencil" : ""}" style="animation-delay:${i * 90}ms">${CC.icon(FIELD_ICON[f.type] || "list")}<span>${esc(f.label)}</span><span class="ft">${esc(f.type)}</span></div>`).join("")}</div>
      ${problems.length ? `<div class="d-red">× ${esc(problems[0])}</div>` : ""}</div><span class="from data">Data</span>`;
    s.classList.remove("slot-in"); void s.offsetWidth; s.classList.add("slot-in");
    const db = $("mkDb");
    if (db && !pencil) {
      const cols = fields.filter(f => f.type !== "info").slice(0, 4).map(f => f.label);
      db.innerHTML = `<div><span>who</span>${cols.map(c => `<span>${esc(c)}</span>`).join("")}</div><div><span></span>${cols.map(() => "<span></span>").join("")}</div>`;
      $("mkPhone").innerHTML = `<i class="t"></i>${fields.filter(f => f.type !== "info").slice(0, 4).map(() => "<i></i>").join("")}<i class="btn"></i>`;
    }
  }
  function dLook(title, description, color) {
    const s = $("dLook");
    if (!s) return;
    if (color) { $("dBand").style.background = color; const ph = $("mkPhone"); if (ph) ph.style.borderTop = `6px solid ${color}`; }
    if (title) {
      s.innerHTML = `<div><div class="d-title">${esc(title)}</div>${description ? `<div class="d-desc">${esc(description)}</div>` : ""}</div><span class="from design">Design</span>`;
      s.classList.remove("slot-in"); void s.offsetWidth; s.classList.add("slot-in");
    }
  }
  function dMeta(due, aud) {
    if (due) $("dDue") && ($("dDue").textContent = fmtDue(due));
    if (aud) { const a = $("dAud"); if (a) { a.textContent = aud; const s = $("dMeta"); s.classList.remove("slot-in"); void s.offsetWidth; s.classList.add("slot-in"); } }
  }
  const fmtDue = d => d ? new Date(d).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) : "none";

  function benchReply(kind, text, err = false) {
    const b = $("bench");
    b.querySelector(".reply-box")?.remove();
    b.insertAdjacentHTML("beforeend", `<div class="reply-box ${err ? "err" : ""}"><span class="face">${CHAR.svg(kind, { crop: "head" })}</span>
      <div><div class="who">${esc(NAME[kind])} agent · ${err ? "couldn't finish" : "reply"}</div><div class="txt">${esc(text)}</div></div></div>`);
  }

  function benchSingle(key, run) {
    $("bench").className = "bench2 three";
    const B = {
      review: [`Submission · <b>${esc(run.user || "")}</b>`, `<div class="sheet" id="sheet"><div class="sh-h"><b>${esc(run.user || "")}</b><span>${esc(run.app || "submission")}</span></div>
          <div class="sh-lines">${Array.from({ length: 7 }, (_, i) => `<i style="width:${92 - (i * 13) % 34}%"></i>`).join("")}</div><div class="sh-marks" id="marks"></div><div class="stamp-zone" id="sStamp"></div></div>`,
        "What it checked", `<div class="bkv" id="kv"></div>`, "Verdict", `<div id="verdict" class="bx-empty">Not decided yet.</div>`],
      reminder: ["Progress", `<div class="bkv" id="kv"></div><div class="progress-bar"><i id="pbar" style="width:0%"></i></div>`,
        "Still missing", `<div class="names" id="missing"><span class="bx-empty" style="border:none;background:none">Not checked yet.</span></div>`,
        "Reminders sent", `<div class="names" id="sent"><span class="bx-empty" style="border:none;background:none">None yet.</span></div>`],
      insights: ["Question", `<div class="question">${esc(run.message || "")}</div>`,
        "What it looked up", `<div class="bkv" id="kv"></div><div class="names" id="found" style="margin-top:.5rem"></div>`,
        "Answer", `<div id="answer" class="bx-empty">Working it out…</div>`],
    }[key];
    $("bench").innerHTML = [0, 2, 4].map(i => `<div class="bx"><div class="bx-h"><span>${B[i]}</span></div>${B[i + 1]}</div>`).join("");
  }
  function kv(label, value, cls = "") { $("kv")?.insertAdjacentHTML("beforeend", `<div class="${cls}"><span>${esc(label)}</span><b>${esc(value)}</b></div>`); }

  // -------------------------------------------------------------- event player
  let current = null;           // the event being played (a replayed one knows when it is due)
  function speed() {
    if (CC.mode !== "agents" || document.hidden) return 0;
    // replaying in step with the Flow: if this event is already late, skip its animation delays and catch up
    if (current && current.due && Date.now() - current.due > 250) return 0;
    return (queue.length > 16 ? .3 : queue.length > 7 ? .6 : 1) * pace;
  }
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const holdWhilePaused = async () => { while (paused) await sleep(120); };
  const wait = async ms => { const s = speed(); if (s) await sleep(ms * s); await holdWhilePaused(); };
  function enqueue(ev) {
    // keep a copy of each complete run so it can be replayed slowly afterwards
    if (!ev.replay) {
      if (ev.type === "agent_start" && !ev.parent) rec = [ev];
      else if (rec) rec.push(ev);
      if (rec && ev.type === "agent_reply" && ev.run_id === rec[0].run_id) { lastRec = rec; rec = null; const b = $("thReplay"); if (b && !replaying) b.disabled = false; }
    }
    queue.push(ev); if (!playing) play();
  }
  async function play() {
    playing = true;
    while (queue.length) {
      await holdWhilePaused();
      const ev = queue.shift();
      current = ev;
      try { await handle(ev); } catch (e) { console.error("theater", e); }
      current = null;
    }
    playing = false;
  }

  /** Which station an agent's own work shows up at. */
  function home(run, k) {
    if (lineKey !== "builder") return k === run.agent ? "agent" : null;
    if (k === "builder") return run.link ? "app" : run.phase === "assemble" ? "assemble" : "brief";
    return k;   // data / design / access
  }

  async function handle(ev) {
    const k = ev.agent;
    if (ev.type === "agent_start") return onStart(ev);
    const run = runs.get(ev.run_id);
    if (!run) return;
    const lead = runs.get(top);
    if (!lead) return;
    const sid = home(lead, k);

    if (ev.type === "agent_llm_start") {
      thinking.add(k); renderClaude();
      if (sid) st(sid, "think", ev.step > 1 ? `Asking Claude again (step ${ev.step})…` : "Asking Claude…");
      if (!run.parent && sid) narrate("bulb", `The <b>${NAME[k]} agent</b> asks <b>Claude</b> ${ev.step > 1 ? "what to do next" : "how to approach it"}.`);
      await wait(run.parent ? 650 : 1100);
    } else if (ev.type === "agent_llm_end") {
      thinking.delete(k); renderClaude();
      lead.calls = (lead.calls || 0) + 1; lead.tin = (lead.tin || 0) + (ev.tokens_in || 0); lead.tout = (lead.tout || 0) + (ev.tokens_out || 0);
      if (sid && stateOf(sid) === "think") st(sid, "active", `Claude replied in ${(ev.ms / 1000).toFixed(1)} s`);
      renderSteps();
      await wait(run.parent ? 200 : 400);
    } else if (ev.type === "agent_tool") {
      await (lineKey === "builder" ? buildTool(ev, lead) : singleTool(ev, lead));
    } else if (ev.type === "agent_tool_result") {
      await (lineKey === "builder" ? buildResult(ev, lead) : singleResult(ev, lead));
    } else if (ev.type === "agent_reply") {
      if (run.parent) {                                   // a specialist hands its part back
        thinking.delete(k); renderClaude();
        st(k, "done", "Part delivered to the Builder");
        say(k, "Done — over to you, Builder", "ok");
        await wait(350);
        return;
      }
      await onReply(ev, lead);
    } else if (ev.type === "agent_error") {
      thinking.delete(k); renderClaude();
      if (sid) { st(sid, "bad", esc(ev.error), true); say(sid, "I couldn't finish this", "bad", 4000); }
      step({ who: k, text: `${NAME[k]} stopped with an error`, sub: esc(ev.error), cls: "bad" });
      if (!run.parent) {
        lead.state = "error";
        thinking.clear(); renderClaude();
        benchReply(k, ev.error, true);
        narrate("alert", `The ${NAME[k]} agent couldn't finish: ${esc(ev.error)}`);
        history.unshift({ agent: k, message: lead.message, ms: 0, state: "error", sim: lead.sim });
        renderHistory(); renderSteps();
      }
      await wait(900);
    }
  }

  async function onStart(ev) {
    const k = ev.agent;
    if (ev.parent && runs.has(ev.parent)) {              // a specialist picks up its brief
      runs.set(ev.run_id, { id: ev.run_id, agent: k, parent: ev.parent });
      if (lineKey === "builder") {
        st(k, "active", "Read the brief, starting");
        say(k, { data: "On it — what should we ask?", access: "I'll find who it's for", design: "I'll make it read well" }[k] || "On it!");
      }
      await wait(250);
      return;
    }
    const run = { id: ev.run_id, agent: k, user: ev.user, message: ev.message, app: ev.app, started: ev.ts || Date.now(), t0: Date.now(),
                  steps: [], state: "working", sim: ev.sim, phase: "brief", asked: [], calls: 0, tin: 0, tout: 0 };
    runs.set(ev.run_id, run);
    top = ev.run_id;
    buildLine(LINES[k] ? k : "insights");
    const who = esc(ev.user || "Someone");
    if (k === "builder") {
      benchBuild(run);
      st("req", "done", `<b>${who}</b>: “${esc(ev.message || "")}”`);
      step({ icon: "phone", text: `<b>${who}</b> asked for an app`, sub: `“${esc(ev.message || "")}”`, at: "req" });
      narrate("message", `<b>${who}</b> asks the <b>Builder</b>: <span class="q">“${esc(ev.message || "")}”</span>`);
      await carry("req", "brief", "request");
      st("brief", "active", "Reading the request");
      say("brief", "Got it — let me plan this");
    } else {
      benchSingle(k, run);
      const trig = k === "review" ? `New submission from <b>${who}</b>` : k === "reminder"
        ? (ev.user && ev.user !== "the schedule" ? `<b>${who}</b> pressed Remind now` : `The deadline for “${esc(ev.app || "")}” is close`)
        : `<b>${who}</b>: “${esc(ev.message || "")}”`;
      st("req", "done", trig);
      step({ icon: { review: "inbox", reminder: "bell", insights: "message" }[k], text: trig, sub: ev.app && k !== "insights" ? esc(ev.app) : "", at: "req" });
      narrate({ review: "inbox", reminder: "bell", insights: "message" }[k], k === "insights"
        ? `<b>${who}</b> asks the <b>Insights agent</b>: <span class="q">“${esc(ev.message || "")}”</span>`
        : k === "review" ? `A new submission arrived. The <b>Review agent</b> reads it before the owner does.`
        : `A deadline is close. The <b>Reminder agent</b> checks who still hasn't responded.`);
      await carry("req", "agent", k === "review" ? "file" : k === "reminder" ? "deadline" : "question");
      st("agent", "active", "Starting");
      say("agent", { review: "Let me read this one", reminder: "Who still needs a nudge?", insights: "Let me look at the data" }[k] || "On it!");
    }
    await wait(500);
  }

  // ---------------------------------------------------------- build line: tools
  async function buildTool(ev, run) {
    const k = ev.agent, t = ev.tool;
    switch (t) {
      case "ask_data_agent": case "ask_access_agent": case "ask_design_agent": {
        const to = ev.to || t.split("_")[1];
        run.asked.push(to);
        if (run.asked.length === 1) {
          st("brief", "done", "Brief written");
          out("brief", chip(ev.summary || "brief"));
          step({ who: "builder", text: "Builder wrote the brief", sub: esc(ev.summary || ""), at: "brief" });
          narrate("send", `The <b>Builder</b> hands the brief out. <b>Data</b> and <b>Access</b> start at the same time; <b>Design</b> waits for Data's fields.`);
          say("brief", "Team — here's the brief!", "ok");
        }
        st(to, "queued", "Brief received");
        const last = run.steps[run.steps.length - 1];
        if (last && last.kind === "handout") { last.names.push(NAME[to]); last.text = `Brief sent to ${last.names.join(", ")}`; renderSteps(); }
        else { const s = step({ icon: "send", text: `Brief sent to ${NAME[to]}`, par: true, at: "brief" }); s.kind = "handout"; s.names = [NAME[to]]; }
        await carry("brief", to, "brief");
        return;
      }
      case "check_fields":
        st("data", "active", `Checking ${ev.fields?.length || 0} fields against the platform rules`);
        out("data", (ev.fields || []).slice(0, 5).map(f => chip(f.label, "pencil")).join(""));
        dFields(ev.fields, true);
        say("data", `Draft: ${ev.fields?.length || 0} fields. Checking…`);
        await wait(700); return;
      case "submit_fields":
        st("data", "active", `Delivering ${ev.fields?.length || 0} fields${ev.closes_at ? " and the deadline" : ""}`);
        out("data", (ev.fields || []).slice(0, 5).map(f => chip(f.label, "ok")).join("") + (ev.closes_at ? chip("due " + fmtDue(ev.closes_at)) : ""));
        dFields(ev.fields); dMeta(ev.closes_at);
        step({ who: "data", text: `Data delivered ${ev.fields?.length || 0} fields`, sub: (ev.fields || []).map(f => esc(f.label)).join(" · ") + (ev.closes_at ? ` · due ${esc(fmtDue(ev.closes_at))}` : ""), cls: "ok" });
        say("data", "Fields are ready!", "ok");
        await carry("data", "assemble", "fields", "back");
        return;
      case "get_fields":
        st("design", "queued", "Waiting for Data's fields…");
        step({ who: "design", text: "Design waits for Data's fields", sub: "so the wording matches what is asked" });
        narrate("clock", `The <b>Design agent</b> needs Data's fields before it can write the wording, so it waits.`);
        say("design", "Waiting for Data's fields…");
        await wait(500); return;
      case "check_color":
        st("design", "active", `Is ${esc(ev.color || "")} readable on white?`);
        say("design", `Is ${ev.color || "this colour"} readable?`);
        out("design", `<span class="chip-o"><i class="sw" style="background:${esc(ev.color || "#888")}"></i>${esc(ev.color || "")}</span>`, true);
        await wait(550); return;
      case "submit_design":
        st("design", "active", "Delivering title, instructions and colour");
        out("design", `<span class="chip-o ok"><i class="sw" style="background:${esc(ev.theme_color || "#888")}"></i>${esc(ev.title || "")}</span>` +
          (ev.style ? chip(`look: ${ev.style}${ev.pattern ? " · " + ev.pattern : ""}`, "ok") : ""));
        dLook(ev.title, ev.description, ev.theme_color);
        step({ who: "design", text: `Design delivered the title and colour`, sub: `“${esc(ev.title || "")}” · ${esc(ev.theme_color || "")}`, cls: "ok" });
        say("design", "Title and colour — done!", "ok");
        await carry("design", "assemble", "title + colour", "back");
        return;
      case "list_groups": case "search_people":
        if (k === "access") {
          st("access", "active", t === "list_groups" ? "Opening the group directory" : `Searching people: ${esc(ev.summary || "")}`);
          say("access", t === "list_groups" ? "Checking the real directory…" : "Looking people up…");
          await wait(500); return;
        }
        return;
      case "submit_access":
        st("access", "active", "Delivering the audience");
        out("access", (ev.share || []).map(s => chip(s, "ok")).join("") || chip("nobody named", "bad"));
        dMeta(null, (ev.share || []).join(", ") || "nobody named");
        step({ who: "access", text: `Access proposed the audience`, sub: esc((ev.share || []).join(", ") || "nobody named"), cls: "ok" });
        say("access", (ev.share || []).length ? `For: ${(ev.share || []).slice(0, 2).join(", ")}` : "Nobody named yet", (ev.share || []).length ? "ok" : "bad");
        await carry("access", "assemble", (ev.share || [])[0] || "audience", "back");
        return;
      case "get_current_app":
        st(home(run, "builder"), "active", "Opening the current app");
        step({ who: "builder", text: "Builder opened the current app", sub: "to change it" });
        await wait(600); return;
      case "save_app": {
        const team = run.asked.length > 0 || ev.team;
        const retry = !!run.rejected;
        if (!team && !run.solo) {          // a small change: the Builder does it alone
          run.solo = true;
          ["data", "design", "access"].forEach(x => { st(x, "skip", "Not needed — small change, the Builder did it"); });
          ["brief>data", "brief>access", "data>design", "data>assemble", "design>assemble", "access>assemble"].forEach(e => { const [a, b] = e.split(">"); edge(a, b, "skip"); });
          st("brief", "done", "Planned the change");
          say("brief", "Small change — I'll do it myself");
          step({ who: "builder", text: "Builder made the change itself", sub: "no specialists needed for a small edit", at: "brief" });
          await carry("brief", "assemble", "change");
        }
        // whatever the Builder sent this time is what the Validator will check
        if (ev.title) dLook(ev.title);
        if (ev.fields) dFields(ev.fields);
        if (ev.closes_at || ev.share?.length) dMeta(ev.closes_at, (ev.share || []).join(", ") || null);
        run.phase = "assemble";
        st("assemble", "done", retry ? "Fixed and resubmitted" : "Draft assembled from the parts");
        step({ who: "builder", text: retry ? "Builder fixed it and resubmitted" : "Builder assembled the draft and sent it to the Validator", at: "assemble" });
        narrate("shield", `The <b>Builder</b> sends the assembled draft to the <b>Validator</b>, which checks every rule before anything is saved.`);
        say("assemble", retry ? "Fixed — check again please" : "Assembled! Validator, check it");
        await carry("assemble", "valid", "draft app");
        st("valid", "active", "Checking fields, deadline, file types, audience…");
        say("valid", "Checking every rule…");
        await wait(700);
        return;
      }
    }
  }

  async function buildResult(ev, run) {
    const k = ev.agent, t = ev.tool;
    switch (t) {
      case "check_fields":
        if (ev.ok) { st("data", "active", "All fields valid"); }
        else {
          const p = (ev.problems || [])[0] || ev.summary;
          st("data", "bad", `Problem: ${esc(p)} — fixing it`, true);
          $("dFields")?.querySelector(".d-fields")?.insertAdjacentHTML("afterend", `<div class="d-red">× ${esc(p)}</div>`);
          step({ who: "data", text: "Data's check found a problem", sub: esc(p), cls: "bad" });
          say("data", "Oops — the platform rejected that. Fixing!", "bad", 3200);
          narrate("alert", `The platform rejected a draft field: <b>${esc(p)}</b>. The Data agent fixes it before handing anything over.`);
          await wait(1100);
          st("data", "active", "Fixing it");
        }
        await wait(300); return;
      case "check_color":
        out("design", ev.ok ? chip(ev.summary, "ok") : chip(ev.summary, "bad"), true);
        say("design", ev.ok ? "Readable — good" : "Too light. A darker one…", ev.ok ? "ok" : "bad");
        if (!ev.ok) step({ who: "design", text: "Design's colour was too light", sub: esc(ev.summary), cls: "bad" });
        st("design", "active", ev.ok ? `Colour OK: ${esc(ev.summary)}` : `Too light (${esc(ev.summary)}) — picking a darker one`, !ev.ok);
        await wait(ev.ok ? 400 : 900); return;
      case "get_fields":
        st("design", "active", `Got ${(ev.items || []).length} fields from Data`);
        out("design", (ev.items || []).slice(0, 4).map(x => chip(x)).join(""));
        step({ who: "design", text: "Design received Data's fields", sub: (ev.items || []).map(esc).join(" · ") });
        await carry("data", "design", "fields");
        say("design", "Got the fields, thanks!", "ok");
        return;
      case "list_groups": case "search_people":
        if (k === "access") {
          out("access", (ev.items || []).slice(0, 4).map(x => chip(x, "pencil")).join(""));
          st("access", "active", t === "list_groups" ? `Directory has ${esc(ev.summary || "")}` : esc(ev.summary || ""));
          step({ who: "access", text: t === "list_groups" ? "Access read the real group directory" : "Access looked people up", sub: esc(ev.summary || ""), par: true });
          await wait(600);
        }
        return;
      case "submit_fields": case "submit_design": case "submit_access":
        if (!ev.ok) { st(k, "bad", esc(ev.summary), true); await wait(900); }
        return;
      case "ask_data_agent": case "ask_design_agent": case "ask_access_agent": {
        const from = t.split("_")[1];
        if (!ev.ok) { st(from, "bad", esc(ev.summary || "couldn't finish"), true); step({ who: from, text: `${NAME[from]} couldn't finish`, sub: esc(ev.summary), cls: "bad" }); await wait(800); return; }
        // the Builder's copy of the part — fill the bench even if the specialist's own events were missed
        if (from === "data" && ev.fields && !$("dFields").querySelector(".d-fields")) dFields(ev.fields);
        if (from === "design" && ev.title && !$("dLook").querySelector(".d-title")) dLook(ev.title, ev.description, ev.theme_color);
        if (from === "access" && ev.share && $("dAud")?.textContent.startsWith("—")) dMeta(null, ev.share.join(", "));
        if (stateOf(from) !== "done") st(from, "done", "Part delivered to the Builder");
        const got = ["data", "design", "access"].filter(x => stateOf(x) === "done").length;
        st("assemble", got === 3 ? "active" : "queued", `${got} of 3 parts in${got === 3 ? " — assembling" : ""}`);
        if (got === 3) { run.phase = "assemble"; $("draftState").textContent = "all parts in"; narrate("check", `All three parts are in. The <b>Builder</b> assembles them into one app.`); say("assemble", "All three parts — assembling!", "ok"); }
        else say("assemble", `${got} of 3 parts here…`);
        await wait(300);
        return;
      }
      case "save_app": {
        if (ev.ok) {
          $("dProblems").innerHTML = "";
          if (run.rejected) edge("valid", "assemble", "skip");
          st("valid", "done", run.rejected ? "Approved after the fix" : "Approved — every rule passes");
          $("dStamp").innerHTML = `<div class="stamp-tool">${stampSvg()}</div><div class="stamp-mark">${markSvg("APPROVED", "#2f8a4c")}</div>`;
          $("draftState").textContent = "approved";
          step({ icon: "shield", text: "Validator approved the app", sub: "fields, deadline, file rules and audience all valid", cls: "ok", at: "valid" });
          say("valid", "Every rule passes", "ok");
          await wait(700);
          await carry("valid", "app", "approved");
          say("app", "It's live!", "ok", 3200);
          run.link = ev.link || "/a/…";
          st("app", "done", `Live at <span class="mono">${esc(run.link)}</span>`);
          out("app", chip("table", "ok") + chip("screens", "ok") + chip(ev.link || "link", "ok"));
          const m = $("made"); m.classList.remove("pending");
          m.querySelectorAll(".mk-row").forEach((r, i) => { r.classList.add("pop"); r.style.animationDelay = i * 180 + "ms"; });
          $("madeState").textContent = "ready";
          $("mkLink").textContent = ev.link || "/a/…";
          step({ icon: "server", text: "App created automatically", sub: `database table, screens and link ${esc(ev.link || "")}`, cls: "ok", at: "app" });
          narrate("check", `Approved. The engine creates the <b>database table</b>, the <b>screens</b> and the link <span class="mono">${esc(ev.link || "")}</span> — no code written.`);
          if (ev.unresolved?.length) step({ icon: "alert", text: "Some names weren't found in the directory", sub: ev.unresolved.map(esc).join(", "), cls: "bad", at: "app" });
          await wait(1400);
        } else {
          const probs = ev.problems?.length ? ev.problems : [ev.summary];
          run.rejected = (run.rejected || 0) + 1;
          st("valid", "bad", `Rejected: ${esc(probs[0] || "")}`, true);
          $("dStamp").innerHTML = `<div class="stamp-tool">${stampSvg()}</div><div class="stamp-mark">${markSvg("REJECTED", "#d03b3b")}</div>`;
          $("dProblems").innerHTML = `<ul class="problems">${probs.map(p => `<li>× ${esc(p)}</li>`).join("")}</ul>`;
          step({ icon: "shield", text: "Validator rejected the draft", sub: probs.map(esc).join("; "), cls: "bad", at: "valid" });
          narrate("alert", `Rejected: <b>${esc(probs[0] || "")}</b>. The draft goes back to the Builder to fix.`);
          say("valid", `Rejected: ${probs[0] || ""}`, "bad", 3400);
          edge("valid", "assemble", "");
          await carry("valid", "assemble", "fix this", "bad");
          st("assemble", "active", "Fixing what the Validator found");
          say("assemble", "Fair — fixing it now", "bad");
          await wait(900);
          $("dStamp").innerHTML = "";
        }
        return;
      }
    }
  }

  // ---------------------------------------------------------- single-agent lines: tools
  /** Move the work item forward along a single line, marking stations it passes without using as skipped. */
  async function advance(from, to, label, kind = "") {
    const ids = line.stations.map(s => s.id);
    const a = ids.indexOf(from), b = ids.indexOf(to);
    if (b <= a) return;                                   // going back to an earlier tool: no conveyor move
    for (let i = a; i < b - 1; i++) {
      edge(ids[i], ids[i + 1], "skip");
      if (i + 1 < b && stateOf(ids[i + 1]) === "wait") st(ids[i + 1], "skip", "Not needed this time");
    }
    await carry(ids[b - 1], to, label, kind);
  }

  async function singleTool(ev, run) {
    const t = ev.tool;
    if (!$("st-" + t)) { st("agent", "active", `Using ${esc(t)}`); await wait(500); return; }
    const prev = run.lastStation || "agent";
    st("agent", "active", `Using ${esc($("st-" + t).querySelector(".st-name").textContent.toLowerCase())}`);
    await advance(prev, t, ev.summary ? ev.summary.slice(0, 40) : t);
    run.lastStation = t;
    st(t, "active", esc(ev.summary || "Working"));
    const SAY = { get_assignment: "First, what was asked?", read_submission: "Reading the file…", compare_with_others: "Anything copied?",
      get_overview: "How many have responded?", list_missing: "Who hasn't responded?", list_responses: "Reading the answers…", send_reminders: "Sending the nudges" };
    if (SAY[t]) say("agent", SAY[t]);
    if (t === "read_submission") { $("sheet")?.classList.add("reading"); narrate("lens", `The <b>Review agent</b> reads the file, line by line.`); }
    if (t === "compare_with_others") narrate("copy", `It compares this file with everyone else's submissions.`);
    if (t === "get_assignment") narrate("blueprint", `First it reads what the assignment asked for.`);
    if (t === "get_overview") narrate("chart", `The <b>${NAME[run.agent]} agent</b> checks progress: responses so far, expected, deadline.`);
    if (t === "list_missing") narrate("list", `It compares the audience with the responses to find who is missing.`);
    if (t === "list_responses") narrate("list", `It reads the responses from the database.`);
    if (t === "send_reminders") narrate("send", `It sends a short reminder to each person still missing — nobody else.`);
    if (t === "submit_review") {
      const words = { ok: ["LOOKS FINE", "#2f8a4c"], check: ["CHECK THIS", "#c98500"], problem: ["PROBLEM", "#d03b3b"] }[ev.verdict] || ["REVIEWED", "#8c8a7f"];
      $("sStamp").innerHTML = `<div class="stamp-tool">${stampSvg()}</div><div class="stamp-mark">${markSvg(words[0], words[1])}</div>`;
      if (ev.flags?.length) $("marks").innerHTML = ev.flags.map(f => `<div>× ${esc(f)}</div>`).join("");
      $("verdict").className = "";
      $("verdict").innerHTML = `<div class="bkv"><div class="${ev.verdict === "ok" ? "ok" : "bad"}"><span>Verdict</span><b>${esc(words[0].toLowerCase())}</b></div></div>
        <p style="margin:.6rem 0 0;font-size:.86rem">${esc(ev.summary || "")}</p>`;
      narrate(ev.verdict === "ok" ? "check" : "alert", `Verdict: <b>${esc(ev.summary || "")}</b>`);
      step({ who: "review", text: `Verdict: ${esc(words[0].toLowerCase())}`, sub: esc(ev.summary || ""), cls: ev.verdict === "ok" ? "ok" : "bad", at: t });
      say("agent", ev.verdict === "ok" ? "Looks fine to me" : ev.verdict === "check" ? "Worth a look" : "This needs attention", ev.verdict === "ok" ? "ok" : "bad", 3200);
    }
    await wait(700);
  }

  async function singleResult(ev, run) {
    const t = ev.tool;
    if (!$("st-" + t)) return;
    st(t, ev.ok ? "done" : "bad", esc(ev.summary || ""), !ev.ok);
    st("agent", "active", "Reading the result");
    const items = ev.items || [];
    if (t === "get_overview") {
      items.forEach(r => { const [a, b] = r.split(": "); kv(a, b || ""); });
      const n = +(items[0] || "").split(": ")[1], of = +(items[1] || "").split(": ")[1];
      if ($("pbar") && of) $("pbar").style.width = Math.round(n / of * 100) + "%";
      out(t, chip(ev.summary || ""));
    } else if (t === "list_missing") {
      out(t, items.slice(0, 3).map(x => chip(x)).join("") + (items.length > 3 ? chip(`+${items.length - 3}`) : ""));
      if ($("missing")) $("missing").innerHTML = items.map((x, i) => `<span class="missing" style="animation-delay:${i * 90}ms">${esc(x)}</span>`).join("") || `<span>Nobody — everyone responded.</span>`;
      if ($("found")) $("found").innerHTML = items.map((x, i) => `<span class="missing" style="animation-delay:${i * 90}ms">${esc(x)}</span>`).join("");
      kv("Not responded", items.length);
    } else if (t === "list_responses") {
      out(t, chip(ev.summary || ""));
      kv("Responses read", ev.summary || "");
      if ($("found")) $("found").innerHTML = items.map(x => `<span>${esc(x)}</span>`).join("");
    } else if (t === "send_reminders") {
      out(t, chip(ev.summary || "", "ok"));
      if ($("sent")) $("sent").innerHTML = items.map((x, i) => `<span class="sent" style="animation-delay:${i * 160}ms">${esc(x)}</span>`).join("") || `<span>Nobody to remind.</span>`;
    } else if (t === "read_submission") {
      kv("File", ev.summary || "");
    } else if (t === "get_assignment") {
      kv("Task", "read");
    } else if (t === "compare_with_others") {
      kv("Copies", ev.summary || "", items.length ? "bad" : "ok");
      items.forEach(x => kv("Matches", x, "bad"));
      out(t, items.length ? chip(items[0], "bad") : chip("no copies", "ok"));
    }
    if (t !== "submit_review") {
      step({ who: run.agent, text: `${$("st-" + t).querySelector(".st-name").textContent}`, sub: esc(ev.summary || ""), cls: ev.ok ? "" : "bad", at: t });
      say("agent", ev.ok ? (ev.summary || "Got it") : "That didn't work", ev.ok ? (items.length && t === "compare_with_others" ? "bad" : "") : "bad");
    }
    await wait(t === "send_reminders" ? 900 + items.length * 160 : 650);
  }

  // ---------------------------------------------------------- the end of a run
  async function onReply(ev, run) {
    const k = ev.agent;
    thinking.clear(); renderClaude();
    run.state = "done"; run.ms = ev.ms;
    if (lineKey === "builder") {
      st("assemble", stateOf("assemble") === "bad" ? "bad" : "done");
      st("app", "done", run.link ? `Live at <span class="mono">${esc(run.link)}</span> · reply sent` : "Reply sent");
      step({ who: "builder", text: "Builder replied to the person", sub: `${((ev.ms || 0) / 1000).toFixed(1)} s from request to reply`, cls: "ok", at: "app" });
      say("assemble", "Done! Ready to share", "ok", 3400);
    } else {
      await advance(run.lastStation || "agent", "out", k === "insights" ? "answer" : "done", "back");
      line.stations.filter(s => s.tool && stateOf(s.id) === "wait").forEach(s => st(s.id, "skip", "Not needed this time"));
      st("agent", "done", "Finished");
      st("out", "done", esc(ev.text || ""));
      if (k === "insights") { $("answer").className = ""; $("answer").innerHTML = `<p style="margin:0;font-size:.92rem">${esc(ev.text || "")}</p>`; }
      step({ who: k, text: k === "insights" ? "Answer sent to the owner" : k === "review" ? "Review saved on the response" : "Reminders logged", sub: `${((ev.ms || 0) / 1000).toFixed(1)} s in total`, cls: "ok", at: "out" });
      say("agent", "All done!", "ok", 3000);
    }
    benchReply(k, ev.text || "");
    narrate("check", `Done in <b>${((ev.ms || 0) / 1000).toFixed(1)} s</b>. ${k === "builder" ? "The app is ready to share." : ""}`);
    history.unshift({ agent: k, message: run.message || run.app || "", ms: ev.ms || 0, state: "done", sim: run.sim });
    renderHistory(); renderSteps();
    await wait(1800);
  }

  // -------------------------------------------------------------- recorded examples (simulation)
  async function playDemo(name) {
    if (demoRunning) return;
    demoRunning = true; demoAbort = false;
    $("demoStop").classList.remove("hidden");
    document.querySelectorAll("[data-demo]").forEach(b => b.disabled = true);
    renderMode();
    const ids = {};
    const idFor = key => ids[key] ||= "demo-" + key + "-" + Math.random().toString(36).slice(2, 6);
    for (const s of Sim.scene(name)) {
      if (demoAbort) break;
      await sleep((s.after || 0) * pace);
      await holdWhilePaused();
      if (demoAbort) break;
      const ev = { ...s.ev, run_id: idFor(s.run || "top"), ts: Date.now(), sim: true };
      if (s.run && s.run !== "top") ev.parent = idFor("top");
      enqueue(ev);
    }
    while ((playing || queue.length) && !demoAbort) await sleep(200);
    demoRunning = false;
    $("demoStop").classList.add("hidden");
    document.querySelectorAll("[data-demo]").forEach(b => b.disabled = false);
    renderMode();
  }
  function stopDemo() {
    demoAbort = true;
    if (paused) togglePause();
    for (let i = queue.length - 1; i >= 0; i--) if (queue[i].sim) queue.splice(i, 1);
    thinking.clear(); renderClaude();
  }

  // -------------------------------------------------------------- replay of a saved round, in step with the Flow tab
  // The Flow sends the round's recorded events (rebuilt by the server from the trace) with their real timestamps;
  // each one is played at its real moment. Works in this window and, via a broadcast channel, in another window.
  let recTimers = [], recTitle = null;
  function playRecorded({ events, t0, startAt, title }) {
    stopRecorded();
    if (!events || !events.length) return;
    recTitle = title || "this app";
    renderMode();
    for (const ev of events) {
      const due = startAt + (ev.ts - t0);                 // the wall-clock moment this happened, replayed now
      recTimers.push(setTimeout(() => enqueue({ ...ev, due }), Math.max(0, due - Date.now())));
    }
    const end = startAt + (events[events.length - 1].ts - t0) - Date.now() + 2500;
    recTimers.push(setTimeout(() => { recTitle = null; recTimers = []; renderMode(); }, Math.max(0, end)));
    setTimeout(() => narrate("clapper", `Replaying the recorded build of <b>“${esc(recTitle || title)}”</b>, in step with the Flow tab. Nothing is re-run.`),
               Math.max(0, startAt - Date.now()) + 50);
  }
  function stopRecorded() {
    recTimers.forEach(clearTimeout);
    recTimers = [];
    for (let i = queue.length - 1; i >= 0; i--) if (queue[i].recorded) queue.splice(i, 1);
    if (recTitle) { recTitle = null; thinking.clear(); renderClaude(); renderMode(); }
  }
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("appshare-replay") : null;
  if (channel) channel.onmessage = m => { if (m.data?.type === "start") playRecorded(m.data); else if (m.data?.type === "stop") stopRecorded(); };

  // -------------------------------------------------------------- wiring
  const AGENT_EVENTS = new Set(["agent_start", "agent_llm_start", "agent_llm_end", "agent_tool", "agent_tool_result", "agent_reply", "agent_error"]);
  CC.on("init", skeleton);
  CC.on("event", ev => { if (AGENT_EVENTS.has(ev.type) && !ev.sim) enqueue(ev); });
  CC.on("status", (st, prev) => { if (!prev || prev.state !== st.state) renderMode(); });
  CC.on("mode", m => { if (m === "agents") { renderMode(); requestAnimationFrame(drawEdges); } });

  return { enqueue, playDemo, playRecorded, stopRecorded };
})();
