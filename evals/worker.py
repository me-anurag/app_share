"""Runs the evaluation tasks of ONE workspace in a throwaway copy of AppShare (fresh seeded database).

Started by evals.run in its own process (the workspace is fixed at import). Reads a plan, writes results.
Modes: live (real API, recorded), replay (recorded replies, no API), fake (harness self-test: reference answers).
"""
import json
import os
import sys
import time


def main(plan_path, out_path):
    plan = json.load(open(plan_path, encoding="utf-8"))
    mode = plan["mode"]
    if mode != "live":
        os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY") or "offline-eval-not-a-key"
        os.environ["GROQ_API_KEY"] = os.environ.get("GROQ_API_KEY") or "offline-eval-not-a-key"
    from fastapi.testclient import TestClient

    from backend import access, agents, main as server, trace
    from backend.db import connect
    from evals import checks
    from evals.cases import ALL
    from evals.cassette import CassetteExhausted, Player, Recorder
    from tests.fake_claude import FakeClaude, text, tool

    agents.RETRY_WAITS = (3.0, 10.0) if mode == "live" else (0.0, 0.0)
    real_call = agents._call_model
    cases = {c["id"]: c for c in ALL}
    results = []

    def truth_for(app_title):
        conn = connect()
        try:
            a = conn.execute("SELECT id FROM apps WHERE title = ?", (app_title,)).fetchone()
            aud = access.audience(conn, a["id"])
            done = {r[0] for r in conn.execute("SELECT user_id FROM submissions WHERE app_id = ?", (a["id"],))}
            return a["id"], {"audience": len(aud), "responders": sorted(p["name"] for p in aud if p["id"] in done),
                             "missing": sorted(p["name"] for p in aud if p["id"] not in done),
                             "missing_emails": sorted(p["email"] for p in aud if p["id"] not in done)}
        finally:
            conn.close()

    def fake_for(case, variant, truth=None):
        """Harness self-test: the stand-in plays the reference answer — except the paraphrase run of the first task,
        which is deliberately broken, to prove the checks and metrics catch mistakes."""
        if case["kind"] == "build":
            ref = json.loads(json.dumps(case["reference"]))
            if variant == "paraphrase" and case["id"] == plan["broken"]:
                ref["spec"]["fields"] = ref["spec"]["fields"][:-1] or ref["spec"]["fields"]
                ref["shares"] = []
            return FakeClaude(agents, {"builder": [[tool("save_app", spec=ref["spec"], share_suggestions=ref["shares"], reason="Reference answer.")],
                                                   text("Built it. Check the preview and press Share.")]}, usage=(1500, 300, 0, 0))
        if case["kind"] == "insights":
            ans = (f"{len(truth['responders'])} of {truth['audience']} have submitted." if case["truth"] == "count"
                   else "Not submitted yet: " + ", ".join(truth["missing"]) + ".")
            return FakeClaude(agents, {"insights": [[tool("get_overview"), tool("list_missing")], text(ans)]}, usage=(1500, 150, 0, 0))
        return FakeClaude(agents, {"reminder": [[tool("get_overview"), tool("list_missing")],
                                                [tool("send_reminders", emails=truth["missing_emails"], title="Assignment 3 closes soon",
                                                      message="A friendly reminder to submit before the deadline.", reason="They haven't submitted.")],
                                                text("Reminded everyone who hasn't submitted.")]}, usage=(1200, 150, 0, 0))

    def run_totals(runs):
        t = {k: 0 for k in ("llm_calls", "tool_calls", "retries", "tool_errors", "rejected", "tokens_in", "tokens_out", "cache_read", "cache_write")}
        cost = 0.0
        for r in runs:
            for k in t:
                t[k] += r["totals"][k]
            cost += r["totals"]["cost"] or 0
        t["cost"] = round(cost, 6)
        t["errors"] = sum(1 for r in runs if r["status"] != "ok")
        return t

    for job in plan["jobs"]:
        case, variant, idx = cases[job["case"]], job["variant"], job["idx"]
        prompt = case["prompt"] if variant == "original" else case["paraphrase"]
        key = f"{case['id']}__{variant}{idx}"
        res = {"case": case["id"], "ws": case["ws"], "kind": case["kind"], "level": case["level"], "variant": variant, "idx": idx,
               "prompt": prompt, "error": None, "checks": []}
        truth, app_id = (None, None)
        if case["kind"] != "build":
            app_id, truth = truth_for(case["app"])
        if mode == "live":
            caller = Recorder(agents, real_call)
        elif mode == "replay":
            caller = Player(agents, os.path.join(plan["cassettes_from"], key + ".json"))
        else:
            caller = fake_for(case, variant, truth)
        agents._call_model = caller
        c = TestClient(server.app)
        c.post("/api/login", json={"email": case["owner"]}).raise_for_status()
        t0 = time.time()
        started_ms = trace.now_ms()
        try:
            if case["kind"] == "build":
                sid = c.post("/api/agent/session", json={}).json()["session_id"]
                r = c.post("/api/agent/build", json={"session_id": sid, "message": prompt}).json()
                res["wall_ms"] = int((time.time() - t0) * 1000)
                res["reply"] = r.get("reply")
                res["error"] = r.get("error")
                conn = connect()
                j = conn_j = None
                try:
                    if r.get("app"):
                        row = conn.execute("SELECT spec, share_suggestions FROM apps WHERE id = ?", (r["app"]["id"],)).fetchone()
                        spec, shares = json.loads(row["spec"]), json.loads(row["share_suggestions"])
                    else:
                        spec, shares = {}, []
                finally:
                    conn.close()
                with trace._lock:
                    conn_j = trace._db().execute("SELECT id FROM journeys WHERE session_id = ?", (sid,)).fetchone()
                j = trace.get_journey(conn_j["id"]) if conn_j else None
                runs = j["runs"] if j else []
                b = next((x for x in runs if x["agent"] == "builder"), None)
                saves = [s for s in (b["steps"] if b else []) if s["kind"] == "validator"]
                dchecks = [s for x in runs if x["agent"] == "data" for s in x["steps"] if s["kind"] == "validator" and "check_fields" in s["name"]]
                res.update(checks=checks.check_build(case, spec, shares, res["reply"] or ""), totals=run_totals(runs),
                           validator_first_pass=(bool(saves[0]["ok"]) if saves else None),
                           data_first_check=(bool(dchecks[0]["ok"]) if dchecks else None),
                           agents_used=sorted({x["agent"] for x in runs}), signature=checks.signature(spec, shares),
                           params=trace.app_params(spec) if spec else None, reference_params=trace.app_params(case["reference"]["spec"]),
                           reference_shares=len(case["reference"]["shares"]), reasons=sum(1 for x in runs for s in x["steps"] if s["detail"].get("reason")),
                           reason_texts=[{"agent": x["agent"], "tool": s["name"], "reason": s["detail"]["reason"]}
                                         for x in runs for s in x["steps"] if s["detail"].get("reason")])
            elif case["kind"] == "insights":
                r = c.post("/api/agent/insights", json={"app_id": app_id, "message": prompt}).json()
                res["wall_ms"] = int((time.time() - t0) * 1000)
                res["reply"], res["error"] = r.get("reply"), r.get("error")
                res["checks"] = checks.check_insights(case, res["reply"], truth)
            else:
                conn = connect()
                before = conn.execute("SELECT COALESCE(MAX(id), 0) FROM notifications").fetchone()[0]
                conn.close()
                try:
                    out = agents.run_reminder(app_id, f"eval-{variant}{idx}", triggered_by=case["owner"])
                    res["reply"] = out["reply"]
                except agents.AgentError as e:
                    res["error"] = str(e)
                res["wall_ms"] = int((time.time() - t0) * 1000)
                conn = connect()
                sent = [r[0] for r in conn.execute("SELECT u.name FROM notifications n JOIN users u ON u.id = n.user_id "
                                                   "WHERE n.id > ? AND n.app_id = ? AND n.kind = 'reminder'", (before, app_id))]
                conn.close()
                res["checks"] = checks.check_reminder(case, sent, truth)
            if case["kind"] != "build":
                jid = trace.journey_for_app(app_id)
                j = trace.get_journey(jid)
                runs = [x for x in j["runs"] if x["started_at"] >= started_ms and x["agent"] in ("insights", "reminder")]
                res["totals"] = run_totals(runs)
                res["truth"] = {k: v for k, v in truth.items() if k != "missing_emails"}
        except CassetteExhausted as e:
            res["error"] = f"replay: {e}"
        except Exception as e:  # noqa: BLE001 — one broken task must not stop the evaluation
            res["error"] = f"{type(e).__name__}: {e}"
        if mode == "live":
            caller.dump(os.path.join(plan["run_dir"], "cassettes", key + ".json"),
                        {"case": case["id"], "variant": variant, "idx": idx, "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                         "wall_ms": res.get("wall_ms"), "prompt": prompt})
        if mode == "replay":
            res["recorded_wall_ms"] = caller.data.get("wall_ms")
            res["replay_ms"] = res.get("wall_ms")
            res["wall_ms"] = caller.data.get("wall_ms")       # latency is what was measured when it was recorded
        res["success"] = not res["error"] and all(x["passed"] for x in res["checks"])
        results.append(res)
        print(f"  {'PASS' if res['success'] else 'FAIL'}  {key:<28} {res.get('wall_ms', 0):>6} ms  "
              f"{sum(x['passed'] for x in res['checks'])}/{len(res['checks'])} checks"
              f"{'  ' + res['error'] if res['error'] else ''}", flush=True)
        json.dump(results, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
