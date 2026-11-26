/* AppShare Control Center — Live server: an isometric illustration driven by real requests.
   Devices → access gate → server cabinet (4 blades) → database / filing cabinet / agents' desk (+ Claude lamp). */
"use strict";

const Live = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const S = 44, CX = 0.866 * S, CY = 0.5 * S;
  const MAX_DEVICES = 6, MAX_PACKETS = 70;

  // footprint centres (screen) of each object
  const GATE = { x: 438, y: 372 };
  const RACK = { x: 650, y: 404, w: 3.6, d: 1.5, h: 5.2 };
  const DB = { x: 905, y: 222 };
  const FILES = { x: 925, y: 402 };
  const DESK = { x: 1075, y: 548 };
  const LAMP = { x: 1075, y: 352 };
  const BLADES = [
    { id: "web", name: "WEB", desc: "pages · api :8000" },
    { id: "auth", name: "AUTH", desc: "sign-in · sessions" },
    { id: "engine", name: "ENGINE", desc: "access · deadlines · files" },
    { id: "ai", name: "AI", desc: "builder · insights" },
  ];

  const P = (o, x, y, z = 0) => ({ x: o.x + (x - y) * CX, y: o.y + (x + y) * CY - z * S });
  let svg, L = {}, devices = new Map(), order = [], packets = [], running = false, bladeLoad = {};
  const ticker = [];

  // -------------------------------------------------------------- svg helpers
  function el(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }
  function txt(parent, x, y, s, cls, anchor = "start", extra = {}) {
    const t = el("text", { x, y, class: cls, "text-anchor": anchor, ...extra }, parent);
    t.textContent = s;
    return t;
  }
  const pts = a => a.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  /** Iso box around a footprint centre. Returns its faces' corner points for detailing. */
  function box(g, o, w, d, h, col, z0 = 0) {
    const q = (x, y, z) => P(o, x - w / 2, y - d / 2, z + z0);
    const top = [q(0, 0, h), q(w, 0, h), q(w, d, h), q(0, d, h)];
    const left = [q(0, d, 0), q(w, d, 0), q(w, d, h), q(0, d, h)];
    const right = [q(w, d, 0), q(w, 0, 0), q(w, 0, h), q(w, d, h)];
    el("polygon", { points: pts(left), fill: col[1] }, g);
    el("polygon", { points: pts(right), fill: col[2] }, g);
    el("polygon", { points: pts(top), fill: col[0] }, g);
    return { q };
  }
  /** Group whose local (u, v) world units map onto a box face. u runs left→right, v downward. */
  function face(g, o, w, d, h, which, z0 = 0) {
    const origin = which === "left" ? P(o, -w / 2, d / 2, h + z0) : P(o, w / 2, d / 2, h + z0);
    const b = which === "left" ? CY : -CY;
    return el("g", { transform: `matrix(${CX} ${b} 0 ${S} ${origin.x} ${origin.y})` }, g);
  }
  function facePt(o, w, d, h, which, u, v, z0 = 0) {
    const origin = which === "left" ? P(o, -w / 2, d / 2, h + z0) : P(o, w / 2, d / 2, h + z0);
    return { x: origin.x + CX * u, y: origin.y + (which === "left" ? CY : -CY) * u + S * v };
  }
  function cylinder(g, cx, cy, r, h, col) {      // iso cylinder standing on (cx, cy)
    const rx = 1.2247 * r * S, ry = 0.7071 * r * S, hh = h * S;
    el("path", { d: `M${cx - rx},${cy - hh} V${cy} A${rx},${ry} 0 0 0 ${cx + rx},${cy} V${cy - hh} Z`, fill: col[1] }, g);
    el("path", { d: `M${cx},${cy - hh + ry} V${cy + ry} A${rx},${ry} 0 0 0 ${cx + rx},${cy} V${cy - hh} A${rx},${ry} 0 0 1 ${cx},${cy - hh + ry} Z`, fill: col[2] }, g);
    el("ellipse", { cx, cy: cy - hh, rx, ry, fill: col[0] }, g);
    return { rx, ry };
  }

  // -------------------------------------------------------------- build the scene
  function build() {
    svg = document.getElementById("scene");
    svg.innerHTML = "";
    const defs = el("defs", {}, svg);
    defs.innerHTML = `
      <radialGradient id="lampLight" cx="50%" cy="0%" r="100%">
        <stop offset="0" stop-color="#ffd89c" stop-opacity=".28"/><stop offset="1" stop-color="#ffd89c" stop-opacity="0"/>
      </radialGradient>`;

    // floor grid along both iso axes
    const grid = el("path", { fill: "none", stroke: "#1c1c1a", "stroke-width": 1 }, svg);
    let d = "";
    const O = { x: 640, y: 330 };
    for (let c = -30; c <= 30; c++) {
      const a = P(O, -30, c), b = P(O, 30, c), e = P(O, c, -30), f = P(O, c, 30);
      d += `M${a.x},${a.y}L${b.x},${b.y}M${e.x},${e.y}L${f.x},${f.y}`;
    }
    grid.setAttribute("d", d);

    L.cables = el("g", {}, svg);
    L.labels = el("g", {}, svg);
    L.devices = el("g", {}, svg);
    buildGate();
    buildRack();
    buildDB();
    buildFiles();
    buildDesk();
    L.packets = el("g", {}, svg);
    L.fx = el("g", {}, svg);

    // section numbers
    [["01  DEVICES", 70], ["02  ACCESS GATE", 380], ["03  SERVER", 600], ["04  STORAGE & AGENTS", 860]].forEach(([s, x]) =>
      txt(svg, x, 34, s, "callout"));
    renderDevices();
    drawCables();
  }

  function buildGate() {
    const g = el("g", {}, svg);
    box(g, GATE, .7, 3, .08, ["#2a2925", "#22211e", "#1c1b19"]);
    [-1.15, 1.15].forEach(y => {
      const o = P(GATE, 0, y);
      box(g, o, .32, .32, 1.95, ["#3b3934", "#2e2d29", "#24231f"]);
    });
    const lintel = P(GATE, 0, 0, 1.95);
    box(g, { x: lintel.x, y: lintel.y + 0 }, .36, 2.62, .24, ["#45433d", "#34322e", "#2a2925"]);
    L.gateLights = [-1.15, 1.15].map(y => {
      const p = P(GATE, 0, y, 2.2);
      return el("rect", { x: p.x - 5, y: p.y - 6, width: 10, height: 6, rx: 1, class: "gate-light", fill: "#4a4842" }, g);
    });
    // scanner strip on the inner face of the lintel
    const s1 = P(GATE, .18, -1, 1.92), s2 = P(GATE, .18, 1, 1.92);
    L.gateScan = el("line", { x1: s1.x, y1: s1.y, x2: s2.x, y2: s2.y, stroke: "#4a4842", "stroke-width": 2 }, g);
    const lab = P(GATE, 0, 1.6);
    el("path", { class: "leader", d: `M${lab.x},${lab.y} l-26,26 h-20` }, L.labels);
    txt(L.labels, lab.x - 50, lab.y + 30, "ACCESS GATE", "callout", "end");
    txt(L.labels, lab.x - 50, lab.y + 45, "who may open what", "callout-sub", "end");
  }

  function buildRack() {
    const g = el("g", {}, svg);
    const { w, d, h } = RACK;
    box(g, RACK, w + .3, d + .3, .18, ["#2a2925", "#201f1c", "#1a1917"]);             // plinth
    box(g, RACK, w, d, h, ["#34332e", "#2a2925", "#201f1c"], .18);
    // top vents
    const top = el("g", {}, g);
    for (let i = 0; i < 7; i++) {
      const a = P(RACK, -w / 2 + .5 + i * .42, -d / 2 + .3, h + .18), b = P(RACK, -w / 2 + .5 + i * .42, d / 2 - .3, h + .18);
      el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: "#26251f", "stroke-width": 3, "stroke-linecap": "round" }, top);
    }
    // front (left) face: title, 4 blades, LCD
    const f = face(g, RACK, w, d, h, "left", .18);
    el("rect", { x: .1, y: .1, width: w - .2, height: h - .2, fill: "#24231f", rx: .04 }, f);
    txt(f, .22, .38, "APPSHARE-01", "", "start", { "font-size": .24, fill: "#cfccbf", "font-family": "ui-monospace, Consolas, monospace", "font-weight": 700, "letter-spacing": .03 });
    L.host = txt(f, w - .22, .38, "", "", "end", { "font-size": .17, fill: "#8c8a7f", "font-family": "ui-monospace, Consolas, monospace" });
    L.blades = {};
    BLADES.forEach((b, i) => {
      const v = .58 + i * 1.0;
      const bg = el("g", {}, f);
      el("rect", { x: .16, y: v, width: w - .32, height: .88, fill: "#1a1917", rx: .03 }, bg);
      el("rect", { x: .16, y: v, width: w - .32, height: .04, fill: "#3b3934" }, bg);
      const pwr = el("rect", { class: "blade-led pwr", x: .28, y: v + .2, width: .1, height: .1 }, bg);
      const act = el("rect", { class: "blade-led act", x: .28, y: v + .42, width: .1, height: .1, fill: "#3a3833" }, bg);
      txt(bg, .52, v + .36, b.name, "", "start", { "font-size": .26, fill: "#ecebe4", "font-family": "ui-monospace, Consolas, monospace", "font-weight": 700 });
      txt(bg, .52, v + .6, b.desc, "", "start", { "font-size": .15, fill: "#8c8a7f", "font-family": "ui-monospace, Consolas, monospace" });
      el("rect", { x: .52, y: v + .7, width: 1.4, height: .06, fill: "#2c2b27" }, bg);
      const meter = el("rect", { x: .52, y: v + .7, width: 0, height: .06, fill: "#8c8a7f" }, bg);
      for (let k = 0; k < 4; k++) {
        el("rect", { x: 2.2 + k * .3, y: v + .14, width: .22, height: .6, fill: "#2a2925", rx: .02 }, bg);
        el("rect", { x: 2.26 + k * .3, y: v + .2, width: .1, height: .03, fill: "#45433d" }, bg);
      }
      L.blades[b.id] = { pwr, act, meter, v };
      bladeLoad[b.id] = 0;
    });
    el("rect", { x: .2, y: h - .55, width: w - .4, height: .32, fill: "#0b120b", rx: .03 }, f);
    L.lcd = txt(f, w / 2, h - .33, "OFFLINE", "lcd-text", "middle", { "font-size": .17 });
    // side (right) face: two fans
    const s = face(g, RACK, w, d, h, "right", .18);
    el("rect", { x: .1, y: .1, width: d - .2, height: h - .2, fill: "#1d1c19" }, s);
    L.fans = [1.5, 3.3].map(v => {
      const c = el("g", {}, s);
      el("circle", { cx: d / 2, cy: v, r: .55, fill: "#141412" }, c);
      const fan = el("g", { class: "fan" }, c);
      for (let k = 0; k < 6; k++) el("path", { d: `M${d / 2},${v} q.12,-.22 0,-.46 q-.2,.08 -.1,.4 z`, fill: "#3b3934", transform: `rotate(${k * 60} ${d / 2} ${v})` }, fan);
      el("circle", { cx: d / 2, cy: v, r: .09, fill: "#4a4842" }, c);
      for (let k = 1; k <= 3; k++) el("circle", { cx: d / 2, cy: v, r: .18 * k, fill: "none", stroke: "#26251f", "stroke-width": .02 }, c);
      return fan;
    });
  }

  function buildDB() {
    const g = el("g", {}, svg);
    L.dbBands = [];
    for (let i = 0; i < 3; i++) {
      const cy = DB.y - i * 30;
      const { rx, ry } = cylinder(g, DB.x, cy, .82, .5, ["#3b3934", "#2e2d29", "#24231f"]);
      L.dbBands.push(el("path", { class: "disk-band", d: `M${DB.x - rx},${cy - 7} A${rx},${ry} 0 0 0 ${DB.x + rx},${cy - 7}`, fill: "none", stroke: "#45433d", "stroke-width": 2 }, g));
    }
    L.db = g;
    const a = { x: DB.x + 62, y: DB.y - 70 };
    el("path", { class: "leader", d: `M${DB.x + 40},${DB.y - 66} L${a.x},${a.y - 14} h16` }, L.labels);
    txt(L.labels, a.x + 22, a.y - 10, "DATABASE", "callout");
    L.dbSub = txt(L.labels, a.x + 22, a.y + 5, "sqlite", "callout-sub");
  }

  function buildFiles() {
    const g = el("g", {}, svg);
    const w = 1.2, d = 1.05, h = 1.9;
    box(g, FILES, w, d, h, ["#3b3934", "#2e2d29", "#24231f"]);
    L.drawers = [];
    for (let i = 0; i < 3; i++) {
      const v = .12 + i * .6;
      const outer = el("g", { class: "drawer" }, g);       // screen-space group, so it can slide along world +y
      L.drawers.push(outer);
      const dr = face(outer, FILES, w, d, h, "left");
      el("rect", { x: .1, y: v, width: w - .2, height: .52, fill: "#34332e", rx: .02 }, dr);
      el("rect", { x: w / 2 - .22, y: v + .3, width: .44, height: .07, fill: "#6b685f", rx: .03 }, dr);
      el("rect", { x: w / 2 - .16, y: v + .1, width: .32, height: .13, fill: "#d9d3c3" }, dr);
    }
    const a = { x: FILES.x + 66, y: FILES.y - 6 };
    el("path", { class: "leader", d: `M${FILES.x + 44},${FILES.y - 22} L${a.x},${a.y} h14` }, L.labels);
    txt(L.labels, a.x + 20, a.y + 4, "FILE STORAGE", "callout");
    L.filesSub = txt(L.labels, a.x + 20, a.y + 19, "uploads", "callout-sub");
  }

  function buildDesk() {
    const g = el("g", {}, svg);
    // the whole team behind the desk: five specialists in the back row, Builder and Insights in front
    const back = ["data", "design", "access", "review", "reminder"];
    back.forEach((k, n) => {
      const p = P(DESK, -.9 + n * .42, -1.25 + n * .02, .3);
      g.insertAdjacentHTML("beforeend", CHAR.svg(k, { crop: "head", x: p.x - 16, y: p.y - 70, w: 34, h: 30 }));
    });
    const b = P(DESK, -.4, -.6, .3), i = P(DESK, .5, -.9, .3);
    g.insertAdjacentHTML("beforeend", CHAR.svg("builder", { x: b.x - 52, y: b.y - 84, w: 76, h: 100 }));
    g.insertAdjacentHTML("beforeend", CHAR.svg("insights", { x: i.x - 30, y: i.y - 94, w: 66, h: 104 }));
    // desk
    [[-.75, -.38], [.75, -.38], [-.75, .38], [.75, .38]].forEach(([x, y]) => box(g, P(DESK, x, y), .08, .08, .72, ["#3b3934", "#2e2d29", "#24231f"]));
    box(g, DESK, 1.7, .95, .09, ["#4a4740", "#3b3934", "#2e2d29"], .72);
    const paper = [P(DESK, -.4, -.25, .82), P(DESK, .2, -.25, .82), P(DESK, .2, .2, .82), P(DESK, -.4, .2, .82)];
    el("polygon", { points: pts(paper), fill: "#1d3b5e" }, g);
    L.desk = g;
    // the Claude lamp hanging over the desk
    const lg = el("g", { class: "claude" }, svg);
    el("line", { x1: LAMP.x, y1: 0, x2: LAMP.x, y2: LAMP.y - 30, stroke: "#4a4842", "stroke-width": 1.5 }, lg);
    el("polygon", { class: "lamp-cone", points: `${LAMP.x - 30},${LAMP.y} ${LAMP.x + 30},${LAMP.y} ${DESK.x + 90},${DESK.y - 20} ${DESK.x - 90},${DESK.y - 20}`, fill: "url(#lampLight)" }, lg);
    el("path", { d: `M${LAMP.x - 34},${LAMP.y} C${LAMP.x - 30},${LAMP.y - 30} ${LAMP.x + 30},${LAMP.y - 30} ${LAMP.x + 34},${LAMP.y} Z`, fill: "#3b3934" }, lg);
    el("path", { d: `M${LAMP.x + 6},${LAMP.y - 22} C${LAMP.x + 22},${LAMP.y - 18} ${LAMP.x + 30},${LAMP.y - 10} ${LAMP.x + 34},${LAMP.y} H${LAMP.x + 14} Z`, fill: "#2a2925" }, lg);
    el("ellipse", { cx: LAMP.x, cy: LAMP.y, rx: 34, ry: 6, fill: "#c9a25a" }, lg);
    el("ellipse", { class: "lamp-bulb", cx: LAMP.x, cy: LAMP.y + 2, rx: 14, ry: 5 }, lg);
    L.lamp = lg;
    el("path", { class: "leader", d: `M${LAMP.x + 40},${LAMP.y - 12} l24,-24 h16` }, L.labels);
    txt(L.labels, LAMP.x + 86, LAMP.y - 32, "CLAUDE", "callout");
    txt(L.labels, LAMP.x + 86, LAMP.y - 17, "ai model · cloud", "callout-sub");
    L.lampStatus = txt(L.labels, LAMP.x + 86, LAMP.y - 2, "", "callout-sub", "start", { fill: "#e8c37a" });
    const a = P(DESK, .9, .5);
    el("path", { class: "leader", d: `M${a.x},${a.y} l22,22 h16` }, L.labels);
    txt(L.labels, a.x + 44, a.y + 26, "AGENTS", "callout");
    L.agentsSub = txt(L.labels, a.x + 44, a.y + 41, "builder · insights", "callout-sub");
  }

  // -------------------------------------------------------------- routes
  const gateIn = () => P(GATE, -1.1, 0);
  const gateMid = () => P(GATE, 0, 0, .35);
  const gateOut = () => P(GATE, 1.1, 0);
  const rackFace = (u, v) => facePt(RACK, RACK.w, RACK.d, RACK.h, "left", u, v, .18);
  const rackBaseIn = () => rackFace(.3, RACK.h + .18);
  const rackBaseOut = () => rackFace(RACK.w - .3, RACK.h + .18);
  const compPort = name => ({ db: { x: DB.x - 44, y: DB.y + 14 }, files: P(FILES, -.2, .9), agents: P(DESK, -.2, .9, 0) }[name]);

  function drawCables() {
    const g = L.cables;
    g.innerHTML = "";
    const lines = [];
    for (const id of visibleIds()) {
      const dv = devices.get(id);
      if (dv.port) lines.push(curve([dv.port, gateIn()]));
    }
    if (!visibleIds().length) lines.push(curve([{ x: 260, y: 360 }, gateIn()]));
    lines.push(curve([gateOut(), rackBaseIn()]));
    ["db", "files", "agents"].forEach(n => lines.push(curve([rackBaseOut(), compPort(n)])));
    for (const d of lines) {
      el("path", { class: "cable", d }, g);
      el("path", { class: "cable-hi", d }, g);
    }
  }

  function curve(points) {
    let d = `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`;
    for (let i = 1; i < points.length; i++) {
      const p = points[i - 1], q = points[i];
      if (q.straight) { d += ` L${q.x.toFixed(1)},${q.y.toFixed(1)}`; continue; }
      const dx = (q.x - p.x) * .5;
      d += ` C${(p.x + dx).toFixed(1)},${p.y.toFixed(1)} ${(q.x - dx).toFixed(1)},${q.y.toFixed(1)} ${q.x.toFixed(1)},${q.y.toFixed(1)}`;
    }
    return d;
  }
  const straight = p => ({ ...p, straight: true });

  function bladeFor(ev) {
    if (ev.path && (ev.path.startsWith("/api/login") || ev.path.startsWith("/api/logout"))) return "auth";
    if (ev.kind === "agent") return "ai";
    if (ev.kind === "page") return "web";
    return "engine";
  }

  function routeFor(ev) {
    const blade = bladeFor(ev), v = L.blades[blade].v + .48;
    const start = deviceAnchor(ev.device);
    const denied = ev.status === 401 || ev.status === 403 || (ev.status === 404 && ev.path?.startsWith("/api/a/"));
    if (denied) {
      const fwd = [start, gateIn(), straight(gateMid())];
      return { forward: fwd, back: reverseRoute(fwd), denied: true };
    }
    const fwd = [start, gateIn(), straight(gateMid()), straight(gateOut()), rackBaseIn(), straight(rackFace(.3, v)), straight(rackFace(RACK.w - .3, v))];
    const rejected = ev.status === 422;
    let target = null;
    if (!rejected && blade !== "web") {
      target = blade === "ai" ? "agents" : ev.kind === "submit" && ev.method === "POST" ? "files" : "db";
      fwd.push(straight(rackBaseOut()), compPort(target));
    }
    return { forward: fwd, back: reverseRoute(fwd), blade, target, rejected };
  }

  /** Reverse a route; a "straight" flag belongs to the segment, so it moves with it. */
  function reverseRoute(fwd) {
    const n = fwd.length;
    return fwd.map((_, k) => {
      const j = n - 1 - k;
      const p = { x: fwd[j].x, y: fwd[j].y };
      if (k > 0 && fwd[j + 1]?.straight) p.straight = true;
      return p;
    });
  }

  // -------------------------------------------------------------- packets
  function spawn(points, color, opts = {}) {
    if (packets.length >= MAX_PACKETS) return;
    const path = el("path", { d: curve(points), fill: "none", stroke: "none" }, L.packets);
    const len = path.getTotalLength();
    const g = el("g", {}, L.packets);
    const trail = [.45, .25].map((o, i) => el("circle", { r: 4 - i, fill: color, opacity: o }, g));
    if (opts.doc) {
      el("rect", { x: -5, y: -19, width: 10, height: 12, fill: "#ecebe4", rx: 1 }, g);
      el("path", { d: "M-2.5 -15 h5 M-2.5 -12 h5", stroke: "#8c8a7f", "stroke-width": 1.2 }, g);
    }
    el("circle", { r: opts.big ? 6.5 : 5.2, fill: color }, g);
    el("circle", { r: opts.big ? 6.5 : 5.2, class: "packet-ring" }, g);
    const dur = Math.max(450, Math.min(2000, len / (opts.speed || .7)));
    packets.push({ path, g, trail, len, dur, t0: performance.now(), onDone: opts.onDone });
    if (!running) { running = true; requestAnimationFrame(frame); }
  }

  function frame(now) {
    for (let i = packets.length - 1; i >= 0; i--) {
      const p = packets[i];
      const t = Math.min(1, (now - p.t0) / p.dur);
      const e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      const at = p.path.getPointAtLength(e * p.len);
      p.g.setAttribute("transform", `translate(${at.x.toFixed(1)},${at.y.toFixed(1)})`);
      p.trail.forEach((c, k) => {
        const q = p.path.getPointAtLength(Math.max(0, e * p.len - (k + 1) * 8));
        c.setAttribute("cx", (q.x - at.x).toFixed(1));
        c.setAttribute("cy", (q.y - at.y).toFixed(1));
      });
      if (t >= 1) {
        p.path.remove(); p.g.remove();
        packets.splice(i, 1);
        p.onDone && p.onDone();
      }
    }
    if (packets.length) requestAnimationFrame(frame); else running = false;
  }

  function cross(x, y) {
    const g = el("g", { transform: `translate(${x},${y})` }, L.fx);
    el("circle", { r: 13, fill: "#141412", stroke: CC.STATUS.critical, "stroke-width": 2 }, g);
    el("path", { class: "mark-x", d: "M-5,-5 L5,5 M5,-5 L-5,5" }, g);
    const t0 = performance.now();
    (function fade(now) {
      const t = Math.min(1, (now - t0) / 1100);
      g.setAttribute("opacity", t < .6 ? 1 : 1 - (t - .6) / .4);
      if (t < 1) requestAnimationFrame(fade); else g.remove();
    })(t0);
  }

  function gateFlash(ok) {
    L.gateLights.forEach(l => { l.setAttribute("class", "gate-light " + (ok ? "ok" : "bad")); });
    L.gateScan.setAttribute("stroke", ok ? CC.STATUS.good : CC.STATUS.critical);
    clearTimeout(L._gt);
    L._gt = setTimeout(() => { L.gateLights.forEach(l => l.setAttribute("class", "gate-light")); L.gateScan.setAttribute("stroke", "#4a4842"); }, ok ? 260 : 900);
  }

  function hitBlade(id, cls) {
    const b = L.blades[id];
    if (!b) return;
    b.act.setAttribute("class", `blade-led act on ${cls}`);
    setTimeout(() => b.act.setAttribute("class", "blade-led act"), 170);
    bladeLoad[id] = Math.min(1, (bladeLoad[id] || 0) + .2);
  }

  function hitTarget(name, kind) {
    if (name === "db") {
      L.dbBands.forEach((b, i) => setTimeout(() => { b.setAttribute("stroke", CC.KINDS[kind]?.color || "#ecebe4"); setTimeout(() => b.setAttribute("stroke", "#45433d"), 260); }, i * 70));
    } else if (name === "files") {
      // the top drawer slides out towards the viewer (world +y) and back
      const dr = L.drawers[0];
      dr.style.transform = `translate(${(-CX * .32).toFixed(1)}px, ${(CY * .32).toFixed(1)}px)`;
      clearTimeout(L._dr);
      L._dr = setTimeout(() => { dr.style.transform = "translate(0px, 0px)"; }, 650);
    }
  }

  function animateRequest(ev) {
    if (document.hidden || CC.mode !== "live") return;
    const r = routeFor(ev);
    const bad = r.denied || r.rejected;
    const color = CC.KINDS[ev.kind]?.color || "#8c8a7f";
    const upload = ev.kind === "submit" && ev.method === "POST";
    pulseDevice(ev.device);
    spawn(r.forward, color, {
      doc: upload, big: upload,
      onDone: () => {
        if (r.denied) {
          gateFlash(false);
          const m = gateMid(); cross(m.x, m.y - 14);
          spawn(r.back, CC.STATUS.critical, { speed: .9 });
          return;
        }
        gateFlash(true);
        hitBlade(r.blade, r.rejected ? "k-bad" : "k-" + ev.kind);
        if (r.rejected) {
          const p = rackFace(RACK.w - .3, L.blades[r.blade].v + .48); cross(p.x, p.y - 12);
          spawn(r.back, CC.STATUS.critical, { speed: .95 });
          return;
        }
        if (r.target) hitTarget(r.target, ev.kind);
        spawn(r.back, "#ecebe4", { speed: .95, onDone: () => pulseDevice(ev.device) });
      },
    });
    // gate light as the packet passes
    setTimeout(() => !r.denied && gateFlash(true), 380);
  }

  function lamp(on, label = "") {
    L.lamp.classList.toggle("on", on);
    L.lampStatus.textContent = label;
  }

  // -------------------------------------------------------------- devices
  function anchorFor(i) { return { x: 300 - i * 24, y: 128 + i * 80 }; }

  function upsertDevice(d, fresh = false) {
    const known = devices.get(d.id);
    if (known) { Object.assign(known, d); return known; }
    devices.set(d.id, { ...d, enter: fresh });
    order.push(d.id);
    return devices.get(d.id);
  }

  function visibleIds() {
    const now = Date.now();
    const alive = order.filter(id => devices.has(id) && now - devices.get(id).last_seen < 300000);
    const recent = [...alive].sort((a, b) => devices.get(b).last_seen - devices.get(a).last_seen).slice(0, MAX_DEVICES);
    return alive.filter(id => recent.includes(id));
  }

  function drawDevice(g, kind, a) {
    if (kind === "laptop") {
      box(g, a, 1.05, 1.25, .07, ["#3b3934", "#2e2d29", "#24231f"]);
      const kb = [P(a, -.35, -.5, .07), P(a, .35, -.5, .07), P(a, .35, .5, .07), P(a, -.35, .5, .07)];
      el("polygon", { points: pts(kb), fill: "#2a2925" }, g);
      const sa = P(a, -.52, 0);
      box(g, sa, .06, 1.25, .82, ["#3b3934", "#2e2d29", "#24231f"], .07);
      const scr = [P(sa, .03, .55, .14), P(sa, .03, -.55, .14), P(sa, .03, -.55, .82), P(sa, .03, .55, .82)];
      el("polygon", { class: "screen", points: pts(scr), fill: "#3a3833" }, g);
    } else {
      box(g, a, .55, .72, .1, ["#34332e", "#2a2925", "#201f1c"]);               // stand
      const pa = P(a, -.08, 0);
      box(g, pa, .1, .62, 1.15, ["#2e2d29", "#24231f", "#1c1b19"], .1);
      const scr = [P(pa, .05, .25, .2), P(pa, .05, -.25, .2), P(pa, .05, -.25, 1.15), P(pa, .05, .25, 1.15)];
      el("polygon", { class: "screen", points: pts(scr), fill: "#3a3833" }, g);
    }
  }

  function renderDevices() {
    const g = L.devices, lab = L.labels.querySelector("[data-dev-labels]") || el("g", { "data-dev-labels": "" }, L.labels);
    g.innerHTML = ""; lab.innerHTML = "";
    const ids = visibleIds(), now = Date.now();
    if (!ids.length) {
      const a = anchorFor(2);
      const ghost = el("g", { opacity: .35 }, g);
      drawDevice(ghost, "phone", a);
      txt(lab, a.x - 40, a.y - 8, CC.online() ? "Waiting for a phone" : "No devices", "callout-name", "end");
      txt(lab, a.x - 40, a.y + 9, CC.online() ? "scan the QR code →" : "turn the server on", "callout-sub", "end");
      drawCables();
      return;
    }
    ids.forEach((id, i) => {
      const d = devices.get(id);
      const a = anchorFor(i);
      d.port = P(a, .6, 0);
      const idle = now - d.last_seen > 45000;
      const node = el("g", { class: `dev${idle ? " idle" : ""}${d.enter ? " enter" : ""}`, "data-id": id }, g);
      d.enter = false;
      d.node = node;
      drawDevice(node, d.kind, a);
      const name = d.user || "Not signed in";
      const lx = a.x - (d.kind === "laptop" ? 66 : 42);
      txt(lab, lx, a.y - 10, name.length > 20 ? name.slice(0, 19) + "…" : name, "callout-name", "end");
      txt(lab, lx, a.y + 6, `${d.label}${d.sim ? " · rehearsal" : d.via ? " · " + d.via : ""}`.toLowerCase(), "callout-sub", "end");
    });
    const hidden = order.filter(id => devices.has(id) && now - devices.get(id).last_seen < 300000).length - ids.length;
    if (hidden > 0) txt(lab, 60, 640, `+ ${hidden} more device${hidden > 1 ? "s" : ""}`, "callout-sub");
    drawCables();
  }

  function deviceAnchor(id) {
    const d = devices.get(id);
    if (d && d.port && visibleIds().includes(id)) return d.port;
    return { x: 120, y: 640 };
  }

  function pulseDevice(id) {
    const d = devices.get(id);
    if (!d || !d.node) return;
    d.node.classList.remove("idle");
    d.node.classList.add("active");
    clearTimeout(d._t);
    d._t = setTimeout(() => d.node && d.node.classList.remove("active"), 900);
  }

  // -------------------------------------------------------------- activity feed
  function describe(ev) {
    const E = CC.esc, q = s => `<span class="q">“${E(s)}”</span>`, who = u => `<b>${E(u || "Someone")}</b>`;
    const st = CC.STATUS, K = CC.KINDS;
    switch (ev.type) {
      case "server_start": return { i: "power", c: st.good, h: `Server started on <b>${E(ev.name)}</b>` };
      case "device_new": return { i: ev.device_kind === "laptop" ? "laptop" : "phone", c: K.page.color, h: `New device: <b>${E(ev.device_label)}</b> via ${E(ev.via)}` };
      case "login": return { i: "key", c: K.data.color, h: `${who(ev.user)} signed in` };
      case "logout": return { i: "door", c: "#8c8a7f", h: `${who(ev.user)} signed out` };
      case "login_failed": return { i: "block", c: st.critical, h: `Sign-in refused for unknown email <span class="mono">${E(ev.email)}</span>` };
      case "app_created": return { i: "blueprint", c: K.agent.color, h: `${who(ev.user)} created ${q(ev.title)} with the Builder agent` };
      case "app_updated": return { i: "pencil", c: K.agent.color, h: `${who(ev.user)} updated ${q(ev.title)}` };
      case "app_shared": return { i: "link", c: K.data.color, h: `${who(ev.user)} shared ${q(ev.title)} with ${E((ev.targets || []).join(", ") || "nobody yet")} — <b>${ev.audience}</b> can submit` };
      case "app_status": return { i: ev.status === "closed" ? "lock" : "unlock", c: "#8c8a7f", h: `${who(ev.user)} ${ev.status === "closed" ? "closed" : "reopened"} ${q(ev.title)}` };
      case "app_deleted": return { i: "trash", c: "#8c8a7f", h: `${who(ev.user)} deleted ${q(ev.title)}` };
      case "submission": {
        const f = (ev.files || [])[0];
        return { i: "inbox", c: K.submit.color, h: `${who(ev.user)} ${ev.updated ? "updated their response to" : "submitted"} ${q(ev.title)}${f ? ` · <span class="mono">${E(f.name)}</span> ${CC.bytes(f.size)}` : ""}` };
      }
      case "submission_rejected": return { i: "shield", c: ev.blocked_file ? st.critical : st.warning, h: `${ev.blocked_file ? "Blocked a file" : "Rejected a response"} from ${who(ev.user)} — ${E((ev.reasons || [])[0] || "")}` };
      case "access_denied": return { i: "block", c: st.serious, h: `${who(ev.user)} tried to open ${q(ev.app)} without access — blocked at the gate` };
      case "agent_start":
        if (ev.parent || !["builder", "insights"].includes(ev.agent)) return null;     // specialists show up via their results
        return { i: ev.agent === "builder" ? "pencil" : "lens", c: K.agent.color, h: `<b>${ev.agent === "builder" ? "Builder + team" : "Insights"}</b> working for ${who(ev.user)}: ${q(ev.message.length > 70 ? ev.message.slice(0, 69) + "…" : ev.message)}` };
      case "agent_reply":
        if (ev.parent || !["builder", "insights"].includes(ev.agent)) return null;
        return { i: "check", c: st.good, h: `<b>${ev.agent === "builder" ? "Builder" : "Insights"}</b> answered in ${(ev.ms / 1000).toFixed(1)} s` };
      case "review_done": return { i: "lens", c: ev.verdict === "ok" ? st.good : ev.verdict === "check" ? st.warning : st.critical,
        h: `<b>Review</b> read ${who(ev.user)}'s submission to ${q(ev.title)}: ${E(ev.summary)}` };
      case "reminders_sent": return { i: "bell", c: K.agent.color,
        h: ev.count ? `<b>Reminder</b> nudged ${ev.count} ${ev.count === 1 ? "person" : "people"} about ${q(ev.title)}` : `<b>Reminder</b>: everyone has submitted ${q(ev.title)}` };
      case "agent_error": return { i: "alert", c: st.warning, h: `<b>Agent</b> couldn't finish: ${E(ev.error)}` };
      default: return null;
    }
  }

  function addTicker(ev) {
    const d = describe(ev);
    if (!d) return;
    ticker.unshift({ ...d, ts: ev.ts, sim: ev.sim });
    ticker.length = Math.min(ticker.length, 7);
    renderTicker();
  }

  function renderTicker() {
    const box = document.getElementById("ticker");
    if (!ticker.length) {
      box.innerHTML = `<li class="empty">${CC.online() ? "Waiting for activity. Open AppShare on a phone and sign in." : "Turn the server on to see live activity."}</li>`;
      return;
    }
    box.innerHTML = ticker.map(t => `<li style="--fi:${t.c}"><span class="f-t">${CC.clock(t.ts)}</span><span class="f-i">${CC.icon(t.i)}</span>
      <span class="f-x">${t.sim ? `<span class="sim">REHEARSAL</span>` : ""}${t.h}</span></li>`).join("");
  }

  // -------------------------------------------------------------- side cards
  function renderLegend() {
    document.getElementById("liveLegend").innerHTML =
      Object.values(CC.KINDS).map(k => `<span><i class="sw dot" style="background:${k.color}"></i>${k.label}</span>`).join("") +
      `<span><i class="sw dot" style="background:${CC.STATUS.critical}"></i>Blocked</span>`;
  }

  function sparkline(values) {
    const w = 300, h = 46, max = Math.max(1, ...values);
    const p = values.map((v, i) => [i * (w / Math.max(1, values.length - 1)), h - 3 - (v / max) * (h - 9)]);
    const line = p.map((q, i) => `${i ? "L" : "M"}${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(" ");
    const last = p[p.length - 1];
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Requests per minute, last 30 minutes">
      <line x1="0" x2="${w}" y1="${h - 3}" y2="${h - 3}" stroke="#3b3a34" stroke-width="1" vector-effect="non-scaling-stroke"/>
      <path d="${line} L${w},${h - 3} L0,${h - 3} Z" fill="#b9b7ac" opacity=".08"/>
      <path d="${line}" fill="none" stroke="#b9b7ac" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
      <circle cx="${last[0]}" cy="${last[1]}" r="4" fill="#ecebe4" stroke="#181816" stroke-width="2"/></svg>`;
  }

  function renderSide() {
    const st = CC.status, snap = CC.snapshot;
    if (!st) return;
    const on = CC.online();
    const lanAddr = st.addresses.find(a => a.kind === "hotspot") || st.addresses.find(a => a.kind === "lan");
    const c = snap?.counters;
    const rpmSeries = (snap?.series || []).map(m => m.page + m.data + m.submit + m.agent);
    const rpm = rpmSeries.length ? rpmSeries[rpmSeries.length - 1] : 0;
    const stTag = on ? `<span class="tag good"><i class="mk"></i>online</span>` : st.state === "starting" ? `<span class="tag warn"><i class="mk"></i>starting</span>` : `<span class="tag muted"><i class="mk"></i>off</span>`;
    document.getElementById("serverCard").innerHTML = `
      <div class="panel-head" style="margin-bottom:.4rem"><div><h2>Server</h2><p class="sub">${CC.esc(st.hostname)} · Python ${CC.esc(st.python)}</p></div>${stTag}</div>
      <dl class="kv">
        <dt>Phone address</dt><dd>${on && st.lan && lanAddr ? CC.esc(lanAddr.url.replace("http://", "")) : "—"}</dd>
        <dt>Uptime</dt><dd>${on && snap ? CC.dur(Date.now() - snap.server.started_at) : "—"}</dd>
        <dt>Process</dt><dd>${on && snap ? snap.server.pid : "—"}</dd>
        <dt>Requests</dt><dd>${c ? CC.num(c.requests) : "—"}</dd>
        <dt>Avg response</dt><dd>${c ? c.avg_ms + " ms" : "—"}</dd>
        <dt>This minute</dt><dd>${on ? rpm + " req" : "—"}</dd>
      </dl>
      ${rpmSeries.length ? `<div class="label" style="margin-top:.9rem">Requests / min · 30 min</div>${sparkline(rpmSeries)}` : ""}`;

    const apps = (snap?.db?.apps || []).filter(a => a.status !== "draft").slice(0, 4);
    document.getElementById("appsCard").innerHTML = `<div class="panel-head" style="margin-bottom:.6rem"><div><h2>Shared apps</h2><p class="sub">Responses received of people it's shared with.</p></div></div>
      ${apps.length ? `<div class="mini-apps">${apps.map(a => {
        const pct = a.audience ? Math.min(100, Math.round(a.responses / a.audience * 100)) : 0;
        return `<div class="mini-app"><div class="ma-top"><span class="ma-t">${CC.esc(a.title)}</span><span class="ma-n">${a.responses}${a.audience ? " / " + a.audience : ""}</span></div>
          <div class="meter ${pct >= 100 ? "done" : ""}" role="img" aria-label="${a.responses} of ${a.audience} responded"><i style="width:${a.audience ? pct : (a.responses ? 100 : 0)}%"></i></div></div>`;
      }).join("")}</div>` : `<div class="empty-note">${on ? "No shared apps yet. Build one with the agent and press Share." : "Turn the server on."}</div>`}`;

    const live = visibleIds().filter(id => Date.now() - devices.get(id).last_seen < 45000).length;
    L.lcd.textContent = on ? `ONLINE  ${rpm} REQ/MIN  ${live} DEV` : st.state === "starting" ? "BOOTING…" : document.body.classList.contains("sim-on") ? "REHEARSAL" : "OFFLINE";
    L.host.textContent = st.hostname.toLowerCase().slice(0, 16);
    if (snap) {
      L.dbSub.textContent = `${snap.db.apps_total} apps · ${snap.db.submissions} responses`;
      L.filesSub.textContent = `${snap.db.files} files · ${CC.bytes(snap.db.files_bytes)}`;
      L.agentsSub.textContent = `${c.agent_runs} runs · ${CC.num(c.tokens_in + c.tokens_out)} tokens`;
    }
    const speed = on ? Math.max(.35, 2.2 - rpm * .06) : 3;
    svg.style.setProperty("--fan-speed", speed.toFixed(2) + "s");
  }

  function decayLoad() {
    for (const id of Object.keys(bladeLoad)) {
      bladeLoad[id] = Math.max(0, bladeLoad[id] * .86 - .01);
      const m = L.blades[id]?.meter;
      if (m) {
        m.setAttribute("width", ((CC.online() || document.body.classList.contains("sim-on")) ? .08 + bladeLoad[id] * 1.32 : 0).toFixed(3));
        m.setAttribute("fill", bladeLoad[id] > .7 ? "#e8c37a" : "#8c8a7f");
      }
    }
  }

  // -------------------------------------------------------------- wiring
  function onEvent(ev) {
    if (ev.type === "http") {
      const known = devices.has(ev.device);
      upsertDevice({ id: ev.device, kind: ev.device_kind, label: ev.device_label, user: ev.user || devices.get(ev.device)?.user, last_seen: Date.now(), sim: ev.sim }, !known);
      if (!known) renderDevices();
      animateRequest(ev);
    } else if (ev.type === "device_new") {
      upsertDevice({ id: ev.device, kind: ev.device_kind, label: ev.device_label, user: ev.user, via: ev.via, last_seen: Date.now(), sim: ev.sim }, true);
      renderDevices();
    } else if (ev.type === "agent_llm_start") {
      lamp(true, "thinking…");
      if (CC.mode === "live") spawn([compPort("agents"), { x: LAMP.x, y: LAMP.y + 6 }], CC.KINDS.agent.color, { speed: .35 });
    } else if (ev.type === "agent_llm_end") {
      if (CC.mode === "live") spawn([{ x: LAMP.x, y: LAMP.y + 6 }, compPort("agents")], CC.KINDS.agent.color, { speed: .35 });
      setTimeout(() => lamp(false), 700);
    } else if (ev.type === "server_start" && !ev.sim) {
      devices.clear(); order = []; renderDevices();
    }
    addTicker(ev);
  }

  function onSnapshot(snap) {
    if (snap) for (const d of snap.devices) upsertDevice({ ...d, user: d.user || devices.get(d.id)?.user, enter: false });
    renderDevices();
    renderSide();
  }

  function onHistory(events) {
    ticker.length = 0;
    events.filter(describe).slice(-7).forEach(e => ticker.unshift({ ...describe(e), ts: e.ts }));
    renderTicker();
  }

  function removeSimDevices() {
    for (const id of [...devices.keys()]) if (devices.get(id).sim) devices.delete(id);
    order = order.filter(id => devices.has(id));
    for (let i = ticker.length - 1; i >= 0; i--) if (ticker[i].sim) ticker.splice(i, 1);
    renderDevices(); renderTicker(); renderSide();
  }

  CC.on("init", () => {
    build(); renderLegend(); renderTicker();
    setInterval(decayLoad, 300);
    setInterval(() => { if (CC.mode === "live") { renderDevices(); renderSide(); } }, 5000);
  });
  CC.on("event", onEvent);
  CC.on("snapshot", onSnapshot);
  CC.on("history", onHistory);
  CC.on("status", (st, prev) => {
    if (!prev || prev.state !== st.state) {
      renderDevices(); renderSide(); renderTicker();
      if (st.state === "starting") BLADES.forEach((b, i) => setTimeout(() => hitBlade(b.id, "k-page"), 260 * i));
    }
  });
  CC.on("mode", m => { if (m === "live") { renderDevices(); renderSide(); } });

  return { onEvent, removeSimDevices, describe };
})();
