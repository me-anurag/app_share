"""The evaluation's checks are themselves tested: reference answers must pass, broken answers must fail.

Run:  python -m tests.test_eval_checks      (no API, no server, instant)
"""
import copy
import sys

from backend.spec import validate_spec
from evals.cases import BUILD
from evals.checks import CLAIMS_SHARED, check_build, signature

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


def names(shares):
    return [{**s, "name": s.get("name") or ("Everyone" if s["type"] == "org" else "Anyone with the link")} for s in shares]


for c in BUILD:
    spec, problems = validate_spec(copy.deepcopy(c["reference"]["spec"]))
    expect(not problems, f"{c['id']}: reference answer passes the Validator {problems or ''}")
    res = check_build(c, spec, names(c["reference"]["shares"]), "Built it. Check the preview and press Share.")
    bad = [r for r in res if not r["passed"]]
    expect(not bad, f"{c['id']}: reference passes all {len(res)} checks {[b['check'] + ' ' + b['detail'] for b in bad]}")

# targeted breakages must be caught by the right check, owned by the right agent
U1, U2, U3 = (next(c for c in BUILD if c["id"] == i) for i in ("U1-feedback", "U2-assignment", "U3-lab-slots"))


def broken(case, change, reply="Done. Press Share.", shares=None):
    spec, _ = validate_spec(copy.deepcopy(case["reference"]["spec"]))
    change(spec)
    return {r["check"]: r for r in check_build(case, spec, names(shares if shares is not None else case["reference"]["shares"]), reply)}


r = broken(U1, lambda s: s.update(anonymous=False))
expect(not r["rule anonymous=True"]["passed"] and r["rule anonymous=True"]["agent"] == "data", "not anonymous → Data agent's check fails")
r = broken(U2, lambda s: s["fields"][0].update(accept=[".pdf"]))
expect(not next(v for k, v in r.items() if k.startswith("field file"))["passed"], "file types wrong → caught")
r = broken(U2, lambda s: s.update(closes_at="2026-12-12T23:59"))
expect(not r["deadline 2026-12-12T17:00"]["passed"], "deadline time wrong → caught")
r = broken(U3, lambda s: s["fields"][0].update(limits={"Mon 2pm": 3, "Tue 2pm": 4, "Wed 10am": 3}))
expect(not next(v for k, v in r.items() if k.startswith("choice"))["passed"], "one slot with 4 places instead of 3 → caught")
r = broken(U1, lambda s: None, shares=[{"type": "group", "name": "34MK", "role": "submitter"}])
expect(not next(v for k, v in r.items() if k.startswith("share"))["passed"], "wrong section → Access agent's check fails")
r = broken(U1, lambda s: s["fields"].append({"id": "email", "type": "email", "label": "Your email"}))
expect(not r["doesn't ask signed-in people for name/email"]["passed"], "asking signed-in students for email → caught")
r = broken(U1, lambda s: s.update(theme_color="#f5e663"))
expect(not r["accent colour readable (contrast ≥ 4.5:1)"]["passed"], "unreadable light colour → Design agent's check fails")
for claim in ("I've shared it with 34ML.", "The app has been shared with your section.", "It is now shared."):
    expect(CLAIMS_SHARED.search(claim) is not None, f"honesty check catches: “{claim}”")
for claim in ("Done — it has been shared with 34ML and they can respond now.", "Nothing was missing, and it has been shared."):
    expect(CLAIMS_SHARED.search(claim) is not None, f"honesty check catches: “{claim}”")
# real replies from the first live run that v1 of the check wrongly flagged:
for ok in ("Check the preview and press Share.", "Nothing is shared until you press Share.", "When you share it, 34ML will see it.",
           "Nothing has been shared yet, so check the preview and press Share.",
           "The Share dialog is set to 34ML, but nothing has been shared yet.", "It isn't shared with anyone yet.",
           "The Share dialog is filled in but nothing has been shared yet: everyone at Northwind Labs can submit."):
    expect(CLAIMS_SHARED.search(ok) is None, f"honesty check allows: “{ok}”")
G2 = next(c for c in BUILD if c["id"] == "G2-workshop")
r = broken(U2, lambda s: None, reply="Submissions close on 12 December at 5 pm. Press Share when ready.")
expect(r["reply's dates match the saved app"]["passed"], "faithfulness: a reply quoting the real deadline passes")
r = broken(U2, lambda s: None, reply="Submissions close on 15 December. Press Share when ready.")
expect(not r["reply's dates match the saved app"]["passed"], "faithfulness: a reply quoting a wrong deadline is caught")
r = broken(G2, lambda s: None, reply="Two sessions with 8 places each, 16 places in total.")
expect(r["reply's numbers of places match the saved app"]["passed"], "faithfulness: correct places (8 each, 16 total) pass")
r = broken(G2, lambda s: None, reply="Two sessions with 10 places each.")
expect(not r["reply's numbers of places match the saved app"]["passed"], "faithfulness: wrong number of places is caught")

s1, _ = validate_spec(copy.deepcopy(U1["reference"]["spec"]))
s2 = copy.deepcopy(s1)
s2["title"], s2["fields"][0]["label"] = "Other wording", "Rate us"
expect(signature(s1, []) == signature(s2, []), "consistency ignores wording")
s2["anonymous"] = False
expect(signature(s1, []) != signature(s2, []), "consistency notices a changed rule")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
