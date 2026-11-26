// AppShare phone app — shared helpers: API, icons, dates, top bar, sheets, sharing, agent progress, reconnect.
"use strict";

// ---------------------------------------------------------------- version (shown in the profile sheet and on sign-in)
// One number for the whole phone app. sw.js uses "appshare-" + this; tests/test_live.py fails if they ever differ.
// Bump it whenever anything in frontend/ changes, so phones pick the change up and people can see they have it.
const APP_VERSION = "v16";
const APP_UPDATED = "26 Nov 2026";
/** The first time a phone opens a new version, say so — then it's obvious an update really arrived. */
window.addEventListener("load", () => {
  try {
    const seen = localStorage.getItem("appshare.version");
    if (seen && seen !== APP_VERSION) setTimeout(() => toast(`AppShare updated to ${APP_VERSION}`), 700);
    localStorage.setItem("appshare.version", APP_VERSION);
  } catch { /* private mode: nothing to compare with */ }
});
function versionLine() {
  return `<div class="app-version">AppShare ${APP_VERSION} · updated ${APP_UPDATED}${isStandalone() ? " · installed app" : ""}</div>`;
}

// ---------------------------------------------------------------- PWA: install + offline
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
let installPrompt = null;
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); installPrompt = e; });

// ---------------------------------------------------------------- icons (24px grid, 1.8 stroke)
const ICONS = {
  home: '<path d="M4 10.5 12 4l8 6.5V20h-5.5v-5.5h-5V20H4z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  inbox: '<path d="M4 13l2.4-7h11.2L20 13v6H4z"/><path d="M4 13h4.5a3.5 3.5 0 0 0 7 0H20"/>',
  bell: '<path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2.5h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  chart: '<path d="M4 20V4M4 20h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
  pencil: '<path d="M4 20l1.2-4.4L16 4.8l3.2 3.2L8.4 18.8z"/><path d="M14 6.8l3.2 3.2"/>',
  message: '<path d="M4 5h16v11H9.5L5 19.5V16H4z"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  send: '<path d="M4 12l16-8-6 16-2.5-6.5z"/>',
  users: '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M15.5 5.3a3 3 0 0 1 0 5.6M17.5 19a5 5 0 0 0-2.6-4.4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  eye: '<path d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>',
  eyeoff: '<path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c6 0 9.5 6 9.5 6a17 17 0 0 1-3 3.6M6.6 7.6A16 16 0 0 0 2.5 12S6 18 12 18a9 9 0 0 0 4-.9"/><path d="M9.9 10a2.8 2.8 0 0 0 4 4"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  chev: '<path d="M9 5l7 7-7 7"/>',
  clip: '<path d="M20 11.5l-8.2 8.2a5 5 0 0 1-7.1-7.1l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7l-8.4 8.4a1.7 1.7 0 0 1-2.4-2.4l7.7-7.7"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v4h16v-4"/>',
  lock: '<rect x="5" y="11" width="14" height="9.5" rx="1.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.4 5.3 3.4 8.5s-1 6.1-3.4 8.5c-2.4-2.4-3.4-5.3-3.4-8.5s1-6.1 3.4-8.5"/>',
  building: '<path d="M4 20V6l8-3 8 3v14"/><path d="M9 20v-4h6v4M8 9h.01M12 9h.01M16 9h.01M8 13h.01M12 13h.01M16 13h.01"/>',
  ticket: '<path d="M4 7h16v3a2 2 0 0 0 0 4v3H4v-3a2 2 0 0 0 0-4z"/><path d="M14 7v10"/>',
  calendar: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',
  spark: '<path d="M12 3v5M12 16v5M3 12h5M16 12h5"/>',
  wrench: '<path d="M15 4a5 5 0 0 0-4.6 6.9L4 17.3V20h2.7l6.4-6.4A5 5 0 0 0 20 9l-3 1-2-2 1-3z"/>',
  dots: '<circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/>',
  trash: '<path d="M5 7h14M10 7V4.5h4V7M7 7l1 13h8l1-13"/>',
  copy: '<rect x="8" y="8" width="11" height="11" rx="1.5"/><path d="M5 15V6a1 1 0 0 1 1-1h9"/>',
  star: '<path d="M12 4l2.4 5 5.4.7-4 3.8 1 5.4L12 16.3 7.2 19l1-5.4-4-3.8 5.4-.7z"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
};
function ic(name, cls = "") { return `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`; }
function hydrateIcons(root = document) { root.querySelectorAll("[data-ic]").forEach(el => { if (!el.dataset.done) { el.insertAdjacentHTML("afterbegin", ic(el.dataset.ic)); el.dataset.done = 1; } }); }

