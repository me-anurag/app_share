"""Turns task results into the evaluation's numbers. Every number here is computed from the results; none is set by hand.

Definitions (also printed in the report):
  task success          every check of the task passed and nothing errored
  check pass rate       passed checks / all checks
  agent accuracy        pass rate of the checks that are that agent's job
  first-pass validity   the Builder's first save_app was accepted by the Validator (no fix-up round needed)
  honesty               the reply never claims the app was shared (only the owner can share)
  repeat consistency    the same request twice gives the same app structure (signature: field types, options,
                        places, rules, deadline date, audience) — wording and colours are ignored
  rewording consistency the reworded request gives the same structure as the original
  complexity score      of the task's reference app: questions + 2 x active rules + audience entries
  95% intervals         Wilson score interval (sound for small samples and rates near 0 or 1)
  cost per success      total cost of all runs of a kind / number of successful runs (failures still cost money)
  steps to success      model calls and tool calls of successful runs; wasted steps = tool errors + Validator rejections
  reply faithfulness    dates and numbers of places the reply mentions exist in the saved app
  reason explains why   heuristic: the stated reason contains a cause or purpose ("because", "so that", "the request",
                        "needs", "asked", "for a/the"...) instead of only restating the action. Samples are listed.
"""
import re

WHY = re.compile(r"\b(because|since|so (that|students|people|it|they|the)|as (the|they|it|this)|to (let|make|keep|avoid|allow|match|meet|stop|give)|"
                 r"the (request|brief|user|owner)|asked|needs?|requires?|required|for (a|an|the|students|people)|given|which|purpose|otherwise|instead)\b", re.I)
import math
import statistics
from collections import Counter, defaultdict


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"rate": round(p, 4), "k": k, "n": n, "lo": round(max(0, c - h), 4), "hi": round(min(1, c + h), 4)}


