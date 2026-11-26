"""Run the agent evaluation and write a report.

  python -m evals.run --mode fake                       harness self-test (no API, no cost; proves the checks work)
  python -m evals.run --mode live --estimate            what a live run would cost, from real measured builds
  python -m evals.run --mode live --yes                 real agents, records every reply   (costs money)
  python -m evals.run --mode replay --from data/evals/<live run folder>   reproduce a live run without an API key

Options: --cases U1-feedback,O2-lunch-poll   --repeats 2   --no-paraphrase
Each workspace runs in its own process with a fresh, seeded copy of AppShare in a temporary folder, so the real
workspace data is never touched. Output: data/evals/<time>-<mode>/report.md, report.html, results.json (+ cassettes/).
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from evals import metrics, report  # noqa: E402
from evals.cases import ALL  # noqa: E402


def env_key():
    """The API key from the environment or the project's .env (never printed)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def plan_jobs(cases, repeats, paraphrase):
    jobs = []
    for c in cases:
        n = repeats if c["kind"] != "reminder" else max(1, repeats)
        jobs += [{"case": c["id"], "variant": "original", "idx": i} for i in range(n)]
        if paraphrase and c.get("paraphrase"):
            jobs.append({"case": c["id"], "variant": "paraphrase", "idx": 0})
    return jobs


