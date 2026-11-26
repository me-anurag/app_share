"""Evidence behind every evaluation number — what the Control Center's Evaluation tab shows.

  python -m evals.proof --seal        fingerprint result files that aren't sealed yet (never re-seals a changed file)
  python -m evals.proof --check       compare every sealed file with its fingerprint
  python -m evals.proof --audit       what changed in the scoring between a live run and its replay

Every number is read from a result file in data/evals/ and carries: its sample (k of n), a 95% Wilson interval, the
folder it came from, and a label that says how it was obtained:
  live       the real agents on the real API
  replayed   the recorded live replies scored again by the current code (free, deterministic)
  measured   no model involved (tests, the scanner, load with a stand-in model) — measured on this laptop
  self-test  a scripted stand-in model played the answers: proves the measuring/guard code works, not model quality
  missing    not measured yet (and what it would take)
Self-test numbers never feed a headline.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "data", "evals")
SEALS = os.path.join(ROOT, "evals", "SEALS.json")          # committed to git, so the fingerprints are public
CODE_FILES = ("evals/cases.py", "evals/checks.py", "evals/metrics.py", "evals/attacks.py", "evals/heldout.py")


# --------------------------------------------------------------------------- small helpers

def _load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _runs(suffix):
    """Run folders of one kind, oldest first. suffix: 'live' (quality live), 'replay', 'fake', 'safety-fake'…"""
    out = []
    for d in sorted(glob.glob(os.path.join(EV, "2*"))):
        name = os.path.basename(d)
        rest = name.split("-", 2)[2] if name.count("-") >= 2 else ""
        if rest == suffix:
            out.append(d)
    return out


def _newest(suffix):
    r = _runs(suffix)
    return r[-1] if r else None


def rel(p):
    if not p:
        return None
    try:
        return os.path.relpath(p, ROOT).replace("\\", "/")
    except ValueError:                       # another drive (e.g. a temporary folder)
        return os.path.abspath(p).replace("\\", "/")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def code_fingerprints():
    """Fingerprints of the files that define the tasks and how they are scored (recorded with every new run)."""
    out = {}
    for f in CODE_FILES:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            out[f] = sha256(p)[:16]
    return out


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return {"rate": round(p, 4), "k": k, "n": n, "lo": round(max(0, c - m), 4), "hi": round(min(1, c + m), 4)}


def M(mid, label, w=None, kind="replayed", source=None, value=None, how="", note=""):
    """One metric as the dashboard shows it."""
    out = {"id": mid, "label": label, "kind": kind, "source": rel(source) if source and os.path.isabs(source) else source,
           "how": how, "note": note}
    if w:
        out.update(rate=w["rate"], k=w["k"], n=w["n"], lo=w["lo"], hi=w["hi"], value=f"{w['rate'] * 100:.1f}%")
    if value is not None:
        out["value"] = value
    if kind == "missing" and "value" not in out:
        out["value"] = "not measured"
    return out


def _quality():
    """The quality run whose numbers are the headline: the newest replay of a live run (else the newest live)."""
    rep = None
    for d in reversed(_runs("replay")):
        R = _load(os.path.join(d, "results.json"))
        if R and (R["meta"].get("source") or "").endswith("-live"):
            rep = (d, R)
            break
    live = _newest("live")
    L = _load(os.path.join(live, "results.json")) if live else None
    return rep, (live, L)


def _suite(T, name):
    s = next((x for x in (T or {}).get("suites", []) if x["suite"] == name), None)
    if not s:
        return None
    return f"{'pass' if s['ok'] else 'FAIL'} · {s['passed']} checks"


# --------------------------------------------------------------------------- the eight categories

def summary():
    (rd, R), (ld, L) = _quality()
    Q = R or L
    qsrc = rd or ld
    qkind = "replayed" if R else "live"
    Mx = Q["metrics"] if Q else {}
    T = _load(os.path.join(EV, "tests.json"))
    H = _load(os.path.join(EV, "heldout.json"))
    s_live, s_fake = _newest("safety-live"), _newest("safety-fake")
    S = _load(os.path.join(s_live or s_fake, "results.json")) if (s_live or s_fake) else None
    r_live, r_fake = _newest("review-live"), _newest("review-fake")
    RV = _load(os.path.join(r_live or r_fake, "results.json")) if (r_live or r_fake) else None
    loads = _runs("load")
    LA = _load(os.path.join(loads[-1], "load.json")) if loads else None
    LB = next((_load(os.path.join(d, "load.json")) for d in loads
               if any(a["errors"] for a in (_load(os.path.join(d, "load.json")) or {}).get("agents", []))), None)
    fake = _newest("fake")
    F = _load(os.path.join(fake, "results.json")) if fake else None
    site = _newest("site-live")
    SI = _load(os.path.join(site, "results.json")) if site else None
    rep = _load(os.path.join(EV, "reproduce.json"))
    eb = (Mx.get("efficiency") or {}).get("build", {})
    se = (Mx.get("success_efficiency") or {}).get("build", {})

    cats = []
    q = [M("q.success", "Task success (every check of a run passed)", Mx.get("success"), qkind, qsrc,
           how="runs where every check passed ÷ all runs"),
         M("q.checks", "Individual checks passed", Mx.get("checks"), qkind, qsrc, how="passed checks ÷ all checks"),
         M("q.first_pass", "Validator accepted the Builder's first save", Mx.get("first_pass_validity"), qkind, qsrc,
           how="builds whose first save_app was valid ÷ builds"),
         M("q.consistency.repeat", "Same app structure when repeated", (Mx.get("consistency") or {}).get("repeat"), qkind, qsrc,
           how="tasks whose two runs share a structure signature ÷ tasks"),
         M("q.consistency.rewording", "Same app structure when reworded", (Mx.get("consistency") or {}).get("rewording"), qkind, qsrc,
           how="tasks whose reworded run matches the original ÷ tasks"),
         M("q.latency", "Build time, median / p90", kind="live", source=ld,
           value=f"{eb['latency_s']['median']:.1f} s / {eb['latency_s']['p90']:.1f} s" if eb else None,
           how="wall clock from request to reply, measured when the run was recorded"),
         M("q.cost", "Calculated cost per build / per successful build", kind="live", source=ld,
           value=f"${eb['cost_usd']['mean']:.4f} / ${se.get('cost_per_success', 0):.4f}" if eb else None,
           how="Σ tokens × published price per million (input, output, cache write, cache read); not a bill")]
    for a, w in sorted((Mx.get("agent_accuracy") or {}).items()):
        q.append(M(f"q.agent.{a}", f"{a.title()} agent: its own checks", w, qkind, qsrc, how=f"{a} checks passed ÷ {a} checks"))
    if SI:
        s = SI["summary"]
        q.append(M("site", "Site builds with blocks nobody asked for", kind="live", source=site,
                   value=f"{s['with_unrequested_blocks']}/{s['tasks']}", note="one live build so far — a small sample"))
    cats.append({"id": "agents", "title": "1 · Metrics for evaluating the agents", "metrics": q})

    ss = (S or {}).get("summary") or {}
    skind = "live" if s_live else "self-test"
    cats.append({"id": "safety", "title": "2 · Safety guardrails and prompt filtering", "metrics": [
        M("safety.off", "Attacks that worked — guards OFF", ss.get("off", {}).get("all_attack_success"), skind, s_live or s_fake,
          how="attacks whose harmful outcome really happened ÷ attacks"),
        M("safety.on", "Attacks that worked — guards ON", ss.get("on", {}).get("all_attack_success"), skind, s_live or s_fake,
          how="same attacks, guards on", note="" if s_live else "stand-in model: proves the code guards, not the real model"),
        M("heldout.detected", "Scanner on attacks it was never tuned on", wilson(H["detected"], H["attacks"]) if H else None, "measured",
          os.path.join(EV, "heldout.json"), how="held-out attacks detected ÷ held-out attacks (written after tuning)"),
        M("heldout.false", "Scanner false alarms on honest text", wilson(H["false_alarms"], H["honest"]) if H else None, "measured",
          os.path.join(EV, "heldout.json"), how="honest texts flagged ÷ honest texts"),
        M("safety.model", "The real model's own resistance", kind="missing" if not s_live else "live", source=s_live,
          note="python -m evals.safety --mode live --yes  (≈ $0.80)") if not s_live else
        M("safety.model", "The real model's own resistance", ss.get("off", {}).get("file_model_resisted"), "live", s_live)]})

    reas = Mx.get("reasons") or {}
    cats.append({"id": "explain", "title": "3 · Explainability of decisions", "metrics": [
        M("q.reasons", "Stated reasons that explain *why*", reas.get("explains_why"), qkind, qsrc,
          how="reasons with a cause/purpose marker ÷ reasons (keyword heuristic, a lower bound)"),
        M("q.honesty", "Reply never claims it was shared", Mx.get("honesty"), qkind, qsrc, how="replies without such a claim ÷ replies"),
        M("q.faithfulness", "Reply's facts match the saved app", Mx.get("reply_faithfulness"), qkind, qsrc,
          how="dates and places in the reply found in the app ÷ checked"),
        M("tests.trace", "Every model call, tool call and verdict traced", kind="measured", source="data/evals/tests.json",
          value=_suite(T, "test_trace_flow"), how="offline test: a full build's trace is complete and costs add up exactly")]})

    rvs = (RV or {}).get("summary") or {}
    rkind = "live" if r_live else "self-test"
    cats.append({"id": "ethics", "title": "4 · Ethics and responsible AI", "metrics": [
        M("tests.anon", "Anonymity end to end; a person decides on AI flags", kind="measured", source="data/evals/tests.json",
          value=_suite(T, "test_responsible")),
        M("tests.min", "No email addresses sent to the AI", kind="measured", source="data/evals/tests.json", value=_suite(T, "test_minimisation")),
        M("review.false", "Honest work wrongly flagged by the Review agent", rvs.get("false_flag_rate_honest"), rkind, r_live or r_fake,
          note="" if r_live else "stand-in model only — the real model: python -m evals.review_eval --mode live --yes (≈ $0.05)"),
        M("review.fair", "Same verdict whoever's name is on the file", kind="missing" if not r_live else "live", source=r_live,
          value=None if not r_live else f"{rvs.get('fair_sets')}", note="needs the live review run")]})

    selftest_caught = None
    if F:
        bad = [r for r in F["results"] if not r["success"]]
        selftest_caught = f"{len(bad)} deliberately broken run caught" if bad else "broken run NOT caught"
    cats.append({"id": "testing", "title": "5 · Testing approaches", "metrics": [
        M("tests.all", "Offline regression gate", kind="measured", source="data/evals/tests.json",
          value=f"{T['checks_passed']} checks · {len(T['suites'])} suites · {'all pass' if not T['suites_failed'] else str(T['suites_failed']) + ' failing'}" if T else None,
          how="python -m tests.run_all — no API key, no cost"),
        M("selftest", "Harness self-test: a broken run must be caught", kind="self-test", source=fake, value=selftest_caught,
          how="the stand-in plays the reference answers with one run deliberately broken"),
        M("reproduce", "Replaying the recorded live run gives identical results", kind="measured", source="data/evals/reproduce.json",
          value=(f"{rep['identical_runs']}/{rep['runs']} runs · {rep['identical_checks']}/{rep['checks']} checks identical" if rep else None),
          note="" if rep else "press Reproduce", how="re-score the recorded replies now and compare every run and check")]})

    def lvl(rows, users):
        return next((r for r in rows if r.get("builds", r.get("users")) == users), None)
    cats.append({"id": "serving", "title": "6 · Scalable serving", "metrics": [
        M("load.reads", "App opens per second (best level)", kind="measured", source=loads[-1] if loads else None,
          value=f"{max(r['per_second'] for r in LA['reads'])}/s · {sum(r['errors'] for r in LA['reads'])} errors" if LA else None,
          note="one laptop, one server process, stand-in model"),
        M("load.writes", "Submissions per second (best level)", kind="measured", source=loads[-1] if loads else None,
          value=f"{max(r['per_second'] for r in LA['writes'])}/s · {sum(r['errors'] for r in LA['writes'])} errors" if LA else None),
        M("load.builds", "16 simultaneous builds that failed", kind="measured", source=loads[-1] if loads else None,
          value=(f"{lvl(LB['agents'], 16)['errors'] if LB else '?'} before the fix → {lvl(LA['agents'], 16)['errors']} after"
                 if LA and lvl(LA.get('agents', []), 16) else None))]})

    cats.append({"id": "monitoring", "title": "7 · Monitoring", "metrics": [
        M("tests.limits", "Daily budget, per-person limits, alerts", kind="measured", source="data/evals/tests.json", value=_suite(T, "test_limits")),
        M("tests.live", "Screens update by themselves within 2 s", kind="measured", source="data/evals/tests.json", value=_suite(T, "test_live")),
        M("q.cost_total", "Calculated cost of the whole live evaluation", kind="live", source=ld,
          value=f"${(L or {}).get('metrics', {}).get('total_cost_usd', 0):.4f}" if L else None)]})

    cats.append({"id": "deploy", "title": "8 · Principles for reliable deployment", "metrics": [
        M("tests.guard", "Validator + guardrails in code, outside the model", kind="measured", source="data/evals/tests.json", value=_suite(T, "test_guard")),
        M("tests.providers", "Provider switch keeps working (Claude / Groq)", kind="measured", source="data/evals/tests.json", value=_suite(T, "test_providers")),
        M("tests.play", "New app kinds tested before release (quizzes, party, sites)", kind="measured", source="data/evals/tests.json",
          value=" · ".join(x for x in (_suite(T, "test_play"), _suite(T, "test_sites")) if x) or None)]})

    for c in cats:
        for m in c["metrics"]:
            if m.get("value") is None and m["kind"] != "missing":
                m["kind"], m["value"] = "missing", "not measured"
    return {"categories": cats, "quality_source": rel(qsrc), "live_source": rel(ld),
            "run_details": run_details(ld, L), "generated": time.strftime("%Y-%m-%d %H:%M:%S")}


def run_details(folder, data):
    if not data:
        return None
    meta = data.get("meta", {})
    return {"folder": rel(folder), "mode": meta.get("mode"), "started": meta.get("started"), "finished": meta.get("finished"),
            "models": meta.get("models"), "jobs": meta.get("jobs"), "code": meta.get("code"), "git": meta.get("git"),
            "cost_usd": data.get("metrics", {}).get("total_cost_usd"),
            "code_now": code_fingerprints(), "git_now": git_commit(),
            "code_note": None if meta.get("code") else
            "This run happened before runs recorded the fingerprints of the task and check files. Runs from now on record them."}


# --------------------------------------------------------------------------- evidence behind a number

def _results():
    (rd, R), (ld, L) = _quality()
    return (R or L or {}).get("results", []), rd or ld


def evidence(mid):
    res, src = _results()
    rows, cols, note = [], [], ""
    if mid in ("q.success", "q.checks", "q.cost", "q.latency") or mid.startswith("q.agent."):
        agent = mid.split(".")[2] if mid.startswith("q.agent.") else None
        cols = ["Task", "Run", "Result", "Checks", "Time", "Cost", "Failed checks"]
        for r in res:
            chk = [c for c in r["checks"] if not agent or c["agent"] == agent]
            if agent and not chk:
                continue
            bad = [f"{c['agent']}: {c['check']} — {c.get('detail', '')}" for c in chk if not c["passed"]]
            rows.append({"cells": [r["case"], f"{r['variant']} {r['idx'] + 1}", "pass" if (all(c["passed"] for c in chk) and not r.get("error")) else "FAIL",
                                   f"{sum(c['passed'] for c in chk)}/{len(chk)}", f"{(r.get('wall_ms') or 0) / 1000:.1f} s",
                                   f"${(r.get('totals') or {}).get('cost', 0):.4f}", "; ".join(bad)[:300] or (r.get("error") or "")],
                         "run": f"{r['case']}|{r['variant']}|{r['idx']}"})
        note = "Every run of the evaluation. Click a run to see its request, the agent's reply and every check."
    elif mid in ("q.honesty", "q.faithfulness"):
        cols = ["Task", "Run", "Check", "Result", "Reply (start)"]
        want = "claim" if mid == "q.honesty" else "match the saved app"
        for r in res:
            for c in r["checks"]:
                if want in c["check"]:
                    rows.append({"cells": [r["case"], f"{r['variant']} {r['idx'] + 1}", c["check"], "pass" if c["passed"] else "FAIL",
                                           (r.get("reply") or "")[:220]], "run": f"{r['case']}|{r['variant']}|{r['idx']}"})
    elif mid.startswith("q.consistency"):
        Q = (_quality()[0] or (None, None))[1] or {}
        cols = ["Task", "Repeat: same structure", "Reworded: same structure", "Same check outcomes"]
        for t, v in ((Q.get("metrics") or {}).get("consistency", {}).get("per_task") or {}).items():
            rows.append({"cells": [t, v.get("repeat_same_structure"), v.get("reworded_same_structure"), v.get("same_check_outcomes")]})
        note = "A structure signature ignores wording, titles and colours; any other difference counts."
    elif mid == "q.reasons":
        cols = ["Agent", "Tool", "Stated reason"]
        for r in res:
            for x in r.get("reason_texts") or []:
                rows.append({"cells": [x["agent"], x["tool"], x["reason"]]})
        note = "Every reason the agents gave, so the 'explains why' score can be judged by eye."
    elif mid.startswith("heldout"):
        H = _load(os.path.join(EV, "heldout.json")) or {}
        cols = ["Held-out attack", "Detected"]
        missed = set(H.get("missed", []))
        rows = [{"cells": [m, "no"]} for m in sorted(missed)]
        rows += [{"cells": [t, "false alarm on honest text"]} for t in H.get("false_alarm_texts", [])]
        note = f"{H.get('detected')} of {H.get('attacks')} attacks detected; the missed ones are listed. Written after the scanner was tuned."
    elif mid.startswith("safety"):
        d = _newest("safety-live") or _newest("safety-fake")
        S = _load(os.path.join(d, "results.json")) if d else {}
        cols = ["Attack", "Kind", "Guards", "Outcome", "Harm happened"]
        for r in (S or {}).get("results", []):
            rows.append({"cells": [r["id"], r["kind"], r["guards"], r.get("verdict_line") or r.get("final"), "yes" if r.get("succeeded") else "no"]})
        note = "Stand-in model (self-test): shows what the code guards stop. The real model's behaviour is not measured yet." if "fake" in (d or "") else ""
    elif mid.startswith("load"):
        d = _runs("load")[-1] if _runs("load") else None
        LA = _load(os.path.join(d, "load.json")) if d else {}
        cols = ["Test", "Users", "Requests", "Per second", "p95 ms", "Errors"]
        for kind in ("reads", "writes"):
            for r in (LA or {}).get(kind, []):
                rows.append({"cells": [kind, r["users"], r["requests"], r["per_second"], r["p95_ms"], r["errors"]]})
        for r in (LA or {}).get("agents", []):
            rows.append({"cells": ["builds", r.get("builds"), r.get("builds"), "", "", r.get("errors")]})
    elif mid.startswith("tests"):
        T = _load(os.path.join(EV, "tests.json")) or {}
        cols = ["Suite", "What it proves", "Result", "Seconds"]
        rows = [{"cells": [s["suite"], s["what"], f"{'pass' if s['ok'] else 'FAIL'} · {s['passed']}", s["seconds"]]} for s in T.get("suites", [])]
        note = f"Last run {T.get('when')}. Press 'Run the tests' to run them again now."
    elif mid == "selftest":
        d = _newest("fake")
        F = _load(os.path.join(d, "results.json")) if d else {}
        cols = ["Task", "Run", "Result", "Failed checks"]
        for r in (F or {}).get("results", []):
            rows.append({"cells": [r["case"], f"{r['variant']} {r['idx'] + 1}", "pass" if r["success"] else "FAIL (deliberately broken)",
                                   "; ".join(c["check"] for c in r["checks"] if not c["passed"])]})
        note = "The stand-in plays the hand-written reference answers; one run has a question and the audience removed on purpose."
    elif mid == "reproduce":
        rep = _load(os.path.join(EV, "reproduce.json")) or {}
        cols = ["Task", "Run", "Difference"]
        rows = [{"cells": d} for d in rep.get("differences", [])] or [{"cells": ["—", "—", "none: every run and check came out identical"]}]
        note = f"Reproduced {rep.get('when', '')} from {rep.get('source', '')}."
    else:
        note = "No itemised evidence for this number; see its source file."
    return {"id": mid, "columns": cols, "rows": rows, "note": note, "source": rel(src)}


def run_detail(key):
    case, variant, idx = key.split("|")
    res, src = _results()
    r = next((x for x in res if x["case"] == case and x["variant"] == variant and str(x["idx"]) == idx), None)
    if not r:
        return None
    return {k: r.get(k) for k in ("case", "ws", "kind", "level", "variant", "idx", "prompt", "reply", "error", "checks", "wall_ms",
                                   "totals", "agents_used", "params", "reason_texts")}


# --------------------------------------------------------------------------- live vs replay: what changed in the scoring

def audit():
    (rd, R), (ld, L) = _quality()
    if not (R and L):
        return {"available": False}
    key = lambda r: (r["case"], r["variant"], r["idx"])
    Lm = {key(r): r for r in L["results"]}
    added, removed, flipped = {}, {}, {}
    changed = []
    for r in R["results"]:
        a = Lm.get(key(r))
        if not a:
            continue
        ca = {(c["agent"], c["check"]): c["passed"] for c in a["checks"]}
        cb = {(c["agent"], c["check"]): c["passed"] for c in r["checks"]}
        for c in set(cb) - set(ca):
            n = re.sub(r"\s+", " ", c[1])
            added.setdefault(n, {"check": f"{c[0]}: {n}", "count": 0, "passed": 0})
            added[n]["count"] += 1
            added[n]["passed"] += int(cb[c])
        for c in set(ca) - set(cb):
            removed.setdefault(c[1], {"check": f"{c[0]}: {c[1]}", "count": 0})
            removed[c[1]]["count"] += 1
        for c in set(ca) & set(cb):
            if ca[c] != cb[c]:
                f = flipped.setdefault((c, ca[c], cb[c]), {"check": f"{c[0]}: {c[1]}", "from": ca[c], "to": cb[c], "count": 0, "examples": []})
                f["count"] += 1
                if len(f["examples"]) < 20:
                    sent = [s.strip() for s in re.split(r"(?<=[.!?])\s+", r.get("reply") or "") if re.search(r"shar", s, re.I)]
                    f["examples"].append({"run": f"{r['case']} {r['variant']} {r['idx'] + 1}", "text": " … ".join(sent)[:300] or (r.get("reply") or "")[:200]})
        if a["success"] != r["success"]:
            changed.append({"run": f"{r['case']} {r['variant']} {r['idx'] + 1}", "live": a["success"], "replay": r["success"]})
    return {"available": True, "live": rel(ld), "replay": rel(rd),
            "live_metrics": {k: L["metrics"][k] for k in ("success", "checks")},
            "replay_metrics": {k: R["metrics"][k] for k in ("success", "checks")},
            "added": list(added.values()), "removed": list(removed.values()), "flipped": list(flipped.values()),
            "success_changed": changed,
            "note": ("The same recorded replies, scored at the time of the live run and again by the current checks. "
                     "Every difference is listed: checks added, checks removed, and checks whose result changed, with the "
                     "reply sentences involved, so anyone can judge whether each change was a fair correction.")}


# --------------------------------------------------------------------------- reproduce: compare two scorings of the same replies

def compare(a, b):
    """Two result lists for the same recorded replies → how many runs and checks came out identical."""
    key = lambda r: (r["case"], r["variant"], r["idx"])
    bm = {key(r): r for r in b}
    runs = checks = same_runs = same_checks = 0
    diffs = []
    for r in a:
        o = bm.get(key(r))
        runs += 1
        if not o:
            diffs.append([r["case"], f"{r['variant']} {r['idx'] + 1}", "missing from the new run"])
            continue
        ca = {(c["agent"], c["check"]): c["passed"] for c in r["checks"]}
        cb = {(c["agent"], c["check"]): c["passed"] for c in o["checks"]}
        checks += len(ca)
        same_checks += sum(1 for k, v in ca.items() if cb.get(k) == v)
        if r["success"] == o["success"] and ca == cb:
            same_runs += 1
        else:
            d = [f"{k[1]}: {v}→{cb.get(k)}" for k, v in ca.items() if cb.get(k) != v] or [f"success {r['success']}→{o['success']}"]
            diffs.append([r["case"], f"{r['variant']} {r['idx'] + 1}", "; ".join(d)[:300]])
    return {"runs": runs, "identical_runs": same_runs, "checks": checks, "identical_checks": same_checks, "differences": diffs}


def record_reproduce(new_dir):
    """After a fresh replay: compare it with the replay the headline numbers come from and save the result."""
    (rd, R), _ = _quality()
    N = _load(os.path.join(new_dir, "results.json"))
    if not (R and N) or os.path.abspath(rd) == os.path.abspath(new_dir):
        # the new replay IS the newest: compare it with the previous replay of the same live run
        reps = [d for d in _runs("replay") if os.path.abspath(d) != os.path.abspath(new_dir)
                and (_load(os.path.join(d, "results.json")) or {}).get("meta", {}).get("source") == (N or {}).get("meta", {}).get("source")]
        if not reps or not N:
            return None
        rd, R = reps[-1], _load(os.path.join(reps[-1], "results.json"))
    out = compare(R["results"], N["results"])
    out.update(when=time.strftime("%Y-%m-%d %H:%M:%S"), source=N["meta"].get("source"), new=rel(new_dir), previous=rel(rd),
               metrics_new={k: N["metrics"][k] for k in ("success", "checks")})
    json.dump(out, open(os.path.join(EV, "reproduce.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out


# --------------------------------------------------------------------------- seals: tamper evidence

def _sealable():
    files = []
    for d in sorted(glob.glob(os.path.join(EV, "2*"))):
        for p in [os.path.join(d, "results.json"), os.path.join(d, "load.json")] + sorted(glob.glob(os.path.join(d, "cassettes", "*.json"))):
            if os.path.exists(p):
                files.append(p)
    hp = os.path.join(EV, "heldout.json")
    if os.path.exists(hp):
        files.append(hp)
    return files


def seal(seals_path=None, files=None):
    """Fingerprint result files that have no seal yet. A file that already has a seal is never re-sealed."""
    seals_path = seals_path or SEALS
    S = _load(seals_path) or {"about": "SHA-256 fingerprints of evaluation result files. Commit this file; a later change to a "
                                 "sealed file shows as 'modified' in the Evaluation tab.", "files": {}}
    new = 0
    for p in (files if files is not None else _sealable()):
        k = rel(p)
        if k not in S["files"]:
            S["files"][k] = {"sha256": sha256(p), "sealed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "bytes": os.path.getsize(p)}
            new += 1
    S["git_at_last_seal"] = git_commit()
    json.dump(S, open(seals_path, "w", encoding="utf-8"), indent=1)
    return {"sealed_now": new, "total": len(S["files"])}


def check_seals(seals_path=None, files=None):
    S = _load(seals_path or SEALS) or {"files": {}}
    ok, bad, missing = 0, [], []
    for k, v in S["files"].items():
        p = os.path.join(ROOT, k)
        if not os.path.exists(p):
            missing.append(k)
        elif sha256(p) != v["sha256"]:
            bad.append(k)
        else:
            ok += 1
    unsealed = [rel(p) for p in (files if files is not None else _sealable()) if rel(p) not in S["files"]]
    first = min((v["sealed_at"] for v in S["files"].values()), default=None)
    return {"sealed": len(S["files"]), "match": ok, "modified": bad, "missing": missing, "unsealed": unsealed,
            "first_sealed": first, "committed": _committed(),
            "note": ("A seal proves a file has not changed since it was sealed. Files sealed after a run can't prove what "
                     "happened before the seal; for that, Reproduce re-scores the recorded replies from scratch.")}


def _committed():
    """Is SEALS.json in git (so its fingerprints and date are public)?"""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%h %ad", "--date=iso", "--", "evals/SEALS.json"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return out or None
    except (OSError, subprocess.SubprocessError):
        return None


# --------------------------------------------------------------------------- history

def history():
    out = []
    for d in sorted(glob.glob(os.path.join(EV, "2*")), reverse=True):
        name = os.path.basename(d)
        kind = name.split("-", 2)[2] if name.count("-") >= 2 else "?"
        R = _load(os.path.join(d, "results.json")) or _load(os.path.join(d, "load.json")) or {}
        m = R.get("metrics") or {}
        head = ""
        if m.get("success"):
            head = f"success {m['success']['k']}/{m['success']['n']} · checks {m['checks']['k']}/{m['checks']['n']}"
        elif R.get("summary", {}).get("on"):
            head = f"attacks worked: off {R['summary']['off']['all_attack_success']['k']}/{R['summary']['off']['all_attack_success']['n']} → on {R['summary']['on']['all_attack_success']['k']}/{R['summary']['on']['all_attack_success']['n']}"
        elif kind == "examiner" and R.get("result"):
            x = R["result"]
            head = f"{'pass' if x['success'] else 'FAIL'} · {sum(c['passed'] for c in x['checks'])}/{len(x['checks'])} checks · {x['request'][:60]}"
        elif R.get("summary", {}).get("tasks"):
            head = f"{R['summary']['tasks']} task(s)"
        meta = R.get("meta") or {}
        out.append({"folder": rel(d), "kind": kind, "when": meta.get("started") or R.get("when") or name[:13],
                    "head": head, "cost": m.get("total_cost_usd"), "source": meta.get("source"),
                    "label": "self-test" if "fake" in kind else "measured" if kind in ("load",) else "replayed" if kind == "replay" else "live"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--reproduce-from", help="a replay folder just written: compare and save data/evals/reproduce.json")
    a = ap.parse_args()
    if a.seal:
        print(json.dumps(seal(), indent=1))
    if a.check:
        print(json.dumps(check_seals(), indent=1))
    if a.audit:
        A = audit()
        print(json.dumps({k: A[k] for k in ("live_metrics", "replay_metrics", "added", "removed")}, indent=1, ensure_ascii=False))
        for f in A["flipped"]:
            print(f["check"], f["from"], "→", f["to"], "×", f["count"])
    if a.reproduce_from:
        print(json.dumps(record_reproduce(a.reproduce_from), indent=1))


if __name__ == "__main__":
    main()
