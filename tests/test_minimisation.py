"""Data minimisation and transparency, tested on everything that would be sent to the AI.   python -m tests.test_minimisation

A recorder captures every message each agent would send to the model (offline: scripted stand-in), across a full
team build that searches the directory, an Insights question, a reminder run and a review of an anonymous
submission. Checks: no email address leaves the laptop; anonymous file names never do; reminders still reach
exactly the right people (by internal ref); owners see generic names for anonymous files; respondents are told
when an AI reads their work and when an app is anonymous.
"""
import json
import os
import re
import sys
import tempfile

os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-min-"), APPSHARE_MODE="university",
                  ANTHROPIC_API_KEY="offline-test-not-a-key")
from fastapi.testclient import TestClient  # noqa: E402

from backend import agents, main  # noqa: E402
from backend.db import connect  # noqa: E402
from backend.seed import Seeder  # noqa: E402
from tests.fake_claude import FakeClaude, text, tool  # noqa: E402

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


class Capture:
    """Wraps the stand-in model and keeps a copy of everything that would be sent to the API."""
    def __init__(self, fake):
        self.fake, self.sent = fake, []

    def __call__(self, model, effort, system, tools, messages):
        self.sent.append(json.dumps(messages, ensure_ascii=False, default=str))
        return self.fake(model, effort, system, tools, messages)


conn = connect()
diya = conn.execute("SELECT id FROM users WHERE email = 'diya@riverside.edu'").fetchone()[0]
a3 = conn.execute("SELECT id FROM apps WHERE title LIKE 'Assignment 3%'").fetchone()["id"]
conn.close()

FIELDS = [{"id": "topic", "type": "radio", "label": "Topic", "options": ["AI", "Networks"], "required": True}]
cap = Capture(FakeClaude(agents, {
    "builder": [[tool("ask_data_agent", brief="topic sign-up"), tool("ask_design_agent", brief="topic sign-up"), tool("ask_access_agent", brief="Diya Patel reviews it")],
                [tool("save_app", use_team_draft=True, reason="t")], text("Built. Press Share.")],
    "data": [[tool("submit_fields", fields=FIELDS, reason="t")]],
    "design": [[tool("get_fields")], [tool("submit_design", title="Topic sign-up", description="Pick one.", theme_color="#1d4ed8", reason="t")]],
    "access": [[tool("search_people", query="Diya"), tool("list_groups")],
               [tool("submit_access", share_suggestions=[{"type": "group", "name": "34ML", "role": "submitter"}, {"type": "user", "name": f"u{diya}", "role": "viewer"}], reason="t")]],
    "insights": [[tool("get_overview"), tool("list_responses"), tool("list_missing")], text("2 of 5 submitted.")],
    "reminder": [[tool("get_overview"), tool("list_missing")], [tool("send_reminders", people=["__MISSING__"], title="Closes soon", message="Please submit.", reason="t")], text("Done.")],
    "review": [[tool("get_assignment"), tool("read_submission"), tool("compare_with_others")], [tool("submit_review", verdict="ok", summary="Fine.", reason="t")]],
}))
agents._call_model = cap

owner = TestClient(main.app)
owner.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
print("Build with the whole team (Access searches the directory):")
r = owner.post("/api/agent/build", json={"message": "Topic sign-up for 34ML; Diya Patel should see the responses"}).json()
expect(r["error"] is None and r["app"], "the team builds the app")
sugg = r["app"]["share_suggestions"]
expect(any(s.get("type") == "user" and s.get("id") == diya for s in sugg), "Access proposed Diya by her internal ref (u…), and it resolved to the right person")
expect(any(s.get("detail") == "diya@riverside.edu" for s in sugg), "…the owner's Share dialog still shows her email (on the laptop only)")

print("Insights and Reminder on Assignment 3:")
prof = TestClient(main.app)
prof.post("/api/login", json={"email": "prof.sharma@riverside.edu"}).raise_for_status()
prof.post("/api/agent/insights", json={"app_id": a3, "message": "Who hasn't submitted?"}).raise_for_status()
conn = connect()
tools = agents.insights_handlers(conn, conn.execute("SELECT * FROM apps WHERE id = ?", (a3,)).fetchone())
missing = tools["list_missing"]()["missing"]
conn.close()
expect(missing and all(set(m) == {"name", "ref"} for m in missing), f"list_missing gives names and refs only ({len(missing)} people)")
cap.fake.scripts["reminder"][1][0][2]["people"] = [m["ref"] for m in missing]
before = connect().execute("SELECT COALESCE(MAX(id), 0) FROM notifications").fetchone()[0]
out = agents.run_reminder(a3, "min-test", triggered_by="Prof. Sharma")
conn = connect()
got = sorted(x[0] for x in conn.execute("SELECT u.name FROM notifications n JOIN users u ON u.id = n.user_id WHERE n.id > ? AND n.kind = 'reminder'", (before,)))
conn.close()
expect(got == sorted(m["name"] for m in missing) and out["sent"] == len(missing), "reminders reach exactly the missing people, by ref")

print("Review of an anonymous submission with a revealing file name:")
conn = connect()
s = Seeder(conn)
anon_id, _ = s.app("dr.mehta@riverside.edu", {"title": "Anonymous essay", "kind": "assignment", "anonymous": True, "description": "Upload your essay.",
                                              "fields": [{"id": "essay", "type": "file", "label": "Essay", "required": True, "accept": [".pdf"], "max_mb": 5}]},
                   [("group", "34ML", "submitter")])
s.respond(anon_id, "aarav@riverside.edu", {}, 20, file=("essay", "aarav_singh_essay.pdf", "My essay about trees and heaps and rotations."))
sid = s.respond(anon_id, "kabir@riverside.edu", {}, 2, file=("essay", "kabir_verma_final.pdf", "My essay about trees and heaps and rotations."))
conn.commit()
conn.close()
agents.run_review(sid)
sent = "\n".join(cap.sent)
emails = sorted(set(EMAIL.findall(sent)))
expect(not emails, f"no email address in anything sent to the AI ({len(cap.sent)} model calls checked){' — found ' + str(emails[:3]) if emails else ''}")
expect(not any(x in sent for x in ("kabir_verma", "aarav_singh")), "anonymous file names never reach the AI")
expect("Kabir" not in sent.split("Anonymous essay")[-1] if "Anonymous essay" in sent else True, "the anonymous author's name never reaches the AI")

R = owner.get(f"/api/apps/{anon_id}/responses").json()
blob = json.dumps(R)
expect("kabir_verma" not in blob and "aarav_singh" not in blob, "the owner's screen shows generic names for anonymous files")
fid = next(v["file_id"] for x in R["responses"] for v in x["data"].values() if isinstance(v, dict) and "file_id" in v)
cd = owner.get(f"/api/files/{fid}").headers.get("content-disposition", "")
expect("uploaded-file.pdf" in cd and "kabir" not in cd and "aarav" not in cd, f"downloads get a generic name too ({cd[:60]})")

print("What the person answering is told:")
st = TestClient(main.app)
st.post("/api/login", json={"email": "diya@riverside.edu"}).raise_for_status()
slug = connect().execute("SELECT slug FROM apps WHERE id = ?", (anon_id,)).fetchone()[0]
D = st.get(f"/api/a/{slug}").json()
expect(D["anonymous"] and D["ai_review"], "the app page knows it is anonymous and that an AI reads uploads (shown as a notice)")
page = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "app.html"), encoding="utf-8").read()
expect("An AI assistant reads your answers" in page and "Don't put your name in your answers" in page, "the notice text is on the app page")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
