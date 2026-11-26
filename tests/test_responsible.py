"""Responsible-AI guarantees, tested exactly (no API).   python -m tests.test_responsible

Anonymity: for an anonymous app, no respondent's name or email reaches the owner's screen, the CSV export, the
Insights agent's tools or the trace store; times are coarsened to the day. Only the owner side can read responses.
Human decision: a Review flag is never final — only an editor can confirm or dismiss it, and that is recorded.
"""
import json
import os
import sys
import tempfile

os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-resp-"), APPSHARE_MODE="university",
                  ANTHROPIC_API_KEY="offline-test-not-a-key", APPSHARE_GUARDS="on")
from fastapi.testclient import TestClient  # noqa: E402

from backend import agents, main, trace  # noqa: E402
from backend.db import connect  # noqa: E402

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


owner, student = TestClient(main.app), TestClient(main.app)
owner.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
student.post("/api/login", json={"email": "diya@riverside.edu"}).raise_for_status()
conn = connect()
anon = conn.execute("SELECT * FROM apps WHERE title LIKE 'Mid-semester feedback%'").fetchone()
who = [dict(r) for r in conn.execute("SELECT u.name, u.email FROM submissions s JOIN users u ON u.id = s.user_id WHERE s.app_id = ?", (anon["id"],))]
conn.close()
names = [w["name"] for w in who] + [w["email"] for w in who]
print(f"Anonymous app: “{anon['title']}” with {len(who)} responses\n")

R = owner.get(f"/api/apps/{anon['id']}/responses").json()
blob = json.dumps(R)
expect(not any(n in blob for n in names), "owner's responses: no respondent names or emails")
expect(all(len(r["created_at"]) == 10 for r in R["responses"]), "owner's responses: only the day, not the exact time")
csv = owner.get(f"/api/apps/{anon['id']}/export.csv").text
expect(not any(n in csv for n in names), "CSV export: no respondent names or emails")
expect(all(len(line.split(",")[1]) == 10 for line in csv.strip().splitlines()[1:]), "CSV export: dates only")
conn = connect()
tools = agents.insights_handlers(conn, conn.execute("SELECT * FROM apps WHERE id = ?", (anon["id"],)).fetchone())
lr = tools["list_responses"]()
conn.close()
expect(lr["anonymous"] and not any(n in json.dumps(lr) for n in names), "Insights agent's tool: no names or emails (the AI never sees who)")
expect(all(len(r["submitted_at"]) == 10 for r in lr["responses"]), "Insights agent's tool: only the day")
expect(student.get(f"/api/apps/{anon['id']}/responses").status_code == 403, "a student can't read the responses at all")

spec = json.loads(anon["spec"])
def answer(f):
    return {"rating": "4", "number": "3"}.get(f["type"]) or ((f.get("options") or ["x"])[0] if f["type"] in ("radio", "select") else "Great lectures, a bit fast.")


full = {f["id"]: answer(f) for f in spec["fields"] if f["type"] not in ("info", "file", "checkbox")}
r = TestClient(main.app)
r.post("/api/login", json={"email": "kabir@riverside.edu"}).raise_for_status()
bad = r.post(f"/api/a/{anon['slug']}/submit", data={}).status_code           # rejected: required answers missing
good = r.post(f"/api/a/{anon['slug']}/submit", data=full).status_code
raw = open(trace.PATH, "rb").read()
expect(bad == 422 and good == 200, f"an incomplete response is refused ({bad}) and a complete one accepted ({good})")
expect(b"Kabir" not in raw and b"kabir@" not in raw, "trace store: neither the refused nor the accepted anonymous response carries the name")
with trace._lock:
    j_owner = trace._db().execute("SELECT owner FROM journeys WHERE app_id = ?", (anon["id"],)).fetchone()[0]
expect(j_owner == "Dr. Mehta", f"the journey's owner is the app's owner (got {j_owner!r}), never a respondent")

print("\nHuman decision on Review flags:")
conn = connect()
a3 = conn.execute("SELECT id FROM apps WHERE title LIKE 'Assignment 3%'").fetchone()["id"]
sid = conn.execute("SELECT id FROM submissions WHERE app_id = ? LIMIT 1", (a3,)).fetchone()["id"]
conn.execute("INSERT OR REPLACE INTO reviews (submission_id, app_id, verdict, summary, flags, evidence) VALUES (?, ?, 'problem', 'Looks copied.', '[]', ?)",
             (sid, a3, json.dumps({"reason": "92% of the text matches another submission"})))
conn.commit()
conn.close()
prof = TestClient(main.app)
prof.post("/api/login", json={"email": "prof.sharma@riverside.edu"}).raise_for_status()
row = next(x for x in prof.get(f"/api/apps/{a3}/responses").json()["responses"] if x["id"] == sid)
expect(row["review"]["evidence"]["reason"].startswith("92%") and row["review"]["decision"] is None, "the owner sees the AI's evidence, and no decision has been made")
expect(student.post(f"/api/apps/{a3}/responses/{sid}/review-decision", json={"decision": "confirmed"}).status_code == 403,
       "a student can't decide on a flag")
expect(prof.post(f"/api/apps/{a3}/responses/{sid}/review-decision", json={"decision": "dismissed"}).status_code == 200, "the owner dismisses it")
row = next(x for x in prof.get(f"/api/apps/{a3}/responses").json()["responses"] if x["id"] == sid)
expect(row["review"]["decision"] == "dismissed" and row["review"]["decided_by"] == "Prof. Sharma", "the decision is recorded with who made it")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