def describe(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    s = sorted(xs)
    return {"n": len(s), "mean": round(statistics.mean(s), 4), "median": round(statistics.median(s), 4),
            "p90": round(s[min(len(s) - 1, int(math.ceil(0.9 * len(s))) - 1)], 4), "min": round(s[0], 4), "max": round(s[-1], 4)}


def pearson(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pts) < 3:
        return None
    mx, my = statistics.mean(p[0] for p in pts), statistics.mean(p[1] for p in pts)
    sx = math.sqrt(sum((p[0] - mx) ** 2 for p in pts))
    sy = math.sqrt(sum((p[1] - my) ** 2 for p in pts))
    if sx == 0 or sy == 0:
        return None
    r = sum((p[0] - mx) * (p[1] - my) for p in pts) / (sx * sy)
    slope = r * sy / sx
    return {"r": round(r, 3), "slope": round(slope, 6), "n": len(pts)}


def complexity(res):
    p = res.get("reference_params")
    if not p:
        return res["level"]
    return p["fields"] + 2 * p["active_rules"] + res.get("reference_shares", 0)


def compute(results):
    M = {}
    ok = [r for r in results if r["success"]]
    M["tasks"] = {"runs": len(results), "distinct_tasks": len({r["case"] for r in results}), "errors": sum(1 for r in results if r["error"])}
    M["success"] = wilson(len(ok), len(results))
    for key in ("kind", "level", "ws"):
        M[f"success_by_{key}"] = {str(v): wilson(sum(1 for r in results if r[key] == v and r["success"]), sum(1 for r in results if r[key] == v))
                                  for v in sorted({r[key] for r in results}, key=str)}
    allc = [c for r in results for c in r["checks"]]
    M["checks"] = wilson(sum(c["passed"] for c in allc), len(allc))
    by_agent = defaultdict(list)
    for c in allc:
        by_agent[c["agent"]].append(c["passed"])
    M["agent_accuracy"] = {a: wilson(sum(v), len(v)) for a, v in sorted(by_agent.items())}
    fails = Counter(f"{c['agent']}: {c['check']}" for c in allc if not c["passed"])
    M["most_failed_checks"] = fails.most_common(10)

    builds = [r for r in results if r["kind"] == "build"]
    fp = [r["validator_first_pass"] for r in builds if r.get("validator_first_pass") is not None]
    M["first_pass_validity"] = wilson(sum(fp), len(fp))
    dfp = [r["data_first_check"] for r in builds if r.get("data_first_check") is not None]
    M["data_first_check_valid"] = wilson(sum(dfp), len(dfp))
    hon = [c["passed"] for r in builds for c in r["checks"] if c["check"].startswith("reply doesn't claim")]
    M["honesty"] = wilson(sum(hon), len(hon))
    M["stated_reasons_per_build"] = describe([r.get("reasons") for r in builds])

    # efficiency of success: what a working result costs, and how many steps it takes
    eff2 = {}
    for kind in sorted({r["kind"] for r in results}):
        rs = [r for r in results if r["kind"] == kind and r.get("totals")]
        ok_rs = [r for r in rs if r["success"]]
        cost = sum(r["totals"]["cost"] or 0 for r in rs)
        eff2[kind] = {"cost_per_success": round(cost / len(ok_rs), 5) if ok_rs else None,
                      "model_calls_to_success": describe([r["totals"]["llm_calls"] for r in ok_rs]),
                      "tool_calls_to_success": describe([r["totals"]["tool_calls"] for r in ok_rs]),
                      "wasted_steps_per_run": describe([r["totals"]["tool_errors"] + r["totals"].get("rejected", 0) for r in rs])}
    M["success_efficiency"] = eff2
    faith = [c["passed"] for r in builds for c in r["checks"] if c["check"].startswith("reply's ")]
    M["reply_faithfulness"] = wilson(sum(faith), len(faith))
    reasons = [x for r in builds for x in r.get("reason_texts") or []]
    why = [bool(WHY.search(x["reason"] or "")) for x in reasons]
    M["reasons"] = {"explains_why": wilson(sum(why), len(why)),
                    "by_agent": {a: wilson(sum(1 for x in reasons if x["agent"] == a and WHY.search(x["reason"] or "")),
                                           sum(1 for x in reasons if x["agent"] == a)) for a in sorted({x["agent"] for x in reasons})},
                    "samples_why": [x["reason"] for x in reasons if WHY.search(x["reason"] or "")][:4],
                    "samples_not": [x["reason"] for x in reasons if not WHY.search(x["reason"] or "")][:4]}

    # consistency across repeats and rewordings
    per = defaultdict(list)
    for r in builds:
        per[r["case"]].append(r)
    cons, rep_same, para_same, outcome_same = {}, [], [], []
    for cid, rs in per.items():
        orig = [r for r in rs if r["variant"] == "original" and not r["error"]]
        para = [r for r in rs if r["variant"] == "paraphrase" and not r["error"]]
        ref = Counter(r["signature"] for r in orig).most_common(1)[0][0] if orig else None
        rep = len({r["signature"] for r in orig}) == 1 if len(orig) >= 2 else None
        par = all(r["signature"] == ref for r in para) if (para and ref) else None
        outs = {tuple(c["passed"] for c in r["checks"]) for r in rs if not r["error"]}
        same_out = len(outs) == 1 if len(rs) >= 2 else None
        cons[cid] = {"repeat_same_structure": rep, "reworded_same_structure": par, "same_check_outcomes": same_out, "runs": len(rs)}
        if rep is not None:
            rep_same.append(rep)
        if par is not None:
            para_same.append(par)
        if same_out is not None:
            outcome_same.append(same_out)
    M["consistency"] = {"repeat": wilson(sum(rep_same), len(rep_same)), "rewording": wilson(sum(para_same), len(para_same)),
                        "check_outcomes": wilson(sum(outcome_same), len(outcome_same)), "per_task": cons}
    other = [r for r in results if r["kind"] != "build"]
    ins_out = defaultdict(set)
    for r in other:
        ins_out[r["case"]].add(tuple(c["passed"] for c in r["checks"]))
    M["consistency"]["insights_reminder_same_outcome"] = wilson(sum(1 for v in ins_out.values() if len(v) == 1), len(ins_out))

    # efficiency
    eff = {}
    for kind in sorted({r["kind"] for r in results}):
        rs = [r for r in results if r["kind"] == kind and r.get("totals")]
        eff[kind] = {"latency_s": describe([r["wall_ms"] / 1000 for r in rs if r.get("wall_ms") is not None]),
                     "model_calls": describe([r["totals"]["llm_calls"] for r in rs]), "tool_calls": describe([r["totals"]["tool_calls"] for r in rs]),
                     "tokens_in": describe([r["totals"]["tokens_in"] + r["totals"]["cache_read"] + r["totals"]["cache_write"] for r in rs]),
                     "tokens_out": describe([r["totals"]["tokens_out"] for r in rs]), "cost_usd": describe([r["totals"]["cost"] for r in rs]),
                     "cache_share": describe([(r["totals"]["cache_read"] / max(1, r["totals"]["tokens_in"] + r["totals"]["cache_read"] + r["totals"]["cache_write"])) for r in rs]),
                     "retries": sum(r["totals"]["retries"] for r in rs), "tool_errors": sum(r["totals"]["tool_errors"] for r in rs)}
    M["efficiency"] = eff
    M["total_cost_usd"] = round(sum((r.get("totals") or {}).get("cost") or 0 for r in results), 4)
    M["total_tokens"] = sum(((r.get("totals") or {}).get("tokens_in", 0) + (r.get("totals") or {}).get("tokens_out", 0)
                             + (r.get("totals") or {}).get("cache_read", 0) + (r.get("totals") or {}).get("cache_write", 0)) for r in results)

    # cost and latency against complexity (builds)
    xs = [complexity(r) for r in builds]
    M["complexity"] = {
        "by_level": {str(lv): {"tasks": len({r["case"] for r in builds if r["level"] == lv}),
                               "success": wilson(sum(1 for r in builds if r["level"] == lv and r["success"]), sum(1 for r in builds if r["level"] == lv)),
                               "latency_s": describe([r["wall_ms"] / 1000 for r in builds if r["level"] == lv and r.get("wall_ms")]),
                               "cost_usd": describe([r["totals"]["cost"] for r in builds if r["level"] == lv and r.get("totals")]),
                               "model_calls": describe([r["totals"]["llm_calls"] for r in builds if r["level"] == lv and r.get("totals")])}
                     for lv in sorted({r["level"] for r in builds})},
        "vs_cost": pearson(xs, [(r.get("totals") or {}).get("cost") for r in builds]),
        "vs_latency": pearson(xs, [r["wall_ms"] / 1000 if r.get("wall_ms") else None for r in builds]),
        "vs_model_calls": pearson(xs, [(r.get("totals") or {}).get("llm_calls") for r in builds]),
        "vs_tokens": pearson(xs, [((r.get("totals") or {}).get("tokens_in", 0) + (r.get("totals") or {}).get("cache_read", 0)
                                   + (r.get("totals") or {}).get("cache_write", 0) + (r.get("totals") or {}).get("tokens_out", 0)) or None for r in builds]),
        "points": [{"case": r["case"], "variant": r["variant"], "complexity": complexity(r), "cost": (r.get("totals") or {}).get("cost"),
                    "latency_s": r["wall_ms"] / 1000 if r.get("wall_ms") else None, "success": r["success"]} for r in builds],
    }
    return M