def measured_costs():
    """Average cost of real agent runs so far, from the live trace stores (for the estimate)."""
    out = {"build": [], "insights": [], "reminder": []}
    for ws in ("university", "office", "general"):
        p = os.path.join(ROOT, "data", ws, "traces.db")
        if not os.path.exists(p):
            continue
        db = sqlite3.connect(p)
        for (cost,) in db.execute("""SELECT SUM(s.cost) FROM runs b JOIN runs r ON (r.id = b.id OR r.parent_id = b.id)
                                     JOIN steps s ON s.run_id = r.id WHERE b.agent = 'builder' AND b.round = 1 AND b.status = 'ok' GROUP BY b.id"""):
            if cost:
                out["build"].append(cost)
        for agent in ("insights", "reminder"):
            for (cost,) in db.execute("SELECT SUM(s.cost) FROM runs r JOIN steps s ON s.run_id = r.id WHERE r.agent = ? AND r.status = 'ok' GROUP BY r.id", (agent,)):
                if cost:
                    out[agent].append(cost)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["live", "replay", "fake"], required=True)
    ap.add_argument("--cases", default="")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--no-paraphrase", action="store_true")
    ap.add_argument("--from", dest="src", default="")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--ai", choices=["claude", "groq", "mixed"], default=None,
                    help="AI provider for the agents (default: whatever .env says, normally claude)")
    a = ap.parse_args()
    envfile = {}
    try:
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                envfile[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    ai_mode = a.ai or os.environ.get("APPSHARE_AI_MODE") or envfile.get("APPSHARE_AI_MODE") or "claude"
    groq_key = os.environ.get("GROQ_API_KEY") or envfile.get("GROQ_API_KEY")
    groq_model = os.environ.get("APPSHARE_GROQ_MODEL") or envfile.get("APPSHARE_GROQ_MODEL") or "openai/gpt-oss-120b"
    agent_providers = os.environ.get("APPSHARE_AGENT_PROVIDERS") or envfile.get("APPSHARE_AGENT_PROVIDERS") or "{}"
    groq_models = os.environ.get("APPSHARE_GROQ_MODELS") or envfile.get("APPSHARE_GROQ_MODELS") or "{}"

    cases = [c for c in ALL if not a.cases or c["id"] in a.cases.split(",")]
    if a.mode == "replay":
        src = json.load(open(os.path.join(a.src, "results.json"), encoding="utf-8"))
        jobs = [{"case": r["case"], "variant": r["variant"], "idx": r["idx"]} for r in src["results"]]
        cases = [c for c in ALL if c["id"] in {j["case"] for j in jobs}]
    else:
        jobs = plan_jobs(cases, a.repeats, not a.no_paraphrase)

    if a.mode == "live" and ai_mode == "groq":
        print(f"Planned: {len(jobs)} runs of {len(cases)} tasks on Groq ({groq_model}). Cost: $0 on the free tier (rate limits apply).")
        if not a.yes:
            print("Not run. Add --yes to run it.")
            return
        if not groq_key:
            sys.exit("No GROQ_API_KEY in the environment or .env (add it in the Control Center: AI provider).")
    elif a.mode == "live":
        mc = measured_costs()
        kinds = {c["id"]: c["kind"] for c in cases}
        fallback = {"build": 0.05, "insights": 0.03, "reminder": 0.01}
        est = 0.0
        for j in jobs:
            k = kinds[j["case"]]
            est += (sum(mc[k]) / len(mc[k])) if mc[k] else fallback[k]
        print(f"Planned: {len(jobs)} runs of {len(cases)} tasks.")
        print(f"Estimated cost: ${est:.2f}  (from {len(mc['build'])} real builds, {len(mc['insights'])} Insights and "
              f"{len(mc['reminder'])} Reminder runs measured so far; tasks with no measurement use a conservative guess)")
        if a.estimate or not a.yes:
            print("Not run. Add --yes to run it for real." if not a.estimate else "")
            return
        if not env_key() and ai_mode != "groq":
            sys.exit("No ANTHROPIC_API_KEY in the environment or .env")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(ROOT, "data", "evals", f"{stamp}-{a.mode}" + ("" if ai_mode == "claude" else f"-{ai_mode}"))
    os.makedirs(os.path.join(run_dir, "cassettes"), exist_ok=True)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    from evals.proof import code_fingerprints, git_commit
    code_at_start, git_at_start = code_fingerprints(), git_commit()   # what the tasks and checks were when the run began
    results = []
    by_ws = {}
    for j in jobs:
        ws = next(c["ws"] for c in cases if c["id"] == j["case"])
        by_ws.setdefault(ws, []).append(j)
    models = {"main": os.environ.get("APPSHARE_MODEL", "claude-opus-5-5"), "specialist": os.environ.get("APPSHARE_SPECIALIST_MODEL", "claude-haiku-5-5")}
    for ws, wjobs in by_ws.items():
        print(f"\n[{ws}] {len(wjobs)} runs")
        tmp = tempfile.mkdtemp(prefix=f"appshare-eval-{ws}-")
        plan = {"mode": a.mode, "jobs": wjobs, "run_dir": run_dir, "cassettes_from": os.path.join(a.src, "cassettes") if a.src else "",
                "broken": next((c["id"] for c in cases if c["kind"] == "build"), None)}
        plan_path, out_path = os.path.join(tmp, "plan.json"), os.path.join(tmp, "results.json")
        json.dump(plan, open(plan_path, "w", encoding="utf-8"))
        env = {**os.environ, "APPSHARE_DATA": tmp, "APPSHARE_MODE": ws, "PYTHONIOENCODING": "utf-8", "APPSHARE_MONITOR_TOKEN": "",
               "APPSHARE_AI_MODE": ai_mode, "APPSHARE_GROQ_MODEL": groq_model, "APPSHARE_AGENT_PROVIDERS": agent_providers,
               "APPSHARE_GROQ_MODELS": groq_models}
        if a.mode == "live":
            env["ANTHROPIC_API_KEY"] = env_key() or ""
            if groq_key:
                env["GROQ_API_KEY"] = groq_key
        subprocess.run([sys.executable, "-m", "evals.worker", plan_path, out_path], cwd=ROOT, env=env, check=False)
        if os.path.exists(out_path):
            results += json.load(open(out_path, encoding="utf-8"))
    if ai_mode == "groq":
        models = {"main": "groq:" + groq_model, "specialist": "groq:" + groq_model}
    meta = {"mode": a.mode, "started": started, "finished": time.strftime("%Y-%m-%d %H:%M:%S"), "models": models, "ai": ai_mode,
            "groq_models": json.loads(groq_models or "{}") if ai_mode != "claude" else {},
            "source": a.src or None, "jobs": len(jobs), "code": code_at_start, "git": git_at_start}
    M = metrics.compute(results)
    report.write(run_dir, meta, M, results)
    print(f"\nTask success: {report.pct(M['success'])}")
    print(f"Checks:       {report.pct(M['checks'])}")
    print(f"Cost:         ${M['total_cost_usd']:.4f}")
    print(f"Report:       {os.path.join(run_dir, 'report.html')}")


if __name__ == "__main__":
    main()
