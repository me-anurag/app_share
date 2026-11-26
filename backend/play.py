"""Play: quizzes with scores and leaderboards, host-led live quizzes, and the party light show.

Spec additions (checked here, called from spec.validate_spec):
  quiz question  a radio/select/checkbox field with `answer` (the right option; a list for checkbox) and `points`
  spec.quiz      {mode: "self" | "host", seconds: 5-120 per question (host mode), reveal: "after_submit" | "end" | "never",
                  leaderboard: bool}
  spec.party     kind "party": {palette: [#hex…], scenes: [...], scene, bpm, strobe, message}

Live state (host quiz and party) lives in `live_state`; players in `players`; host-quiz answers in `live_answers`.
Everything is decided on the server: the right answers never reach a player's phone before the reveal, points are
computed here, and only an editor of the app can move the game on or change the lights. Phones stay in sync by
computing the light pattern from the server's clock (one small message per change, not per flash).
"""
import json
import re
import time

SCENES = {
    "solid": "one steady colour",
    "pulse": "fades in and out on the beat",
    "chase": "steps through the colours on the beat",
    "wave": "a colour wave rolls across the room, phone by phone",
    "rainbow": "slowly cycles through every colour",
    "sparkle": "phones twinkle at random on the beat",
    "strobe": "flashes on the beat — max 3 per second, only if the host allows strobe",
}
DEFAULT_PALETTE = ["#ff2d55", "#ffcc00", "#34c759", "#0a84ff", "#bf5af2"]
MAX_FLASH_HZ = 3            # WCAG 2.3.1: no more than three flashes in any one second
REVEAL = ("after_submit", "end", "never")
PHASES = ("lobby", "question", "reveal", "board", "end")
NAME_MAX = 24

TABLES = """
CREATE TABLE IF NOT EXISTS live_state (
    app_id INTEGER PRIMARY KEY REFERENCES apps(id) ON DELETE CASCADE,
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    pkey TEXT NOT NULL,                 -- u<user id> or the device cookie of a guest
    name TEXT NOT NULL DEFAULT '',
    seat INTEGER NOT NULL DEFAULT 0,    -- join order: places the phone in a light wave
    last_seen REAL NOT NULL DEFAULT 0,
    UNIQUE (app_id, pkey)
);
CREATE TABLE IF NOT EXISTS live_answers (
    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    q INTEGER NOT NULL,
    answer TEXT NOT NULL,
    ms INTEGER NOT NULL,
    points INTEGER NOT NULL,
    PRIMARY KEY (app_id, player_id, q)
);
"""


def now_ms():
    return int(time.time() * 1000)


# --------------------------------------------------------------------------- spec checks

def validate_question(f, raw, errors):
    """Copy a checked `answer` / `points` onto a choice field (in place)."""
    if raw.get("answer") in (None, "", []):
        return
    label = f["label"]
    if f["type"] not in ("radio", "select", "checkbox"):
        errors.append(f"field '{label}': only choice questions (radio, select, checkbox) can have a right answer")
        return
    ans = raw["answer"]
    if f["type"] == "checkbox":
        ans = [str(a).strip() for a in (ans if isinstance(ans, list) else [ans])]
        if not ans or any(a not in f["options"] for a in ans):
            errors.append(f"field '{label}': answer must be among its options")
            return
    else:
        ans = str(ans[0] if isinstance(ans, list) and ans else ans).strip()
        if ans not in f["options"]:
            errors.append(f"field '{label}': answer “{ans[:40]}” is not one of its options")
            return
    try:
        pts = int(raw.get("points") or 1)
    except (TypeError, ValueError):
        pts = 1
    f["answer"], f["points"] = ans, max(1, min(pts, 100))


def validate_quiz(raw, spec, errors):
    scored = [f for f in spec["fields"] if "answer" in f]
    if spec["kind"] == "quiz" and not scored:
        errors.append("a quiz needs at least one question with a right answer (set `answer` on a choice field)")
    if not scored:
        return None
    raw = raw if isinstance(raw, dict) else {}
    mode = "host" if raw.get("mode") == "host" else "self"
    try:
        seconds = int(raw.get("seconds") or 20)
    except (TypeError, ValueError):
        seconds = 20
    q = {"mode": mode, "seconds": max(5, min(seconds, 120)),
         "reveal": raw.get("reveal") if raw.get("reveal") in REVEAL else "after_submit",
         "leaderboard": raw.get("leaderboard", True) is not False}
    if mode == "host":
        extra = [f for f in spec["fields"] if f["type"] not in ("info",) and "answer" not in f]
        if extra:
            errors.append("a host-led quiz shows one question at a time: every question needs a right answer "
                          f"(no answer on: {', '.join(f['label'][:30] for f in extra[:3])}); players type a nickname when they join")
    return q


