"""Test it yourself: an examiner types any request and says what they expect; the real agents build it and the same
exact checks as the evaluation mark it — in front of them.

  python -m evals.examiner --job job.json [--yes]          live (real API, about $0.05; --yes required)
  python -m evals.examiner --replay data/evals/<…-examiner>  re-score a recorded examiner task (free)
  python -m evals.examiner --job job.json --fake-spec s.json  offline test: a scripted model saves s.json

job.json: {"request": "...", "workspace": "university|office|general", "expect": {...}}
expect (all optional):
  fields        ["file", "rating", ...]        the app must ask these kinds of question (repeat a type to need two)
  file_accept   [".pdf", ".docx"]   file_max_mb 10
  choice        ["Mon", "Tue", "Wed"]          a choice question with these options   places_each 3
  deadline      "2026-12-12" or "2026-12-12T17:00"
  anonymous     true            per_person "one" | "many"     total_places 60
  statuses      ["Pending", "Approved"]
  audience      {"type": "group", "name": "34ML", "role": "submitter"} | {"type": "public"} | {"type": "org"}
  no_identity   true (don't ask signed-in people for name/email)     max_questions 4     title_has "TechFest"
Every build also gets the automatic checks: readable colour, title and instructions, saved, honest reply, reply's
dates and places true of the saved app. Output: data/evals/<time>-examiner/results.json + cassettes/ (the recording).
"""
import argparse
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OWNERS = {"university": "dr.mehta@riverside.edu", "office": "ananya.rao@northwind.co", "general": "riya@example.com"}
FIELD_TYPES = ("short_text", "long_text", "number", "email", "phone", "date", "select", "radio", "checkbox", "file", "rating")


def to_checks(expect):
    """The examiner's expectations as evaluation checks (agent, kind, args) — the format evals/cases.py uses."""
    e, out = expect or {}, []
    file_extra = {k2: e[k1] for k1, k2 in (("file_accept", "accept"), ("file_max_mb", "max_mb")) if e.get(k1)}
    counts = {}
    for t in e.get("fields") or []:
        if t in FIELD_TYPES:
            counts[t] = counts.get(t, 0) + 1
    for t, n in counts.items():
        want = {"type": t, **(file_extra if t == "file" else {})}
        if n > 1:
            want["count"] = n
        out.append(("data", "field", want))
    if file_extra and "file" not in counts:
        out.append(("data", "field", {"type": "file", **file_extra}))
    if e.get("choice"):
        want = {"options": [str(o).strip().lower() for o in e["choice"] if str(o).strip()]}
        if e.get("places_each"):
            want["limits"] = int(e["places_each"])
        out.append(("data", "choice", want))
    if e.get("deadline"):
        out.append(("data", "closes", str(e["deadline"]).strip()))
    if e.get("anonymous") is not None:
        out.append(("data", "rule", "anonymous", bool(e["anonymous"])))
    if e.get("per_person") in ("one", "many"):
        out.append(("data", "rule", "responses_per_person", e["per_person"]))
    if e.get("total_places"):
        out.append(("data", "rule", "max_responses", int(e["total_places"])))
    if e.get("statuses"):
        out.append(("data", "statuses", [str(s).strip().lower() for s in e["statuses"] if str(s).strip()]))
    if e.get("no_identity"):
        out.append(("data", "no_identity"))
    if e.get("max_questions"):
        out.append(("data", "max_fields", int(e["max_questions"])))
    a = e.get("audience") or {}
    if a.get("type") in ("group", "user") and a.get("name"):
        out.append(("access", "share", {"type": a["type"], "name": a["name"], **({"role": a["role"]} if a.get("role") else {})}))
    elif a.get("type") in ("public", "org"):
        out.append(("access", "share", {"type": a["type"]}))
    if e.get("title_has"):
        out.append(("design", "title_has", str(e["title_has"])))
    return out


