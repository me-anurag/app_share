"""App spec: the contract between the agents and the engine.

The agents never write code. They produce a spec, this module validates and normalizes it,
and the generic renderer + storage make it a working app. One engine covers many kinds of app:
  - forms, surveys, feedback (optionally anonymous)
  - registrations and bookings with seat limits (overall and per option, e.g. time slots)
  - polls whose results respondents can see
  - requests and tickets that move through statuses (Pending -> Approved, Open -> Resolved)
  - submissions with files
"""
import re
from datetime import datetime

FIELD_TYPES = {
    "short_text", "long_text", "number", "email", "phone", "date",
    "select", "radio", "checkbox", "file", "rating", "info",
}
# Fields that identify or contact a person: the owner reads them as one row per person, never summarised.
RECORD_TYPES = {"short_text", "email", "phone", "date", "file"}
CHOICE_TYPES = {"select", "radio", "checkbox"}
LIMITABLE = {"select", "radio"}
MAX_FILE_MB = 25
DEFAULT_FILE_MB = 10
DATETIME_FMT = "%Y-%m-%dT%H:%M"
KINDS = {"assignment", "survey", "feedback", "poll", "registration", "booking", "request", "rsvp", "quiz", "form", "sign-up", "site", "party"}

# Looks: a library of crafted designs the engine renders. The Design agent only picks names from it
# (a few tokens), never writes HTML or CSS — cheap, consistent and safe on everyone's phone.
LOOK_STYLES = ("classic", "elegant", "festive", "playful", "bold", "minimal", "academic", "corporate", "natural")
LOOK_PATTERNS = ("none", "dots", "grid", "waves", "sparkle", "confetti", "leaves", "diagonal", "rings")
STYLE_PATTERN = {"classic": "dots", "elegant": "sparkle", "festive": "confetti", "playful": "rings", "bold": "diagonal",
                 "minimal": "none", "academic": "grid", "corporate": "grid", "natural": "leaves"}
KIND_STYLE = {"assignment": "academic", "quiz": "playful", "party": "festive", "survey": "minimal", "feedback": "minimal", "poll": "playful",
              "registration": "bold", "booking": "corporate", "request": "corporate", "rsvp": "festive", "sign-up": "playful",
              "form": "classic"}
COVER_RE = re.compile(r"cover-[0-9a-f]{8}\.(jpg|png|webp)")


def normalize_look(raw, kind="form"):
    """Clean a look object; anything missing falls back to a sensible design for the kind of app."""
    raw = raw if isinstance(raw, dict) else {}
    style = raw.get("style") if raw.get("style") in LOOK_STYLES else KIND_STYLE.get(kind, "classic")
    pattern = raw.get("pattern") if raw.get("pattern") in LOOK_PATTERNS else STYLE_PATTERN[style]
    look = {"style": style, "pattern": pattern}
    if isinstance(raw.get("cover"), str) and COVER_RE.fullmatch(raw["cover"]):
        look["cover"] = raw["cover"]
    return look


def contrast_with_white(hex_color):
    h = str(hex_color or "").lstrip("#")
    try:
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except (ValueError, IndexError):
        return 0.0
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return round(1.05 / (0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2] + 0.05), 2)

# Light content sniffing so a renamed .exe can't pass as a PDF.
MAGIC = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"], ".pptx": [b"PK\x03\x04"], ".xlsx": [b"PK\x03\x04"], ".zip": [b"PK\x03\x04"],
    ".png": [b"\x89PNG"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"],
    ".doc": [b"\xd0\xcf\x11\xe0"], ".ppt": [b"\xd0\xcf\x11\xe0"], ".xls": [b"\xd0\xcf\x11\xe0"],
}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s[:40] or "field"


