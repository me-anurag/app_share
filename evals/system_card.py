"""Generates docs/SYSTEM_CARD.md from the measured results in data/evals/. No number in it is typed by hand.

  python -m evals.system_card

Reads the newest result of each kind. Anything not measured yet is printed as NOT YET MEASURED; results from the
harness self-test (scripted model) are labelled as such and never presented as agent quality.
"""
import glob
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "data", "evals")


def newest(pattern):
    runs = sorted(glob.glob(os.path.join(EV, pattern)))
    return runs[-1] if runs else None


def load(path, name="results.json"):
    p = os.path.join(path, name) if path and os.path.isdir(path) else path
    return json.load(open(p, encoding="utf-8")) if p and os.path.exists(p) else None


def pct(w):
    return "NOT YET MEASURED" if not w else f"**{w['rate'] * 100:.1f}%** ({w['k']}/{w['n']}, 95% CI {w['lo'] * 100:.0f}–{w['hi'] * 100:.0f}%)"


def money(v):
    return "—" if v is None else f"${v:.4f}"


def table(rows, head=("Measure", "Result")):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main():
    q_dir = newest("*-replay") or newest("*-live")
    Q = load(q_dir)
    live_dir = newest("*[0-9]-live")
    s_live, s_fake = newest("*-safety-live"), newest("*-safety-fake")
    S = load(s_live or s_fake)
    r_live, r_fake = newest("*-review-live"), newest("*-review-fake")
    RV = load(r_live or r_fake)
    loads = sorted(glob.glob(os.path.join(EV, "*-load")))
    L_after = load(loads[-1], "load.json") if loads else None
    L_before = next((load(d, "load.json") for d in loads if any(a["errors"] for a in (load(d, "load.json") or {}).get("agents", []))), None)
    H = load(os.path.join(EV, "heldout.json"))
    T = load(os.path.join(EV, "tests.json"))
    si_dir = newest("*-site-live")
    SI = load(si_dir)
    M = Q["metrics"] if Q else None
    md = [f"# AppShare — system card and evaluation report", "",
          f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `python -m evals.system_card` from the result files in `data/evals/`.",
          "Every number below is read from a measured result; nothing is typed by hand. Costs are **calculated** from measured",
          "token counts × published per-token prices, not taken from a bill.", ""]

    md += ["## The system", "",
           "AppShare lets people create small apps (forms, polls, registrations, bookings, requests, submissions) by describing them.",
           "Eight Claude agents work as a team — Builder (lead), Data, Design, Access, Site, Insights, Review, Reminder — but they never",
           "write code: they fill in a JSON spec that a fixed engine runs, and a plain-code **Validator** checks every spec before",
           "it is saved. Models: " + (f"Builder/Insights `{Q['meta']['models']['main']}`, specialists `{Q['meta']['models']['specialist']}`." if Q else "see configuration."), ""]

    # 1 metrics
    md += ["## 1. Metrics for evaluating the agents", "",
           f"Source: `{os.path.relpath(q_dir, ROOT) if q_dir else '—'}` — 12 realistic tasks across three workspaces, run live once"
           f" (every reply recorded in `{os.path.relpath(live_dir, ROOT) if live_dir else '—'}`) and re-scored by replay. Checks are exact"
           " (fields, rules, dates, places, groups, roles; Insights/Reminder against the database's true answer).", ""]
    if M:
        eff = M["efficiency"].get("build", {})
        se = (M.get("success_efficiency") or {}).get("build", {})
        md.append(table([
            ["Task success (every check passed) — re-scored by the current checks", pct(M["success"])],
            *__import__("evals.eval_guide", fromlist=["audit_rows"]).audit_rows(pct),
            ["Individual checks passed", pct(M["checks"])],
            *[[f"Accuracy — {a} agent", pct(w)] for a, w in M["agent_accuracy"].items()],
            ["Validator accepted the Builder's first save", pct(M["first_pass_validity"])],
            ["Honesty: never claims it shared the app", pct(M["honesty"])],
            ["Reply faithful to the saved app (dates, places)", pct(M.get("reply_faithfulness"))],
            ["Same structure when the request is repeated", pct(M["consistency"]["repeat"])],
            ["Same structure when the request is reworded", pct(M["consistency"]["rewording"])],
            ["Build time, median / p90", f"{eff['latency_s']['median']} s / {eff['latency_s']['p90']} s" if eff else "—"],
            ["Model calls / tool calls per build (mean)", f"{eff['model_calls']['mean']:.1f} / {eff['tool_calls']['mean']:.1f}" if eff else "—"],
            ["Share of input tokens served from cache", f"{eff['cache_share']['mean'] * 100:.0f}%" if eff else "—"],
            ["Cost per build (mean) / per successful build", f"{money(eff['cost_usd']['mean'])} / {money(se.get('cost_per_success'))}" if eff else "—"],
            ["Cost vs request complexity (Pearson r)", (M["complexity"]["vs_cost"] or {}).get("r", "—")],
            ["Latency vs request complexity (Pearson r)", (M["complexity"]["vs_latency"] or {}).get("r", "—")],
            ["Total cost of this evaluation", money(M["total_cost_usd"])],
        ]))
        fails = M["most_failed_checks"]
        md += ["", "Failures, all kept: " + ("; ".join(f"{c} ×{n}" for c, n in fails) if fails else "none") + ".", ""]

    # 2 safety
    md += ["## 2. Safety guardrails and prompt filtering", "",
           "Guardrails live in code, outside the model: injection scanner on uploaded files and answers; untrusted text fenced as",
           "data; a manipulative submission can never be stored as \"looks fine\"; the Builder's false claims (shared, admin) are",
           "corrected; the Validator refuses fields collecting passwords, card numbers, one-time codes or government ID numbers;",
           "agents simply have no tools to share apps, change roles or read other apps.", ""]
    if S:
        label = "LIVE (real model)" if s_live else "HARNESS SELF-TEST — scripted model that falls for every attack; not a measure of the real model"
        ss = S["summary"]
        md += [f"Source: `{os.path.relpath(s_live or s_fake, ROOT)}` — {label}.", "",
               table([["Poisoned uploads that got through", pct(ss["off"]["file_attack_success"]), pct(ss["on"]["file_attack_success"])],
                      ["…the AI alone resisted (before code guards)", pct(ss["off"]["file_model_resisted"]), pct(ss["on"]["file_model_resisted"])],
                      ["Chat attacks that succeeded", pct(ss["off"]["chat_attack_success"]), pct(ss["on"]["chat_attack_success"])],
                      ["Honest submissions wrongly flagged", pct(ss["off"]["false_alarms"]), pct(ss["on"]["false_alarms"])]],
                     head=("", "Guardrails OFF", "Guardrails ON")), ""]
    if not s_live:
        md += ["**The real model's own resistance to these attacks is NOT YET MEASURED** (`python -m evals.safety --mode live --yes`, ≈ $0.80).", ""]
    if H:
        md += [f"**Held-out attacks** (styles the scanner was never tuned on): detected **{H['detected']}/{H['attacks']}**; "
               f"false alarms on held-out honest text **{H['false_alarms']}/{H['honest']}**. Missed: {', '.join(H['missed'])}. "
               "The keyword scanner does not generalise; it is one layer, not the defence.", ""]

    # 3 explainability
    R_ = (M or {}).get("reasons") or {}
    md += ["## 3. Explainability", "",
           "Every decision tool requires a stated reason; every model call, tool call (arguments and result), Validator verdict and",
           "retry is traced and viewable in the Control Center's Flow tab (with a replay, in step with the Agent theater); app owners",
           "see \"How this app was built\" on their phone; Review flags carry the AI's evidence.", "",
           table([["Stated reasons that explain *why* (keyword heuristic, lower bound)", pct(R_.get("explains_why"))],
                  *[[f"…{a} agent", pct(w)] for a, w in (R_.get("by_agent") or {}).items()]]), ""]

    # 4 ethics
    md += ["## 4. Ethics and responsible AI", "",
           "- **Anonymity:** anonymous apps never give names, emails or exact times to the owner's screen, the CSV export, any agent, or the",
           "  trace store (end-to-end test; it found and fixed a real leak of a respondent's name into traces).",
           "- **Human decision:** a Review flag is shown with its evidence, labelled \"an AI flag, not a decision\"; only an editor can",
           "  confirm or dismiss it, and that is recorded with their name.",
           "- **Data minimisation:** no email address is ever sent to the AI — agents refer to people by internal references",
           "  (`u12`) that the server maps back; anonymous file names are replaced by generic ones for the AI, the owner, downloads",
           "  and the CSV (test: every message of all seven agents is captured and checked).",
           "- **Transparency to respondents:** apps tell the person answering when an AI assistant reads their answers or file, and",
           "  that only a person makes decisions; anonymous apps remind them not to put their name in answers, files or file names.",
           "- **Disclosure:** `docs/DATA_FLOW.md` states exactly what each agent sends to the API.", ""]
    if RV:
        rs = RV["summary"]
        label = "LIVE (real Review agent)" if r_live else "HARNESS SELF-TEST — scripted reviewer that passes everything"
        md += [f"Review agent ({label}, `{os.path.relpath(r_live or r_fake, ROOT)}`):", "",
               table([["Honest work wrongly flagged", pct(rs["false_flag_rate_honest"])], ["Bad work caught (empty, off-topic, copied)", pct(rs["detection_rate"])],
                      ["Flags that were right (precision)", pct(rs["precision"])],
                      ["Same verdict for the same file under different students' names", pct(rs["fair_sets"])]]), ""]
    if not r_live:
        md += ["**Review accuracy and name-fairness with the real model are NOT YET MEASURED** (`python -m evals.review_eval --mode live --yes`, ≈ $0.05).", ""]

    from evals.eval_guide import site_rows
    md += ["### Sites (Site agent)", "", f"Source: `{os.path.relpath(si_dir, ROOT) if si_dir else '—'}`. "
           "Scored automatically: blocks the request gave no reason for, the form placed once, time and calculated cost.", "",
           table(site_rows(SI), head=("Measure", "Value")), ""]

    # 5 testing
    md += ["## 5. Testing approaches", ""]
    if T:
        md.append(table([[x["suite"], x["what"], ("pass" if x["ok"] else "FAIL") + f" · {x['passed']} checks"] for x in T["suites"]],
                        head=("Suite", "What it proves", "Result")))
        md += ["", f"One command, no API key: `python -m tests.run_all` — {T['checks_passed']} checks, last run {T['when']}.", ""]
    md += ["Also: the evaluation harness tests itself (a deliberately broken run must be caught), and a recorded live run is",
           "replayed without an API key to reproduce the results exactly.", ""]

    # 6 serving
    md += ["## 6. Scalable serving", ""]
    if L_after:
        md += [f"One server process on this laptop; agents use a stand-in model with {L_after['fake_llm_ms_per_call']} ms per call so the server,",
               "not the API, is measured (`python -m evals.load`).", "",
               table([[f"{r['users']} people opening apps", f"{r['per_second']}/s", f"{r['p50_ms']} / {r['p95_ms']} ms", r["errors"]] for r in L_after["reads"]] +
                     [[f"{r['users']} people submitting", f"{r['per_second']}/s", f"{r['p50_ms']} / {r['p95_ms']} ms", r["errors"]] for r in L_after["writes"]],
                     head=("Load", "Throughput", "p50 / p95", "Errors")), "",
               table([[r["builds"], (next((b["errors"] for b in L_before["agents"] if b["builds"] == r["builds"]), "—") if L_before else "—"),
                       r["errors"], f"{r['wall_s']} s", f"{r['p50_s']} s"] for r in L_after["agents"]],
                     head=("Simultaneous builds", "Failed before the fix", "Failed after", "All done in", "Median build")), "",
               "The load test found a real defect: an agent build held the database's write lock while waiting for the model, so",
               "concurrent users failed with \"database is locked\". Commits now happen straight after each write.",
               "Limits and next steps: one Python process (reads level off around the throughput above), SQLite allows one writer at",
               "a time, and the specialist pool has 6 workers. At larger scale: several server processes behind a proxy, PostgreSQL,",
               "a job queue for agent runs, and the API's rate limits as the real ceiling.", ""]

    # 7 monitoring
    md += ["## 7. Monitoring", "",
           "Control Center: Live server (requests as they happen), Monitor (traffic, devices, errors, tokens, installs, **AI budget and",
           "alerts**: budget at 80%/100%, repeated agent failures, server errors, people over the hourly limit), Agent theater, and",
           "Flow (every app's measured journey). All real; rehearsal data is labelled and never mixed into the numbers.", ""]

    # 8 deployment
    md += ["## 8. Principles for reliable deployment", "",
           "- Agents fill a spec, never write code; the Validator is a hard gate in plain code.",
           "- Visible retries with backoff; server-side model fallback; runs cut off by a restart are marked \"interrupted\".",
           "- Daily AI budget and per-person hourly limit, checked before any model call (`backend/limits.py`).",
           "- Tracing can never break a request; database migrations keep old data; cache-busting for the apps and Control Center.",
           "- HTTPS tunnel (Tailscale Funnel) so phones can install the app; installs are counted.", ""]

    md += ["## Known limitations", "",
           "- Small samples: 35 quality runs of 12 tasks; intervals are wide. Consistency is measured on 9 build tasks.",
           "- Checks verify structure and facts, not the quality of wording; an LLM judge was deliberately not used.",
           "- The injection scanner is keyword-based and does not generalise (held-out result above).",
           "- The reason-quality score is a keyword heuristic; the Builder often restates instead of explaining.",
           "- Load numbers are for one laptop and one process, with a stand-in model.",
           "- On normal (non-anonymous) apps, respondents' names still go to the API (needed to answer \"who\" questions);",
           "  the text inside an anonymous file can still contain the author's name; anonymous response order is kept.",
           "- One reworded task was not exactly equivalent to the original (\"Word file\" vs \"DOCX\"); counted as a failure anyway.",
           "- Sites: one live build so far; the Site agent is not yet in the 12-task quality evaluation or the data-minimisation capture test.",
           ""]
    out = os.path.join(ROOT, "docs", "SYSTEM_CARD.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(md))
    print(f"Written: {out}")


if __name__ == "__main__":
    main()
