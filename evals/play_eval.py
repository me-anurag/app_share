"""Quizzes and party lights built by the real agents, scored with exact checks.

  python -m evals.play_eval --live --yes      the real agents build each task (≈ $0.05 each; recorded)

Checks (automatic): the right kind of app; the requested mode and number of questions; every question has a right
answer among its options; right answers not always in the same position; no name/email questions in a live quiz;
a light show has no questions, at least two colours, and no strobe unless asked; the reply never claims it was shared.
The questions and answers are saved so their correctness can be judged by a person (not by an AI).
Output: data/evals/<time>-play-live/results.json (+ cassettes/).
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TASKS = [
    {"id": "quiz-host", "workspace": "general", "owner": "riya@example.com",
     "request": "Make a quick movie quiz for my daughter's birthday party: 6 questions about famous kids' movies. We'll play it together on the TV.",
     "expect": {"kind": "quiz", "mode": "host", "questions": 6}},
    {"id": "party-lights", "workspace": "general", "owner": "riya@example.com",
     "request": "Turn everyone's phones into party lights for Riya's birthday tonight.",
     "expect": {"kind": "party", "mentions": "riya"}},
]


def score(task, spec, reply):
    from evals.checks import CLAIMS_SHARED
    e, out = task["expect"], []
    add = lambda name, ok, detail="": out.append({"check": name, "passed": bool(ok), "detail": detail})
    add(f"kind is {e['kind']}", spec.get("kind") == e["kind"], f"got {spec.get('kind')!r}")
    if e["kind"] == "quiz":
        qs = [f for f in spec.get("fields", []) if "answer" in f]
        add(f"quiz mode {e['mode']}", (spec.get("quiz") or {}).get("mode") == e["mode"], f"got {(spec.get('quiz') or {}).get('mode')!r}")
        add(f"{e['questions']} questions", len(qs) == e["questions"], f"got {len(qs)}")
        add("every question's answer is one of its options", qs and all(
            (set(f["answer"]) <= set(f["options"])) if isinstance(f["answer"], list) else f["answer"] in f["options"] for f in qs))
        pos = [f["options"].index(f["answer"]) for f in qs if isinstance(f.get("answer"), str) and f["answer"] in f["options"]]
        add("right answers not always in the same position", len(set(pos)) > 1, f"positions {pos}")
        # only a question WITHOUT a right answer can be asking for the player's name
        # ("What is the name of the cowboy doll?" is a quiz question, not a name field)
        asks = [f["label"] for f in spec.get("fields", []) if "answer" not in f and (f["type"] == "email" or re.search(r"\bname\b", f["label"], re.I))]
        add("no name or email questions (players join with a nickname)", not asks, f"asks: {asks}" if asks else "")
    else:
        p = spec.get("party") or {}
        add("no questions", not spec.get("fields"), f"{len(spec.get('fields', []))} fields")
        add("at least two colours", len(p.get("palette", [])) >= 2, f"{p.get('palette')}")
        add("no strobe (not asked for)", "strobe" not in p.get("scenes", []) and not p.get("strobe"), f"scenes {p.get('scenes')}")
        if e.get("mentions"):
            add(f"title or message mentions {e['mentions'].title()}",
                re.search(e["mentions"], f"{spec.get('title', '')} {p.get('message', '')}", re.I), f"{spec.get('title')!r} / {p.get('message')!r}")
    add("reply doesn't claim it was shared", not CLAIMS_SHARED.search(reply or ""), (CLAIMS_SHARED.search(reply or "") or [""])[0])
    return out


def run_task(task, out_dir):
    os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-play-eval-"), APPSHARE_MODE=task["workspace"], APPSHARE_AI_MODE="claude")
    from fastapi.testclient import TestClient

    from backend import agents, main as server, trace
    from backend.db import connect
    from evals.cassette import Recorder
    rec = Recorder(agents, agents._call_model)
    agents._call_model = rec
    c = TestClient(server.app)
    c.post("/api/login", json={"email": task["owner"]}).raise_for_status()
    sid = c.post("/api/agent/session", json={}).json()["session_id"]
    t0 = time.time()
    r = c.post("/api/agent/build", json={"session_id": sid, "message": task["request"]}).json()
    wall = int((time.time() - t0) * 1000)
    spec = {}
    if r.get("app"):
        conn = connect()
        spec = json.loads(conn.execute("SELECT spec FROM apps WHERE id = ?", (r["app"]["id"],)).fetchone()[0])
        conn.close()
    with trace._lock:
        jrow = trace._db().execute("SELECT id FROM journeys WHERE session_id = ?", (sid,)).fetchone()
    J = trace.get_journey(jrow["id"]) if jrow else None
    runs = (J or {}).get("runs", [])
    rec.dump(os.path.join(out_dir, "cassettes", task["id"] + ".json"),
             {"case": task["id"], "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"), "wall_ms": wall, "prompt": task["request"]})
    checks = score(task, spec, r.get("reply"))
    return {"id": task["id"], "request": task["request"], "checks": checks, "error": r.get("error"),
            "success": bool(spec) and not r.get("error") and all(x["passed"] for x in checks), "reply": r.get("reply"),
            "wall_ms": wall, "cost_usd": round(sum(x["totals"]["cost"] or 0 for x in runs), 6),
            "agents": sorted({x["agent"] for x in runs}), "spec": {k: spec.get(k) for k in ("title", "kind", "quiz", "party", "description")},
            "questions": [{"q": f["label"], "options": f["options"], "answer": f.get("answer")} for f in spec.get("fields", []) if "answer" in f],
            "fields": spec.get("fields", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--task", help="run one task in this process (used internally)")
    ap.add_argument("--out")
    ap.add_argument("--rescore", help="score a recorded run again with the current checks (free); writes rescored.json beside it")
    a = ap.parse_args()
    if a.rescore:                                    # the original results.json stays untouched (and sealed)
        d = os.path.join(ROOT, a.rescore)
        R = json.load(open(os.path.join(d, "results.json"), encoding="utf-8"))
        out = []
        for r in R["results"]:
            task = next(t for t in TASKS if t["id"] == r["id"])
            fields = r.get("fields") or [{"type": "radio", "label": q["q"], "options": q["options"], "answer": q["answer"]}
                                         for q in r.get("questions", [])]
            spec = {**{k: v for k, v in r["spec"].items() if v is not None}, "fields": fields}
            checks = score(task, spec, r.get("reply"))
            out.append({"id": r["id"], "checks": checks, "success": not r.get("error") and all(c["passed"] for c in checks),
                        "changed": [c["check"] for c, o in zip(checks, r["checks"]) if c["passed"] != o["passed"]]})
        from evals.proof import code_fingerprints
        json.dump({"rescored_at": time.strftime("%Y-%m-%d %H:%M:%S"), "code": code_fingerprints(), "results": out},
                  open(os.path.join(d, "rescored.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        for r in out:
            print(f"{'PASS' if r['success'] else 'FAIL'}  {r['id']}  {sum(c['passed'] for c in r['checks'])}/{len(r['checks'])} checks"
                  f"  changed: {r['changed'] or 'nothing'}")
        return
    if a.task:                                       # one task per process: each gets a fresh workspace
        task = next(t for t in TASKS if t["id"] == a.task)
        res = run_task(task, a.out)
        json.dump(res, open(os.path.join(a.out, task["id"] + ".result.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        return
    if not (a.live and a.yes):
        sys.exit("Live builds cost money (≈ $0.05 each). Use --live --yes.")
    from evals.examiner import _key
    if not _key():
        sys.exit("No ANTHROPIC_API_KEY in the environment or .env")
    import subprocess
    from evals.proof import code_fingerprints, git_commit
    out = os.path.join(ROOT, "data", "evals", time.strftime("%Y%m%d-%H%M%S") + "-play-live")
    os.makedirs(os.path.join(out, "cassettes"), exist_ok=True)
    meta = {"mode": "live", "started": time.strftime("%Y-%m-%d %H:%M:%S"), "code": code_fingerprints(), "git": git_commit()}
    results = []
    for t in TASKS:
        env = {**os.environ, "ANTHROPIC_API_KEY": _key(), "PYTHONIOENCODING": "utf-8"}
        subprocess.run([sys.executable, "-m", "evals.play_eval", "--task", t["id"], "--out", out], cwd=ROOT, env=env, check=False)
        p = os.path.join(out, t["id"] + ".result.json")
        r = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"id": t["id"], "success": False, "error": "did not finish", "checks": []}
        results.append(r)
        print(f"{'PASS' if r['success'] else 'FAIL'}  {t['id']}  {sum(c['passed'] for c in r['checks'])}/{len(r['checks'])} checks  "
              f"${r.get('cost_usd', 0):.4f}  {r.get('wall_ms', 0) / 1000:.1f} s")
        for c in r["checks"]:
            print(f"   {'✓' if c['passed'] else '✗'} {c['check']}  {c.get('detail', '')[:100]}")
    summary = {"tasks": len(results), "passed": sum(r["success"] for r in results),
               "checks": sum(len(r["checks"]) for r in results), "checks_passed": sum(c["passed"] for r in results for c in r["checks"]),
               "cost_usd": round(sum(r.get("cost_usd", 0) for r in results), 6)}
    json.dump({"meta": meta, "summary": summary, "results": results}, open(os.path.join(out, "results.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print(json.dumps(summary), "→", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
