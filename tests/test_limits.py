"""Cost budget, per-person rate limit and alerts (offline: scripted stand-in model).   python -m tests.test_limits"""
import os
import sys
import tempfile

os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-limits-"), APPSHARE_MODE="university",
                  ANTHROPIC_API_KEY="offline-test-not-a-key", APPSHARE_MODEL="claude-opus-5-5")
from fastapi.testclient import TestClient  # noqa: E402

from backend import agents, limits, main  # noqa: E402
from tests.fake_claude import FakeClaude, text, tool  # noqa: E402

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


SPEC = {"title": "Quick poll", "description": "Pick one.", "fields": [{"id": "q", "type": "radio", "label": "Pick", "options": ["A", "B"]}]}
agents._call_model = FakeClaude(agents, {"builder": [[tool("save_app", spec=SPEC, reason="test")], text("Built. Press Share.")]},
                                usage=(2000, 300, 0, 0))
c = TestClient(main.app)
c.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
build = lambda: c.post("/api/agent/build", json={"message": "a quick poll"}).json()

print("Daily budget:")
limits.BUDGET, limits.PER_HOUR = 0.05, 100   # one scripted build costs $0.028: two fit, the third must not
r1 = build()
spent = limits.spent_today()
expect(r1["error"] is None and spent > 0, f"a build under budget works and its cost is counted (${spent:.4f})")
r2 = build()
expect(r2["error"] is None, "a second build still fits")
r3 = build()
expect(r3["error"] and "budget" in r3["error"].lower(), f"over budget, the next request is refused: “{(r3['error'] or '')[:70]}…”")
expect(agents._call_model.calls.count("builder") == 4, "…and no model call was made for it")
a = limits.alerts()
expect(any(x["level"] == "critical" and "budget" in x["text"] for x in a), "the Monitor gets a critical budget alert")
expect(agents.run_review(1) is None, "background reviews pause too (they can be re-run later)")

print("\nPer-person hourly limit:")
limits.BUDGET, limits.PER_HOUR = 100.0, 2
limits._recent.clear()
d = TestClient(main.app)
d.post("/api/login", json={"email": "prof.sharma@riverside.edu"}).raise_for_status()
rs = [d.post("/api/agent/build", json={"message": "a quick poll"}).json() for _ in range(3)]
expect(rs[0]["error"] is None and rs[1]["error"] is None, "the first two requests in the hour work")
expect(rs[2]["error"] and "last hour" in rs[2]["error"], f"the third is refused: “{(rs[2]['error'] or '')[:70]}…”")
r = c.post("/api/agent/build", json={"message": "a quick poll"}).json()
expect(r["error"] is None, "another person is not affected by someone else's limit")
expect(any("hourly limit" in x["text"] for x in limits.alerts()), "the Monitor shows that someone hit the hourly limit")
lap = TestClient(main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
snap = lap.get("/api/monitor/snapshot").json()
expect("limits" in snap and "alerts" in snap and snap["limits"]["refused"]["rate"] >= 1, "budget and alerts are in the Monitor snapshot")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
