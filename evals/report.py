"""Writes the evaluation report (Markdown + a self-contained HTML page) from results and metrics."""
import html
import json

from evals.metrics import __doc__ as DEFINITIONS

MODE_NOTE = {
    "live": "LIVE — real Claude agents on the real AppShare code. Every reply was recorded, so this run can be replayed without an API key.",
    "replay": "REPLAY — recorded real Claude replies fed back through the current code (no API calls). Latency is the time measured when recorded.",
    "fake": "HARNESS SELF-TEST — a scripted stand-in plays the reference answers (one run is deliberately broken). These numbers test the "
            "evaluation itself and say NOTHING about agent quality.",
}


def pct(w):
    return "—" if not w else f"{w['rate'] * 100:.1f}% ({w['k']}/{w['n']}, 95% CI {w['lo'] * 100:.0f}–{w['hi'] * 100:.0f}%)"


def num(d, k="mean", f="{:.3g}"):
    return "—" if not d else f.format(d[k])


def sections(meta, M, results):
    S = []
    S.append(("Summary", [
        ["Mode", MODE_NOTE[meta["mode"]]],
        ["When", meta["started"]], ["Models", f"Builder/Insights: {meta['models']['main']} · specialists: {meta['models']['specialist']}"],
        ["Runs", f"{M['tasks']['runs']} runs of {M['tasks']['distinct_tasks']} tasks ({M['tasks']['errors']} errored)"],
        ["Task success", pct(M["success"])], ["Checks passed", pct(M["checks"])],
        ["First-pass validity (Builder)", pct(M["first_pass_validity"])], ["Honesty (never claims it shared)", pct(M["honesty"])],
        ["Repeat consistency", pct(M["consistency"]["repeat"])], ["Rewording consistency", pct(M["consistency"]["rewording"])],
        ["Total cost of this evaluation", f"${M['total_cost_usd']:.4f} (calculated from measured tokens)"],
    ]))
    S.append(("Agent accuracy (checks that are each agent's job)", [[a, pct(w)] for a, w in M["agent_accuracy"].items()]))
    rows = [["Reply faithful to the saved app (dates, places)", pct(M.get("reply_faithfulness"))]]
    for kind, e in (M.get("success_efficiency") or {}).items():
        rows.append([f"{kind}: cost per successful run", "—" if e["cost_per_success"] is None else f"${e['cost_per_success']:.4f}"])
        rows.append([f"{kind}: steps to success", f"{num(e['model_calls_to_success'])} model calls · {num(e['tool_calls_to_success'])} tool calls (mean)"])
        rows.append([f"{kind}: wasted steps per run", f"{num(e['wasted_steps_per_run'])} (tool errors + Validator rejections)"])
    R_ = M.get("reasons") or {}
    if R_.get("explains_why"):
        rows.append(["Stated reasons that explain why (heuristic)", pct(R_["explains_why"])])
        rows += [[f"  {a}", pct(w)] for a, w in R_["by_agent"].items()]
        rows += [["  sample: explains why", x] for x in R_["samples_why"][:2]] + [["  sample: restates what", x] for x in R_["samples_not"][:2]]
    S.append(("Faithfulness, efficiency of success, explanation quality", rows))
    S.append(("Success by task kind / level / workspace",
              [[f"kind: {k}", pct(w)] for k, w in M["success_by_kind"].items()] + [[f"level {k}", pct(w)] for k, w in M["success_by_level"].items()]
              + [[f"workspace: {k}", pct(w)] for k, w in M["success_by_ws"].items()]))
    rows = []
    for kind, e in M["efficiency"].items():
        rows.append([kind, f"latency {num(e['latency_s'], 'median')} s median · p90 {num(e['latency_s'], 'p90')} s",
                     f"{num(e['model_calls'])} model calls · {num(e['tool_calls'])} tool calls (mean)",
                     f"{num(e['tokens_in'], 'mean', '{:,.0f}')} tokens in · {num(e['tokens_out'], 'mean', '{:,.0f}')} out · cache {num(e['cache_share'], 'mean', '{:.0%}')}",
                     f"${num(e['cost_usd'], 'mean', '{:.4f}')} mean · ${num(e['cost_usd'], 'max', '{:.4f}')} max",
                     f"{e['retries']} retries · {e['tool_errors']} tool errors"])
    S.append(("Efficiency per run", rows))
    cx = M["complexity"]
    rows = [[f"level {lv}", f"{d['tasks']} tasks", pct(d["success"]), f"{num(d['latency_s'], 'median')} s", f"${num(d['cost_usd'], 'mean', '{:.4f}')}",
             f"{num(d['model_calls'])} calls"] for lv, d in cx["by_level"].items()]
    for k, label in (("vs_cost", "cost"), ("vs_latency", "latency"), ("vs_model_calls", "model calls"), ("vs_tokens", "tokens")):
        p = cx[k]
        rows.append([f"complexity vs {label}", "—" if not p else f"Pearson r = {p['r']} (n={p['n']}), slope {p['slope']:.4g} per complexity point", "", "", "", ""])
    S.append(("Cost and latency against request complexity", rows))
    S.append(("Consistency per task", [[cid, f"repeat same: {v['repeat_same_structure']}", f"reworded same: {v['reworded_same_structure']}",
                                        f"same check outcomes: {v['same_check_outcomes']}"] for cid, v in M["consistency"]["per_task"].items()]))
    S.append(("Most failed checks", [[c, str(n)] for c, n in M["most_failed_checks"]] or [["none", "0"]]))
    rows = []
    for r in results:
        failed = [f"{c['agent']}: {c['check']} — {c['detail']}" for c in r["checks"] if not c["passed"]]
        rows.append([f"{r['case']} · {r['variant']} #{r['idx']}", "PASS" if r["success"] else "FAIL",
                     f"{sum(c['passed'] for c in r['checks'])}/{len(r['checks'])}",
                     f"{(r.get('wall_ms') or 0) / 1000:.1f} s", f"${(r.get('totals') or {}).get('cost', 0):.4f}",
                     r["error"] or ("; ".join(failed) or "")])
    S.append(("Every run", rows))
    return S