def _key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def run(job, mode, out_dir, fake_spec=None, cassette=None):
    ws = job.get("workspace") if job.get("workspace") in OWNERS else "university"
    os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-examiner-"), APPSHARE_MODE=ws, APPSHARE_AI_MODE="claude")
    if mode != "live":
        os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY") or "offline-examiner-not-a-key"
    from fastapi.testclient import TestClient

    from backend import agents, main as server, trace
    from backend.db import connect
    from evals import checks
    from evals.cassette import Player, Recorder

    real = agents._call_model
    if mode == "live":
        caller = Recorder(agents, real)
    elif mode == "replay":
        caller = Player(agents, cassette)
    else:
        from tests.fake_claude import FakeClaude, text, tool
        spec = json.load(open(fake_spec, encoding="utf-8"))
        caller = FakeClaude(agents, {"builder": [[tool("save_app", spec=spec.get("spec", spec), share_suggestions=spec.get("shares", []),
                                                       reason="Scripted test answer.")], text("Built it. Check the preview and press Share.")]})
    agents._call_model = caller
    case = {"id": "examiner", "checks": to_checks(job.get("expect"))}
    c = TestClient(server.app)
    c.post("/api/login", json={"email": OWNERS[ws]}).raise_for_status()
    sid = c.post("/api/agent/session", json={}).json()["session_id"]
    t0 = time.time()
    r = c.post("/api/agent/build", json={"session_id": sid, "message": job["request"]}).json()
    wall = int((time.time() - t0) * 1000)
    spec, shares = {}, []
    if r.get("app"):
        conn = connect()
        row = conn.execute("SELECT spec, share_suggestions FROM apps WHERE id = ?", (r["app"]["id"],)).fetchone()
        conn.close()
        spec, shares = json.loads(row["spec"]), json.loads(row["share_suggestions"])
    with trace._lock:
        jrow = trace._db().execute("SELECT id FROM journeys WHERE session_id = ?", (sid,)).fetchone()
    J = trace.get_journey(jrow["id"]) if jrow else None
    cost = round(sum(x["totals"]["cost"] or 0 for x in (J or {}).get("runs", [])), 6)
    res = checks.check_build(case, spec, shares, r.get("reply") or "")
    result = {"request": job["request"], "workspace": ws, "expect": job.get("expect") or {}, "checks": res,
              "examiner_checks": len(case["checks"]), "success": bool(spec) and not r.get("error") and all(x["passed"] for x in res),
              "reply": r.get("reply"), "error": r.get("error"), "wall_ms": wall if mode != "replay" else (caller.data or {}).get("wall_ms"),
              "cost_usd": cost, "app": {"title": spec.get("title"), "kind": spec.get("kind"), "closes_at": spec.get("closes_at"),
                                        "fields": [f"{f.get('type')}: {f.get('label')}" for f in spec.get("fields", [])],
                                        "rules": trace.app_params(spec)["rules"] if spec else {},
                                        "share": [f"{s.get('name') or s.get('type')} ({s.get('role')})" for s in shares]},
              "agents": sorted({x["agent"] for x in (J or {}).get("runs", [])})}
    if mode == "live":
        caller.dump(os.path.join(out_dir, "cassettes", "examiner.json"),
                    {"case": "examiner", "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"), "wall_ms": wall, "prompt": job["request"]})
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--fake-spec")
    ap.add_argument("--replay")
    ap.add_argument("--out", help="write here instead of data/evals/<time>-examiner (tests)")
    a = ap.parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if a.replay:
        src = os.path.join(ROOT, a.replay) if not os.path.isabs(a.replay) else a.replay
        old = json.load(open(os.path.join(src, "results.json"), encoding="utf-8"))
        job = {"request": old["result"]["request"], "workspace": old["result"]["workspace"], "expect": old["result"]["expect"]}
        mode, out_dir = "replay", os.path.join(ROOT, "data", "evals", f"{stamp}-examiner-replay")
        cassette = os.path.join(src, "cassettes", "examiner.json")
    else:
        job = json.load(open(a.job, encoding="utf-8"))
        if not job.get("request", "").strip():
            sys.exit("The request is empty.")
        mode = "fake" if a.fake_spec else "live"
        if mode == "live":
            if not a.yes:
                sys.exit("A live examiner task calls the real API (about $0.05). Add --yes.")
            if not _key():
                sys.exit("No ANTHROPIC_API_KEY in the environment or .env")
            os.environ["ANTHROPIC_API_KEY"] = _key()
        out_dir = os.path.join(ROOT, "data", "evals", f"{stamp}-examiner" + ("" if mode == "live" else "-fake"))
        cassette = None
    out_dir = a.out or out_dir
    os.makedirs(os.path.join(out_dir, "cassettes"), exist_ok=True)
    from evals.proof import code_fingerprints, git_commit, rel
    meta = {"mode": mode, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "code": code_fingerprints(), "git": git_commit(),
            "source": rel(src) if a.replay else None}
    result = run(job, mode, out_dir, a.fake_spec, cassette)
    json.dump({"meta": meta, "result": result}, open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{'PASS' if result['success'] else 'FAIL'}  {sum(c['passed'] for c in result['checks'])}/{len(result['checks'])} checks  "
          f"${result['cost_usd']:.4f}  → {rel(out_dir)}")
    for c in result["checks"]:
        print(f"  {'✓' if c['passed'] else '✗'} {c['agent']}: {c['check']}  {c.get('detail', '')[:90]}")
    print("RESULT_DIR=" + rel(out_dir))
    sys.exit(0)


if __name__ == "__main__":
    main()
