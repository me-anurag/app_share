// AppShare play: the party light engine (shared by phones and the host screen) and the phone side of live quizzes.
// Phones never run a clock of their own for the lights: each one computes its colour from the server's clock, the
// host's scene and its seat number, so a room full of phones flashes together after a single small update.
"use strict";

const Light = (() => {
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const mod = (a, n) => ((a % n) + n) % n;
  const hash = (a, b) => { let x = Math.sin(a * 127.1 + b * 311.7) * 43758.5453; return x - Math.floor(x); };
  function hsl(h, s, l) {
    const k = n => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
    return [0, 8, 4].map(n => Math.round(255 * (l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1)))));
  }
  /** [r,g,b] for this phone at server time t. Strobe stays on for a quarter beat; bpm is capped at 180 by the server (≤ 3 flashes/s). */
  function colorAt(st, seat, t) {
    if (!st || st.on === false) return [0, 0, 0];
    const cols = (st.colors && st.colors.length ? st.colors : ["#ffffff"]).map(hex), n = cols.length;
    const beatMs = 60000 / Math.max(40, Math.min(180, st.bpm || 120));
    const dt = Math.max(0, t - (st.started_at || 0)), beat = Math.floor(dt / beatMs), frac = (dt % beatMs) / beatMs;
    const dim = (c, b) => c.map(v => Math.round(v * b));
    switch (st.scene) {
      case "solid": return cols[0];
      case "pulse": return dim(cols[mod(beat, n)], 0.2 + 0.8 * Math.pow(1 - frac, 2));
      case "chase": return cols[mod(beat + seat, n)];
      case "wave": {
        const phase = dt / (beatMs * 4) - seat * 0.12;
        return dim(cols[mod(Math.floor(phase), n)], 0.15 + 0.85 * (0.5 + 0.5 * Math.sin(phase * 2 * Math.PI)));
      }
      case "rainbow": return hsl(mod(dt / 8000 * 360 + seat * 25, 360), 0.95, 0.5);
      case "sparkle": return hash(beat, seat) < 0.35 ? cols[Math.floor(hash(seat, beat) * n)] : dim(cols[0], 0.06);
      case "strobe": return frac < 0.25 ? cols[mod(beat, n)] : [0, 0, 0];
    }
    return cols[0];
  }
  /** Run the light on an element until stop() is called. getState() returns {state, seat, offset}. */
  function run(el, get) {
    let on = true;
    const frame = () => {
      if (!on) return;
      const g = get();
      const c = colorAt(g.state, g.seat || 0, Date.now() + (g.offset || 0));
      el.style.backgroundColor = `rgb(${c[0]},${c[1]},${c[2]})`;
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
    return () => { on = false; };
  }
  return { colorAt, run };
})();

/** Fetch a live view and work out the difference between this device's clock and the server's. */
async function liveFetch(url) {
  const t0 = Date.now();
  const d = await api(url, { allow401: true });
  const t1 = Date.now();
  d.offset = d.server_now - (t0 + t1) / 2;
  return d;
}

const SHAPES = ["▲", "◆", "●", "■", "★", "✚"];