def validate_party(raw, errors):
    raw = raw if isinstance(raw, dict) else {}
    pal = []
    for c in raw.get("palette") or DEFAULT_PALETTE:
        c = str(c).strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", c) and c.lower() not in pal:
            pal.append(c.lower())
    if not pal:
        errors.append("party.palette needs at least one colour like #ff2d55")
        pal = list(DEFAULT_PALETTE)
    strobe = bool(raw.get("strobe", False))
    scenes = [s for s in (raw.get("scenes") or list(SCENES)) if s in SCENES and (strobe or s != "strobe")]
    if not scenes:
        scenes = [s for s in SCENES if s != "strobe"]
    try:
        bpm = int(raw.get("bpm") or 120)
    except (TypeError, ValueError):
        bpm = 120
    scene = raw.get("scene") if raw.get("scene") in scenes else scenes[0]
    return {"palette": pal[:8], "scenes": scenes, "scene": scene, "bpm": max(40, min(bpm, MAX_FLASH_HZ * 60)),
            "strobe": strobe, "message": str(raw.get("message") or "").strip()[:80]}


def public_spec(spec, can_see_answers):
    """The spec as sent to a phone: right answers removed unless the viewer may edit the app."""
    if can_see_answers or not any("answer" in f for f in spec.get("fields", [])):
        return spec
    out = dict(spec)
    out["fields"] = [{k: v for k, v in f.items() if k not in ("answer",)} for f in spec["fields"]]
    return out


# --------------------------------------------------------------------------- self-paced scoring

def is_right(f, value):
    if "answer" not in f:
        return None
    if f["type"] == "checkbox":
        return sorted(value or []) == sorted(f["answer"])
    return value == f["answer"]


def score(spec, data):
    """(points, max_points, per-question [{id, right}])."""
    got, best, per = 0, 0, []
    for f in spec["fields"]:
        if "answer" not in f:
            continue
        right = bool(is_right(f, data.get(f["id"])))
        best += f["points"]
        got += f["points"] if right else 0
        per.append({"id": f["id"], "right": right})
    return got, best, per


def review(spec, data):
    """What a player sees after a self-paced quiz when answers are revealed."""
    return [{"label": f["label"], "yours": data.get(f["id"]), "answer": f["answer"], "right": bool(is_right(f, data.get(f["id"]))),
             "points": f["points"]} for f in spec["fields"] if "answer" in f]


def leaderboard(conn, app, spec, limit=10):
    """Self-paced quiz: best scores first, ties broken by who finished first."""
    rows = conn.execute(
        "SELECT s.id, s.data, s.created_at, s.updated_at, s.guest_name, u.name FROM submissions s "
        "LEFT JOIN users u ON u.id = s.user_id WHERE s.app_id = ?", (app["id"],)).fetchall()
    scored = []
    for r in rows:
        data = json.loads(r["data"])
        pts, best, _ = score(spec, data)
        scored.append({"sid": r["id"], "points": pts, "max": best, "at": r["updated_at"] or r["created_at"],
                       "name": _display_name(spec, data, r)})
    scored.sort(key=lambda x: (-x["points"], x["at"]))
    for i, s in enumerate(scored):
        s["rank"] = i + 1
    return scored if limit is None else scored[:limit]


def _display_name(spec, data, row):
    if spec.get("anonymous"):
        return "Player"
    for f in spec["fields"]:
        if f["type"] == "short_text" and re.search(r"name", f["id"] + " " + f["label"], re.I) and data.get(f["id"]):
            return str(data[f["id"]])[:NAME_MAX]
    return (row["name"] or row["guest_name"] or "Player")[:NAME_MAX]


# --------------------------------------------------------------------------- live state

def init(conn):
    conn.executescript(TABLES)


def get_state(conn, app_id, spec):
    row = conn.execute("SELECT state FROM live_state WHERE app_id = ?", (app_id,)).fetchone()
    if row:
        return json.loads(row["state"])
    if spec.get("kind") == "party":
        p = spec.get("party") or {}
        return {"scene": p.get("scene", "pulse"), "colors": p.get("palette", DEFAULT_PALETTE)[:3], "bpm": p.get("bpm", 120),
                "started_at": now_ms(), "message": p.get("message", ""), "on": True}
    return {"phase": "lobby", "q": -1, "started_at": 0}


def set_state(conn, app_id, state):
    conn.execute("INSERT INTO live_state (app_id, state, updated_at) VALUES (?, ?, datetime('now')) "
                 "ON CONFLICT(app_id) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at",
                 (app_id, json.dumps(state)))


def questions(spec):
    return [f for f in spec["fields"] if "answer" in f]


