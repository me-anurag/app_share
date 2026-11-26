"""The account answers "your name / your email" for signed-in people.   python -m tests.test_creator"""
import json
import os
import sys
import tempfile

os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-creator-"), APPSHARE_MODE="university", ANTHROPIC_API_KEY="")
from fastapi.testclient import TestClient  # noqa: E402

from backend import main  # noqa: E402
from backend.db import connect  # noqa: E402
from backend.seed import Seeder  # noqa: E402

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


FIELDS = [{"id": "your_name", "type": "short_text", "label": "Your name", "required": True},
          {"id": "email", "type": "email", "label": "Email", "required": True},
          {"id": "team_name", "type": "short_text", "label": "Team name", "required": True},
          {"id": "pick", "type": "radio", "label": "Pick", "options": ["A", "B"], "required": True}]
conn = connect()
s = Seeder(conn)
normal, _ = s.app("dr.mehta@riverside.edu", {"title": "Sign-up", "description": "x", "fields": FIELDS}, [("group", "All students", "submitter")], link="public")
anon, _ = s.app("dr.mehta@riverside.edu", {"title": "Anon", "description": "x", "anonymous": True, "fields": FIELDS}, [("group", "All students", "submitter")])
slug = {a: conn.execute("SELECT slug FROM apps WHERE id = ?", (a,)).fetchone()[0] for a in (normal, anon)}
conn.commit()
conn.close()

st = TestClient(main.app)
st.post("/api/login", json={"email": "kabir@riverside.edu"}).raise_for_status()
D = st.get(f"/api/a/{slug[normal]}").json()
expect(D["auto"] == {"your_name": "Kabir Verma", "email": "kabir@riverside.edu"}, f"signed in: name and email come from the account ({D['auto']})")
expect("team_name" not in D["auto"], "'Team name' is not taken as the person's name")
r = st.post(f"/api/a/{slug[normal]}/submit", data={"team_name": "Null Pointers", "pick": "A"})
expect(r.status_code == 200, "submitting without the hidden name/email works")
conn = connect()
saved = json.loads(conn.execute("SELECT data FROM submissions WHERE app_id = ?", (normal,)).fetchone()[0])
conn.close()
expect(saved.get("your_name") == "Kabir Verma" and saved.get("email") == "kabir@riverside.edu", "the server stored the account's name and email")
expect(st.get(f"/api/a/{slug[anon]}").json()["auto"] == {}, "anonymous apps never fill in a name or email")
guest = TestClient(main.app)
expect(guest.get(f"/api/a/{slug[normal]}").json()["auto"] == {}, "guests (public link, no account) still type their own")
owner = TestClient(main.app)
owner.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
expect(owner.get(f"/api/a/{slug[normal]}").json()["role"] == "owner", "the creator opening their own app is recognised as the owner (banner shown)")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
