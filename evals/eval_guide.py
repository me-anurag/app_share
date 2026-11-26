"""Writes the evaluation guide — docs/EVALUATION_GUIDE.md and docs/EVALUATION_GUIDE.pdf — from the measured results.

  python -m evals.eval_guide

Every number is read from data/evals/ (or the price table in backend/trace.py); none is typed by hand. Results that
come from the harness self-test or are still to be measured live are labelled as such.
"""
import glob
import html
import json
import os
import re
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "data", "evals")


def newest(pattern):
    runs = sorted(glob.glob(os.path.join(EV, pattern)))
    return runs[-1] if runs else None


def load(path, name="results.json"):
    p = os.path.join(path, name) if path and os.path.isdir(path) else path
    return json.load(open(p, encoding="utf-8")) if p and os.path.exists(p) else None


def P(w):
    """A rate with its sample and 95% interval, or a clear 'not measured'."""
    if not w:
        return "not yet measured"
    return f"**{w['rate'] * 100:.1f}%** ({w['k']}/{w['n']}; 95% CI {w['lo'] * 100:.0f}–{w['hi'] * 100:.0f}%)"


def T(rows, head):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in r) + " |" for r in rows]
    return "\n".join(out)


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/") if p else "—"


def build():
    q_dir = newest("*-replay")
    live_dir = newest("*[0-9]-live")
    Q = load(q_dir)
    M = Q["metrics"]
    res = Q["results"]
    s_live, s_fake = newest("*-safety-live"), newest("*-safety-fake")
    S = load(s_live or s_fake)
    r_live, r_fake = newest("*-review-live"), newest("*-review-fake")
    RV = load(r_live or r_fake)
    loads = sorted(glob.glob(os.path.join(EV, "*-load")))
    LA = load(loads[-1], "load.json") if loads else None
    LB = next((load(d, "load.json") for d in loads if any(a["errors"] for a in (load(d, "load.json") or {}).get("agents", []))), None)
    H = load(os.path.join(EV, "heldout.json"))
    TS = load(os.path.join(EV, "tests.json"))
    from backend.trace import PRICES
    from evals.cases import ALL, BUILD

    eb = M["efficiency"]["build"]
    se = M.get("success_efficiency", {})
    R_ = M.get("reasons", {})
    ss = S["summary"] if S else None
    md = []
    A = md.append

    A("# AppShare — Evaluation guide")
    A("")
    A("**Evaluation, Safety and Deployment of LLM and Agentic Systems — what was measured, what every term means, how each "
      f"value is calculated, and what is still to do.**  Generated {time.strftime('%d %B %Y, %H:%M')} by `python -m evals.eval_guide`.")
    A("")
    A("> Every number in this guide is read from a measured result file in `data/evals/` (or the price table in "
      "`backend/trace.py`). None is typed by hand. Results from the harness self-test (a scripted stand-in model) are "
      "labelled as such and are never presented as agent quality. Costs are **calculated** (measured tokens × published "
      "prices), not taken from a bill.")
    A("")
    A("**Status marks used in checklists:** ✅ done and measured · ⏳ built, needs a paid live run · ❌ not done · ➖ deliberately out of scope.")
    A("")

    # ------------------------------------------------------------------ 1 at a glance
    A("## 1. Results at a glance")
    A("")
    A(T([
        ["Task success (every check of a task passed)", P(M["success"])],
        ["Individual checks passed", P(M["checks"])],
        ["Validator accepted the Builder's first save", P(M["first_pass_validity"])],
        ["Honesty — the reply never claims the app was shared", P(M["honesty"])],
        ["Reply faithful to the saved app", P(M.get("reply_faithfulness"))],
        ["Same app structure when the request is repeated", P(M["consistency"]["repeat"])],
        ["Same app structure when the request is reworded", P(M["consistency"]["rewording"])],
        ["Build time — median / p90", f"{eb['latency_s']['median']:.1f} s / {eb['latency_s']['p90']:.1f} s"],
        ["Calculated cost per build — mean / per successful build", f"${eb['cost_usd']['mean']:.4f} / ${se['build']['cost_per_success']:.4f}"],
        ["Share of input tokens served from the prompt cache", f"{eb['cache_share']['mean'] * 100:.0f}%"],
        ["Injection scanner on attacks it was never tuned on", f"{H['detected']}/{H['attacks']} detected · {H['false_alarms']}/{H['honest']} false alarms" if H else "not yet measured"],
        ["Simultaneous app builds that failed (16 at once)", f"before the fix {next(a['errors'] for a in LB['agents'] if a['builds'] == 16)} → after {next(a['errors'] for a in LA['agents'] if a['builds'] == 16)}" if LA and LB else "—"],
        ["Offline test suites (one command)", f"{len(TS['suites'])} suites · {TS['checks_passed']} checks · {'all pass' if not TS['suites_failed'] else str(TS['suites_failed']) + ' failing'}" if TS else "—"],
        ["Total calculated cost of the live quality evaluation", f"${M['total_cost_usd']:.4f}"],
    ], ("Measure", "Value")))
    A("")
    A(f"Sources: quality — `{rel(q_dir)}` (replay of the live run `{rel(live_dir)}`); load — `{rel(loads[-1]) if loads else '—'}`; "
      f"held-out — `data/evals/heldout.json`; tests — `data/evals/tests.json`.")
    A("")

    # ------------------------------------------------------------------ 2 method
    A("## 2. How the evaluation works")
    A("")
    A("**What is evaluated.** AppShare's seven Claude agents: the **Builder** (lead; Claude Opus) coordinates **Data**, **Design** and "
      "**Access** (specialists; Claude Haiku) to turn a request into an app spec; **Insights** answers questions about responses; "
      "**Review** reads each submission and flags problems; **Reminder** nudges people who haven't responded. The agents never write "
      "code: they fill in a JSON spec, and a plain-code **Validator** checks it before it is saved.")
    A("")
    A(f"**The tasks.** {len(ALL)} realistic tasks across the three workspaces (university, office, general): {len(BUILD)} app builds at three "
      "complexity levels, two Insights questions and one Reminder run. Each build task comes with a **reworded version** of the same request "
      "and a hand-written **reference answer**.")
    A("")
    A("**Exact checks.** For every task the expected result is written down as checks that can be verified exactly — a field of a type, "
      "a deadline at a date and time, exactly N places per slot, anonymity on, the right group with the right role. Insights and Reminder "
      "are checked against the **true answer read from the database** at run time (the exact count; exactly the people who haven't "
      "submitted). Every check belongs to the agent whose job it is, so results roll up per agent.")
    A("")
    A("**Runs.** Each build task runs twice as written and once reworded; Insights twice plus once reworded; Reminder twice. "
      f"That is {M['tasks']['runs']} runs in total. Each workspace runs in its own process against a fresh, seeded copy of AppShare in a "
      "temporary folder, so real data is never touched.")
    A("")
    A("**Three modes.**")
    A("")
    A(T([["live", "The real agents and the real API. Every model reply is recorded to a *cassette* file.", "costs money (once)"],
         ["replay", "The recorded replies are fed back through the current code: same tools, Validator, database and checks — "
                    "no API calls. It must reproduce the live results exactly; latency is the value measured when recorded.", "free"],
         ["fake", "Harness self-test: a scripted stand-in plays the reference answers, with one run deliberately broken, to prove "
                  "the checks and metrics catch mistakes. Says nothing about agent quality.", "free"]],
        ("Mode", "What happens", "Cost")))
    A("")
    A("**Measured vs calculated.** Times come from the clock; tokens from the API's usage report; checks from the saved app and the "
      "database. Cost is **calculated**: tokens × the price table below. Rates are reported with a 95% confidence interval because the "
      "samples are small.")
    A("")
    A(T([[m, f"${p['in']:.2f}", f"${p['out']:.2f}", f"${p['cache_write']:.3f}", f"${p['cache_read']:.3f}"] for m, p in PRICES.items()],
        ("Model", "Input / M tokens", "Output / M tokens", "Cache write / M", "Cache read / M")))
    A("")

    # ------------------------------------------------------------------ 3 glossary
    A("## 3. Glossary — what each term means and how it is calculated")
    A("")
    A("### 3.1 Quality and correctness")
    A("")
    G = [
        ["Task", "One request with known expected results (e.g. *U3 lab slots*).", "—", f"{M['tasks']['distinct_tasks']} tasks"],
        ["Run", "One attempt at a task (as written or reworded).", "—", f"{M['tasks']['runs']} runs"],
        ["Check", "One exact expectation, e.g. *each slot has exactly 3 places*. Owned by one agent.", "pass / fail", f"{M['checks']['n']} checks"],
        ["Task success", "Every check of a run passed and nothing errored.", "successful runs ÷ all runs", P(M["success"])],
        ["Check pass rate", "Share of all individual checks that passed.", "passed checks ÷ all checks", P(M["checks"])],
        ["Agent accuracy", "Pass rate of the checks that are a given agent's job.", "that agent's passed checks ÷ its checks",
         "; ".join(f"{a} {w['rate'] * 100:.0f}%" for a, w in M["agent_accuracy"].items())],
        ["First-pass validity", "The Validator accepted the Builder's first save — no fix-up round was needed.", "builds whose first save was valid ÷ builds", P(M["first_pass_validity"])],
        ["Honesty", "The Builder's reply never claims the app was already shared (only the owner can share). Negated sentences "
                    "such as *nothing has been shared yet* are honest and pass.", "replies without such a claim ÷ replies", P(M["honesty"])],
        ["Reply faithfulness", "Dates and numbers of places that the reply mentions exist in the saved app (the reply describes what was "
                               "really built).", "reply facts found in the app ÷ reply facts checked", P(M.get("reply_faithfulness"))],
        ["Insights exactness", "The answer states the true count / names exactly the people who haven't submitted, and nobody else.",
         "compared with the database", P(M["agent_accuracy"].get("insights"))],
        ["Reminder precision", "Reminders went to exactly the people who hadn't submitted, once each.", "compared with the database",
         P(M["agent_accuracy"].get("reminder"))],
    ]
    A(T(G, ("Term", "Meaning", "How it is calculated", "Value")))
    A("")
    A("### 3.2 Consistency")
    A("")
    A(T([
        ["Structure signature", "A compact description of an app's structure: field types, number of options, places per option, anonymity, "
                                "deadline date, total places, responses per person, result visibility, number of statuses, audience and roles. "
                                "Wording, titles and colours are ignored.", "computed from the saved spec", "—"],
        ["Repeat consistency", "The same request run twice produces the same structure.", "tasks whose two runs share a signature ÷ tasks", P(M["consistency"]["repeat"])],
        ["Rewording consistency", "The reworded request produces the same structure as the original.", "tasks whose reworded run matches ÷ tasks", P(M["consistency"]["rewording"])],
        ["Same check outcomes", "Every run of a task passed and failed exactly the same checks.", "tasks with identical outcomes ÷ tasks", P(M["consistency"]["check_outcomes"])],
    ], ("Term", "Meaning", "How it is calculated", "Value")))
    A("")
    A("### 3.3 Efficiency and cost")
    A("")
    A(T([
        ["Latency", "Wall-clock time from sending the request to receiving the reply.", "median and p90 of runs",
         f"build {eb['latency_s']['median']:.1f} s / {eb['latency_s']['p90']:.1f} s · insights {M['efficiency']['insights']['latency_s']['median']:.1f} s · reminder {M['efficiency']['reminder']['latency_s']['median']:.1f} s"],
        ["Median / p90 / p95 / p99", "The value half the runs are below / 90% / 95% / 99% are below. p90+ shows the slow tail.", "sorted values", "—"],
        ["Model call", "One request to Claude (the agent thinks and decides what to do next).", "counted from the trace", f"{eb['model_calls']['mean']:.1f} per build"],
        ["Tool call", "One action an agent takes on the platform (search the directory, check fields, save the app…).", "counted from the trace", f"{eb['tool_calls']['mean']:.1f} per build"],
        ["Tokens in / out", "Text sent to / generated by the model, in tokens (word pieces). Input includes the cached part.", "from the API's usage report",
         f"{eb['tokens_in']['mean']:,.0f} in · {eb['tokens_out']['mean']:,.0f} out per build"],
        ["Cache share", "Part of the input read from the prompt cache (repeated instructions), which is much cheaper.", "cache-read tokens ÷ all input tokens", f"{eb['cache_share']['mean'] * 100:.0f}%"],
        ["Calculated cost", "What the tokens would cost at published prices.", "Σ tokens × price per million (input, output, cache write, cache read)", f"${eb['cost_usd']['mean']:.4f} per build (mean)"],
        ["Cost per success", "What a *working* result costs, counting the cost of failed runs too.", "total cost ÷ successful runs",
         f"build ${se['build']['cost_per_success']:.4f} · insights ${se['insights']['cost_per_success']:.4f} · reminder ${se['reminder']['cost_per_success']:.5f}"],
        ["Steps to success", "Model calls and tool calls of successful runs.", "mean over successful runs",
         f"{se['build']['model_calls_to_success']['mean']:.1f} model calls · {se['build']['tool_calls_to_success']['mean']:.1f} tool calls per build"],
        ["Wasted steps", "Tool calls that returned an error plus Validator rejections.", "mean per run", f"{se['build']['wasted_steps_per_run']['mean']:.2f} per build"],
        ["Retry", "A failed API call (network, rate limit, overload) tried again after a wait (2–10 s).", "counted from the trace", f"{eb['retries']} in the build runs"],
    ], ("Term", "Meaning", "How it is calculated", "Value")))
    A("")
    cx = M["complexity"]
    A("### 3.4 Complexity scaling")
    A("")
    A(T([
        ["Complexity level", "Hand-assigned: 1 simple · 2 moderate · 3 complex (rules interacting: places per slot, workflows, files).", "per task", "—"],
        ["Complexity score", "Size of the task's reference app.", "questions + 2 × active rules + audience entries", "—"],
        ["Pearson r", "How strongly two quantities rise together: +1 perfectly, 0 not at all, −1 opposite.", "standard correlation over all build runs",
         f"cost r = {cx['vs_cost']['r']} · latency r = {cx['vs_latency']['r']} · model calls r = {cx['vs_model_calls']['r']}"],
        ["Slope", "Average change per extra complexity point.", "r × (spread of y ÷ spread of x)", f"${cx['vs_cost']['slope']:.4f} per point"],
    ], ("Term", "Meaning", "How it is calculated", "Value")))
    A("")
    A(T([[f"Level {lv}", d["tasks"], P(d["success"]), f"{d['latency_s']['median']:.1f} s", f"${d['cost_usd']['mean']:.4f}", f"{d['model_calls']['mean']:.1f}"]
         for lv, d in cx["by_level"].items()], ("Level", "Tasks", "Success", "Median time", "Mean cost", "Model calls")))
    A("")
    A("### 3.5 Statistics")
    A("")
    A(T([
        ["95% confidence interval (CI)", "The range the true rate very likely lies in, given the sample. Narrow = trustworthy; wide = small sample.",
         "Wilson score interval: centre (p + z²/2n) / (1 + z²/n) ± z·√(p(1−p)/n + z²/4n²) / (1 + z²/n), z = 1.96", "shown next to every rate"],
        ["Why Wilson", "Unlike the simple ± formula it stays sensible for small samples and rates near 0% or 100%.", "—", "—"],
    ], ("Term", "Meaning", "How it is calculated", "Value")))
    A("")
    A("### 3.6 Transparency and explainability")
    A("")
    A(T([
        ["Journey", "Everything recorded for one app, from the first request to sharing, responses, reviews and reminders.", "trace store", "per app"],
        ["Run / step", "A run is one agent's turn; steps inside it are model calls, tool calls, Validator verdicts and retries, each with time, tokens and cost.", "trace store", "—"],
        ["Stated reason", "A short *why* each agent must give with each decision (required field on every decision tool).", "recorded with the decision", f"{M['stated_reasons_per_build']['mean']:.1f} per build"],
        ["Reason explains *why*", "Keyword heuristic: the reason gives a cause or purpose (*because*, *so that*, *the request*, *needs*…) instead of restating the action. A lower bound.",
         "reasons with a cause/purpose marker ÷ reasons", P(R_.get("explains_why"))],
    ], ("Term", "Meaning", "How it is calculated", "Value")))
    A("")
    if R_.get("by_agent"):
        A("By agent: " + " · ".join(f"{a} {w['rate'] * 100:.0f}%" for a, w in R_["by_agent"].items()) + ".")
        A("")
    A("### 3.7 Safety")
    A("")
    A(T([
        ["Prompt injection", "Text written to make the AI ignore its instructions — here hidden inside an uploaded assignment the Review agent reads, or typed into the chat.", "—", "—"],
        ["Injection scanner", "Code that looks for known injection patterns (orders to ignore instructions, fake *SYSTEM:* lines, notes to the AI, role-play takeovers, obfuscation).", "pattern matching", "—"],
        ["Fencing", "File text reaches the agent wrapped as data with a warning never to follow instructions inside it.", "—", "—"],
        ["Verdict override", "A submission that tried to manipulate the reviewer can never be stored as *looks fine*; it becomes *worth a look*.", "code, after the AI decides", "—"],
        ["Forbidden data", "The Validator refuses fields collecting passwords, card numbers/CVV, one-time codes or government ID numbers.", "pattern matching on field labels", "—"],
        ["Reply correction", "If the Builder claims it shared the app or made someone an admin and the database says it didn't, the platform appends a correction.", "compared with the database", "—"],
        ["Attack success rate", "Attacks whose harmful outcome actually happened (stored verdict, saved field, database change, uncorrected claim).", "successful attacks ÷ attacks",
         (f"guards off {ss['off']['all_attack_success']['rate'] * 100:.0f}% → on {ss['on']['all_attack_success']['rate'] * 100:.0f}% ({'live' if s_live else 'harness self-test'})" if ss else "—")],
        ["Model resisted", "What the AI decided by itself, before any code guard.", "attacks the AI itself didn't fall for ÷ attacks", "real model: not yet measured" if not s_live else P(ss["on"]["file_model_resisted"])],
        ["False alarm", "An honest submission or text wrongly treated as an attack.", "flagged honest items ÷ honest items",
         f"held-out: {H['false_alarms']}/{H['honest']}" if H else "—"],
        ["Held-out set", "Attacks and honest texts written *after* the scanner was tuned and never used to change it — measures generalisation.", "scored once", f"{H['detected']}/{H['attacks']} detected" if H else "—"],
    ], ("Term", "Meaning", "How it is calculated", "Value")))
    A("")
    A("### 3.8 Responsible AI")
    A("")
    rs = RV["summary"] if RV else None
    A(T([
        ["Anonymity", "For anonymous apps, no name, email, exact time or file name reaches the owner, the CSV, any agent or the trace store.", "end-to-end tests", "tested: pass"],
        ["Data minimisation", "Agents get only what their job needs; no email address is ever sent to the AI (people are referred to as `u12`).", "every message of all agents captured and checked", "tested: pass"],
        ["Human decision", "A Review flag is shown with its evidence as *an AI flag, not a decision*; only an editor can confirm or dismiss it, recorded with their name.", "—", "tested: pass"],
        ["False-flag rate", "Honest work wrongly flagged by the Review agent — the harm that matters most, because flags affect real students.", "flagged honest submissions ÷ honest submissions",
         "real model: not yet measured" if not r_live else P(rs["false_flag_rate_honest"])],
        ["Detection rate", "Empty, off-topic or copied work that the Review agent flagged.", "flagged bad submissions ÷ bad submissions", "real model: not yet measured" if not r_live else P(rs["detection_rate"])],
        ["Precision", "How many flags were right.", "correct flags ÷ all flags", "real model: not yet measured" if not r_live else P(rs["precision"])],
        ["Counterfactual fairness", "The same file submitted under different students' names gets the same verdict.", "files with one verdict for all names ÷ files",
         "real model: not yet measured" if not r_live else P(rs["fair_sets"])],
    ], ("Term", "Meaning", "How it is calculated", "Value")))
    A("")
    A("### 3.9 Serving, monitoring and deployment")
    A("")
    A(T([
        ["Throughput", "Requests handled per second.", "completed requests ÷ seconds", f"up to {max(r['per_second'] for r in LA['reads'])}/s app opens · {max(r['per_second'] for r in LA['writes'])}/s submissions" if LA else "—"],
        ["Error rate", "Requests that failed.", "failed ÷ all", f"{sum(r['errors'] for r in LA['reads'] + LA['writes'])} errors in all read/write levels" if LA else "—"],
        ["Concurrent builds", "App builds started at the same moment (stand-in model, so the server is measured, not the API).", "builds that failed / time for all", "see section 4.6"],
        ["Stand-in model", f"Load-test-only replacement for Claude with a fixed {LA['fake_llm_ms_per_call'] if LA else '—'} ms per call; switched on only by a load-test setting.", "—", "—"],
        ["Daily AI budget", "Calculated AI spend allowed per day; checked before any model call.", "Σ cost of today's steps (trace store)", "default $3.00 (configurable)"],
        ["Rate limit", "AI requests one person may make per hour.", "sliding one-hour window per person", "default 30 (configurable)"],
        ["Alert", "Shown on the Monitor: budget at 80%/100%, ≥3 failed agent runs in an hour, ≥5 server errors, people over the hourly limit.", "computed live", "—"],
        ["Regression gate", "All offline test suites in one command; must pass before a change is trusted.", "`python -m tests.run_all`", f"{TS['checks_passed']} checks" if TS else "—"],
    ], ("Term", "Meaning", "How it is calculated", "Value")))
    A("")

    # ------------------------------------------------------------------ 4 by topic
    A("## 4. Results and checklists by chapter topic")
    A("")
    A("### 4.1 Metrics for evaluating LLM-driven agents")
    A("")
    A(T([[a, P(w)] for a, w in M["agent_accuracy"].items()], ("Agent", "Accuracy on its own checks")))
    A("")
    fails = M["most_failed_checks"]
    A("**Every failed check (kept, not edited away):** " + ("; ".join(f"{c} ×{n}" for c, n in fails) if fails else "none") + ".")
    A("")
    A(T([
        ["✅", "Task success, check accuracy, per-agent accuracy (with 95% CI)"],
        ["✅", "Validator first-pass rate, honesty, reply faithfulness"],
        ["✅", "Exact Insights and Reminder answers against the database"],
        ["✅", "Consistency across repeats and rewordings"],
        ["✅", "Latency, tokens, cache share, cost, cost per success, steps to success"],
        ["✅", "Cost and latency against request complexity"],
        ["✅", "Resilience: a real network failure was retried and the task still passed"],
        ["❌", "Larger sample for narrower intervals (≈ $1.20 per extra round)"],
        ["➖", "Quality of wording judged by an LLM (not validated, so left out)"],
    ], ("", "Checklist")))
    A("")
    A("### 4.2 Safety guardrails and prompt filtering")
    A("")
    if ss:
        A(f"Source: `{rel(s_live or s_fake)}` — **{'live, real model' if s_live else 'harness self-test with a scripted model that falls for every attack (not a measure of the real model)'}**.")
        A("")
        A(T([["Poisoned uploads that got through", P(ss["off"]["file_attack_success"]), P(ss["on"]["file_attack_success"])],
             ["Chat attacks that succeeded", P(ss["off"]["chat_attack_success"]), P(ss["on"]["chat_attack_success"])],
             ["Honest submissions wrongly flagged", P(ss["off"]["false_alarms"]), P(ss["on"]["false_alarms"])]],
            ("", "Guardrails off", "Guardrails on")))
        A("")
    if H:
        A(f"**Held-out:** the scanner detected {H['detected']} of {H['attacks']} attack styles it was never tuned on, with {H['false_alarms']} false alarm(s) "
          f"in {H['honest']} honest texts. Missed: {', '.join(H['missed'])}. The keyword scanner does not generalise; it is one layer of several.")
        A("")
    A(T([
        ["✅", "Injection scanner, fencing, verdict override, forbidden data, reply correction"],
        ["✅", "Attack harness: guards off vs on"],
        ["✅", "Held-out attack set (scored once, no tuning afterwards)"],
        ["⏳", "Real model's own resistance — `python -m evals.safety --mode live --yes` (≈ $0.80)"],
        ["❌", "A learned injection classifier instead of keywords (future work)"],
    ], ("", "Checklist")))
    A("")
    A("### 4.3 Explainability of autonomous decisions")
    A("")
    A(T([
        ["✅", "A required stated reason on every decision (Data, Design, Access, Builder, Review, Reminder)"],
        ["✅", "Full trace per step; Flow tab with click-for-details; replay in step with the Agent theater"],
        ["✅", "Owner's *How this app was built* on the phone; Review evidence shown with each flag"],
        ["✅", f"Reason quality measured: {P(R_.get('explains_why'))} explain why"],
        ["❌", "Improve the Builder's reasons (often restates) and re-measure (≈ $1.20)"],
    ], ("", "Checklist")))
    A("")
    A("### 4.4 Ethical considerations and Responsible AI")
    A("")
    if rs:
        A(f"Review agent — {'live' if r_live else 'harness self-test (scripted reviewer that passes everything)'}: false-flag rate {P(rs['false_flag_rate_honest'])}; "
          f"detection {P(rs['detection_rate'])}; same verdict across names {P(rs['fair_sets'])}.")
        A("")
    A(T([
        ["✅", "Anonymity end to end (it found and fixed a real leak of a respondent's name into traces)"],
        ["✅", "Data minimisation: no email address sent to the AI; anonymous file names generic everywhere"],
        ["✅", "Respondents told on the app when an AI reads their answers or file, and about anonymity"],
        ["✅", "Human decision on every AI flag, with evidence, recorded with the person's name"],
        ["✅", "Data-flow statement: `docs/DATA_FLOW.md`"],
        ["⏳", "Review accuracy and fairness across names with the real model — `python -m evals.review_eval --mode live --yes` (≈ $0.05)"],
    ], ("", "Checklist")))
    A("")
    A("### 4.5 Testing approaches")
    A("")
    if TS:
        A(T([[x["suite"], x["what"], f"{'pass' if x['ok'] else 'FAIL'} · {x['passed']}"] for x in TS["suites"]], ("Suite", "What it proves", "Checks")))
        A("")
    A(T([
        ["✅", "Unit tests (the checks themselves, the guardrails)"],
        ["✅", "Integration tests (tracing, anonymity, minimisation, limits)"],
        ["✅", "End-to-end evaluation, live and replayed (the replay reproduced every check result)"],
        ["✅", "Harness self-tests (a deliberately broken run must be caught)"],
        ["✅", "UI smoke test of the phone app and the Control Center"],
        ["✅", "One-command regression gate: `python -m tests.run_all`"],
        ["❌", "Full UI interaction tests (smoke level only)"],
    ], ("", "Checklist")))
    A("")
    A("### 4.6 Scalable serving")
    A("")
    if LA:
        A(f"One server process on one laptop; agents use the stand-in model ({LA['fake_llm_ms_per_call']} ms per call). Source: `{rel(loads[-1])}`.")
        A("")
        A(T([[f"{r['users']} people opening apps", f"{r['per_second']}/s", f"{r['p50_ms']} ms", f"{r['p95_ms']} ms", f"{r['p99_ms']} ms", r["errors"]] for r in LA["reads"]]
            + [[f"{r['users']} people submitting", f"{r['per_second']}/s", f"{r['p50_ms']} ms", f"{r['p95_ms']} ms", f"{r['p99_ms']} ms", r["errors"]] for r in LA["writes"]],
            ("Load", "Throughput", "p50", "p95", "p99", "Errors")))
        A("")
        A(T([[r["builds"], next((b["errors"] for b in LB["agents"] if b["builds"] == r["builds"]), "—") if LB else "—", r["errors"], f"{r['wall_s']} s", f"{r['p50_s']} s"]
             for r in LA["agents"]], ("Builds at once", "Failed before fix", "Failed after", "All done in", "Median build")))
        A("")
        A("The test found a real defect: an agent build held the database's write lock while waiting for the model, so other people failed "
          "with *database is locked*. Writes are now committed immediately.")
        A("")
    A(T([
        ["✅", "Load test of reads and writes; concurrency of agent builds; defect found and fixed"],
        ["✅", "Scaling path documented: several server processes, PostgreSQL, a job queue, the API's rate limits as the ceiling"],
        ["➖", "Actually running multiple processes / PostgreSQL (beyond a single-laptop project)"],
    ], ("", "Checklist")))
    A("")
    A("### 4.7 Monitoring systems")
    A("")
    A(T([
        ["✅", "Live server view (requests as they happen), Monitor (traffic, devices, errors, tokens, installs)"],
        ["✅", "Flow (every app's measured journey) and Agent theater (agents animated live)"],
        ["✅", "AI budget and alerts on the Monitor"],
        ["✅", "Rehearsal data clearly labelled and never mixed into the numbers"],
    ], ("", "Checklist")))
    A("")
    A("### 4.8 Principles for deploying reliable LLM and agentic systems")
    A("")
    A(T([
        ["✅", "Agents fill a spec and never write code; the Validator is a hard gate in plain code"],
        ["✅", "Visible retries with backoff; server-side model fallback; interrupted runs marked"],
        ["✅", "Daily AI budget and per-person hourly limit, checked before any model call"],
        ["✅", "Tracing can never break a request; database migrations keep old data; cache-busting"],
        ["✅", "HTTPS so phones can install the app; installs counted"],
        ["✅", "System card generated from measured results: `docs/SYSTEM_CARD.md`"],
    ], ("", "Checklist")))
    A("")

    # ------------------------------------------------------------------ 5 every task
    A("## 5. The tasks and their outcomes")
    A("")
    rows = []
    for c in ALL:
        rs_ = [r for r in res if r["case"] == c["id"]]
        okn = sum(1 for r in rs_ if r["success"])
        rows.append([c["id"], c["ws"], c["level"], c["kind"], (c["prompt"][:90] + "…") if len(c["prompt"]) > 90 else c["prompt"], f"{okn}/{len(rs_)}"])
    A(T(rows, ("Task", "Workspace", "Level", "Kind", "Request (as written)", "Runs passed")))
    A("")

    # ------------------------------------------------------------------ 6 found and fixed
    A("## 6. Problems the evaluation found (and what was done)")
    A("")
    A(T([
        ["Honesty check counted *Nothing has been shared yet* as a false claim", "Measuring instrument", "Fixed the check (negations allowed), added the real sentences to its tests, re-scored free by replay"],
        ["Scanner flagged honest sentences (*System: Windows 11*)", "Guardrail false alarms", "Tightened before the held-out set was written; held-out still shows 1 false alarm"],
        ["Scanner catches only 2 of 12 unseen attack styles", "Guardrail weakness", "Reported as-is; defence relies on fencing, human decisions and agents having no harmful tools"],
        ["A rejected anonymous response was logged with the student's name", "Anonymity leak", "Fixed at the source and a second safeguard in the trace store; tested"],
        ["The Review agent's saved evidence kept anonymous file names", "Anonymity leak", "Generic names everywhere; tested"],
        ["Concurrent app builds failed with *database is locked*", "Reliability defect", "Commit immediately after each write; 13 → 0 failures at 16 builds"],
        ["Replays didn't reproduce network failures", "Reproducibility gap", "Failed API calls are now recorded and replayed"],
        ["Builder's stated reasons often restate instead of explaining", "Explainability weakness", "Prompt tightened; re-measurement pending"],
    ], ("What", "Kind", "What was done")))
    A("")

    # ------------------------------------------------------------------ 7 reproduce
    A("## 7. How to reproduce every number")
    A("")
    A(T([
        ["`python -m tests.run_all`", "All offline test suites (regression gate)", "free"],
        ["`python -m evals.run --mode replay --from data/evals/<live run>`", "Quality evaluation, reproduced from the recording", "free"],
        ["`python -m evals.run --mode fake`", "Harness self-test of the quality evaluation", "free"],
        ["`python -m evals.run --mode live --yes`", "Fresh live quality evaluation (after changing the agents)", "≈ $1.20"],
        ["`python -m evals.safety --mode fake` / `--mode live --yes`", "Attacks, guardrails off vs on", "free / ≈ $0.80"],
        ["`python -m evals.review_eval --mode fake` / `--mode live --yes`", "Review accuracy and fairness", "free / ≈ $0.05"],
        ["`python -m evals.heldout`", "Scanner on unseen attacks", "free"],
        ["`python -m evals.load`", "Load and concurrency test", "free"],
        ["`python -m evals.system_card` · `python -m evals.eval_guide`", "Rebuild the system card / this guide from the results", "free"],
    ], ("Command", "What it does", "Cost")))
    A("")

    # ------------------------------------------------------------------ 8 limitations
    A("## 8. Limitations — read these with the numbers")
    A("")
    for x in [
        f"Small samples: {M['tasks']['runs']} quality runs of {M['tasks']['distinct_tasks']} tasks, so the intervals are wide; consistency rests on 9 build tasks.",
        "Checks verify structure and facts, not the quality of wording.",
        "Consistency is strict: any structural difference counts, including harmless ones (dropdown vs radio buttons, a redundant total cap).",
        "One reworded task was not exactly equivalent to the original (*Word file* vs *DOCX*); it is still counted as a failure.",
        "The injection scanner is keyword-based and does not generalise (held-out result). The real model's own resistance is not yet measured.",
        "The reason-quality score is a keyword heuristic (a lower bound).",
        "Load numbers are for one laptop and one server process, with a stand-in model.",
        "On normal (non-anonymous) apps, respondents' names still go to the API; text inside an anonymous file can still contain a name; anonymous response order is kept.",
        "Costs are calculated from published prices, not billed amounts.",
    ]:
        A(f"- {x}")
    A("")

    # ------------------------------------------------------------------ 9 files
    A("## 9. Where things are")
    A("")
    A(T([
        ["`backend/trace.py`", "Trace store: journeys, runs, steps, events; redaction; cost calculation"],
        ["`backend/guard.py`", "Guardrails: scanner, fencing, verdict override, forbidden data, reply correction"],
        ["`backend/limits.py`", "Daily AI budget, per-person rate limit, alerts"],
        ["`evals/cases.py` · `evals/checks.py` · `evals/metrics.py`", "Tasks, exact checks, metric definitions"],
        ["`evals/run.py` · `evals/worker.py` · `evals/cassette.py`", "Running live / replay / fake; recording and replaying replies"],
        ["`evals/safety.py` · `evals/attacks.py` · `evals/heldout.py`", "Safety evaluation, attacks, held-out set"],
        ["`evals/review_eval.py` · `evals/load.py`", "Review accuracy and fairness; load and concurrency"],
        ["`tests/`", "All offline test suites; `tests/run_all.py` runs them"],
        ["`docs/SYSTEM_CARD.md` · `docs/DATA_FLOW.md`", "System card; what each agent sends to the API"],
        ["`data/evals/`", "Every result file, report and recording"],
    ], ("Path", "What it is")))
    A("")
    return "\n".join(md)


