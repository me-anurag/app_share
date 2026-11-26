"""Sites: does the Site agent build only what was asked, and what does a site cost?

  python -m evals.site_eval --import <run.json>     record a live site build already made (no cost)
  python -m evals.site_eval --live --yes            run the site tasks live (paid, about $0.055 per task)

Writes data/evals/<time>-site-live/results.json. Scored automatically:
  - unrequested blocks: blocks whose type the request gave no reason for (FAQ, schedule, prizes…)
  - form placed: a site that collects answers shows its form exactly once
  - Validator rejections, time and calculated cost (tokens x published prices), per agent
Invented facts are judged by hand and recorded as such (`facts_note`); this is a small sample — say so when quoting it.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "data", "evals")

# Each task names the block types its request justifies. Anything else on the page is "unrequested".
TASKS = {
    "robotics-open-day": {
        "request": ("Make a site for our Robotics Club open day on 14 Dec 2026, 11 am to 3 pm, in Workshop B. "
                    "Visitors should be able to sign up."),
        "allowed": ["hero", "text", "image_text", "map", "form", "divider"],
        "collects": True,
    },
}


def score(task, spec, totals, runs, secs, facts_note=""):
    site = spec.get("site") or {}
    blocks = [b["type"] for p in site.get("pages", []) for b in p.get("blocks", [])]
    unrequested = [b for b in blocks if b not in task["allowed"]]
    return {
        "request": task["request"], "kind": spec.get("kind"), "theme": site.get("theme"),
        "pages": len(site.get("pages", [])), "blocks": blocks, "unrequested_blocks": unrequested,
        "suggested": [s["type"] for s in site.get("suggested", [])],
        "form_ok": (blocks.count("form") == 1) == task["collects"],
        "fields": [f["label"] for f in spec.get("fields", [])],
        "secs": round(secs, 1), "cost_usd": round(totals["cost"], 6),
        "validator_rejected": totals.get("rejected", 0), "llm_calls": totals.get("llm_calls"),
        "agents": [{"agent": r["agent"], "model": r["model"], "ms": r["ms"], "cost_usd": round(r["cost"], 6)} for r in runs],
        "facts_note": facts_note,
    }


def write(results, mode):
    out = os.path.join(EV, time.strftime("%Y%m%d-%H%M%S") + "-site-live")
    os.makedirs(out, exist_ok=True)
    n = len(results)
    summary = {
        "mode": mode, "tasks": n,
        "with_unrequested_blocks": sum(1 for r in results if r["unrequested_blocks"]),
        "form_ok": sum(1 for r in results if r["form_ok"]),
        "mean_cost_usd": round(sum(r["cost_usd"] for r in results) / n, 6),
        "mean_secs": round(sum(r["secs"] for r in results) / n, 1),
        "site_agent_cost_usd": round(sum(a["cost_usd"] for r in results for a in r["agents"] if a["agent"] == "site") / n, 6),
    }
    json.dump({"when": time.strftime("%Y-%m-%d %H:%M"), "summary": summary, "results": results},
              open(os.path.join(out, "results.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1))
    print("Written:", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--import", dest="imp", help="a run file saved by a live site build")
    ap.add_argument("--task", default="robotics-open-day")
    ap.add_argument("--facts", default="", help="hand-checked note on invented facts")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if a.imp:
        R = json.load(open(a.imp, encoding="utf-8"))
        task = TASKS[a.task]
        assert R["request"] == task["request"], "the imported run is not this task"
        runs = [{"agent": x["agent"], "model": x["model"], "ms": x["ms"], "cost": x["cost"]} for x in R["runs"]]
        write([score(task, R["spec"], R["totals"], runs, R["secs"], a.facts)], "live (imported)")
        return
    if not (a.live and a.yes):
        sys.exit("Live site builds cost money (about $0.055 each). Use --live --yes, or --import a saved run.")
    import tempfile
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8") if os.path.exists(os.path.join(ROOT, ".env")) else []:
        if line.strip().startswith("ANTHROPIC_API_KEY=") and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
    os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-site-eval-"), APPSHARE_MODE="university")
    from fastapi.testclient import TestClient
    from backend import main as server
    results = []
    for name, task in TASKS.items():
        c = TestClient(server.app)
        c.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
        t0 = time.time()
        r = c.post("/api/agent/build", json={"message": task["request"]}).json()
        secs = time.time() - t0
        spec = c.get(f"/api/apps/{r['app']['id']}").json()["spec"]
        lap = TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
        j = lap.get("/api/trace/journeys").json()["journeys"]
        J = lap.get(f"/api/trace/journeys/{next(x['id'] for x in j if x['app_id'] == r['app']['id'])}").json()
        runs = [{"agent": x["agent"], "model": x["model"], "ms": x["ms"], "cost": x["totals"]["cost"]} for x in J["runs"]]
        results.append(score(task, spec, J["totals"], runs, secs, "not yet checked by hand"))
    write(results, "live")


if __name__ == "__main__":
    main()