def join(conn, app_id, pkey, name):
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:NAME_MAX]
    row = conn.execute("SELECT * FROM players WHERE app_id = ? AND pkey = ?", (app_id, pkey)).fetchone()
    if row:
        if name and name != row["name"]:
            conn.execute("UPDATE players SET name = ?, last_seen = ? WHERE id = ?", (name, time.time(), row["id"]))
        return row["id"]
    seat = conn.execute("SELECT COUNT(*) FROM players WHERE app_id = ?", (app_id,)).fetchone()[0]
    return conn.execute("INSERT INTO players (app_id, pkey, name, seat, last_seen) VALUES (?, ?, ?, ?, ?)",
                        (app_id, pkey, name, seat, time.time())).lastrowid


def seen(conn, app_id, pkey):
    """Mark a phone as present (at most every 10 s, so 50 phones don't mean 50 writes a second)."""
    row = conn.execute("SELECT id, last_seen, seat, name FROM players WHERE app_id = ? AND pkey = ?", (app_id, pkey)).fetchone()
    if row and time.time() - row["last_seen"] > 10:
        conn.execute("UPDATE players SET last_seen = ? WHERE id = ?", (time.time(), row["id"]))
    return row


def present(conn, app_id, window=45):
    return conn.execute("SELECT COUNT(*) FROM players WHERE app_id = ? AND last_seen > ?", (app_id, time.time() - window)).fetchone()[0]


def host_scores(conn, app_id, limit=10):
    rows = conn.execute(
        "SELECT p.id, p.name, COALESCE(SUM(a.points), 0) AS points, COUNT(a.q) AS answered, "
        "COALESCE(SUM(CASE WHEN a.points > 0 THEN 1 ELSE 0 END), 0) AS right_n FROM players p "
        "LEFT JOIN live_answers a ON a.player_id = p.id AND a.app_id = p.app_id WHERE p.app_id = ? AND p.name != '' "
        "GROUP BY p.id ORDER BY points DESC, p.id ASC", (app_id,)).fetchall()
    out = [{"pid": r["id"], "name": r["name"], "points": r["points"], "right": r["right_n"], "rank": i + 1} for i, r in enumerate(rows)]
    return out if limit is None else out[:limit]


def control(conn, app, spec, action, body):
    """The host moves the game on (or changes the lights). Returns the new state."""
    st = get_state(conn, app["id"], spec)
    if spec.get("kind") == "party":
        p = spec.get("party") or {}
        if action == "party":
            if body.get("scene") is not None:
                if body["scene"] not in p.get("scenes", []):
                    raise ValueError(f"scene must be one of {', '.join(p.get('scenes', []))}")
                st["scene"] = body["scene"]
            if body.get("colors") is not None:
                cols = [c.lower() for c in body["colors"] if re.fullmatch(r"#[0-9a-fA-F]{6}", str(c))][:6]
                if not cols:
                    raise ValueError("colors must be like #ff2d55")
                st["colors"] = cols
            if body.get("bpm") is not None:
                st["bpm"] = max(40, min(int(body["bpm"]), MAX_FLASH_HZ * 60))
            if body.get("message") is not None:
                st["message"] = str(body["message"]).strip()[:80]
            if body.get("on") is not None:
                st["on"] = bool(body["on"])
            st["started_at"] = now_ms()          # everyone restarts the pattern together
        elif action == "reset":
            conn.execute("DELETE FROM live_state WHERE app_id = ?", (app["id"],))
            return get_state(conn, app["id"], spec)
        else:
            raise ValueError("a party app takes the 'party' or 'reset' action")
        set_state(conn, app["id"], st)
        return st

    qs = questions(spec)
    if not qs or (spec.get("quiz") or {}).get("mode") != "host":
        raise ValueError("this app is not a host-led quiz")
    secs = spec["quiz"]["seconds"]
    if action == "reset":
        conn.execute("DELETE FROM live_answers WHERE app_id = ?", (app["id"],))
        conn.execute("DELETE FROM live_state WHERE app_id = ?", (app["id"],))
        return get_state(conn, app["id"], spec)
    if action in ("start", "next"):
        nq = 0 if action == "start" else st["q"] + 1
        if action == "start":
            conn.execute("DELETE FROM live_answers WHERE app_id = ?", (app["id"],))
        if nq >= len(qs):
            st = {"phase": "end", "q": len(qs) - 1, "started_at": now_ms()}
        else:
            st = {"phase": "question", "q": nq, "started_at": now_ms(), "ends_at": now_ms() + secs * 1000}
    elif action == "reveal":
        if st["phase"] != "question":
            raise ValueError("reveal comes after a question")
        st = {**st, "phase": "reveal"}
    elif action == "board":
        st = {**st, "phase": "board"}
    elif action == "end":
        st = {**st, "phase": "end"}
    else:
        raise ValueError("action must be start, reveal, board, next, end or reset")
    set_state(conn, app["id"], st)
    return st


