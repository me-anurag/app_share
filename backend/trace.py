"""Traces: the full, saved record of what the agents and the platform did for each app.

One **journey** per app, from the first request typed by its owner to sharing, responses, reviews and reminders.
Inside a journey:
  runs    one agent turn (Builder, Data, Design, Access, Insights, Review, Reminder), nested by parent run
  steps   inside a run, in order: model calls (tokens, cost, time, stop reason), tool calls (arguments and result),
          Validator verdicts, and retries of failed API calls
  events  what happened to the app around the agents: created, edited, shared, published, responses, reviews,
          reminders, status changes
Plus the measured parameters of the app itself (fields, rules, audience…) in `journeys.params`.

Rules this module keeps:
  - Measured only. Times come from the clock, tokens from the API's usage report; cost = tokens x the PRICES table
    below (labelled as calculated, never as billed). Unknown models have no cost rather than a guessed one.
  - Redacted before saving, not when shown: answers people gave, uploaded file text, and full email addresses never
    reach this database. Anonymous apps never get respondent names.
  - Never in the way: any failure here is swallowed and counted, so tracing can't break an agent or a request.
  - Only real activity. Rehearsal/simulation lives in the Control Center's browser and never reaches the server.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time

from .db import DATA_DIR

PATH = os.path.join(DATA_DIR, "traces.db")

# USD per million tokens. Source: Anthropic's published model pricing (Claude API skill docs, checked 2026-11-25).
# Cache writes are the 5-minute TTL rate (1.25x input); cache reads as listed per model.
# Override with APPSHARE_PRICES='{"model": {"in":..,"out":..,"cache_write":..,"cache_read":..}}'.
PRICES = {
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_write": 5.00, "cache_read": 0.20},
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cache_write": 0.125, "cache_read": 0.01},
}
try:
    PRICES.update(json.loads(os.environ.get("APPSHARE_PRICES") or "{}"))
except ValueError:
    pass
PRICE_NOTE = "calculated from measured tokens x published per-token prices (not a bill)"

# Agents whose model output may quote people's answers or files: their thinking text is not stored.
SENSITIVE_AGENTS = {"review", "insights", "reminder"}
# Tools that run the Validator: each call also becomes a "validator" step with its verdict.
VALIDATOR_TOOLS = {"check_fields", "submit_fields", "save_app"}

_lock = threading.RLock()
_conn = None
FAILURES = {"count": 0, "last": ""}

SCHEMA = """
CREATE TABLE IF NOT EXISTS journeys (
  id TEXT PRIMARY KEY, app_id INTEGER UNIQUE, session_id INTEGER, title TEXT, owner TEXT, origin TEXT,
  request TEXT, params TEXT, created_at INTEGER, updated_at INTEGER);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, journey_id TEXT, parent_id TEXT, agent TEXT, round INTEGER, trigger TEXT,
  input TEXT, output TEXT, model TEXT, prompt_sha TEXT, status TEXT, error TEXT,
  started_at INTEGER, ended_at INTEGER, ms INTEGER);
CREATE TABLE IF NOT EXISTS steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, journey_id TEXT, seq INTEGER, loop_step INTEGER,
  kind TEXT, name TEXT, started_at INTEGER, ms INTEGER, ok INTEGER, model TEXT, stop_reason TEXT,
  tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0, cache_read INTEGER DEFAULT 0, cache_write INTEGER DEFAULT 0,
  cost REAL, detail TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, journey_id TEXT, app_id INTEGER, type TEXT, ts INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS prompts (sha TEXT PRIMARY KEY, agent TEXT, text TEXT, tools TEXT);
