"""Idea validation: reads the survey's answers and checks them against success thresholds fixed in advance.

  python -m evals.validation          (free; run any time — it works with however many answers there are)

The thresholds below were written on 2026-11-25, BEFORE any answer arrived, so the result can't be bent afterwards.
Writes data/evals/validation.json and data/evals/requests.csv (the "describe an app" answers, for part B: running
real requests through the agents to measure what share the engine can build).
"""
import csv
import json
import os
import sqlite3
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from evals.metrics import wilson  # noqa: E402

SURVEY_TITLE = "Quick apps for groups — 2-minute survey"
FIXED_ON = "2026-11-25"
THRESHOLDS = {                                  # the vision is validated if every one is met
    "need": 0.60,        # needed a quick group app in the last month
    "would_use": 0.40,   # answered "Yes" (not "Maybe") to using AppShare instead
    "games": 0.25,       # want quizzes or games with scores/rankings (justifies building game blocks)
}
FIT_THRESHOLD = 0.50     # part B: share of real requests buildable today or with one planned block
MIN_ANSWERS = 25


def main():
    db = sqlite3.connect(os.path.join(ROOT, "data", "university", "appshare.db"))
    db.row_factory = sqlite3.Row
    app = db.execute("SELECT id FROM apps WHERE title = ?", (SURVEY_TITLE,)).fetchone()
    if not app:
        sys.exit("The survey app isn't in the university workspace.")
    rows = [json.loads(r["data"]) for r in db.execute("SELECT data FROM submissions WHERE app_id = ?", (app["id"],))]
    n = len(rows)
    pick = lambda k: [r.get(k) for r in rows if r.get(k)]
    many = lambda k: Counter(x for r in rows for x in (r.get(k) or []))
    need = wilson(sum(1 for r in rows if (r.get("needed") or "").startswith("Yes")), n)
    use = wilson(sum(1 for r in rows if r.get("would_use") == "Yes"), n)
    games = wilson(sum(1 for r in rows if {"Quiz or test", "Game with scores or rankings"} & set(r.get("kinds") or [])), n)
    met = {k: (w is not None and w["rate"] >= THRESHOLDS[k]) for k, w in (("need", need), ("would_use", use), ("games", games))}
    out = {"answers": n, "enough_answers": n >= MIN_ANSWERS, "thresholds_fixed_on": FIXED_ON, "thresholds": THRESHOLDS,
           "need": need, "would_use": use, "would_use_breakdown": Counter(pick("would_use")), "games": games, "met": met,
           "validated": n >= MIN_ANSWERS and all(met.values()),
           "roles": Counter(pick("role")), "kinds": many("kinds"), "tools": many("tools"), "how": Counter(pick("how")),
           "size": Counter(pick("size")), "annoyed": pick("annoyed"), "must": pick("must"), "why": pick("why")}
    os.makedirs(os.path.join(ROOT, "data", "evals"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "evals", "validation.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(ROOT, "data", "evals", "requests.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["#", "role", "request", "buildable_today", "buildable_with_block", "which_block", "notes"])
        for i, r in enumerate(rows, 1):
            if r.get("dream_app"):
                w.writerow([i, r.get("role"), r["dream_app"], "", "", "", ""])

    pct = lambda w: "—" if not w else f"{w['rate'] * 100:.0f}% ({w['k']}/{w['n']}, 95% CI {w['lo'] * 100:.0f}–{w['hi'] * 100:.0f}%)"
    print(f"Answers: {n}{'' if n >= MIN_ANSWERS else f'  (fewer than {MIN_ANSWERS}: too early to decide)'}")
    print(f"Need a quick group app:   {pct(need):<34} target ≥ {THRESHOLDS['need']:.0%}  {'MET' if met['need'] else 'not met'}")
    print(f"Would use it ('Yes'):     {pct(use):<34} target ≥ {THRESHOLDS['would_use']:.0%}  {'MET' if met['would_use'] else 'not met'}")
    print(f"Want quizzes / games:     {pct(games):<34} target ≥ {THRESHOLDS['games']:.0%}  {'MET' if met['games'] else 'not met'}")
    print(f"Most wanted: {', '.join(f'{k} ({v})' for k, v in out['kinds'].most_common(5)) or '—'}")
    print(f"Used today:  {', '.join(f'{k} ({v})' for k, v in out['tools'].most_common(5)) or '—'}")
    print(f"\nVerdict: {'VALIDATED' if out['validated'] else 'NOT YET' if n < MIN_ANSWERS else 'NOT VALIDATED — see which target was missed'}")
    print(f"Requests for part B: data/evals/requests.csv ({sum(1 for r in rows if r.get('dream_app'))} rows)")


if __name__ == "__main__":
    main()
