// AppShare Assistant — the person's own agent, as a full-screen companion (not a feature tucked in a list).
// Opened from the orb in the top bar, the "Ask AppShare" bar on Home, or a suggestion. It looks things up and PREPARES
// actions as cards; nothing happens until the person presses Confirm (the server checks everything again then).
"use strict";

/** The Assistant's mark: one orb, used everywhere it appears, so it is recognisable at a glance. */
function orb(size = 28, live = false) {
  return `<span class="orb ${live ? "live" : ""}" style="--o:${size}px" aria-hidden="true"><i></i></span>`;
}

const Assistant = (() => {
  let root = null, session = null, busy = false, thinkTimer = null;
  try { session = +sessionStorage.getItem("appshare.asst") || null; } catch { /* private mode */ }
  const THINKING = ["Looking at your apps…", "Checking the details…", "Working it out…", "Getting a card ready…"];
  const STARTERS = [
    { icon: "inbox", t: "Catch me up", s: "What's due, what's waiting", q: "What do I need to do?" },
    { icon: "send", t: "Answer an app for me", s: "You check every answer first", fill: "Answer " },
    { icon: "sparkle", t: "Build an app", s: "Describe it — the team builds it", fill: "Build an app for " },
    { icon: "clock", t: "Automate a reminder", s: "Runs on a schedule, no AI", fill: "Every Monday at 9am, remind people who haven't answered " },
  ];

  function build() {
    root = document.createElement("div");
    root.className = "asst hidden";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "Assistant");
    const first = (ME?.name || "").replace(/^(Prof\.|Dr\.|Ms\.|Mr\.)\s*/, "").split(" ")[0];
    root.innerHTML = `
      <header class="asst-top">
        <button class="icon-btn" data-x aria-label="Close">${ic("back")}</button>
        <div class="asst-id">${orb(30)}<div><b>Assistant</b><span>Acts only when you confirm</span></div></div>
        <button class="icon-btn" data-auto aria-label="Your automations" title="Your automations">${ic("clock")}</button>
      </header>
      <div class="asst-body" id="asstBody">
        <div class="asst-hello" id="asstHello">
          ${orb(64, true)}
          <h1>${first ? `Hi ${esc(first)}, how can I help?` : "How can I help?"}</h1>
          <p>I can build and share apps, answer them for you, run your apps and set up reminders. I prepare everything — you check it and press Confirm.</p>
          <div class="asst-starters">${STARTERS.map((x, i) => `<button data-st="${i}"><span class="st-ic">${ic(x.icon)}</span><b>${esc(x.t)}</b><span>${esc(x.s)}</span></button>`).join("")}</div>
        </div>
        <div class="asst-convo" id="asstConvo"></div>
      </div>
      <form class="asst-ask" id="asstForm">
        <div class="asst-field"><textarea id="asstIn" rows="1" placeholder="Ask AppShare…" aria-label="Message the Assistant"></textarea>
          <button class="asst-send" id="asstGo" aria-label="Send" disabled>${ic("send")}</button></div>
        <p class="asst-fine">Nothing is sent or changed until you press Confirm on a card.</p>
      </form>`;
    document.body.appendChild(root);
    const input = root.querySelector("#asstIn"), go = root.querySelector("#asstGo");
    const grow = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; go.disabled = !input.value.trim() || busy; };
    input.addEventListener("input", grow);
    input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); } });
    root.querySelector("#asstForm").onsubmit = e => { e.preventDefault(); send(input.value); };
    root.querySelector("[data-x]").onclick = () => history.state?.asst ? history.back() : close();
    root.querySelector("[data-auto]").onclick = automations;
    root.querySelectorAll("[data-st]").forEach(b => b.onclick = () => {
      const s = STARTERS[+b.dataset.st];
      if (s.q) send(s.q); else { input.value = s.fill; grow(); input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
    });
    root.addEventListener("keydown", e => { if (e.key === "Escape") root.querySelector("[data-x]").click(); });
    window.addEventListener("popstate", () => { if (!root.classList.contains("hidden") && !history.state?.asst) close(); });
  }

  const convo = () => root.querySelector("#asstConvo");
  function add(html) {
    root.querySelector("#asstHello").classList.add("gone");
    convo().insertAdjacentHTML("beforeend", html);
    const el = convo().lastElementChild;
    requestAnimationFrame(() => el.scrollIntoView({ block: "end", behavior: "smooth" }));
    return el;
  }
  const said = t => esc(t).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");

  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    const input = root.querySelector("#asstIn");
    busy = true; input.value = ""; input.style.height = "auto"; root.querySelector("#asstGo").disabled = true;
    add(`<div class="msg me"><div class="bub">${esc(text)}</div></div>`);
    const think = add(`<div class="msg ai"><span class="av">${orb(26, true)}</span><div class="bub thinking"><span class="dots"><i></i><i></i><i></i></span><span class="tl">${THINKING[0]}</span></div></div>`);
    let n = 0; clearInterval(thinkTimer);
    thinkTimer = setInterval(() => { const tl = think.querySelector(".tl"); if (tl) tl.textContent = THINKING[++n % THINKING.length]; }, 1800);
    try {
      const r = await api("/api/agent/assistant", { json: { message: text, session_id: session } });
      session = r.session_id;
      try { sessionStorage.setItem("appshare.asst", session); } catch { /* private mode */ }
      think.remove();
      add(r.error ? `<div class="msg ai"><span class="av">${orb(26)}</span><div class="bub err">${esc(r.error)}</div></div>`
                  : `<div class="msg ai"><span class="av">${orb(26)}</span><div class="bub">${said(r.reply || "")}</div></div>`);
      (r.cards || []).forEach(card);
    } catch (e) {
      think.remove();
      add(`<div class="msg ai"><span class="av">${orb(26)}</span><div class="bub err">${esc(e.message)}</div></div>`);
    }
    clearInterval(thinkTimer);
    busy = false; input.focus();
  }

  const CARD_ICON = { build: "sparkle", share: "users", submit: "send", status: "check", remind: "bell", deadline: "calendar", app_status: "lock", edit: "pencil", automation: "clock", automation_off: "clock" };
  function card(c) {
    const el = add(`<div class="acard"><div class="acard-h"><span class="ach-ic">${ic(CARD_ICON[c.kind] || "sparkle")}</span>
        <div><span class="ach-k">Ready for you to check</span><b>${esc(c.title)}</b></div></div>
        <dl>${c.rows.map(x => `<div><dt>${esc(x.label)}</dt><dd>${esc(x.value)}${x.tag ? `<span class="tag">${esc(x.tag)}</span>` : ""}</dd></div>`).join("")}</dl>
        ${c.note ? `<p class="acard-note">${ic("info")}${esc(c.note)}</p>` : ""}${c.cost ? `<p class="acard-note">${ic("sparkle")}Uses the AI once more: ${esc(c.cost)}.</p>` : ""}
        ${c.reason ? `<details class="acard-why"><summary>Why the Assistant chose this</summary><p>${esc(c.reason)}</p></details>` : ""}
        <div class="acard-acts"><button class="btn" data-no>Cancel</button><button class="btn primary" data-yes>${ic("check")}${esc(c.confirm_label || "Confirm")}</button></div></div>`);
    const settle = html => { el.querySelector(".acard-acts").outerHTML = `<div class="acard-done">${html}</div>`; };
    el.querySelector("[data-yes]").onclick = async e => {
      const b = e.currentTarget; b.disabled = true; b.innerHTML = `<span class="conn-spin"></span> Working…`;
      try {
        const r = await api("/api/assistant/confirm", { json: { id: c.id, accept: true } });
        el.classList.add("ok");
        const open = r.open || (r.slug || c.slug ? "/a/" + (r.slug || c.slug) : null);
        settle(`${ic("check")}<span>${esc(r.done || "Done.")}</span>${open ? `<a class="btn sm" href="${esc(open)}">Open</a>` : ""}`);
        window.dispatchEvent(new Event("appshare:changed"));
      } catch (err) { el.classList.add("bad"); settle(`${ic("x")}<span>${esc(err.message)}</span>`); }
    };
    el.querySelector("[data-no]").onclick = async () => {
      try { await api("/api/assistant/confirm", { json: { id: c.id, accept: false } }); } catch { /* already gone */ }
      el.classList.add("off");
      settle(`<span>Cancelled — nothing happened.</span>`);
    };
  }

  async function automations() {
    const sh = sheet(`<div class="sheet-head"><h2>Automations</h2><button class="icon-btn" data-close aria-label="Close">${ic("x")}</button></div>
      <p class="muted small" style="margin-bottom:12px">Set up by asking the Assistant. They run without AI, stop when the app closes, and you can switch them off here.</p>
      <div id="auList" class="stack"><p class="muted">Loading…</p></div>`);
    const box = sh.el.querySelector("#auList");
    async function draw() {
      const { automations: L } = await api("/api/automations");
      box.innerHTML = L.length ? L.map(x => `<div class="au-row ${x.enabled ? "" : "off"}"><div class="grow"><b>${esc(x.what)}</b>
          <span class="muted small">${x.runs} run${x.runs === 1 ? "" : "s"}${x.last_run ? ` · last ${esc(timeAgo(x.last_run))}` : ""}${x.last_result ? ` · ${esc(x.last_result)}` : ""}</span></div>
          <label class="switch" title="On / off"><input type="checkbox" data-au="${x.id}" ${x.enabled ? "checked" : ""}><i></i></label>
          <button class="icon-btn" data-del="${x.id}" aria-label="Delete">${ic("trash")}</button></div>`).join("")
        : `<div class="card empty-state"><div class="ei">${ic("clock")}</div><b>No automations yet</b><p>Try: “Every Monday at 9, remind people who haven't answered my feedback form.”</p></div>`;
      box.querySelectorAll("[data-au]").forEach(i => i.onchange = async () => { await api(`/api/automations/${i.dataset.au}`, { json: { enabled: i.checked } }); draw(); });
      box.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { await api(`/api/automations/${b.dataset.del}`, { method: "DELETE" }); draw(); });
    }
    draw();
  }

  function open({ ask = null, fill = null } = {}) {
    if (!root) build();
    if (root.classList.contains("hidden")) {
      root.classList.remove("hidden");
      document.body.classList.add("asst-open");
      history.pushState({ asst: true }, "", location.pathname + location.search + "#assistant");
    }
    const input = root.querySelector("#asstIn");
    if (ask) send(ask);
    else {
      if (fill) { input.value = fill; input.dispatchEvent(new Event("input")); }
      setTimeout(() => input.focus(), 250);
    }
  }
  function close() {
    if (!root) return;
    root.classList.add("hidden");
    document.body.classList.remove("asst-open");
    if (location.hash === "#assistant") history.replaceState(null, "", location.pathname + location.search);
  }
  return { open, close, isOpen: () => !!root && !root.classList.contains("hidden") };
})();