const MARK = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="5" width="14" height="3.4" fill="#fff"/><rect x="5" y="10.3" width="9" height="3.4" fill="#fff"/><rect x="15.6" y="10.3" width="3.4" height="3.4" fill="#fff" opacity=".55"/><rect x="5" y="15.6" width="14" height="3.4" fill="#fff"/></svg>`;

const KIND = {
  assignment: { icon: "upload", label: "Submission" }, survey: { icon: "message", label: "Survey" }, feedback: { icon: "star", label: "Feedback" },
  poll: { icon: "chart", label: "Poll" }, registration: { icon: "users", label: "Registration" }, booking: { icon: "calendar", label: "Booking" },
  request: { icon: "ticket", label: "Request" }, rsvp: { icon: "users", label: "RSVP" }, quiz: { icon: "list", label: "Quiz" },
  "sign-up": { icon: "pencil", label: "Sign-up" }, form: { icon: "file", label: "Form" },
};
const kindOf = k => KIND[k] || KIND.form;
const MODE_LABEL = { university: "University", office: "Office", general: "Personal" };

// ---------------------------------------------------------------- API
async function api(path, opts = {}) {
  const init = { credentials: "same-origin", ...opts };
  if (opts.json !== undefined) {
    init.method = init.method || "POST";
    init.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    init.body = JSON.stringify(opts.json);
  }
  let res;
  try { res = await fetch(path, init); }
  catch { Connection.check(); throw new Error("Can't reach the server right now. It will reconnect automatically — try again in a moment."); }
  if (res.status === 401 && !opts.allow401) {
    location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
    throw new Error("Not signed in");
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const d = data && data.detail;
    const err = new Error(d && d.errors ? d.errors.join("\n") : (typeof d === "string" ? d : "Something went wrong"));
    err.status = res.status; err.errors = d && d.errors;
    throw err;
  }
  return data;
}

// ---------------------------------------------------------------- formatting
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function initials(name) { return (name || "?").replace(/^(Prof\.|Dr\.|Ms\.|Mr\.|Mrs\.)\s*/, "").split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join(""); }
function toDate(s) { return new Date(String(s).replace(" ", "T")); }
function fmtDate(s, withTime = true) {
  if (!s) return "";
  const d = toDate(s);
  return d.toLocaleString(undefined, withTime ? { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" } : { day: "numeric", month: "short", year: "numeric" });
}
function timeAgo(s) {
  const m = Math.round((Date.now() - toDate(s)) / 60000);
  if (m < 1) return "just now"; if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60); if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24); return d === 1 ? "yesterday" : `${d} days ago`;
}
/** "Closes in 2 days" / "Closes today at 5 pm" / "Closed" — plus whether it is soon. */
function deadline(s) {
  if (!s) return { text: "No deadline", soon: false };
  const d = toDate(s), ms = d - Date.now();
  if (ms <= 0) return { text: "Closed " + fmtDate(s, false), soon: false, closed: true };
  const h = ms / 3600000;
  const at = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (h < 1) return { text: `Closes in ${Math.max(1, Math.round(ms / 60000))} min`, soon: true };
  if (d.toDateString() === new Date().toDateString()) return { text: `Closes today, ${at}`, soon: true };
  if (h < 48 && new Date(Date.now() + 86400000).toDateString() === d.toDateString()) return { text: `Closes tomorrow, ${at}`, soon: true };
  const days = Math.round(h / 24);
  return { text: days < 7 ? `Closes in ${days} days` : `Closes ${fmtDate(s, false)}`, soon: false };
}
function greeting() { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; }

function appTag(a) {
  if (a.status === "draft") return `<span class="tag warn">Draft</span>`;
  if (a.status === "closed" || a.window === "closed") return `<span class="tag">Closed</span>`;
  if (a.window === "not_open") return `<span class="tag">Opens later</span>`;
  return `<span class="tag ok">Open</span>`;
}
function statusTag(status, statuses) {
  if (!status) return "";
  const i = (statuses || []).indexOf(status), last = statuses && i === statuses.length - 1;
  const bad = /reject|declin|cancel/i.test(status), good = /approv|resolv|paid|done|complete|accept/i.test(status);
  return `<span class="tag ${bad ? "bad" : good || last ? "ok" : i === 0 ? "warn" : "brand"}">${esc(status)}</span>`;
}

/** Quiet status words (a coloured dot + word) for list rows. */
function appWord(a) {
  if (a.status === "draft") return `<span class="sw warn">Draft</span>`;
  if (a.status === "closed" || a.window === "closed") return `<span class="sw">Closed</span>`;
  if (a.window === "not_open") return `<span class="sw">Opens later</span>`;
  return `<span class="sw ok">Open</span>`;
}
function statusWord(status, statuses) {
  if (!status) return "";
  const i = (statuses || []).indexOf(status), last = statuses && i === statuses.length - 1;
  const bad = /reject|declin|cancel/i.test(status), good = /approv|resolv|paid|done|complete|accept/i.test(status);
  return `<span class="sw ${bad ? "bad" : good || last ? "ok" : i === 0 ? "warn" : "brand"}">${esc(status)}</span>`;
}
const tileHtml = (kind, color, soft = false) => `<span class="ti ${soft ? "soft" : ""}" style="--tc:${esc(color || "#c4471a")}">${ic(kindOf(kind).icon)}</span>`;
function todayLine() { return new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" }); }

// ---------------------------------------------------------------- small UI pieces
function toast(msg) {
  document.querySelector(".toast")?.remove();
  const t = document.createElement("div");
  t.className = "toast"; t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = 0; }, 2600);
  setTimeout(() => t.remove(), 3000);
}

