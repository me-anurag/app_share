"""Exact checks: does what the agents saved match what the request asked for?

Every check returns (agent, name, passed, detail). `agent` says whose job it was, so results roll up into
per-agent accuracy. Checks never call a model: they read the saved spec, the share suggestions, the reply text
and the database.
"""
import re

CHOICE = {"radio", "select", "checkbox"}
ID_WORDS = re.compile(r"\b(name|e-?mail|roll|student id|employee id)\b", re.I)
# The reply must not claim the app was already shared: sharing only happens when the owner presses Share.
_SHARED = re.compile(r"\b(i(?:'ve| have)|has been|have been|is now|was|it's been)\s+(?:also\s+)?shared\b", re.I)
# A negated clause ("Nothing has been shared yet", "it isn't shared with anyone") is the honest answer, not a claim.
_NEGATED = re.compile(r"\b(nothing|not|never|no one|nobody|none|n't)\b|n't\b", re.I)


class _Claims:
    """Finds a claim that the app was already shared, ignoring negated clauses (v2: v1 counted
    'Nothing has been shared yet' as a claim — found in the first live run, see the report)."""
    def search(self, text):
        for m in _SHARED.finditer(text or ""):
            clause = re.split(r"[.;:!?,]|\b(?:but|and|so)\b", (text or "")[:m.start()])[-1]
            if not _NEGATED.search(clause):
                return m
        return None


CLAIMS_SHARED = _Claims()


def _contrast(hex_color):
    h = str(hex_color or "").lstrip("#")
    try:
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return 0.0
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 1.05 / (0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2] + 0.05)


def _inputs(spec):
    return [f for f in spec.get("fields") or [] if f.get("type") != "info"]