const Play = (() => {
  let D, root, L = null, offset = 0, tick = null, stopLight = null, wake = null;

  async function load() {
    try {
      L = await liveFetch(`/api/a/${D.slug}/live`); offset = L.offset;
      if (!userIsBusy()) draw();                         // never wipe a nickname being typed
    }
    catch (e) { root.innerHTML = `<div class="pl-wrap"><div class="pl-card"><b>Can't load the game</b><p>${esc(e.message)}</p></div></div>`; }
  }

  // ------------------------------------------------------------------ party lights (phone)
  function party() {
    const P = L.party;
    if (stopLight) return;                                   // already a light: the loop reads the newest state itself
    root.innerHTML = `<div class="pl-wrap pl-dark"><div class="pl-card pl-center">
        <div class="pl-kicker">${ic("sparkle")}Party lights</div>
        <h1>${esc(D.spec.title)}</h1>
        ${P.message ? `<p class="pl-msg">${esc(P.message)}</p>` : ""}
        <button class="pl-go" id="goLight">Turn my phone into a light</button>
        <p class="pl-note">Turn your screen brightness up and hold your phone up, screen facing out. ${L.present} phone${L.present === 1 ? "" : "s"} in the room.</p>
        <p class="pl-warn">${ic("eye")}This screen changes colour${(L.scenes || []).includes("strobe") ? " and can flash quickly" : ""}. If flashing lights affect you, don't join.</p>
      </div></div>`;
    document.getElementById("goLight").onclick = startLight;
  }
  async function startLight() {
    root.innerHTML = `<div class="pl-light" id="light"><div class="pl-hud" id="hud"><span>${esc(D.spec.title)}</span><button id="leave">Exit</button></div></div>`;
    const el = document.getElementById("light"), hud = document.getElementById("hud");
    try { await document.documentElement.requestFullscreen?.(); } catch { /* not allowed: still works */ }
    try { wake = await navigator.wakeLock?.request("screen"); } catch { /* the screen may dim on its own */ }
    stopLight = Light.run(el, () => ({ state: L.party, seat: L.me?.seat || 0, offset }));
    let t = setTimeout(() => hud.classList.add("hide"), 2500);
    el.onclick = e => { if (e.target.id === "leave") return; hud.classList.remove("hide"); clearTimeout(t); t = setTimeout(() => hud.classList.add("hide"), 2500); };
    document.getElementById("leave").onclick = () => {
      stopLight(); stopLight = null; wake?.release?.(); document.exitFullscreen?.().catch(() => {}); party();
    };
  }

  // ------------------------------------------------------------------ live quiz (phone)
  function quiz() {
    const me = L.me || {};
    const head = `<div class="pl-top"><b>${esc(D.spec.title)}</b>${me.joined ? `<span>${esc(me.name)} · ${me.points || 0} pts</span>` : ""}</div>`;
    let body = "";
    if (!me.joined) {
      body = `<div class="pl-card pl-center"><div class="pl-kicker">${ic("star")}Live quiz</div><h1>${esc(D.spec.title)}</h1>
          <form id="joinF" class="pl-join"><input class="input" id="nick" maxlength="24" placeholder="Your nickname" autocomplete="nickname" required>
          <button class="pl-go">Join</button></form><p class="pl-note">${L.present} player${L.present === 1 ? "" : "s"} here. Fast right answers score more.</p></div>`;
    } else if (L.phase === "lobby") {
      body = `<div class="pl-card pl-center"><div class="pl-big">${ic("check")}</div><h2>You're in, ${esc(me.name)}!</h2>
          <p class="pl-note">Watch the big screen — the host starts soon.</p>${L.players?.length ? `<div class="pl-names">${L.players.map(n => `<span>${esc(n)}</span>`).join("")}</div>` : ""}</div>`;
    } else if (L.phase === "question") {
      const q = L.question, mine = L.mine;
      const left = Math.max(0, L.ends_at - (Date.now() + offset));
      body = `<div class="pl-q"><div class="pl-qn">Question ${L.q + 1} of ${L.total}${q.points > 1 ? ` · ${q.points}× points` : ""}</div>
          <h2>${esc(q.label)}</h2><div class="pl-timer"><i id="tbar" style="width:${left / (L.seconds * 10)}%"></i></div>
          ${mine ? `<div class="pl-card pl-center"><div class="pl-big">${ic("clock")}</div><h3>Locked in: ${esc([].concat(mine.answer).join(", "))}</h3><p class="pl-note">Wait for the reveal…</p></div>`
            : left <= 0 ? `<div class="pl-card pl-center"><h3>Time's up</h3></div>`
            : `<div class="pl-opts n${q.options.length}">${q.options.map((o, i) => `<button class="pl-opt c${i % 6}" data-o="${esc(o)}"><span class="sh">${SHAPES[i % 6]}</span><span>${esc(o)}</span></button>`).join("")}</div>`}</div>`;
    } else if (L.phase === "reveal" || L.phase === "board") {
      const mine = L.mine, right = mine && mine.points > 0;
      body = `<div class="pl-card pl-center ${mine ? (right ? "ok" : "bad") : ""}"><div class="pl-big">${ic(right ? "check" : "x")}</div>
          <h2>${mine ? (right ? `Right! +${mine.points}` : "Not this time") : "No answer"}</h2>
          <p class="pl-note">The answer: <b>${esc([].concat(L.answer).join(", "))}</b></p>
          ${me.rank ? `<p class="pl-rank">You're <b>#${me.rank}</b> with ${me.points} points</p>` : `<p class="pl-note">${me.points || 0} points so far</p>`}</div>`;
    } else if (L.phase === "end") {
      const top = (L.leaderboard || []).slice(0, 3);
      body = `<div class="pl-card pl-center"><div class="pl-kicker">${ic("star")}Final scores</div>
          <div class="pl-podium">${top.map((p, i) => `<div class="p${i + 1}"><b>${esc(p.name)}</b><span>${p.points}</span><i>${i + 1}</i></div>`).join("")}</div>
          ${me.rank ? `<p class="pl-rank">You finished <b>#${me.rank}</b> with ${me.points} points</p>` : ""}</div>`;
    }
    root.innerHTML = `<div class="pl-wrap">${head}${body}</div>`;
    const jf = document.getElementById("joinF");
    if (jf) jf.onsubmit = async e => {
      e.preventDefault();
      try { await api(`/api/a/${D.slug}/live/join`, { json: { name: document.getElementById("nick").value }, allow401: true }); document.activeElement?.blur(); load(); }
      catch (err) { toast(err.message); }
    };
    root.querySelectorAll("[data-o]").forEach(b => b.onclick = async () => {
      root.querySelectorAll("[data-o]").forEach(x => { x.disabled = true; x.classList.toggle("dim", x !== b); });
      try { await api(`/api/a/${D.slug}/live/answer`, { json: { q: L.q, answer: b.dataset.o }, allow401: true }); navigator.vibrate?.(30); }
      catch (err) { toast(err.message); }
      load();
    });
    clearInterval(tick);
    if (L.phase === "question" && !L.mine) {
      tick = setInterval(() => {
        const left = Math.max(0, L.ends_at - (Date.now() + offset)), bar = document.getElementById("tbar");
        if (bar) bar.style.width = left / (L.seconds * 10) + "%";
        if (left <= 0) { clearInterval(tick); draw(); }
      }, 200);
    }
  }

  function draw() { if (D.spec.kind === "party") party(); else quiz(); }

  function start(data, el) {
    D = data; root = el;
    document.body.className = "pl-body";
    document.querySelector('meta[name="theme-color"]').content = "#111015";
    root.className = "pl-root";
    load();
    Live.on(load);                                       // the host moved the game on, or changed the lights
    setInterval(() => { if (!document.hidden) load(); }, D.spec.kind === "party" ? 15000 : 4000);   // safety net
  }
  return { start };
})();