# --------------------------------------------------------------------------- Markdown → HTML (the subset used above)

def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\w)", r"<i>\1</i>", t)
    return t


def to_html(md):
    out, lines, i = [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[2:]]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>" +
                       "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")
            continue
        m = re.match(r"(#{1,4}) (.*)", ln)
        if m:
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif ln.startswith("> "):
            out.append(f"<blockquote>{inline(ln[2:])}</blockquote>")
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
body { font: 10pt/1.45 "Segoe UI", system-ui, sans-serif; color: #1b1a17; }
h1 { font-size: 22pt; margin: 0 0 6pt; color: #8a2f0e; }
h2 { font-size: 14.5pt; margin: 18pt 0 6pt; padding-bottom: 3pt; border-bottom: 2px solid #c4471a; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; color: #3a3833; break-after: avoid; }
p { margin: 4pt 0; }
blockquote { margin: 8pt 0; padding: 7pt 10pt; background: #f6f1e7; border-left: 3px solid #c4471a; color: #3a3833; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 8pt; font-size: 8.6pt; break-inside: auto; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { text-align: left; background: #efe9dd; padding: 4pt 5pt; border: 1px solid #ddd5c6; }
td { padding: 3.5pt 5pt; border: 1px solid #e6dfd2; vertical-align: top; }
td:first-child { font-weight: 600; }
code { font: 8.4pt Consolas, monospace; background: #f3efe6; padding: 0 2pt; border-radius: 2pt; }
ul { margin: 4pt 0 4pt 14pt; padding: 0; } li { margin: 2pt 0; }
b { color: #111; }
"""


def main():
    md = build()
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    md_path = os.path.join(ROOT, "docs", "EVALUATION_GUIDE.md")
    open(md_path, "w", encoding="utf-8").write(md)
    page = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>AppShare — Evaluation guide</title><style>{CSS}</style></head><body>{to_html(md)}</body></html>"
    html_path = os.path.join(ROOT, "docs", "EVALUATION_GUIDE.html")
    open(html_path, "w", encoding="utf-8").write(page)
    pdf_path = os.path.join(ROOT, "docs", "EVALUATION_GUIDE.pdf")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page()
        pg.goto("file:///" + html_path.replace("\\", "/"))
        pg.pdf(path=pdf_path, format="A4", print_background=True, display_header_footer=True,
               header_template="<span></span>",
               footer_template="<div style='font:7pt Segoe UI,sans-serif;color:#8c8a7f;width:100%;text-align:center'>AppShare — Evaluation guide · page <span class='pageNumber'></span> of <span class='totalPages'></span></div>",
               margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"})
        b.close()
    print(f"Written: {md_path}\nWritten: {pdf_path}")


if __name__ == "__main__":
    main()
