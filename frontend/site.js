// AppShare sites: renders a site spec (pages of blocks) as a page that looks like the creator's own site.
// Everything is escaped text — no HTML from the spec is ever inserted. The app's form (if any) is passed in and
// placed where the site's "form" block is. Navigation between pages uses #p=<page-id>.
"use strict";

const Site = (() => {
  const md = t => esc(t || "").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>");
  function paras(t) {
    const out = [];
    let list = [];
    const flush = () => { if (list.length) { out.push(`<ul>${list.map(x => `<li>${md(x)}</li>`).join("")}</ul>`); list = []; } };
    String(t || "").split(/\n/).forEach(line => {
      const l = line.trim();
      if (/^[-•]\s+/.test(l)) list.push(l.replace(/^[-•]\s+/, ""));
      else { flush(); if (l) out.push(`<p>${md(l)}</p>`); }
    });
    flush();
    return out.join("");
  }
  const href = to => to && /^(https?:|mailto:|tel:|#)/i.test(to) ? esc(to) : "#";
  const ext = to => /^https?:/i.test(to || "") ? ' target="_blank" rel="noopener noreferrer"' : "";
  const pageOf = () => (location.hash.match(/#p=([a-z0-9-]+)/) || [])[1];

  function block(b, ctx) {
    switch (b.type) {
      case "hero": return `<section class="s-hero ${b.size === "full" ? "full" : ""} ${b.align === "left" ? "left" : ""}" data-bg="${esc(ctx.site.background)}" ${ctx.cover}>
          <div class="s-in"><h1>${esc(b.title)}</h1>${b.subtitle ? `<p class="s-sub">${md(b.subtitle)}</p>` : ""}
          ${b.button ? `<a class="s-btn" href="${href(b.button.to)}"${ext(b.button.to)}>${esc(b.button.label)}</a>` : ""}</div></section>`;
      case "text": return `<section class="s-block s-text">${b.heading ? `<h2>${esc(b.heading)}</h2>` : ""}${paras(b.body)}</section>`;
      case "image_text": return `<section class="s-block s-imgtext ${b.side === "right" ? "right" : ""}"><div class="s-img" data-bg="${esc(ctx.site.background === "none" ? "paper" : ctx.site.background)}" ${ctx.cover}></div>
          <div>${b.heading ? `<h2>${esc(b.heading)}</h2>` : ""}${paras(b.body)}</div></section>`;
      case "cards": return `<section class="s-block">${b.heading ? `<h2>${esc(b.heading)}</h2>` : ""}<div class="s-cards">${b.items.map(c => `<div class="s-card">
          ${c.icon ? `<span class="s-ic">${ic(c.icon)}</span>` : ""}<b>${esc(c.title)}</b>${c.body ? `<div>${paras(c.body)}</div>` : ""}</div>`).join("")}</div></section>`;
      case "timeline": return `<section class="s-block">${b.heading ? `<h2>${esc(b.heading)}</h2>` : ""}<ol class="s-time">${b.items.map(x => `<li>
          <span class="s-when">${esc(x.when)}</span><div><b>${esc(x.title)}</b>${x.body ? paras(x.body) : ""}</div></li>`).join("")}</ol></section>`;
      case "faq": return `<section class="s-block">${b.heading ? `<h2>${esc(b.heading)}</h2>` : ""}<div class="s-faq">${b.items.map(x => `<details>
          <summary>${esc(x.q)}</summary><div>${paras(x.a)}</div></details>`).join("")}</div></section>`;
      case "countdown": return `<section class="s-block s-count" data-to="${esc(b.to)}"><div class="s-clabel">${esc(b.label)}</div><div class="s-digits"></div></section>`;
      case "buttons": return `<section class="s-block s-buttons">${b.items.map((x, i) => `<a class="s-btn ${i ? "ghost" : ""}" href="${href(x.to)}"${ext(x.to)}>${esc(x.label)}</a>`).join("")}</section>`;
      case "map": return `<section class="s-block s-map">${b.heading ? `<h2>${esc(b.heading)}</h2>` : ""}<div class="s-place">${ic("globe")}<span>${esc(b.place)}</span></div>
          <a class="s-btn ghost" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(b.place)}" target="_blank" rel="noopener noreferrer">Open in Maps</a></section>`;
      case "contact": return `<section class="s-block s-contact"><h2>${esc(b.heading)}</h2>${b.note ? paras(b.note) : ""}<div class="s-buttons">
          ${b.email ? `<a class="s-btn ghost" href="mailto:${esc(b.email)}">${ic("message")}${esc(b.email)}</a>` : ""}
          ${b.phone ? `<a class="s-btn ghost" href="tel:${esc(b.phone.replace(/[^\d+]/g, ""))}">${esc(b.phone)}</a>` : ""}</div></section>`;
      case "divider": return `<hr class="s-hr">`;
      case "form": return `<section class="s-block s-form" id="s-form">${b.heading ? `<h2>${esc(b.heading)}</h2>` : ""}${ctx.form}</section>`;
    }
    return "";
  }

  function render(D, parts) {
    const site = D.spec.site, pages = site.pages || [];
    const cur = pages.find(p => p.id === pageOf()) || pages[0];
    const cover = D.spec.look?.cover && site.background === "photo"
      ? `style="background-image:url('/api/a/${encodeURIComponent(D.slug)}/cover?v=${encodeURIComponent(D.spec.look.cover)}')"` : "";
    const ctx = { site, cover, form: parts.form || "" };
    const nav = pages.length > 1 ? `<nav class="s-nav"><b class="s-brand">${esc(D.spec.title)}</b>
        <button class="s-menu" aria-label="Menu" aria-expanded="false">${ic("list")}</button>
        <div class="s-links">${pages.map(p => `<a href="#p=${esc(p.id)}" class="${p === cur ? "on" : ""}">${esc(p.title)}</a>`).join("")}</div></nav>` : "";
    return `<div class="site" data-theme="${esc(site.theme)}" style="${site.accent ? `--s-accent:${esc(site.accent)};` : ""}">
        ${parts.top || ""}${nav}
        <main class="s-main">${(cur?.blocks || []).map(b => block(b, ctx)).join("")}</main>
        ${site.footer || site.show_badge || parts.bottom ? `<footer class="s-foot">${site.footer ? `<span>${esc(site.footer)}</span>` : ""}${site.show_badge ? `<span>Made with AppShare</span>` : ""}${parts.bottom || ""}</footer>` : ""}
      </div>`;
  }

  let ticker = null;
  function wire(root, onPage) {
    root.querySelector(".s-menu")?.addEventListener("click", e => {
      const nav = e.currentTarget.closest(".s-nav"), open = !nav.classList.contains("open");
      nav.classList.toggle("open", open); e.currentTarget.setAttribute("aria-expanded", open);
    });
    root.querySelectorAll('a[href="#form"]').forEach(a => a.addEventListener("click", e => {
      const f = root.querySelector(".s-form");
      if (f) { e.preventDefault(); f.scrollIntoView({ behavior: "smooth", block: "start" }); }
    }));
    clearInterval(ticker);
    const counts = [...root.querySelectorAll(".s-count")];
    const tick = () => counts.forEach(c => {
      const ms = new Date(c.dataset.to).getTime() - Date.now(), box = c.querySelector(".s-digits");
      if (!(ms > 0)) { box.innerHTML = `<div class="s-now">It's on!</div>`; return; }
      const d = Math.floor(ms / 864e5), h = Math.floor(ms % 864e5 / 36e5), m = Math.floor(ms % 36e5 / 6e4), s = Math.floor(ms % 6e4 / 1e3);
      box.innerHTML = [[d, "days"], [h, "hours"], [m, "min"], [s, "sec"]].map(([v, l]) => `<div><b>${String(v).padStart(2, "0")}</b><span>${l}</span></div>`).join("");
    });
    if (counts.length) { tick(); ticker = setInterval(tick, 1000); }
    window.onhashchange = () => { if (/^#p=/.test(location.hash)) { onPage(); scrollTo(0, 0); } };
  }
  return { render, wire };
})();