def parse_dt(value):
    if not value:
        return None
    value = str(value).strip().replace(" ", "T")
    for fmt, n in ((DATETIME_FMT, 16), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            dt = datetime.strptime(value[:n], fmt)
            if fmt == "%Y-%m-%d" and len(value) <= 10:
                dt = dt.replace(hour=23, minute=59)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date/time '{value}'. Use YYYY-MM-DDTHH:MM.")


def validate_spec(raw: dict, require_future_deadline: bool = True):
    """Return (clean_spec, errors). errors is a list of human-readable strings."""
    errors = []
    if not isinstance(raw, dict):
        return None, ["spec must be an object"]

    title = str(raw.get("title") or "").strip()
    if not title:
        errors.append("title is required")
    kind = str(raw.get("kind") or "form").strip().lower()[:40]

    spec = {
        "title": title[:120],
        "description": str(raw.get("description") or "").strip()[:2000],
        "kind": kind if kind in KINDS else "form",
        "theme_color": raw.get("theme_color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(raw.get("theme_color") or "")) else "#c4471a",
        "allow_edit_after_submit": bool(raw.get("allow_edit_after_submit", True)),
        "confirmation_message": str(raw.get("confirmation_message") or "Thanks! Your response has been recorded.").strip()[:500],
        "anonymous": bool(raw.get("anonymous", False)),
        "responses_per_person": "many" if raw.get("responses_per_person") == "many" else "one",
        "max_responses": None,
        "show_results": raw.get("show_results") if raw.get("show_results") in ("never", "after_submit", "always") else "never",
        # the Review agent reads each response (files, long answers) for the owner; off for surveys that don't need it
        "ai_review": raw.get("ai_review") is not False,
        "statuses": [],
        "opens_at": None,
        "closes_at": None,
        "fields": [],
    }
    spec["look"] = normalize_look(raw.get("look"), spec["kind"])

    for key in ("opens_at", "closes_at"):
        if raw.get(key):
            try:
                spec[key] = parse_dt(raw[key]).strftime(DATETIME_FMT)
            except ValueError as e:
                errors.append(f"{key}: {e}")
    if spec["closes_at"] and require_future_deadline and parse_dt(spec["closes_at"]) <= datetime.now():
        errors.append(f"closes_at {spec['closes_at']} is in the past (now is {datetime.now().strftime(DATETIME_FMT)})")
    if spec["opens_at"] and spec["closes_at"] and parse_dt(spec["opens_at"]) >= parse_dt(spec["closes_at"]):
        errors.append("opens_at must be before closes_at")

    if raw.get("max_responses") not in (None, "", 0):
        try:
            n = int(raw["max_responses"])
            if n < 1:
                raise ValueError
            spec["max_responses"] = min(n, 100000)
        except (TypeError, ValueError):
            errors.append("max_responses must be a whole number of at least 1")

    statuses = [str(s).strip()[:30] for s in (raw.get("statuses") or []) if str(s).strip()]
    if statuses:
        if len(statuses) < 2 or len(set(s.lower() for s in statuses)) != len(statuses) or len(statuses) > 6:
            errors.append("statuses needs 2 to 6 different names, the first is the starting status (e.g. Pending, Approved, Rejected)")
        else:
            spec["statuses"] = statuses
    if spec["anonymous"] and spec["statuses"]:
        errors.append("an anonymous app can't track request statuses (the owner couldn't tell anyone the outcome)")

    fields = raw.get("fields") or []
    if not isinstance(fields, list) or (not fields and spec["kind"] not in ("site", "party")):   # a site may only show information
        errors.append("at least one field is required")
        fields = []
    seen = set()
    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            errors.append(f"fields[{i}] must be an object")
            continue
        ftype = f.get("type")
        if ftype not in FIELD_TYPES:
            errors.append(f"fields[{i}].type '{ftype}' invalid; use one of {sorted(FIELD_TYPES)}")
            continue
        label = str(f.get("label") or "").strip()
        if not label:
            errors.append(f"fields[{i}].label is required")
            continue
        fid = _slug(f.get("id") or label)
        base, n = fid, 2
        while fid in seen:
            fid, n = f"{base}_{n}", n + 1
        seen.add(fid)
        field = {"id": fid, "type": ftype, "label": label[:300], "help": str(f.get("help") or "").strip()[:500],
                 "required": bool(f.get("required", False)) and ftype != "info"}
        if ftype in CHOICE_TYPES:
            opts = []
            for o in f.get("options") or []:
                o = str(o).strip()[:120]
                if o and o not in opts:
                    opts.append(o)
            if not opts:
                errors.append(f"field '{label}' ({ftype}) needs options")
            field["options"] = opts[:50]
            limits = f.get("limits") or {}
            if limits:
                if ftype not in LIMITABLE:
                    errors.append(f"field '{label}': seat limits only work on select or radio fields")
                elif not isinstance(limits, dict):
                    errors.append(f"field '{label}': limits must map option -> number of places")
                else:
                    clean = {}
                    for opt, n in limits.items():
                        if opt not in opts:
                            errors.append(f"field '{label}': limit for unknown option '{opt}'")
                            continue
                        try:
                            clean[opt] = max(1, int(n))
                        except (TypeError, ValueError):
                            errors.append(f"field '{label}': limit for '{opt}' must be a number")
                    if clean:
                        field["limits"] = clean
        if ftype == "file":
            accept = []
            for ext in f.get("accept") or []:
                ext = str(ext).strip().lower()
                if ext:
                    accept.append(ext if ext.startswith(".") else "." + ext)
            field["accept"] = accept
            try:
                mb = float(f.get("max_mb") or DEFAULT_FILE_MB)
            except (TypeError, ValueError):
                mb = DEFAULT_FILE_MB
            field["max_mb"] = max(0.1, min(mb, MAX_FILE_MB))
        if ftype in CHOICE_TYPES and not errors_before(errors, label):
            from .play import validate_question
            validate_question(field, f, errors)            # quiz: the right answer and its points
        if ftype == "number":
            for k in ("min", "max"):
                if isinstance(f.get(k), (int, float)):
                    field[k] = f[k]
        spec["fields"].append(field)

    if spec["fields"] and all(f["type"] == "info" for f in spec["fields"]):
        errors.append("the app needs at least one input field (not only info blocks)")
    from .guard import forbidden_fields       # never collect passwords, card numbers, one-time codes or ID numbers
    errors.extend(forbidden_fields(spec["fields"]))
    from .play import validate_party, validate_quiz
    quiz = validate_quiz(raw.get("quiz"), spec, errors)
    if quiz:
        spec["quiz"] = quiz
    if spec["kind"] == "party":
        if spec["fields"]:
            errors.append("a party light show has no questions (fields); people just open the link")
        spec["party"] = validate_party(raw.get("party"), errors)
    if spec["kind"] == "site":
        from .site import validate_site
        spec["site"], site_errors = validate_site(raw.get("site"), spec["title"], bool([f for f in spec["fields"] if f["type"] != "info"]))
        errors.extend(site_errors)
    return spec, errors


def errors_before(errors, label):
    """True if this field already has a problem (no options), so its answer can't be checked yet."""
    return any(f"field '{label}' (" in e for e in errors)


def window_state(spec, now=None):
    """'not_open' | 'open' | 'closed' based on the schedule in the spec."""
    now = now or datetime.now()
    if spec.get("opens_at") and now < parse_dt(spec["opens_at"]):
        return "not_open"
    if spec.get("closes_at") and now > parse_dt(spec["closes_at"]):
        return "closed"
    return "open"


def check_file(field, filename: str, head: bytes, size: int):
    """Return an error string or None. Runs on the server, never trusts the browser."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    accept = field.get("accept") or []
    if accept and ext not in accept:
        return f"'{filename}': only {', '.join(accept)} files are allowed"
    if size > field.get("max_mb", DEFAULT_FILE_MB) * 1024 * 1024:
        return f"'{filename}' is larger than {field.get('max_mb')} MB"
    if size == 0:
        return f"'{filename}' is empty"
    sigs = MAGIC.get(ext)
    if sigs and not any(head.startswith(s) for s in sigs):
        return f"'{filename}' does not look like a real {ext} file"
    return None


def check_value(field, value):
    """Validate one non-file answer. Returns (clean_value, error)."""
    t = field["type"]
    if t == "checkbox":
        vals = value if isinstance(value, list) else ([value] if value else [])
        if any(v not in field.get("options", []) for v in vals):
            return None, f"{field['label']}: invalid choice"
        if field["required"] and not vals:
            return None, f"{field['label']} is required"
        return vals, None
    value = (value or "").strip() if isinstance(value, str) else value
    if not value:
        return ("", f"{field['label']} is required") if field["required"] else ("", None)
    if t in ("select", "radio") and value not in field.get("options", []):
        return None, f"{field['label']}: invalid choice"
    if t == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return None, f"{field['label']}: invalid email"
    if t == "phone":
        cleaned = re.sub(r"[\s\-().]", "", value)
        if not re.fullmatch(r"\+?\d{7,15}", cleaned):
            return None, f"{field['label']}: enter a phone number using digits (7 to 15), optionally starting with +"
        return cleaned, None
    if t == "number":
        try:
            num = float(value)
        except ValueError:
            return None, f"{field['label']}: must be a number"
        if ("min" in field and num < field["min"]) or ("max" in field and num > field["max"]):
            return None, f"{field['label']}: must be between {field.get('min', '…')} and {field.get('max', '…')}"
        return (int(num) if num.is_integer() else num), None
    if t == "rating":
        if str(value) not in {"1", "2", "3", "4", "5"}:
            return None, f"{field['label']}: rating must be 1-5"
        return int(value), None
    if t == "date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None, f"{field['label']}: invalid date"
    return str(value)[:10000], None


def summarize(spec, rows):
    """Per-question summary of responses (what the Summary tab and poll results show).
    rows: list of decoded `data` dicts."""
    out = []
    for f in spec["fields"]:
        if f["type"] == "info":
            continue
        vals = [r.get(f["id"]) for r in rows if r.get(f["id"]) not in (None, "", [])]
        item = {"id": f["id"], "label": f["label"], "type": f["type"], "answered": len(vals)}
        if f["type"] in CHOICE_TYPES:
            counts = {o: 0 for o in f.get("options", [])}
            for v in vals:
                for x in (v if isinstance(v, list) else [v]):
                    if x in counts:
                        counts[x] += 1
            item["counts"] = counts
            if f.get("limits"):
                item["limits"] = f["limits"]
        elif f["type"] == "rating":
            nums = [int(v) for v in vals if str(v).isdigit()]
            item["average"] = round(sum(nums) / len(nums), 2) if nums else None
            item["counts"] = {str(i): nums.count(i) for i in range(1, 6)}
        elif f["type"] == "number":
            nums = [float(v) for v in vals if isinstance(v, (int, float))]
            if nums:
                item.update(average=round(sum(nums) / len(nums), 2), min=min(nums), max=max(nums), total=round(sum(nums), 2))
        elif f["type"] in ("short_text", "long_text"):
            item["samples"] = [str(v)[:280] for v in vals[-6:]][::-1]
        if f["type"] in RECORD_TYPES:
            item["record"] = True       # shown per person, not as a summary
        out.append(item)
    return out


def describe_rules(spec):
    """One-line plain description of how an app behaves (shown to respondents and owners)."""
    bits = []
    if spec.get("anonymous"):
        bits.append("anonymous")
    if spec.get("responses_per_person") == "many":
        bits.append("you can send more than one")
    if spec.get("max_responses"):
        bits.append(f"{spec['max_responses']} places")
    if spec.get("statuses"):
        bits.append("tracked: " + " → ".join(spec["statuses"]))
    if spec.get("show_results") != "never":
        bits.append("results visible")
    return bits