/** A bottom sheet (dialog on wide screens). Returns {el, close}. */
function sheet(html, { onClose } = {}) {
  const bg = document.createElement("div");
  bg.className = "sheet-bg";
  bg.innerHTML = `<div class="sheet" role="dialog" aria-modal="true"><div class="grab"></div>${html}</div>`;
  document.body.appendChild(bg);
  document.body.style.overflow = "hidden";
  const close = () => { bg.remove(); document.body.style.overflow = ""; onClose && onClose(); document.removeEventListener("keydown", esc_); };
  const esc_ = e => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", esc_);
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-close]")) close(); });
  hydrateIcons(bg);
  return { el: bg.querySelector(".sheet"), close };
}

/** The address other people can open: the server's public address (HTTPS tunnel or Wi-Fi), never 127.0.0.1. */
function shareUrl(slug) { return ((ME && ME.share_base) || location.origin) + "/a/" + slug; }

/** Copy text everywhere — including plain-http Wi-Fi addresses, where the modern clipboard API doesn't exist. */
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fall through */ }
  const ta = document.createElement("textarea");
  ta.value = text; ta.setAttribute("readonly", "");
  ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;pointer-events:none";
  document.body.appendChild(ta);
  ta.select(); ta.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  ta.remove();
  return ok;
}
async function copyLink(link) {
  if (await copyText(link)) toast("Link copied");
  else linkSheet("", link);                 // last resort: show it, selected, to copy by hand
}

/** Send: the phone's own share menu when it has one; otherwise our sheet with WhatsApp, SMS, email and a QR code. */
async function sendLink(title, link) {
  if (navigator.share && window.isSecureContext) {
    try { await navigator.share({ title, text: title, url: link }); return; } catch (e) { if (e && e.name === "AbortError") return; }
  }
  linkSheet(title, link);
}
function linkSheet(title, link) {
  const msg = title ? `${title}\n${link}` : link;
  const s = sheet(`
    <div class="sheet-head"><h2>${title ? "Send “" + esc(title) + "”" : "The link"}</h2><button class="icon-btn" data-close aria-label="Close">${ic("x")}</button></div>
    <input class="input link-input" id="lsLink" readonly value="${esc(link)}" aria-label="Link">
    <div class="send-grid">
      <button class="send-opt" id="lsCopy">${ic("copy")}<span>Copy</span></button>
      <a class="send-opt" href="https://wa.me/?text=${encodeURIComponent(msg)}" target="_blank" rel="noopener">${ic("message")}<span>WhatsApp</span></a>
      <a class="send-opt" href="sms:?&body=${encodeURIComponent(msg)}">${ic("send")}<span>SMS</span></a>
      <a class="send-opt" href="mailto:?subject=${encodeURIComponent(title || "A link for you")}&body=${encodeURIComponent(msg)}">${ic("file")}<span>Email</span></a>
    </div>
    <div class="qr-box"><img src="/api/qr?data=${encodeURIComponent(link)}" alt="QR code for the link"><p class="muted small">Or scan this with another phone's camera — handy on a projector or noticeboard.</p></div>
    ${!link.startsWith("https://") ? `<p class="muted tiny" style="margin-top:10px">This link works for phones on the same Wi-Fi or hotspot. For anyone, anywhere: turn on the internet address in the Control Center.</p>` : ""}`);
  const inp = s.el.querySelector("#lsLink");
  inp.onfocus = () => inp.select();
  s.el.querySelector("#lsCopy").onclick = async () => {
    if (await copyText(link)) { toast("Link copied"); s.close(); }
    else { inp.focus(); inp.select(); toast("Long-press the link above to copy it"); }
  };
}

// ---------------------------------------------------------------- the signed-in person + top bar
let ME = null;
async function loadMe() { if (!ME) ME = await api("/api/me"); return ME; }

async function renderTopbar({ back = null, title = null } = {}) {
  const me = await loadMe();
  const bar = document.createElement("header");
  bar.className = "topbar";
  bar.innerHTML = `<div class="inner">
    ${back ? `<button class="back" id="tbBack">${ic("back")}${esc(back.label || "Back")}</button><span class="grow"></span>`
      : `<span class="mark">${MARK}</span><div class="ws"><b>${esc(title || me.org)}</b></div>`}
    ${back ? `<a class="icon-btn" href="/?tab=inbox" aria-label="Inbox">${ic("bell")}<span class="dot-n hidden" id="tbBellN"></span></a>` : ""}
    <button class="avatar" id="tbMe" aria-label="Your profile">${esc(initials(me.name))}</button></div>`;
  document.body.prepend(bar);
  if (back) bar.querySelector("#tbBack").onclick = () => (history.length > 1 && document.referrer.startsWith(location.origin) ? history.back() : location.href = back.href || "/");
  bar.querySelector("#tbMe").onclick = profileSheet;
  window.addEventListener("scroll", () => bar.classList.toggle("scrolled", scrollY > 4), { passive: true });
  Live.now();
  window.addEventListener("appshare:reconnected", () => Live.now());
  return me;
}
function setUnread(n) {
  const b = document.getElementById("tbBellN");
  if (b) { b.textContent = n > 9 ? "9+" : n; b.classList.toggle("hidden", !n); }
  document.querySelectorAll("[data-inbox-n]").forEach(el => { el.textContent = n > 9 ? "9+" : n; el.classList.toggle("hidden", !n); });
}
function refreshBell() { return Live.now(); }