CREATE INDEX IF NOT EXISTS ix_runs_j ON runs(journey_id);
CREATE INDEX IF NOT EXISTS ix_steps_r ON steps(run_id);
CREATE INDEX IF NOT EXISTS ix_steps_j ON steps(journey_id);
CREATE INDEX IF NOT EXISTS ix_events_j ON events(journey_id);
"""


def now_ms():
    return int(time.time() * 1000)


def _db():
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = sqlite3.connect(PATH, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode = WAL")
        _conn.executescript(SCHEMA)
        # Runs still "running" from a previous server process were cut off (server stopped mid-run): say so.
        # It ends where its last recorded step ended, so timelines don't stretch to "now".
        _conn.execute("""UPDATE runs SET status = 'interrupted', error = 'server stopped during this run',
                           ended_at = COALESCE((SELECT MAX(s.started_at + COALESCE(s.ms, 0)) FROM steps s WHERE s.run_id = runs.id), started_at),
                           ms = COALESCE((SELECT MAX(s.started_at + COALESCE(s.ms, 0)) FROM steps s WHERE s.run_id = runs.id), started_at) - started_at
                         WHERE status = 'running'""")
    return _conn


def safe(fn):
    """Tracing must never break the thing being traced."""
    def wrapper(*a, **k):
        try:
            with _lock:
                return fn(*a, **k)
        except Exception as e:  # noqa: BLE001
            FAILURES["count"] += 1
            FAILURES["last"] = f"{fn.__name__}: {type(e).__name__}: {e}"
            print(f"[trace] {FAILURES['last']}", file=sys.stderr)
            return None
    wrapper.__name__ = fn.__name__
    return wrapper


# --------------------------------------------------------------------------- redaction

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def mask_email(text):
    return EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)


def scrub(value, depth=0, n=600):
    """Bounded, email-masked copy of any JSON-like value."""
    if depth > 6:
        return "…"
    if isinstance(value, str):
        value = mask_email(value)
        return value if len(value) <= n else value[: n - 1] + "…"
    if isinstance(value, dict):
        return {str(k): scrub(v, depth + 1, n) for k, v in list(value.items())[:60]}
    if isinstance(value, (list, tuple)):
        out = [scrub(v, depth + 1, n) for v in list(value)[:40]]
        if len(value) > 40:
            out.append(f"… {len(value) - 40} more")
        return out
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return scrub(str(value), depth, n)


def _shape(answer):
    """What an answer looks like, without what it says."""
    if isinstance(answer, dict) and ("file" in answer or "file_id" in answer):
        return {"file": True, "pages": answer.get("pages"), "words": answer.get("words"), "size_bytes": answer.get("size_bytes") or answer.get("size")}
    if isinstance(answer, list):
        return f"‹{len(answer)} choices›"
    if answer in (None, ""):
        return "‹empty›"
    return f"‹answer, {len(str(answer))} chars›"


def redact_result(tool, out):
    """Tool results that carry people's answers or file text keep only their shape and counts."""
    if not isinstance(out, dict):
        return scrub(out)
    if tool == "read_submission":
        return {"by": out.get("by"), "submitted_at": out.get("submitted_at"),
                "answers": {k: _shape(v) for k, v in (out.get("answers") or {}).items()},
                "_redacted": "answers and file text are not stored in traces"}
    if tool == "list_responses":
        rows = out.get("responses") or []
        return {"anonymous": out.get("anonymous"), "responses": len(rows),
                "per_response": [{"answers": len(r.get("answers") or {}), "status": r.get("status")} for r in rows[:40]],
                "_redacted": "answers and names are not stored in traces"}
    if tool == "save_app" and "spec" in out:
        out = {k: v for k, v in out.items() if k != "spec"}      # the spec itself is on the save_app call
    return scrub(out)


# --------------------------------------------------------------------------- app parameters

def app_params(spec):
    """Measured parameters of an app spec: what it collects and which rules it enforces."""
    spec = spec or {}
    fields =[f for f in (spec or {}).get("fields") or [] if isinstance(f, dict)]
    inputs = [f for f in fields if f.get("type") != "info"]
    by_type = {}
    for f in inputs:
        by_type[f.get("type")] = by_type.get(f.get("type"), 0) + 1
    options = sum(len(f.get("options") or []) for f in inputs)
    limited = sum(len(f.get("limits") or {}) for f in inputs)
    rules = {
        "deadline": bool(spec.get("closes_at")), "opens_later": bool(spec.get("opens_at")),
        "anonymous": bool(spec.get("anonymous")), "many_per_person": spec.get("responses_per_person") == "many",
        "total_cap": spec.get("max_responses") or 0, "per_option_places": limited,
        "results_visible": spec.get("show_results") not in (None, "never"), "statuses": len(spec.get("statuses") or []),
        "edit_after_submit": bool(spec.get("allow_edit_after_submit")),
    }
    active_rules = sum(1 for v in rules.values() if v)
    return {"fields": len(inputs), "required": sum(1 for f in inputs if f.get("required")), "by_type": by_type,
            "choice_options": options, "file_fields": by_type.get("file", 0), "rules": rules, "active_rules": active_rules,
            "title": spec.get("title"), "look": (spec.get("look") or {}).get("style")}