def answer(conn, app, spec, player_id, q, choice):
    """A player's answer to the current host-led question: faster right answers score more (500-1000 × points)."""
    st = get_state(conn, app["id"], spec)
    qs = questions(spec)
    if st.get("phase") != "question" or st.get("q") != q:
        raise ValueError("That question is closed.")
    now = now_ms()
    if now > st["ends_at"] + 500:                 # half a second of grace for a slow network
        raise ValueError("Time's up for this question.")
    f = qs[q]
    if conn.execute("SELECT 1 FROM live_answers WHERE app_id = ? AND player_id = ? AND q = ?", (app["id"], player_id, q)).fetchone():
        raise ValueError("You've already answered this one.")
    value = choice if f["type"] != "checkbox" else (choice if isinstance(choice, list) else [choice])
    if (f["type"] == "checkbox" and any(v not in f["options"] for v in value)) or (f["type"] != "checkbox" and value not in f["options"]):
        raise ValueError("Pick one of the options.")
    total = max(1, st["ends_at"] - st["started_at"])
    left = max(0, min(total, st["ends_at"] - now))
    pts = round(f["points"] * 1000 * (0.5 + 0.5 * left / total)) if is_right(f, value) else 0
    conn.execute("INSERT INTO live_answers (app_id, player_id, q, answer, ms, points) VALUES (?, ?, ?, ?, ?, ?)",
                 (app["id"], player_id, q, json.dumps(value), now - st["started_at"], pts))
    return pts


def view(conn, app, spec, pkey, is_host):
    """What one screen needs right now. Players never get the right answer before the reveal."""
    st = get_state(conn, app["id"], spec)
    me = seen(conn, app["id"], pkey) if pkey else None
    out = {"server_now": now_ms(), "present": present(conn, app["id"]), "host": is_host,
           "me": {"joined": bool(me and (me["name"] or spec.get("kind") == "party")), "name": me["name"] if me else "",
                  "seat": me["seat"] if me else 0} if pkey else None}
    if spec.get("kind") == "party":
        out["party"] = st
        out["scenes"] = spec["party"]["scenes"]
        out["palette"] = spec["party"]["palette"]
        return out

    qs = questions(spec)
    out.update(phase=st["phase"], q=st["q"], total=len(qs), seconds=spec["quiz"]["seconds"])
    if 0 <= st["q"] < len(qs) and st["phase"] in ("question", "reveal", "board"):
        f = qs[st["q"]]
        out["question"] = {"label": f["label"], "help": f.get("help", ""), "options": f["options"], "type": f["type"],
                           "points": f["points"]}
        out["ends_at"] = st.get("ends_at")
        counts = {o: 0 for o in f["options"]}
        answered = 0
        for (a,) in conn.execute("SELECT answer FROM live_answers WHERE app_id = ? AND q = ?", (app["id"], st["q"])):
            answered += 1
            for v in (json.loads(a) if isinstance(json.loads(a), list) else [json.loads(a)]):
                if v in counts:
                    counts[v] += 1
        out["answered"] = answered
        if st["phase"] != "question" or is_host:
            out["answer"] = f["answer"] if (st["phase"] != "question") else None
            out["counts"] = counts if st["phase"] != "question" else None
        if me:
            mine = conn.execute("SELECT answer, points FROM live_answers WHERE app_id = ? AND player_id = ? AND q = ?",
                                (app["id"], me["id"], st["q"])).fetchone()
            out["mine"] = {"answer": json.loads(mine["answer"]), "points": mine["points"] if st["phase"] != "question" else None} if mine else None
    if is_host and st["phase"] == "question":
        out["answer_for_host"] = qs[st["q"]]["answer"]
    board = host_scores(conn, app["id"], None)
    out["joined"] = len(board)
    if st["phase"] in ("board", "end") or is_host:
        out["leaderboard"] = board[:10]
    if me:
        mine = next((b for b in board if b["pid"] == me["id"]), None)
        out["me"]["points"] = mine["points"] if mine and st["phase"] != "question" else (
            sum(r["points"] for r in conn.execute("SELECT points FROM live_answers WHERE app_id = ? AND player_id = ? AND q < ?",
                                                   (app["id"], me["id"], st["q"]))) if me else 0)
        out["me"]["rank"] = mine["rank"] if mine and st["phase"] in ("board", "end") else None
    out["players"] = [p["name"] for p in board][:60] if st["phase"] == "lobby" else None
    return out