/** Live updates. The server PUSHES a message the moment anything changes (a response, a status, a notification),
 *  so every open screen refreshes itself within a fraction of a second. If the push stream can't be held open
 *  (some networks), the screen checks every few seconds instead. Updates that arrive while the person is typing or
 *  has a sheet open are applied as soon as they finish — never lost. Pages subscribe with Live.on(fn). */
const Live = (() => {
  let version = null, timer = null, busy = false, es = null, lastPush = 0, pending = false;
  const subs = [];
  const pushing = () => es && Date.now() - lastPush < 35000;
  function fire() {
    if (userIsBusy()) { pending = true; return; }
    pending = false;
    subs.forEach(fn => { try { fn(); } catch (e) { console.error(e); } });
  }
  function apply(d) {
    if (d.unread !== undefined && d.unread !== null) setUnread(d.unread);
    if (version !== null && d.v !== version) fire();
    version = d.v;
  }
  function connect() {
    if (es || !("EventSource" in window)) return;
    try { es = new EventSource("/api/live/stream"); } catch { es = null; return; }
    es.onmessage = m => { lastPush = Date.now(); try { apply(JSON.parse(m.data)); } catch { /* ignore */ } };
    es.onerror = () => { if (es) es.close(); es = null; setTimeout(connect, 5000); };   // fall back to checking meanwhile
  }
  async function tick() {
    clearTimeout(timer);
    if (busy) return;
    if (document.hidden) { timer = setTimeout(tick, 15000); return; }
    if (pushing()) { timer = setTimeout(tick, 20000); return; }      // the push stream is alive: no need to check
    busy = true;
    try {
      const res = await fetch("/api/live", { cache: "no-store", credentials: "same-origin" });
      apply(await res.json());
    } catch { /* offline: the connection watcher handles it */ }
    busy = false;
    timer = setTimeout(tick, 3000);
  }
  setInterval(() => { if (pending && !userIsBusy()) fire(); }, 800);     // apply a held-back update once they're done
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { connect(); tick(); } });
  window.addEventListener("load", () => { connect(); setTimeout(tick, 600); });
  return { on(fn) { subs.push(fn); }, now: tick };
})();

/** True while the person is typing or a sheet is open — live refreshes must not wipe what they're doing. */
function userIsBusy(root = document) {
  const a = document.activeElement;
  return !!document.querySelector(".sheet-bg") || (a && root.contains(a) && a.matches("input, textarea, select"));
}

// ---------------------------------------------------------------- install help + "open in the app"
const isStandalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
/** Why this phone can't install right now — and the exact fix for its browser. */
async function installHelp() {
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua);
  const inApp = /; wv\)|FBAN|FBAV|Instagram|WhatsApp|Line\/|MicroMessenger|GSA\/|Snapchat|LinkedInApp/.test(ua);
  const samsung = /SamsungBrowser/.test(ua), otherIOS = ios && /CriOS|FxiOS|EdgiOS/.test(ua);
  let base = ME && ME.share_base;
  if (!base) { try { base = (await api("/api/workspace", { allow401: true })).share_base; } catch { /* offline */ } }
  const here = location.pathname + location.search;
  const secureBtn = base && base.startsWith("https://") && !location.href.startsWith(base)
    ? `<a class="btn primary block" style="margin-top:14px" href="${esc(base + here)}">${ic("globe")}Open the secure address</a>` : "";
  let why, steps;
  if (inApp) {
    why = "This page is open inside another app's mini-browser (a QR scanner, WhatsApp, Instagram…). Those can't install apps.";
    steps = `<ol class="steps-list"><li>Tap the <b>⋮</b> (or <b>…</b>) menu at the top of this screen.</li><li>Choose <b>Open in Chrome</b> (or <b>Open in browser</b>).</li><li>In Chrome, tap <b>Install</b> at the bottom of the page.</li></ol>`;
  } else if (!window.isSecureContext) {
    why = "Phones only install apps from a secure <b>https</b> address. This page is open on a plain Wi-Fi address.";
    steps = secureBtn ? `${secureBtn}<p class="muted small" style="margin-top:8px">Then tap <b>Install</b> there. If you see “You are about to visit…”, tap <b>Visit Site</b> first.</p>`
      : `<p class="muted" style="margin-top:10px">Ask whoever runs AppShare to turn on <b>Internet address (HTTPS)</b> in the Control Center (Connect phones), then open the new https link.</p>`;
  } else if (otherIOS) {
    why = "On iPhone only Safari can add apps to the home screen.";
    steps = `<ol class="steps-list"><li>Copy this page's address and open it in <b>Safari</b>.</li><li>Tap <b>Share</b> (square with an arrow) → <b>Add to Home Screen</b> → <b>Add</b>.</li></ol>`;
  } else if (ios) {
    why = "iPhones install apps from Safari's Share menu (there's no Install button).";
    steps = `<ol class="steps-list"><li>Tap <b>Share</b> (the square with an arrow) at the bottom.</li><li>Scroll and tap <b>Add to Home Screen</b>, then <b>Add</b>.</li></ol>`;
  } else if (samsung) {
    why = "In Samsung Internet the option is in the menu.";
    steps = `<ol class="steps-list"><li>Tap the <b>≡</b> menu at the bottom.</li><li>Tap <b>Add page to</b> → <b>Home screen</b>.</li></ol>`;
  } else if (/Android/.test(ua)) {
    // Opened by the camera / Google Lens / a scanner, Android shows the page in a quick-view window (a "Custom Tab"):
    // it looks like Chrome but its menu has no Install or Add to Home screen. Open it in the real Chrome app instead.
    why = "This page is open in a quick-view window (that's what happens when the camera or a QR scanner opens a link). Quick views can't install apps — the full Chrome app can.";
    steps = `<a class="btn primary block" style="margin-top:14px" href="${esc(chromeIntent(location.href))}">${ic("globe")}Open in Chrome</a>
      <ol class="steps-list" style="margin-top:12px"><li>Chrome opens this same page.</li><li>Tap <b>Install</b> on the bar at the bottom — or Chrome's <b>⋮</b> → <b>Install app</b> / <b>Add to Home screen</b>.</li></ol>
      <p class="muted small" style="margin-top:10px">Already installed? Open <b>AppShare</b> from your home screen or app drawer.</p>`;
  } else {
    why = "Your browser hasn't offered to install yet. Either it's already installed, or it needs the page opened once more.";
    steps = `<ol class="steps-list"><li>Open the browser's menu.</li><li>Choose <b>Install app</b> or <b>Add to Home screen</b>.</li><li>Already installed? Open <b>AppShare</b> from your home screen or app drawer.</li></ol>`;
  }
  sheet(`<div class="sheet-head"><h2>Install AppShare</h2><button class="icon-btn" data-close aria-label="Close">${ic("x")}</button></div>
    <p>${why}</p>${steps}`);
}
/** An Android link that opens this page in the full Chrome app (not a quick view or another app's browser). */
function chromeIntent(href) {
  const u = new URL(href);
  return `intent://${u.host}${u.pathname}${u.search}#Intent;scheme=${u.protocol.replace(":", "")};package=com.android.chrome;S.browser_fallback_url=${encodeURIComponent(href)};end`;
}

