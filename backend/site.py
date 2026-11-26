"""Sites: an app whose page is made of blocks the creator controls (like a small Google Sites page).

A site is an app of kind "site". Its spec carries `site`:
  theme        one of THEMES (fonts, colours, spacing)              accent      optional #rrggbb
  background   one of BACKGROUNDS (built-in, no downloads)          footer      optional footer text
  show_badge   show "Made with AppShare" (off unless the creator wants it)
  pages        1-6 pages, each {id, title, blocks: [...]}; a menu appears only when there is more than one page
  suggested    optional extras the AI *suggested* but did NOT add — the creator switches them on if they want them

Nothing is added by default: a site has exactly the blocks the creator asked for. Every value is checked here:
plain text only (no HTML; the page escapes everything), links must be http(s), mailto or tel, and sizes are bounded.
If the app collects answers, its form appears where the `form` block is (or at the end of the first page).
"""
import re

THEMES = {
    "clean": "White, crisp sans-serif — fits anything",
    "editorial": "Serif headings, calm and readable — announcements, clubs, notices",
    "bold": "Big type, dark banner — events, hackathons, launches",
    "warm": "Cream and soft corners — parties, community, food",
    "night": "Dark throughout — gaming, music, late events",
    "fresh": "Light green accents — outdoors, health, volunteering",
    "academic": "Navy and serif — courses, departments, seminars",
    "playful": "Rounded and colourful — kids, games, fun",
}
BACKGROUNDS = ("none", "sunrise", "ocean", "forest", "dusk", "berry", "mint", "paper", "night", "photo")
ICON_NAMES = ("calendar", "clock", "users", "user", "check", "star", "spark", "sparkle", "ticket", "globe", "building", "message",
              "chart", "file", "link", "wrench", "home", "bell", "list", "grid")
BLOCK_TYPES = {
    "hero": "big banner: title, subtitle, optional button",
    "text": "a heading and paragraphs (supports **bold** and lines starting with '- ' as a list)",
    "image_text": "the cover photo (or a background) beside a heading and text",
    "cards": "a grid of short cards: prizes, people, features, menu items",
    "timeline": "a schedule or steps: time/label, title, details",
    "faq": "questions that open to show their answers",
    "countdown": "a live countdown to a date and time",
    "buttons": "one or more link buttons",
    "map": "a place with an Open in Maps link",
    "contact": "email / phone / a note",
    "divider": "a thin line between sections",
    "form": "the app's form (sign-up, registration, RSVP…) — only if the site collects answers",
}
LIMITS = {"pages": 6, "blocks": 25, "items": 12, "short": 120, "long": 3000}
_URL = re.compile(r"^(https?://[^\s<>\"']{3,500}|mailto:[^\s<>\"']{3,200}|tel:[+\d\s\-()]{3,30}|#[a-z0-9\-=]{1,60})$", re.I)
_DT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def _s(v, n):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(v or "")).strip()[:n]


def _slug(v, fallback):
    s = re.sub(r"[^a-z0-9]+", "-", str(v or "").lower()).strip("-")[:30]
    return s or fallback


def _link(v, errors, where):
    v = _s(v, 520)
    if not v:
        return ""
    if v.startswith("www."):
        v = "https://" + v
    if not _URL.match(v):
        errors.append(f"{where}: links must start with https://, mailto: or tel: (got “{v[:40]}”)")
        return ""
    return v


def _items(raw, keys, errors, where):
    out = []
    for i, it in enumerate((raw or [])[:LIMITS["items"]]):
        if not isinstance(it, dict):
            errors.append(f"{where}.items[{i}] must be an object")
            continue
        item = {k: _s(it.get(k), LIMITS["long"] if k in ("body", "a") else LIMITS["short"]) for k in keys}
        if "icon" in item and item["icon"] not in ICON_NAMES:
            item["icon"] = ""
        if any(item.values()):
            out.append(item)
    return out


