"""The tools that prove the numbers are themselves tested.   python -m tests.test_proof

Offline, in a temporary folder (the real data/evals is never touched): fingerprints catch a hand-edited file, the
reproduce comparison catches a changed result, examiner expectations become the right checks, and an examiner task
passes when the app matches and FAILS when it doesn't.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from evals import proof  # noqa: E402
from evals.examiner import to_checks  # noqa: E402

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


tmp = tempfile.mkdtemp(prefix="appshare-proof-")

print("== Fingerprints ==")
f1, f2 = os.path.join(tmp, "results.json"), os.path.join(tmp, "cassette.json")
json.dump({"metrics": {"success": 0.857}}, open(f1, "w"))
json.dump({"calls": [1, 2]}, open(f2, "w"))
seals = os.path.join(tmp, "SEALS.json")
r = proof.seal(seals, [f1, f2])
expect(r["sealed_now"] == 2, "new files are sealed")
c = proof.check_seals(seals, [f1, f2])
expect(c["match"] == 2 and not c["modified"], "untouched files match their fingerprints")
json.dump({"metrics": {"success": 0.95}}, open(f1, "w"))          # someone "improves" a number by hand
c = proof.check_seals(seals, [f1, f2])
expect(c["modified"] == [proof.rel(f1)], "a hand-edited result file shows as modified")
proof.seal(seals, [f1, f2])
expect(proof.check_seals(seals, [f1, f2])["modified"] == [proof.rel(f1)], "sealing again does NOT hide the edit (no re-sealing)")

print("\n== Reproduce comparison ==")
run = lambda ok, ok2=True: {"case": "T1", "variant": "original", "idx": 0, "success": ok and ok2,
                            "checks": [{"agent": "data", "check": "deadline", "passed": ok}, {"agent": "builder", "check": "saved", "passed": ok2}]}
same = proof.compare([run(True)], [run(True)])
expect(same["identical_runs"] == 1 and same["identical_checks"] == 2 and not same["differences"], "identical scorings are reported identical")
diff = proof.compare([run(True)], [run(False)])
expect(diff["identical_runs"] == 0 and diff["identical_checks"] == 1 and "deadline" in diff["differences"][0][2], "one changed check is caught and named")
gone = proof.compare([run(True)], [])
expect(gone["differences"] and "missing" in gone["differences"][0][2], "a run missing from the new scoring is caught")

print("\n== Examiner expectations → checks ==")
ch = to_checks({"fields": ["file", "rating", "rating"], "file_accept": [".pdf"], "file_max_mb": 10, "choice": ["Mon", "Tue"], "places_each": 3,
                "deadline": "2026-12-12T17:00", "anonymous": True, "per_person": "one", "total_places": 60, "statuses": ["Pending", "Approved"],
                "audience": {"type": "group", "name": "34ML", "role": "submitter"}, "no_identity": True, "max_questions": 4, "title_has": "Lab"})
kinds = [c[1] for c in ch]
expect(("data", "field", {"type": "file", "accept": [".pdf"], "max_mb": 10}) in ch, "file type and size go into the file check")
expect(("data", "field", {"type": "rating", "count": 2}) in ch, "asking for two ratings needs two")
expect(("data", "choice", {"options": ["mon", "tue"], "limits": 3}) in ch, "choice options with places each")
expect(("data", "rule", "max_responses", 60) in ch and ("data", "rule", "anonymous", True) in ch, "rules become exact rule checks")
expect(("access", "share", {"type": "group", "name": "34ML", "role": "submitter"}) in ch, "the audience becomes a share check")
expect(kinds.count("closes") == 1 and "statuses" in kinds and "no_identity" in kinds and "title_has" in kinds, "deadline, statuses, identity, title")
expect(to_checks({}) == [], "no expectations → no examiner checks (only the automatic ones)")

print("\n== An examiner task, offline (scripted model) ==")
job = {"request": "A sign-up for the robotics workshop for section 34ML, 20 places, closes 12 December 2026, morning or afternoon session.",
       "workspace": "university",
       "expect": {"choice": ["morning", "afternoon"], "total_places": 20, "deadline": "2026-12-12",
                  "audience": {"type": "group", "name": "34ML", "role": "submitter"}, "no_identity": True}}
good = {"spec": {"title": "Robotics workshop sign-up", "description": "Pick a session.", "kind": "registration", "theme_color": "#1f5f7a",
                 "max_responses": 20, "closes_at": "2026-12-12T23:59",
                 "fields": [{"id": "session", "type": "radio", "label": "Which session?", "options": ["Morning", "Afternoon"], "required": True}]},
        "shares": [{"type": "group", "name": "34ML", "role": "submitter"}]}
bad = json.loads(json.dumps(good))
bad["spec"]["max_responses"] = 30                                   # the agents got the number of places wrong
bad["shares"] = [{"type": "public", "role": "submitter"}]           # and shared it with the wrong people


def examine(spec, name):
    jp, sp, out = os.path.join(tmp, f"job-{name}.json"), os.path.join(tmp, f"spec-{name}.json"), os.path.join(tmp, f"out-{name}")
    json.dump(job, open(jp, "w")), json.dump(spec, open(sp, "w"))
    p = subprocess.run([sys.executable, "-m", "evals.examiner", "--job", jp, "--fake-spec", sp, "--out", out], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=240)
    return json.load(open(os.path.join(out, "results.json"), encoding="utf-8"))["result"] if p.returncode == 0 else {"error": p.stdout[-500:] + p.stderr[-500:]}


R = examine(good, "good")
expect(R.get("success") is True and R["examiner_checks"] == 5, f"a correct app passes all checks ({R.get('error') or str(sum(c['passed'] for c in R['checks'])) + '/' + str(len(R['checks']))})")
R = examine(bad, "bad")
failed_names = [c["check"] for c in R.get("checks", []) if not c["passed"]]
expect(R.get("success") is False and any("max_responses" in n for n in failed_names) and any("share" in n for n in failed_names),
       f"a wrong app FAILS, naming exactly what is wrong ({failed_names})")
expect(not os.listdir(os.path.join(ROOT, "data", "evals")) or not any(n.endswith("-examiner-fake") for n in os.listdir(os.path.join(ROOT, "data", "evals"))),
       "tests leave nothing in the real data/evals")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