/** Report this phone's install state (after load, and again if Chrome offers to install), to diagnose from the laptop. */
async function sendDiag(when) {
  let related = null;
  try { related = navigator.getInstalledRelatedApps ? (await navigator.getInstalledRelatedApps()).length : null; } catch { /* ignore */ }
  const d = { ua: navigator.userAgent.slice(0, 300), url: location.origin, standalone: isStandalone(), secure: window.isSecureContext,
              offered: !!installPrompt, sw: !!(navigator.serviceWorker && navigator.serviceWorker.controller), path: location.pathname,
              when, installed_here: related, manifest: !!document.querySelector('link[rel="manifest"]'), version: APP_VERSION,
              brands: (navigator.userAgentData?.brands || []).map(b => b.brand + " " + b.version).join(", "),
              mode: ["standalone", "minimal-ui", "browser"].find(m => matchMedia(`(display-mode: ${m})`).matches) || "?" };
  fetch("/api/client-diag", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d), credentials: "same-origin" }).catch(() => {});
}
window.addEventListener("load", () => setTimeout(() => sendDiag("6s after opening"), 6000));
window.addEventListener("beforeinstallprompt", () => setTimeout(() => sendDiag("chrome offered install"), 300));

/** A visible "Install AppShare" bar on the main screens (sign-in, Home, an app's page) — never hidden in a menu. */
function installBar() {
  if (isStandalone() || document.querySelector(".install-bar")) return;
  try { if (Number(localStorage.getItem("appshare.installHidden") || 0) > Date.now()) return; } catch { /* ignore */ }
  const bar = document.createElement("div");
  bar.className = "install-bar";
  bar.innerHTML = `<span class="ib-mark">${MARK}</span><span class="ib-t"><b>Install AppShare</b><span>Opens like an app; shared links open in it</span></span>
    <button class="btn primary sm" data-go>Install</button><button class="ib-x" aria-label="Not now">${ic("x")}</button>`;
  bar.querySelector("[data-go]").onclick = async () => {
    if (installPrompt) {
      try {
        installPrompt.prompt();
        const choice = await installPrompt.userChoice;
        installPrompt = null;
        if (choice && choice.outcome === "accepted") bar.remove();
        return;
      } catch { installPrompt = null; /* fall through to the help */ }
    }
    installHelp();
  };
  bar.querySelector(".ib-x").onclick = () => { bar.remove(); try { localStorage.setItem("appshare.installHidden", String(Date.now() + 3 * 86400000)); } catch { /* ignore */ } };
  document.body.appendChild(bar);
  document.body.classList.add("has-install-bar");
}
/** Count installs: a random id per browser (the installed app shares it), reported on install and on each
 *  open from the home-screen icon, so the server laptop can show "installed on N devices". */