def write(run_dir, meta, M, results):
    S = sections(meta, M, results)
    md = [f"# AppShare agent evaluation — {meta['started']}", "", f"> {MODE_NOTE[meta['mode']]}", ""]
    for title, rows in S:
        md += [f"## {title}", ""]
        w = max(len(r) for r in rows) if rows else 2
        md += ["| " + " | ".join([""] * w) + " |", "|" + "---|" * w]
        md += ["| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in r + [""] * (w - len(r))) + " |" for r in rows]
        md.append("")
    md += ["## Definitions", "", "```", DEFINITIONS.strip(), "```", ""]
    open(f"{run_dir}/report.md", "w", encoding="utf-8").write("\n".join(md))

    E = html.escape
    pts = M["complexity"]["points"]
    chart = scatter(pts, "cost", "Cost per build (USD)", "${:.3f}") + scatter(pts, "latency_s", "Build time (s)", "{:.0f} s")
    body = [f"<h1>AppShare agent evaluation</h1><p class='sub'>{E(meta['started'])}</p>",
            f"<div class='banner {meta['mode']}'>{E(MODE_NOTE[meta['mode']])}</div>"]
    for title, rows in S:
        body.append(f"<h2>{E(title)}</h2><table>{''.join('<tr>' + ''.join(f'<td>{E(str(c))}</td>' for c in r) + '</tr>' for r in rows)}</table>")
        if title.startswith("Cost and latency"):
            body.append(f"<div class='charts'>{chart}</div>")
    body.append(f"<h2>Definitions</h2><pre>{E(DEFINITIONS.strip())}</pre>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent evaluation</title><style>
:root{{--bg:#faf8f3;--ink:#1b1a17;--ink2:#5d5a52;--line:#e3ded2;--card:#fff;--acc:#c4471a;--dot:#3987e5;--bad:#d03b3b}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#111110;--ink:#ecebe4;--ink2:#a9a79c;--line:#2c2b27;--card:#181816;--acc:#ff8a5c;--dot:#5b9cf0;--bad:#f08a7f}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:24px 16px 60px;max-width:1100px;margin:auto}}
h1{{margin:0;font-size:1.6rem}} h2{{font-size:1.05rem;margin:28px 0 8px}} .sub{{color:var(--ink2);margin:2px 0 14px}}
.banner{{padding:12px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);border-left:4px solid var(--acc)}}
.banner.fake{{border-left-color:var(--bad)}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:.86rem}}
td{{padding:7px 10px;border-top:1px solid var(--line);vertical-align:top}} tr:first-child td{{border-top:none}} td:first-child{{font-weight:600;white-space:nowrap}}
pre{{background:var(--card);border:1px solid var(--line);padding:12px;border-radius:8px;white-space:pre-wrap;font-size:.8rem}}
.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;margin-top:12px}}
.chart{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}} .chart svg{{width:100%;height:auto}}
.ax{{fill:var(--ink2);font-size:11px}} .grid{{stroke:var(--line)}} .pt{{fill:var(--dot);stroke:var(--card);stroke-width:2}} .pt.fail{{fill:var(--bad)}}
@media (max-width:640px){{td:first-child{{white-space:normal}}}}
</style></head><body>{''.join(body)}</body></html>"""
    open(f"{run_dir}/report.html", "w", encoding="utf-8").write(page)
    json.dump({"meta": meta, "metrics": M, "results": results}, open(f"{run_dir}/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def scatter(pts, key, title, fmt):
    pts = [p for p in pts if p.get(key) is not None]
    if not pts:
        return ""
    W, H, L, B, T, R = 460, 260, 56, 36, 14, 12
    xs, ys = [p["complexity"] for p in pts], [p[key] for p in pts]
    x0, x1 = 0, max(xs) * 1.1 or 1
    y1 = max(ys) * 1.15 or 1
    X = lambda v: L + (v - x0) / (x1 - x0) * (W - L - R)
    Y = lambda v: H - B - v / y1 * (H - B - T)
    g = "".join(f"<line class='grid' x1='{L}' x2='{W - R}' y1='{Y(y1 * f / 4):.1f}' y2='{Y(y1 * f / 4):.1f}'/><text class='ax' x='{L - 6}' y='{Y(y1 * f / 4) + 4:.1f}' text-anchor='end'>{fmt.format(y1 * f / 4)}</text>" for f in range(5))
    dots = "".join(f"<circle class='pt {'' if p['success'] else 'fail'}' cx='{X(p['complexity']):.1f}' cy='{Y(p[key]):.1f}' r='5'><title>{html.escape(p['case'])} ({p['variant']}): {fmt.format(p[key])}</title></circle>" for p in pts)
    xt = "".join(f"<text class='ax' x='{X(v):.1f}' y='{H - B + 16}' text-anchor='middle'>{v}</text>" for v in sorted(set(xs)))
    return (f"<div class='chart'><b>{html.escape(title)} vs complexity</b><svg viewBox='0 0 {W} {H}' role='img' aria-label='{html.escape(title)} against complexity'>"
            f"{g}{dots}{xt}<text class='ax' x='{(L + W) / 2}' y='{H - 4}' text-anchor='middle'>complexity score (questions + 2×rules + audience)</text></svg>"
            f"<div class='sub' style='font-size:.78rem'>Blue = task passed · red = failed. Hover a point for the task.</div></div>")
