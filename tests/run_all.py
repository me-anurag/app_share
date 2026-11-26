"""Run every offline test suite with one command (no API key, no cost) — the regression gate.

  python -m tests.run_all

Each suite runs in its own process with its own throwaway data folder. Writes data/evals/tests.json.
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITES = [
    ("test_eval_checks", "The evaluation's checks are themselves correct"),
    ("test_guard", "Guardrails: injection scanner, forbidden data, review override"),
    ("test_trace_flow", "Tracing, redaction, retries, Validator, owner's view"),
    ("test_responsible", "Anonymity end to end, human decision on AI flags"),
    ("test_minimisation", "No emails or anonymous file names sent to the AI; respondents told about AI review"),
    ("test_providers", "AI provider switch: Claude / Groq / mixed; translation, errors, a full build on simulated Groq"),
    ("test_limits", "Cost budget, rate limits, alerts"),
    ("test_ui_smoke", "Phone app and Control Center pages load without script errors"),
    ("test_live", "Open screens update by themselves within 2 s; files compressed and cached"),
]


def main():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out, failed = [], 0
    for mod, what in SUITES:
        if not os.path.exists(os.path.join(ROOT, "tests", mod + ".py")):
            continue
        t0 = time.time()
        p = subprocess.run([sys.executable, "-m", f"tests.{mod}"], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        text = p.stdout + p.stderr
        passed, fails = len(re.findall(r"^\s*PASS\b", text, re.M)), len(re.findall(r"^\s*FAIL\b", text, re.M))
        skipped = "SKIPPED" in text
        ok = p.returncode == 0
        failed += 0 if ok else 1
        out.append({"suite": mod, "what": what, "ok": ok, "passed": passed, "failed": fails, "skipped": skipped, "seconds": round(time.time() - t0, 1)})
        print(f"{'PASS' if ok else 'FAIL'}  {mod:<18} {passed:>3} checks passed{f', {fails} failed' if fails else ''}{' (skipped)' if skipped else ''}  "
              f"{time.time() - t0:5.1f}s  {what}")
        if not ok:
            print("\n".join("      " + line for line in text.strip().splitlines()[-15:]))
    total = sum(x["passed"] for x in out)
    print(f"\n{'ALL SUITES PASSED' if not failed else f'{failed} SUITE(S) FAILED'} · {total} checks")
    os.makedirs(os.path.join(ROOT, "data", "evals"), exist_ok=True)
    json.dump({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "suites": out, "checks_passed": total, "suites_failed": failed},
              open(os.path.join(ROOT, "data", "evals", "tests.json"), "w", encoding="utf-8"), indent=1)
    return failed


if __name__ == "__main__":
    sys.exit(main())