def _field_ok(f, want):
    if f.get("type") != want["type"]:
        return False
    if want.get("label") and not re.search(want["label"], f"{f.get('label', '')} {f.get('id', '')}", re.I):
        return False
    acc = {a.lower() for a in f.get("accept") or []}
    if "accept" in want and acc != {a.lower() for a in want["accept"]}:
        return False
    for alt in want.get("accept_has", []):
        if not any(a in acc for a in alt.split("|")):
            return False
    if "max_mb" in want and float(f.get("max_mb") or 0) != float(want["max_mb"]):
        return False
    return True


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def check_build(case, spec, shares, reply):
    out = []
    add = lambda agent, name, ok, detail="": out.append({"agent": agent, "check": name, "passed": bool(ok), "detail": detail})
    fields = _inputs(spec)
    for agent, kind, *arg in case["checks"]:
        if kind == "field":
            want = arg[0]
            n = sum(1 for f in fields if _field_ok(f, want))
            need = want.get("count", 1)
            add(agent, f"field {want['type']}{' ~' + want['label'] if want.get('label') else ''}{' ×' + str(need) if need > 1 else ''}"
                f"{' accept=' + ','.join(want['accept']) if want.get('accept') else ''}{' max_mb=' + str(want['max_mb']) if want.get('max_mb') else ''}",
                n >= need, f"found {n}: " + ", ".join(f"{f.get('type')}:{f.get('label')}" for f in fields))
        elif kind == "choice":
            want = arg[0]
            hit = None
            for f in fields:
                if f.get("type") not in CHOICE:
                    continue
                opts = [_norm(o) for o in f.get("options") or []]
                if len(opts) == len(want["options"]) and all(any(w in o for o in opts) for w in want["options"]):
                    hit = f
                    break
            ok = hit is not None
            if ok and "limits" in want:
                lim = hit.get("limits") or {}
                ok = len(lim) == len(want["options"]) and all(int(v) == want["limits"] for v in lim.values())
            add(agent, f"choice {'/'.join(want['options'])}{' with ' + str(want['limits']) + ' places each' if 'limits' in want else ''}", ok,
                "; ".join(f"{f.get('label')}: {f.get('options')} limits={f.get('limits')}" for f in fields if f.get("type") in CHOICE) or "no choice field")
        elif kind == "rule":
            key, val = arg
            got = spec.get(key)
            add(agent, f"rule {key}={val}", got == val, f"got {got!r}")
        elif kind == "closes":
            want = arg[0]
            got = spec.get("closes_at") or ""
            add(agent, f"deadline {want}", got.startswith(want) if len(want) == 10 else got == want, f"got {got!r}")
        elif kind == "no_identity":
            bad = [f.get("label") for f in fields if f.get("type") == "email" or (f.get("type") == "short_text" and ID_WORDS.search(f"{f.get('label')} {f.get('id')}"))]
            add(agent, "doesn't ask signed-in people for name/email", not bad, f"asked: {bad}" if bad else "")
        elif kind == "max_fields":
            add(agent, f"at most {arg[0]} questions", len(fields) <= arg[0], f"{len(fields)} questions")
        elif kind == "statuses":
            st = [s.lower() for s in spec.get("statuses") or []]
            add(agent, f"statuses include {'/'.join(arg[0])}", all(any(w in s for s in st) for w in arg[0]), f"got {spec.get('statuses')}")
        elif kind == "share":
            want = arg[0]
            types = want["type"].split("|")

            def match(s):
                for t in types:
                    if ":" in t:
                        tt, name = t.split(":", 1)
                        if s.get("type") == tt and _norm(s.get("name")) == _norm(name):
                            return True
                    elif s.get("type") == t and (t in ("org", "public") or _norm(s.get("name")) == _norm(want.get("name"))):
                        return True
                return False
            hits = [s for s in shares if match(s)]
            ok = bool(hits) and (not want.get("role") or any(s.get("role") == want["role"] for s in hits))
            add(agent, f"share {want.get('name') or want['type']}{' as ' + want['role'] if want.get('role') else ''}", ok,
                "suggested: " + ", ".join(f"{s.get('type')}:{s.get('name')}({s.get('role')})" for s in shares))
        elif kind == "title_has":
            add(agent, f"title mentions {arg[0]}", re.search(arg[0], spec.get("title") or "", re.I), spec.get("title"))
    # checks every build gets
    add("design", "accent colour readable (contrast ≥ 4.5:1)", _contrast(spec.get("theme_color")) >= 4.5, f"{spec.get('theme_color')} → {_contrast(spec.get('theme_color')):.2f}:1")
    add("design", "has a title and instructions", bool((spec.get("title") or "").strip()) and bool((spec.get("description") or "").strip()),
        f"title={spec.get('title')!r}")
    add("builder", "app saved", bool(fields), f"{len(fields)} questions")
    add("builder", "reply doesn't claim it was shared", not CLAIMS_SHARED.search(reply or ""), (CLAIMS_SHARED.search(reply or "") or [""])[0])
    # Faithfulness: what the reply tells the person about the app must be true of the saved app.
    bad_dates = [d for d in _dates(reply) if d not in _allowed_dates(spec)]
    add("builder", "reply's dates match the saved app", not bad_dates,
        f"reply mentions {bad_dates}; app has {sorted(_allowed_dates(spec))}" if bad_dates else "")
    bad_places = [n for n in _places(reply) if n not in _allowed_places(spec)]
    add("builder", "reply's numbers of places match the saved app", not bad_places,
        f"reply says {bad_places}; app has {sorted(_allowed_places(spec))}" if bad_places else "")
    return out


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE_DM = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}\b", re.I)
_DATE_MD = re.compile(rf"\b{_MON}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)


def _dates(text):
    """(month, day) pairs written in free text: "12 December", "Dec 12", "30th Nov"."""
    out = set()
    for d, m in _DATE_DM.findall(text or ""):
        out.add((MONTHS[m[:3].lower()], int(d)))
    for m, d in _DATE_MD.findall(text or ""):
        out.add((MONTHS[m[:3].lower()], int(d)))
    return sorted(out)


def _allowed_dates(spec):
    """Dates the reply may truthfully mention: the deadline, the opening, and dates written in the app itself."""
    ok = set()
    for k in ("closes_at", "opens_at"):
        v = spec.get(k) or ""
        if len(v) >= 10:
            ok.add((int(v[5:7]), int(v[8:10])))
    text = " ".join([spec.get("title") or "", spec.get("description") or ""] +
                    [f"{f.get('label', '')} {f.get('help', '')} {' '.join(map(str, f.get('options') or []))}" for f in spec.get("fields") or []])
    ok.update(_dates(text))
    return ok


_PLACES = re.compile(r"\b(\d{1,4})\s+(?:places|spots|seats|slots? each|people (?:each|per)|students (?:each|per)|places each)\b", re.I)


def _places(text):
    return sorted({int(n) for n in _PLACES.findall(text or "")})


def _allowed_places(spec):
    ok = set()
    if spec.get("max_responses"):
        ok.add(int(spec["max_responses"]))
    for f in spec.get("fields") or []:
        lim = list((f.get("limits") or {}).values())
        ok.update(int(v) for v in lim)
        if lim:
            ok.add(sum(int(v) for v in lim))
    return ok


def check_insights(case, reply, truth):
    out = []
    text = reply or ""
    if case["truth"] == "count":
        n = len(truth["responders"])
        words = {0: "no|zero|none", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}
        ok = re.search(rf"\b({n}|{words.get(n, '_')})\b", text, re.I) is not None
        out.append({"agent": "insights", "check": f"states the exact count ({n})", "passed": ok, "detail": text[:200]})
        out.append({"agent": "insights", "check": f"mentions the audience size ({truth['audience']})",
                    "passed": re.search(rf"\b{truth['audience']}\b", text) is not None, "detail": ""})
    else:
        named = [m for m in truth["missing"] if m.split()[0].lower() in text.lower()]
        wrong = [r for r in truth["responders"] if r.split()[0].lower() in text.lower()]
        out.append({"agent": "insights", "check": f"names everyone missing ({len(truth['missing'])})", "passed": len(named) == len(truth["missing"]),
                    "detail": f"named {named}"})
        out.append({"agent": "insights", "check": "names nobody who already submitted", "passed": not wrong, "detail": f"wrongly named {wrong}" if wrong else ""})
    return out


def check_reminder(case, sent_to, truth):
    sent, missing = set(sent_to), set(truth["missing"])
    return [
        {"agent": "reminder", "check": f"reminded everyone missing ({len(missing)})", "passed": missing <= sent, "detail": f"not reminded: {sorted(missing - sent)}"},
        {"agent": "reminder", "check": "reminded nobody else", "passed": sent <= missing, "detail": f"wrongly reminded: {sorted(sent - missing)}"},
        {"agent": "reminder", "check": "one reminder each", "passed": len(sent_to) == len(sent), "detail": f"{len(sent_to)} sent to {len(sent)} people"},
    ]


def signature(spec, shares):
    """A compact description of an app's structure, to compare runs for consistency (wording ignored)."""
    fields = _inputs(spec)
    return repr((
        tuple(sorted(f.get("type") for f in fields)),
        tuple(sorted(len(f.get("options") or []) for f in fields if f.get("type") in CHOICE)),
        tuple(sorted(tuple(sorted((f.get("limits") or {}).values())) for f in fields if f.get("limits"))),
        bool(spec.get("anonymous")), (spec.get("closes_at") or "")[:10], spec.get("max_responses") or 0,
        spec.get("responses_per_person"), spec.get("show_results"), len(spec.get("statuses") or []),
        tuple(sorted(f"{s.get('type')}:{_norm(s.get('name') or '')}:{s.get('role')}" for s in shares)),
    ))