# --------------------------------------------------------------------------- journeys

def _new_id(prefix):
    return prefix + secrets.token_hex(5)


def _touch(jid, ts=None):
    _db().execute("UPDATE journeys SET updated_at = ? WHERE id = ?", (ts or now_ms(), jid))


@safe
def journey_for_session(session_id, app_id, owner, title=None, request=None):
    """The journey a Builder conversation belongs to (its app's journey once the app exists)."""
    db = _db()
    row = None
    if app_id:
        row = db.execute("SELECT id FROM journeys WHERE app_id = ?", (app_id,)).fetchone()
    if row is None:
        row = db.execute("SELECT id FROM journeys WHERE session_id = ? AND app_id IS NULL", (session_id,)).fetchone()
    if row:
        return row["id"]
    jid, ts = _new_id("j"), now_ms()
    db.execute("INSERT INTO journeys (id, app_id, session_id, title, owner, origin, request, params, created_at, updated_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
               (jid, app_id, session_id, title or "New app", owner, "edit" if app_id else "agent", scrub(request or "", n=2000), ts, ts))
    return jid


@safe
def journey_for_app(app_id, title=None, owner=None, origin="existing"):
    db = _db()
    row = db.execute("SELECT id FROM journeys WHERE app_id = ?", (app_id,)).fetchone()
    if row:
        return row["id"]
    jid, ts = _new_id("j"), now_ms()
    db.execute("INSERT INTO journeys (id, app_id, title, owner, origin, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (jid, app_id, title or f"App {app_id}", owner, origin, ts, ts))
    return jid


@safe
def attach_app(session_id, app_id, title):
    """The Builder just created the app of this conversation: its journey now belongs to that app."""
    _db().execute("UPDATE journeys SET app_id = ?, title = ? WHERE session_id = ? AND app_id IS NULL", (app_id, title, session_id))


@safe
def set_params(app_id, spec):
    jid = journey_for_app(app_id, spec.get("title"))
    _db().execute("UPDATE journeys SET params = ?, title = ?, updated_at = ? WHERE id = ?",
                  (json.dumps(app_params(spec)), spec.get("title"), now_ms(), jid))


def journey_of_run(run_id):
    with _lock:
        try:
            row = _db().execute("SELECT journey_id FROM runs WHERE id = ?", (run_id,)).fetchone()
            return row["journey_id"] if row else None
        except Exception:  # noqa: BLE001
            return None


# --------------------------------------------------------------------------- runs and steps

@safe
def set_prompt(run_id, agent, model, system, tools):
    """The instructions and tools this run's model had (stored once per distinct prompt)."""
    db = _db()
    sha = hashlib.sha256((system or "").encode()).hexdigest()[:16]
    db.execute("INSERT OR IGNORE INTO prompts (sha, agent, text, tools) VALUES (?, ?, ?, ?)",
               (sha, agent, system or "", json.dumps([t.get("name") for t in tools or []])))
    db.execute("UPDATE runs SET prompt_sha = ?, model = ? WHERE id = ?", (sha, model, run_id))


@safe
def start_run(run_id, agent, journey_id, parent_id, input_text, model=None, trigger="user"):
    db = _db()
    if journey_id is None and parent_id:
        row = db.execute("SELECT journey_id FROM runs WHERE id = ?", (parent_id,)).fetchone()
        journey_id = row["journey_id"] if row else None
    sha = None
    rnd = None
    if agent == "builder" and journey_id:
        rnd = db.execute("SELECT COUNT(*) FROM runs WHERE journey_id = ? AND agent = 'builder'", (journey_id,)).fetchone()[0] + 1
    elif parent_id:
        row = db.execute("SELECT round FROM runs WHERE id = ?", (parent_id,)).fetchone()
        rnd = row["round"] if row else None
    db.execute("INSERT OR REPLACE INTO runs (id, journey_id, parent_id, agent, round, trigger, input, model, prompt_sha, status, started_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)",
               (run_id, journey_id, parent_id, agent, rnd, trigger, scrub(input_text or "", n=4000), model, sha, now_ms()))
    if journey_id:
        _touch(journey_id)


@safe
def end_run(run_id, output=None, error=None):
    ts = now_ms()
    db = _db()
    row = db.execute("SELECT started_at, journey_id FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return
    db.execute("UPDATE runs SET output = ?, status = ?, error = ?, ended_at = ?, ms = ? WHERE id = ?",
               (scrub(output or "", n=4000), "error" if error else "ok", scrub(error, n=600) if error else None,
                ts, ts - row["started_at"], run_id))
    if row["journey_id"]:
        _touch(row["journey_id"], ts)


def _run_ctx(db, run_id):
    row = db.execute("SELECT journey_id, agent FROM runs WHERE id = ?", (run_id,)).fetchone()
    seq = db.execute("SELECT COUNT(*) FROM steps WHERE run_id = ?", (run_id,)).fetchone()[0] + 1
    return (row["journey_id"] if row else None), (row["agent"] if row else None), seq


def cost_of(model, tin, tout, cache_read=0, cache_write=0):
    if str(model or "").startswith("groq:"):
        return 0.0                         # Groq free tier: no charge (paid Groq tiers would need their own prices)
    p = PRICES.get(model)
    if not p:
        return None
    return round((tin * p["in"] + tout * p["out"] + cache_read * p["cache_read"] + cache_write * p["cache_write"]) / 1e6, 6)


@safe
def llm_step(run_id, loop_step, model, started, ms, resp):
    """One model call: measured tokens (uncached input, output, cache read, cache write), cost, time, what it said."""
    db = _db()
    jid, agent, seq = _run_ctx(db, run_id)
    usage = getattr(resp, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    text, thinking, calls = [], [], []
    for b in getattr(resp, "content", []) or []:
        if b.type == "text":
            text.append(b.text)
        elif b.type == "thinking":
            thinking.append(getattr(b, "thinking", "") or "")
        elif b.type == "tool_use":
            calls.append(b.name)
    think = "\n".join(t for t in thinking if t).strip()
    detail = {"text": scrub("\n".join(text).strip(), n=2000), "tool_calls": calls,
              "thinking_chars": len(think), "fallback_model": getattr(resp, "model", None) if getattr(resp, "model", model) != model else None}
    if think and agent not in SENSITIVE_AGENTS:
        detail["thinking"] = scrub(think, n=2500)
    elif think:
        detail["thinking_withheld"] = "may quote people's answers or files"
    db.execute("INSERT INTO steps (run_id, journey_id, seq, loop_step, kind, name, started_at, ms, ok, model, stop_reason, "
               "tokens_in, tokens_out, cache_read, cache_write, cost, detail) VALUES (?, ?, ?, ?, 'llm', ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
               (run_id, jid, seq, loop_step, model, started, ms, model, getattr(resp, "stop_reason", None),
                tin, tout, cr, cw, cost_of(model, tin, tout, cr, cw), json.dumps(detail, ensure_ascii=False)))


@safe
def retry_step(run_id, loop_step, model, attempt, error, wait_s):
    db = _db()
    jid, _, seq = _run_ctx(db, run_id)
    db.execute("INSERT INTO steps (run_id, journey_id, seq, loop_step, kind, name, started_at, ms, ok, model, detail) "
               "VALUES (?, ?, ?, ?, 'retry', ?, ?, ?, 0, ?, ?)",
               (run_id, jid, seq, loop_step, f"retry {attempt}", now_ms(), int(wait_s * 1000), model,
                json.dumps({"error": scrub(error, n=400), "waited_s": wait_s})))


@safe
def tool_step(run_id, loop_step, tool, args, out, is_error, started, ms):
    db = _db()
    jid, _, seq = _run_ctx(db, run_id)
    detail = {"args": scrub(args or {}, n=1500), "result": redact_result(tool, out)}
    if isinstance(args, dict) and args.get("reason"):
        detail["reason"] = scrub(args["reason"], n=500)          # the agent's own stated reason for this decision
    db.execute("INSERT INTO steps (run_id, journey_id, seq, loop_step, kind, name, started_at, ms, ok, detail) "
               "VALUES (?, ?, ?, ?, 'tool', ?, ?, ?, ?, ?)",
               (run_id, jid, seq, loop_step, tool, started, ms, 0 if is_error else 1, json.dumps(detail, ensure_ascii=False)))
    if tool in VALIDATOR_TOOLS:
        problems = (out or {}).get("problems") if isinstance(out, dict) else None
        if tool == "check_fields":
            passed = not problems
        else:
            passed = not is_error
        if tool == "save_app" and is_error and not problems:
            return                       # refused for another reason (no draft, no access): not a Validator verdict
        db.execute("INSERT INTO steps (run_id, journey_id, seq, loop_step, kind, name, started_at, ms, ok, detail) "
                   "VALUES (?, ?, ?, ?, 'validator', ?, ?, 0, ?, ?)",
                   (run_id, jid, seq + 1, loop_step, f"validator · {tool}", started + ms, 1 if passed else 0,
                    json.dumps({"verdict": "valid" if passed else "rejected", "problems": scrub(problems or [], n=300)})))


# --------------------------------------------------------------------------- app lifecycle (from monitor events)

LIFECYCLE = {"app_created", "app_updated", "app_shared", "app_status", "app_deleted", "submission", "submission_rejected",
             "status_changed", "review_done", "review_decided", "reminders_sent"}


def _event_detail(ev):
    t = ev["type"]
    keep = {
        "app_created": ("fields", "closes_at", "template"),
        "app_updated": (),
        "app_shared": ("audience", "targets", "link_access", "published"),
        "app_status": ("status",),
        "app_deleted": (),
        "submission": ("updated",),
        "submission_rejected": ("reasons", "blocked_file"),
        "status_changed": ("status",),
        "review_done": ("verdict", "ai_verdict", "guard", "summary", "flags"),
        "review_decided": ("decision",),
        "reminders_sent": ("count", "stage"),
    }[t]
    d = {k: ev.get(k) for k in keep if ev.get(k) is not None}
    if t == "submission":
        files = ev.get("files") or []
        d.update(files=len(files), file_bytes=sum(f.get("size") or 0 for f in files))
    if ev.get("user"):
        d["by"] = ev["user"]
    return scrub(d, n=400)


RESPONDENT_EVENTS = {"submission", "submission_rejected", "review_done"}


def _app_facts(app_id):
    """(owner's name, is it anonymous) from the app database."""
    from .db import connect
    conn = connect()
    try:
        row = conn.execute("SELECT u.name, a.spec FROM apps a JOIN users u ON u.id = a.owner_id WHERE a.id = ?", (app_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None, False
    try:
        return row["name"], bool(json.loads(row["spec"]).get("anonymous"))
    except ValueError:
        return row["name"], False


@safe
def on_event(ev):
    if ev.get("type") not in LIFECYCLE or not ev.get("app_id"):
        return
    origin = "template" if ev.get("template") else ("blank" if ev["type"] == "app_created" else "existing")
    owner, anonymous = _app_facts(ev["app_id"])
    jid = journey_for_app(ev["app_id"], ev.get("title"), owner, origin)       # the owner comes from the app, never from the event
    detail = _event_detail(ev)
    if anonymous and ev["type"] in RESPONDENT_EVENTS:
        detail.pop("by", None)                 # anonymous app: no respondent name in the trace, whatever the emitter sent
    _db().execute("INSERT INTO events (journey_id, app_id, type, ts, detail) VALUES (?, ?, ?, ?, ?)",
                  (jid, ev["app_id"], ev["type"], ev["ts"], json.dumps(detail, ensure_ascii=False)))
    _touch(jid, ev["ts"])
    if ev["type"] in ("app_created", "app_updated"):
        # The request that emitted this hasn't committed yet: read the saved spec a moment later.
        t = threading.Timer(1.5, _refresh_params, args=(ev["app_id"],))
        t.daemon = True
        t.start()


@safe
def _refresh_params(app_id):
    from .db import connect
    conn = connect()
    try:
        row = conn.execute("SELECT spec FROM apps WHERE id = ?", (app_id,)).fetchone()
    finally:
        conn.close()
    if row:
        spec = json.loads(row["spec"])
        _db().execute("UPDATE journeys SET params = ?, title = ? WHERE app_id = ?", (json.dumps(app_params(spec)), spec.get("title"), app_id))


from . import monitor as _monitor  # noqa: E402

_monitor.HOOKS.append(on_event)


# --------------------------------------------------------------------------- reading

def _totals(db, where, arg):
    r = db.execute(f"""SELECT COUNT(*) AS steps,
          SUM(kind = 'llm') AS llm_calls, SUM(kind = 'tool') AS tool_calls, SUM(kind = 'retry') AS retries,
          SUM(kind = 'validator' AND ok = 1) AS valid, SUM(kind = 'validator' AND ok = 0) AS rejected,
          SUM(kind = 'tool' AND ok = 0) AS tool_errors,
          COALESCE(SUM(tokens_in), 0) AS tokens_in, COALESCE(SUM(tokens_out), 0) AS tokens_out,
          COALESCE(SUM(cache_read), 0) AS cache_read, COALESCE(SUM(cache_write), 0) AS cache_write,
          SUM(cost) AS cost, COALESCE(SUM(CASE WHEN kind = 'llm' THEN ms END), 0) AS model_ms,
          COALESCE(SUM(CASE WHEN kind = 'tool' THEN ms END), 0) AS tool_ms
        FROM steps WHERE {where}""", (arg,)).fetchone()
    out = {k: (r[k] or 0) for k in r.keys()}
    out["cost"] = round(out["cost"], 6) if r["cost"] is not None else None
    return out


def list_journeys(limit=50):
    with _lock:
        db = _db()
        rows = db.execute("SELECT * FROM journeys ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for j in rows:
            t = _totals(db, "journey_id = ?", j["id"])
            ev = {r["type"]: r["n"] for r in db.execute("SELECT type, COUNT(*) AS n FROM events WHERE journey_id = ? GROUP BY type", (j["id"],))}
            runs = db.execute("SELECT COUNT(*) AS n, SUM(status = 'running') AS running, SUM(status = 'error') AS errors FROM runs WHERE journey_id = ?", (j["id"],)).fetchone()
            out.append({"id": j["id"], "app_id": j["app_id"], "title": j["title"], "owner": j["owner"], "origin": j["origin"],
                        "created_at": j["created_at"], "updated_at": j["updated_at"], "runs": runs["n"], "running": runs["running"] or 0,
                        "run_errors": runs["errors"] or 0, "events": ev, "totals": t})
        return out


def get_journey(jid):
    with _lock:
        db = _db()
        j = db.execute("SELECT * FROM journeys WHERE id = ?", (jid,)).fetchone()
        if not j:
            return None
        runs = []
        for r in db.execute("SELECT * FROM runs WHERE journey_id = ? ORDER BY started_at", (jid,)):
            steps = [{**{k: s[k] for k in s.keys() if k != "detail"}, "detail": json.loads(s["detail"] or "{}")}
                     for s in db.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY seq, id", (r["id"],))]
            runs.append({**dict(r), "totals": _totals(db, "run_id = ?", r["id"]), "steps": steps})
        events = [{**{k: e[k] for k in e.keys() if k != "detail"}, "detail": json.loads(e["detail"] or "{}")}
                  for e in db.execute("SELECT * FROM events WHERE journey_id = ? ORDER BY ts, id", (jid,))]
        return {**dict(j), "params": json.loads(j["params"]) if j["params"] else None,
                "totals": _totals(db, "journey_id = ?", jid), "runs": runs, "events": events,
                "cost_note": PRICE_NOTE, "prices": PRICES}


# --------------------------------------------------------------------------- the owner's view ("How this app was built")

def _last_call(run, tool):
    calls = [s for s in run["steps"] if s["kind"] == "tool" and s["name"] == tool and s["ok"]]
    return calls[-1]["detail"] if calls else None


def _did(agent, run):
    """One plain sentence for what an agent decided, plus its stated reason, from its final hand-back."""
    if agent == "data":
        d = _last_call(run, "submit_fields")
        if not d:
            return None, None
        a = d["args"]
        fields = [f.get("label") for f in a.get("fields") or [] if isinstance(f, dict) and f.get("type") != "info"]
        rules = []
        if a.get("closes_at"):
            rules.append(f"closes {a['closes_at'].replace('T', ' ')}")
        if a.get("anonymous"):
            rules.append("anonymous")
        if a.get("max_responses"):
            rules.append(f"{a['max_responses']} places")
        limited = [f for f in a.get("fields") or [] if isinstance(f, dict) and f.get("limits")]
        if limited:
            rules.append("places per option")
        if a.get("statuses"):
            rules.append("statuses " + " → ".join(a["statuses"]))
        if a.get("responses_per_person") == "many":
            rules.append("many responses per person")
        return (f"Chose {len(fields)} question{'s' if len(fields) != 1 else ''}: {', '.join(fields[:8])}"
                + (f". Rules: {', '.join(rules)}" if rules else "") + "."), d.get("reason")
    if agent == "design":
        d = _last_call(run, "submit_design")
        if not d:
            return None, None
        a = d["args"]
        look = " + ".join(x for x in (a.get("style"), a.get("pattern")) if x)
        return f"Titled it “{a.get('title')}”, wrote the instructions, picked {look or 'a'} look in {a.get('theme_color')}.", d.get("reason")
    if agent == "access":
        d = _last_call(run, "submit_access")
        if not d:
            return None, None
        who = [f"{s.get('name') or ('everyone' if s.get('type') == 'org' else 'anyone with the link')} ({s.get('role')})"
               for s in d["args"].get("share_suggestions") or [] if isinstance(s, dict)]
        return f"Suggested sharing with {', '.join(who) or 'nobody yet'}. Nothing is shared until you press Share.", d.get("reason")
    if agent == "builder":
        saves = [s for s in run["steps"] if s["kind"] == "tool" and s["name"] == "save_app"]
        asked = [s["name"].split("_")[1] for s in run["steps"] if s["kind"] == "tool" and s["name"].startswith("ask_")]
        did = (f"Briefed the {', '.join(dict.fromkeys(asked))} agent{'s' if len(set(asked)) > 1 else ''} and put their work together."
               if asked else "Made the change itself." if saves else "Answered without changing the app.")
        reason = next((s["detail"].get("reason") for s in reversed(saves) if s["ok"] and s["detail"].get("reason")), None)
        return did, reason
    return None, None


def story(app_id):
    """What the app's owner may see about how it was made: requests, what each agent decided and why, Validator
    checks, time and calculated cost. Built only from the (already redacted) trace."""
    with _lock:
        row = _db().execute("SELECT id FROM journeys WHERE app_id = ?", (app_id,)).fetchone()
    if not row:
        return {"origin": None, "rounds": []}
    J = get_journey(row["id"])
    rounds = []
    for b in [r for r in J["runs"] if r["agent"] == "builder"]:
        kids = [r for r in J["runs"] if r["parent_id"] == b["id"]]
        steps = []
        for agent, run in [("builder", b)] + [(k["agent"], k) for k in kids]:
            did, reason = _did(agent, run)
            if did:
                steps.append({"agent": agent, "did": did, "reason": reason, "ms": run["ms"], "status": run["status"]})
        checks = [s for r in [b, *kids] for s in r["steps"] if s["kind"] == "validator"]
        fixed = [p for s in checks if not s["ok"] for p in s["detail"].get("problems") or []]
        t = [r["totals"] for r in [b, *kids]]
        cost = sum(x["cost"] or 0 for x in t)
        rounds.append({"round": b["round"], "request": b["input"], "when": b["started_at"], "ms": b["ms"], "status": b["status"],
                       "reply": b["output"], "steps": steps,
                       "validator": {"checks": len(checks), "rejected": sum(1 for s in checks if not s["ok"]), "problems_fixed": fixed[:6]},
                       "model_calls": sum(x["llm_calls"] for x in t), "cost": round(cost, 4),
                       "agents": len({r["agent"] for r in [b, *kids]})})
    after = {"shared": sum(1 for e in J["events"] if e["type"] == "app_shared"),
             "reviews": sum(1 for r in J["runs"] if r["agent"] == "review"),
             "reminders": sum(1 for r in J["runs"] if r["agent"] == "reminder"),
             "questions": sum(1 for r in J["runs"] if r["agent"] == "insights"),
             "cost": round(sum(r["totals"]["cost"] or 0 for r in J["runs"] if r["agent"] in ("review", "reminder", "insights")), 4)}
    return {"origin": J["origin"], "since": J["created_at"], "rounds": rounds[::-1], "after": after, "cost_note": PRICE_NOTE}


def get_prompt(sha):
    with _lock:
        row = _db().execute("SELECT * FROM prompts WHERE sha = ?", (sha,)).fetchone()
        return dict(row) if row else None


def health():
    return {"path": PATH, "failures": FAILURES["count"], "last_failure": FAILURES["last"]}