function deviceId() {
  try {
    let id = localStorage.getItem("appshare.device");
    if (!id) { id = Array.from(crypto.getRandomValues(new Uint8Array(12)), b => b.toString(16).padStart(2, "0")).join(""); localStorage.setItem("appshare.device", id); }
    return id;
  } catch { return null; }
}
function reportInstall(event) {
  const device = deviceId();
  if (!device) return;
  fetch("/api/device-install", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
    body: JSON.stringify({ device, event }) }).catch(() => {});
}
window.addEventListener("load", () => {
  if (!isStandalone()) return;
  try { if (sessionStorage.getItem("appshare.openCounted")) return; sessionStorage.setItem("appshare.openCounted", "1"); } catch { /* ignore */ }
  setTimeout(() => reportInstall("app_open"), 1500);
});
window.addEventListener("appinstalled", () => { reportInstall("installed"); document.querySelector(".install-bar")?.remove(); toast("AppShare is installed — find it on your home screen"); });
window.addEventListener("load", () => { if (document.body.dataset.install !== undefined) setTimeout(installBar, 900); });
async function openInAppHint() {
  if (isStandalone() || !navigator.getInstalledRelatedApps) return;
  try { if (localStorage.getItem("appshare.hideOpenHint")) return; } catch { /* ignore */ }
  try {
    const apps = await navigator.getInstalledRelatedApps();
    if (!apps.length) return;
    const bar = document.createElement("div");
    bar.className = "open-hint";
    bar.innerHTML = `${ic("phone")}<span>AppShare is installed. To open this there, tap <b>⋮</b> → <b>Open in AppShare</b>.</span><button aria-label="Dismiss">${ic("x")}</button>`;
    bar.querySelector("button").onclick = () => { bar.remove(); try { localStorage.setItem("appshare.hideOpenHint", "1"); } catch { /* ignore */ } };
    document.body.appendChild(bar);
  } catch { /* not supported */ }
}
window.addEventListener("load", () => setTimeout(openInAppHint, 1200));
function profileSheet() {
  const me = ME;
  const s = sheet(`
    <div class="row" style="gap:14px"><span class="avatar" style="width:52px;height:52px;font-size:1.05rem">${esc(initials(me.name))}</span>
      <div class="grow"><h2>${esc(me.name)}</h2><div class="muted small">${esc(me.title || me.email)}</div></div></div>
    <div class="card pad stack" style="margin-top:16px">
      <div class="row"><span class="muted small grow">Workspace</span><b class="small">${esc(me.org)} · ${MODE_LABEL[me.mode]}</b></div>
      <div class="row"><span class="muted small grow">Email</span><span class="small">${esc(me.email)}</span></div>
      ${me.groups.length ? `<div><div class="muted small" style="margin-bottom:6px">Your groups</div><div class="chips">${me.groups.map(g => `<span class="chip">${esc(g)}</span>`).join("")}</div></div>` : ""}
    </div>
    <div class="stack" style="margin-top:14px">
      ${isStandalone() ? `<div class="notice ok">${ic("check")}<span>You're using the installed app.</span></div>`
        : `<button class="btn block primary" id="pfInstall">${ic("download")} Install the app</button>`}
      ${me.is_admin ? `<label class="btn block">${ic("upload")} Import members (CSV)<input type="file" id="pfImport" accept=".csv,text/csv" hidden></label>
        <div class="muted tiny">Columns: email, name, groups (separated by ;), title</div>` : ""}
      <button class="btn block danger" id="pfOut">Sign out</button></div>
    ${versionLine()}`);
  s.el.querySelector("#pfOut").onclick = async () => { await api("/api/logout", { json: {} }); location.href = "/login"; };
  const imp = s.el.querySelector("#pfImport");
  if (imp) imp.onchange = async () => {
    const f = imp.files[0]; if (!f) return;
    try {
      const r = await api("/api/admin/import", { method: "POST", body: await f.text(), headers: { "Content-Type": "text/csv" } });
      toast(`Imported ${r.imported ?? r.count ?? 0} members`); s.close();
    } catch (e) { toast(e.message); }
  };
  const ib = s.el.querySelector("#pfInstall");
  if (ib) ib.onclick = async () => {
    if (installPrompt) { installPrompt.prompt(); await installPrompt.userChoice; installPrompt = null; s.close(); }
    else { s.close(); installHelp(); }      // explain why not, and what to do — never a dead button
  };
}

// ---------------------------------------------------------------- sharing (Docs-style, mode-aware)
const ROLE_LABEL = { submitter: "Can respond", viewer: "Can see responses", editor: "Can edit" };

function openShare(app, onDone) {
  const me = ME;
  let entries = (app.shares || []).map(s => ({ ...s }));
  let access = app.link_access || (me.mode === "general" ? "public" : "restricted");
  const fromAgent = !entries.length && (app.share_suggestions || []).length > 0;
  if (fromAgent) {
    for (const s of app.share_suggestions) {
      if (s.type === "org") access = "org";
      else if (s.type === "public") access = "public";
      else entries.push({ type: s.type, id: s.id, name: s.name, kind: s.detail || "", role: s.role });
    }
  }
  const link = shareUrl(app.slug);
  const levels = [
    { k: "restricted", icon: "lock", t: "Only people added", s: "Just the people and groups below" },
    ...(me.mode !== "general" ? [{ k: "org", icon: "building", t: `Everyone at ${me.org}`, s: "Anyone who signs in can respond" }] : []),
    { k: "public", icon: "globe", t: "Anyone with the link", s: "No account needed — like a public Doc" },
  ];
  const s = sheet(`
    <div class="sheet-head"><h2>Share “${esc(app.title)}”</h2><button class="icon-btn" data-close aria-label="Close">${ic("x")}</button></div>
    ${fromAgent ? `<div class="notice" style="margin-bottom:12px">${ic("sparkle")}<span>The Access agent suggested who this is for. Check it, then share.</span></div>` : ""}
    <div class="label" style="margin-bottom:8px">Who can respond</div>
    <div class="opt-list" id="shLevels"></div>
    <div id="shPeopleWrap">
      <div class="label" style="margin:18px 0 8px">People & groups</div>
      <div class="search">${ic("users")}<input id="shQ" placeholder="${me.mode === "university" ? "Add a section, department, club or person" : me.mode === "office" ? "Add a team, department or person" : "Add a person or list"}" autocomplete="off"></div>
      <div class="results hidden" id="shRes"></div>
      <div id="shList" style="margin-top:6px"></div>
    </div>
    <div class="label" style="margin:18px 0 8px">Link</div>
    <div class="link-row"><code>${esc(link)}</code><button class="btn sm" id="shCopy">${ic("copy")}Copy</button></div>
    <div id="shErr"></div>
    <div class="row" style="margin-top:16px"><button class="btn grow" data-close>Cancel</button>
      <button class="btn primary grow" id="shGo">${app.status === "draft" ? "Share & publish" : "Save"}</button></div>`);
  const $ = q => s.el.querySelector(q);

  function drawLevels() {
    $("#shLevels").innerHTML = levels.map(l => `<button class="access-opt ${l.k === access ? "on" : ""}" data-k="${l.k}">
      <span class="ai">${ic(l.icon)}</span><span><b>${esc(l.t)}</b><span>${esc(l.s)}</span></span><span class="radio"></span></button>`).join("");
    s.el.querySelectorAll("[data-k]").forEach(b => b.onclick = () => { access = b.dataset.k; drawLevels(); });
  }
  function drawList() {
    $("#shList").innerHTML = entries.length ? entries.map((e, i) => `<div class="person-row">
      <span class="pi">${e.type === "group" ? ic("users") : esc(initials(e.name))}</span>
      <div style="min-width:0"><div class="ellipsis"><b class="small">${esc(e.name)}</b></div><div class="tiny muted ellipsis">${esc(e.kind_label || e.kind || "")}</div></div>
      <select data-i="${i}" aria-label="Role">${Object.entries(ROLE_LABEL).map(([r, l]) => `<option value="${r}" ${r === e.role ? "selected" : ""}>${l}</option>`).join("")}<option value="x">Remove</option></select></div>`).join("")
      : `<div class="muted small" style="padding:8px 0">${access === "public" ? "Not needed — anyone with the link can respond. Add people only to give them extra rights." : "No one yet."}</div>`;
    s.el.querySelectorAll("#shList select").forEach(sel => sel.onchange = () => { const i = +sel.dataset.i; if (sel.value === "x") entries.splice(i, 1); else entries[i].role = sel.value; drawList(); });
  }
  let t;
  $("#shQ").oninput = () => {
    clearTimeout(t);
    const q = $("#shQ").value.trim();
    if (!q) return $("#shRes").classList.add("hidden");
    t = setTimeout(async () => {
      const d = await api("/api/directory?q=" + encodeURIComponent(q));
      const items = [...d.groups.map(g => ({ type: "group", id: g.id, name: g.name, kind_label: `${g.kind_label} · ${g.members} people` })),
                     ...d.people.map(p => ({ type: "user", id: p.id, name: p.name, kind_label: p.title || p.email }))]
        .filter(it => !entries.some(e => e.type === it.type && e.id === it.id));
      $("#shRes").innerHTML = items.length ? items.map((it, i) => `<button data-i="${i}"><span class="pi" style="width:32px;height:32px;border-radius:8px;background:var(--surface-2);display:grid;place-items:center">${it.type === "group" ? ic("users") : ic("user")}</span><span><b class="small">${esc(it.name)}</b><div class="tiny muted">${esc(it.kind_label)}</div></span></button>`).join("") : `<div class="muted small" style="padding:10px">No matches</div>`;
      $("#shRes").classList.remove("hidden");
      $("#shRes").querySelectorAll("[data-i]").forEach(b => b.onclick = () => { entries.push({ ...items[+b.dataset.i], role: "submitter" }); $("#shQ").value = ""; $("#shRes").classList.add("hidden"); drawList(); });
    }, 180);
  };
  $("#shCopy").onclick = () => copyLink(link);
  $("#shGo").onclick = async () => {
    $("#shGo").disabled = true;
    try {
      const res = await api(`/api/apps/${app.id}/share`, { json: { entries: entries.map(e => ({ type: e.type, id: e.id, role: e.role })), link_access: access, publish: true } });
      s.close();
      onDone && onDone(res);
    } catch (e) { $("#shErr").innerHTML = `<div class="notice bad" style="margin-top:12px">${esc(e.message)}</div>`; $("#shGo").disabled = false; }
  };
  drawLevels(); drawList();
}

/** After sharing: one clear confirmation with the link and a Send button. */
function sharedSheet(app, res) {
  const link = shareUrl(res.link.split("/").pop());
  const who = res.link_access === "public" ? "Anyone with the link can respond" : res.link_access === "org" ? `Everyone at ${ME.org} can respond` : `${res.audience} ${res.audience === 1 ? "person" : "people"} can respond`;
  const s = sheet(`<div class="done-card" style="padding-top:6px"><div class="big">${ic("check")}</div><h2>Shared</h2>
      <p class="muted" style="margin-top:6px">${esc(who)}${res.link_access !== "public" ? " — it's in their app now" : ""}.</p></div>
    <div class="link-row"><code>${esc(link)}</code><button class="btn sm" id="sdCopy">${ic("copy")}Copy</button></div>
    <div class="row" style="margin-top:14px"><button class="btn grow" data-close>Done</button><button class="btn primary grow" id="sdSend">${ic("send")}Send link</button></div>`);
  s.el.querySelector("#sdCopy").onclick = () => copyLink(link);
  s.el.querySelector("#sdSend").onclick = () => sendLink(app.title, link);
}

// ---------------------------------------------------------------- agent team progress (Builder + specialists)
const AGENT_NAME = { builder: "Builder", data: "Data", design: "Design", access: "Access", insights: "Insights" };
const TOOL_TEXT = {
  ask_data_agent: "handing the brief to Data", ask_design_agent: "handing the brief to Design", ask_access_agent: "handing the brief to Access",
  check_fields: "checking the fields", submit_fields: "handing the fields back", get_fields: "reading Data's fields", check_color: "checking the colour",
  submit_design: "handing the design back", list_groups: "looking up groups", search_people: "looking people up", submit_access: "handing the audience back",
  save_app: "saving — the Validator checks it", get_current_app: "opening the app", get_overview: "reading the overview", list_responses: "reading responses",
  list_missing: "finding who's missing",
};
function face(kind) { return window.CHAR ? CHAR.svg(kind, { crop: "head" }) : ""; }

function TeamProgress(container, kinds = ["builder", "data", "design", "access"]) {
  const state = Object.fromEntries(kinds.map(k => [k, { st: "", act: k === "builder" ? "reading your request" : "waiting for the brief" }]));
  function draw() {
    container.innerHTML = `<div class="card team"><div class="label" style="margin-bottom:4px">The agent team is working</div>
      ${kinds.map(k => `<div class="team-row"><span class="face">${face(k)}</span><div style="min-width:0"><b>${AGENT_NAME[k]}</b><div class="act">${esc(state[k].act)}</div></div><span class="st-dot ${state[k].st}"></span></div>`).join("")}</div>`;
  }
  draw();
  return {
    update(steps) {
      for (const s of steps) {
        const k = s.agent; if (!state[k]) continue;
        if (s.type === "agent_start") state[k] = { st: "work", act: k === "builder" ? "reading your request" : "got the brief" };
        else if (s.type === "agent_llm_start") state[k] = { st: "work", act: "thinking with Claude…" };
        else if (s.type === "agent_tool") state[k] = { st: "work", act: TOOL_TEXT[s.tool] || s.tool };
        else if (s.type === "agent_tool_result") state[k] = { st: s.ok === false ? "bad" : "work", act: s.summary || "done" };
        else if (s.type === "agent_reply") state[k] = { st: "done", act: k === "builder" ? "done" : "handed back ✓" };
        else if (s.type === "agent_error") state[k] = { st: "bad", act: s.summary || "couldn't finish" };
      }
      draw();
    },
  };
}

/** Run a builder message while showing live team progress. Resolves with the /api/agent/build response. */
async function runBuilder({ message, sessionId, appId, progressEl }) {
  if (!sessionId) { const s = await api("/api/agent/session", { json: appId ? { app_id: appId } : {} }); sessionId = s.session_id; var cursor = s.cursor; }
  const tp = TeamProgress(progressEl);
  let stop = false; cursor = cursor || 0;
  (async function poll() {
    while (!stop) {
      try { const p = await api(`/api/agent/progress?session_id=${sessionId}&after=${cursor}`); cursor = p.cursor; tp.update(p.steps); } catch { /* keep going */ }
      await new Promise(r => setTimeout(r, 700));
    }
  })();
  try { return await api("/api/agent/build", { json: { message, session_id: sessionId, app_id: appId || null } }); }
  finally { stop = true; setTimeout(() => progressEl.innerHTML = "", 400); }
}

// ---------------------------------------------------------------- connection watcher (auto-reconnect)
const Connection = (() => {
  let online = true, timer = null, banner = null;
  async function check() {
    try {
      const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), 4000);
      const res = await fetch("/api/ping", { cache: "no-store", credentials: "same-origin", signal: ctrl.signal });
      clearTimeout(t);
      const data = res.ok && res.headers.get("content-type")?.includes("json") ? await res.json() : null;
      if (!data || data.app !== "appshare") throw new Error();
      try { localStorage.setItem("appshare.server", data.server); } catch { /* ignore */ }
      set(true);
    } catch { set(false); }
    clearTimeout(timer); timer = setTimeout(check, online ? 8000 : 3000);
  }
  function show(html, cls) {
    if (!banner) { banner = document.createElement("div"); banner.setAttribute("role", "status"); document.body.appendChild(banner); }
    banner.className = "conn-banner " + cls; banner.innerHTML = html;
  }
  function set(now) {
    if (now === online) return;
    online = now;
    if (!now) show(`<span class="conn-spin"></span> Server offline · reconnecting…`, "off");
    else { show(`${ic("check")} Reconnected`, "on"); setTimeout(() => banner && banner.classList.add("gone"), 2000); window.dispatchEvent(new Event("appshare:reconnected")); }
  }
  window.addEventListener("online", check);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
  window.addEventListener("load", () => { timer = setTimeout(check, 1500); });
  return { check };
})();