def validate_block(b, errors, where, has_fields):
    if not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES:
        errors.append(f"{where}: type must be one of {', '.join(BLOCK_TYPES)}")
        return None
    t = b["type"]
    out = {"type": t}
    if b.get("extra"):
        out["extra"] = True                  # added by switching on a suggested extra (switching it off removes it)
    if t == "hero":
        out.update(title=_s(b.get("title"), LIMITS["short"]), subtitle=_s(b.get("subtitle"), 400),
                   size="full" if b.get("size") == "full" else "normal", align="left" if b.get("align") == "left" else "center")
        if not out["title"]:
            errors.append(f"{where}: a hero needs a title")
        btn = b.get("button") or {}
        if isinstance(btn, dict) and _s(btn.get("label"), 40):
            out["button"] = {"label": _s(btn.get("label"), 40), "to": _link(btn.get("to") or "#form", errors, where + ".button")}
    elif t == "text":
        out.update(heading=_s(b.get("heading"), LIMITS["short"]), body=_s(b.get("body"), LIMITS["long"]))
        if not out["heading"] and not out["body"]:
            errors.append(f"{where}: text needs a heading or a body")
    elif t == "image_text":
        out.update(heading=_s(b.get("heading"), LIMITS["short"]), body=_s(b.get("body"), LIMITS["long"]),
                   side="right" if b.get("side") == "right" else "left")
    elif t == "cards":
        out.update(heading=_s(b.get("heading"), LIMITS["short"]), items=_items(b.get("items"), ("icon", "title", "body"), errors, where))
        if not out["items"]:
            errors.append(f"{where}: cards need at least one item")
    elif t == "timeline":
        out.update(heading=_s(b.get("heading"), LIMITS["short"]), items=_items(b.get("items"), ("when", "title", "body"), errors, where))
        if not out["items"]:
            errors.append(f"{where}: a timeline needs at least one item")
    elif t == "faq":
        out.update(heading=_s(b.get("heading"), LIMITS["short"]) or "Questions", items=_items(b.get("items"), ("q", "a"), errors, where))
        if not out["items"]:
            errors.append(f"{where}: an FAQ needs at least one question")
    elif t == "countdown":
        to = _s(b.get("to"), 16)
        if not _DT.match(to):
            errors.append(f"{where}: countdown 'to' must be YYYY-MM-DDTHH:MM")
        out.update(to=to, label=_s(b.get("label"), 80) or "Starts in")
    elif t == "buttons":
        btns = []
        for i, x in enumerate((b.get("items") or [])[:6]):
            if isinstance(x, dict) and _s(x.get("label"), 40):
                btns.append({"label": _s(x.get("label"), 40), "to": _link(x.get("to"), errors, f"{where}.items[{i}]")})
        out["items"] = [x for x in btns if x["to"]]
        if not out["items"]:
            errors.append(f"{where}: buttons need a label and a link")
    elif t == "map":
        out.update(heading=_s(b.get("heading"), LIMITS["short"]), place=_s(b.get("place"), 200))
        if not out["place"]:
            errors.append(f"{where}: a map needs a place")
    elif t == "contact":
        email = _s(b.get("email"), 120)
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors.append(f"{where}: contact email isn't valid")
            email = ""
        out.update(heading=_s(b.get("heading"), LIMITS["short"]) or "Contact", email=email,
                   phone=re.sub(r"[^\d+\-\s()]", "", _s(b.get("phone"), 30)), note=_s(b.get("note"), 400))
    elif t == "form":
        out["heading"] = _s(b.get("heading"), LIMITS["short"])
        if not has_fields:
            errors.append(f"{where}: a form block needs the app to have questions (fields)")
    return out


def validate_site(raw, title, has_fields):
    """Return (clean_site, errors)."""
    errors = []
    raw = raw if isinstance(raw, dict) else {}
    site = {"theme": raw.get("theme") if raw.get("theme") in THEMES else "clean",
            "accent": raw.get("accent") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(raw.get("accent") or "")) else "",
            "background": raw.get("background") if raw.get("background") in BACKGROUNDS else "none",
            "footer": _s(raw.get("footer"), 200), "show_badge": bool(raw.get("show_badge", False)), "pages": [], "suggested": []}
    pages = raw.get("pages") or []
    if not isinstance(pages, list) or not pages:
        errors.append("a site needs at least one page")
        pages = []
    if len(pages) > LIMITS["pages"]:
        errors.append(f"a site can have at most {LIMITS['pages']} pages")
    seen, forms = set(), 0
    for pi, p in enumerate(pages[:LIMITS["pages"]]):
        if not isinstance(p, dict):
            errors.append(f"pages[{pi}] must be an object")
            continue
        pid = _slug(p.get("id") or p.get("title"), f"page-{pi + 1}")
        while pid in seen:
            pid += "-2"
        seen.add(pid)
        blocks = p.get("blocks") or []
        if len(blocks) > LIMITS["blocks"]:
            errors.append(f"pages[{pi}] has more than {LIMITS['blocks']} blocks")
        clean = [x for x in (validate_block(b, errors, f"pages[{pi}].blocks[{bi}]", has_fields)
                             for bi, b in enumerate(blocks[:LIMITS["blocks"]])) if x]
        forms += sum(1 for b in clean if b["type"] == "form")
        site["pages"].append({"id": pid, "title": _s(p.get("title"), 60) or (title if pi == 0 else f"Page {pi + 1}"), "blocks": clean})
    if forms > 1:
        errors.append("a site can have only one form block")
    if has_fields and not forms and site["pages"]:
        site["pages"][0]["blocks"].append({"type": "form", "heading": ""})     # the app's questions must appear somewhere
    for s in (raw.get("suggested") or [])[:6]:
        if isinstance(s, dict) and s.get("type") in BLOCK_TYPES and s.get("type") != "form":
            site["suggested"].append({"type": s["type"], "label": _s(s.get("label"), 60) or s["type"], "why": _s(s.get("why"), 160)})
    return site, errors


def block_types_used(site):
    return [b["type"] for p in (site or {}).get("pages", []) for b in p.get("blocks", [])]
