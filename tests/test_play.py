"""Quizzes and party lights: scoring, live games, no answer leaks, host-only controls, flash-rate cap.   python -m tests.test_play

Offline: no API key, no cost. A throwaway workspace; phones are separate test clients (each with its own cookie).
"""
import json
import os
import sys
import tempfile
import time

os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-play-"), APPSHARE_MODE="university", ANTHROPIC_API_KEY="")
from fastapi.testclient import TestClient  # noqa: E402

from backend import main  # noqa: E402
from backend.db import connect  # noqa: E402
from backend.seed import Seeder  # noqa: E402
from backend.spec import validate_spec  # noqa: E402

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


Q = [{"id": "simba", "type": "radio", "label": "Who is Simba's father?", "options": ["Mufasa", "Scar", "Rafiki"], "answer": "Mufasa", "points": 1},
     {"id": "nemo", "type": "radio", "label": "What kind of fish is Nemo?", "options": ["Clownfish", "Shark"], "answer": "Clownfish", "points": 2}]

print("== Validator ==")
_, e = validate_spec({"title": "Q", "kind": "quiz", "fields": [{**Q[0], "answer": "Simba"}]})
expect(any("not one of its options" in x for x in e), "a right answer must be one of the options")
_, e = validate_spec({"title": "Q", "kind": "quiz", "fields": [{"type": "radio", "label": "x", "options": ["a", "b"]}]})
expect(any("needs at least one question with a right answer" in x for x in e), "a quiz needs scored questions")
_, e = validate_spec({"title": "Q", "kind": "quiz", "quiz": {"mode": "host"}, "fields": Q + [{"type": "long_text", "label": "Comments"}]})
expect(any("host-led quiz" in x for x in e), "a host-led quiz can't have unscored questions")
s, e = validate_spec({"title": "P", "kind": "party", "party": {"scenes": ["pulse", "strobe"], "bpm": 999}})
expect(not e and "strobe" not in s["party"]["scenes"] and s["party"]["bpm"] == 180, "party: no strobe unless asked; at most 180 bpm (3 flashes/s)")
_, e = validate_spec({"title": "P", "kind": "party", "fields": Q})
expect(any("no questions" in x for x in e), "a party light show has no questions")

conn = connect()
sd = Seeder(conn)
self_id, _ = sd.app("dr.mehta@riverside.edu", {"title": "Movie quiz", "kind": "quiz", "quiz": {"mode": "self", "reveal": "after_submit"},
                                               "fields": [{"id": "your_name", "type": "short_text", "label": "Your name"}] + Q},
                    [("group", "All students", "submitter")], link="public")
host_id, _ = sd.app("dr.mehta@riverside.edu", {"title": "Party quiz", "kind": "quiz", "quiz": {"mode": "host", "seconds": 6}, "fields": Q},
                    [("group", "All students", "submitter")], link="public")
party_id, _ = sd.app("dr.mehta@riverside.edu", {"title": "Birthday lights", "kind": "party", "fields": [],
                                                "party": {"palette": ["#ff2d55", "#0a84ff"], "message": "Happy birthday!"}},
                     [("group", "All students", "submitter")], link="public")
slug = {i: conn.execute("SELECT slug FROM apps WHERE id = ?", (i,)).fetchone()[0] for i in (self_id, host_id, party_id)}
conn.execute("UPDATE apps SET status = 'live'")
conn.commit()
conn.close()


def phone():
    c = TestClient(main.app)
    c.get("/api/workspace")          # gets the device cookie, like a phone opening the page
    return c


owner = TestClient(main.app)
owner.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()

print("\n== Self-paced quiz ==")
p1 = phone()
D = p1.get(f"/api/a/{slug[self_id]}").json()
expect(all("answer" not in f for f in D["spec"]["fields"]) and '"answer"' not in json.dumps(D["spec"]), "players never receive the right answers")
expect("answer" in owner.get(f"/api/a/{slug[self_id]}").json()["spec"]["fields"][1], "the owner (editor) does see them")
r = p1.post(f"/api/a/{slug[self_id]}/submit", data={"your_name": "Aarav", "simba": "Mufasa", "nemo": "Shark"}).json()
expect(r["quiz"]["points"] == 1 and r["quiz"]["max"] == 3, f"scored on the server: 1 of 3 ({r['quiz']['points']}/{r['quiz']['max']})")
expect([x["right"] for x in r["quiz"]["review"]] == [True, False], "the review shows which were right")
p2 = phone()
r2 = p2.post(f"/api/a/{slug[self_id]}/submit", data={"your_name": "Diya", "simba": "Mufasa", "nemo": "Clownfish"}).json()
expect(r2["quiz"]["rank"] == 1 and r2["quiz"]["leaderboard"][0]["name"] == "Diya", "a perfect score ranks first on the leaderboard")
expect(p1.post(f"/api/a/{slug[self_id]}/submit", data={"your_name": "Aarav", "simba": "Mufasa", "nemo": "Clownfish"}).status_code == 400,
       "a quiz can be played only once")
expect(p1.get(f"/api/a/{slug[self_id]}").json()["quiz"]["rank"] == 2, "reopening shows my score and rank (#2)")

print("\n== Host-led quiz ==")
s = slug[host_id]
expect(phone().post(f"/api/a/{s}/submit", data={"simba": "Mufasa"}).status_code == 400, "a live quiz can't be answered as a form")
a, b, c = phone(), phone(), phone()
for ph, n in ((a, "Aarav"), (b, "Diya"), (c, "Kabir")):
    ph.post(f"/api/a/{s}/live/join", json={"name": n}).raise_for_status()
lob = a.get(f"/api/a/{s}/live").json()
expect(lob["phase"] == "lobby" and sorted(lob["players"]) == ["Aarav", "Diya", "Kabir"], "players join with a nickname and appear in the lobby")
expect(a.post(f"/api/apps/{host_id}/live", json={"action": "start"}).status_code in (401, 403, 404), "a player can't start the game")
owner.post(f"/api/apps/{host_id}/live", json={"action": "start"}).raise_for_status()
v = a.get(f"/api/a/{s}/live").json()
expect(v["phase"] == "question" and v.get("answer") is None and not v.get("counts") and "answer_for_host" not in v,
       "during a question, phones get no answer and no vote counts")
expect(owner.get(f"/api/a/{s}/live?host=1").json().get("answer_for_host") == "Mufasa", "the host screen does get the answer")
a.post(f"/api/a/{s}/live/answer", json={"q": 0, "answer": "Mufasa"}).raise_for_status()
expect(a.post(f"/api/a/{s}/live/answer", json={"q": 0, "answer": "Scar"}).status_code == 400, "one answer per question")
expect(b.post(f"/api/a/{s}/live/answer", json={"q": 0, "answer": "Lion King"}).status_code == 400, "answers must be one of the options")
time.sleep(1.5)
b.post(f"/api/a/{s}/live/answer", json={"q": 0, "answer": "Mufasa"}).raise_for_status()
c.post(f"/api/a/{s}/live/answer", json={"q": 0, "answer": "Scar"}).raise_for_status()
owner.post(f"/api/apps/{host_id}/live", json={"action": "reveal"}).raise_for_status()
va, vb, vc = (x.get(f"/api/a/{s}/live").json() for x in (a, b, c))
expect(va["answer"] == "Mufasa" and va["counts"] == {"Mufasa": 2, "Scar": 1, "Rafiki": 0}, "after the reveal: the answer and the counts")
expect(va["mine"]["points"] > vb["mine"]["points"] > 0 and vc["mine"]["points"] == 0,
       f"faster right answers score more ({va['mine']['points']} > {vb['mine']['points']}), wrong scores 0")
owner.post(f"/api/apps/{host_id}/live", json={"action": "board"}).raise_for_status()
vb2 = b.get(f"/api/a/{s}/live").json()
expect(vb2["me"]["rank"] == 2 and vb2["leaderboard"][0]["name"] == "Aarav", "leaderboard: ranks by points")
owner.post(f"/api/apps/{host_id}/live", json={"action": "next"}).raise_for_status()
expect(a.post(f"/api/a/{s}/live/answer", json={"q": 0, "answer": "Mufasa"}).status_code == 400, "an old question can't be answered")
owner.post(f"/api/apps/{host_id}/live", json={"action": "next"}).raise_for_status()
expect(a.get(f"/api/a/{s}/live").json()["phase"] == "end", "after the last question: final scores")
owner.post(f"/api/apps/{host_id}/live", json={"action": "reset"}).raise_for_status()
expect(a.get(f"/api/a/{s}/live").json()["phase"] == "lobby", "play again resets the game")

print("\n== Party lights ==")
s = slug[party_id]
ph1, ph2 = phone(), phone()
v1, v2 = ph1.get(f"/api/a/{s}/live").json(), ph2.get(f"/api/a/{s}/live").json()
expect(v1["me"]["seat"] != v2["me"]["seat"] and v2["present"] == 2, "each phone gets its own place in the wave; 2 phones counted")
expect(v1["party"]["message"] == "Happy birthday!" and "server_now" in v1, "phones get the scene and the server clock to sync on")
expect(ph1.post(f"/api/apps/{party_id}/live", json={"action": "party", "scene": "rainbow"}).status_code in (401, 403, 404),
       "a guest can't change the lights")
r = owner.post(f"/api/apps/{party_id}/live", json={"action": "party", "scene": "wave", "bpm": 500, "colors": ["#00ff00"]}).json()
expect(r["state"]["scene"] == "wave" and r["state"]["bpm"] == 180 and r["state"]["colors"] == ["#00ff00"], "the host changes scene, colour and speed (capped)")
expect(owner.post(f"/api/apps/{party_id}/live", json={"action": "party", "scene": "strobe"}).status_code == 400,
       "strobe can't be switched on when the app didn't allow it")
expect(ph2.get(f"/api/a/{s}/live").json()["party"]["scene"] == "wave", "every phone gets the new scene")
expect(owner.get(f"/a/{s}/host").status_code == 200, "the host screen page loads")

print("\n== Built by the agents (scripted model, offline) ==")
from backend import agents  # noqa: E402
from tests.fake_claude import FakeClaude, text, tool  # noqa: E402
os.environ["ANTHROPIC_API_KEY"] = "offline-test-not-a-key"
QZ = [{"id": "olaf", "type": "radio", "label": "Which movie has Olaf the snowman?", "options": ["Frozen", "Moana"], "answer": "Frozen"},
      {"id": "shrek", "type": "radio", "label": "What colour is Shrek?", "options": ["Green", "Blue"], "answer": "Green", "points": 2}]
fake = FakeClaude(agents, {
    "builder": [[tool("ask_data_agent", brief="Kids' movie quiz, 2 questions, played together on the TV."),
                 tool("ask_design_agent", brief="Kids' movie quiz for a party.")],
                [tool("save_app", use_team_draft=True, reason="The team's draft.")],
                text("Built a live movie quiz. Open the host screen on the TV and press Share.")],
    "data": [[tool("submit_fields", fields=QZ, quiz={"mode": "host", "seconds": 15},
                   reason="A party quiz played together on a TV: host mode, two simple questions children know.")]],
    "design": [[tool("submit_design", title="Kids' movie quiz", description="Answer fast!", theme_color="#7c2d92", kind="quiz",
                     reason="A playful quiz for children.")]],
})
agents._call_model = fake
r = owner.post("/api/agent/build", json={"message": "a quick movie quiz for my kid's party, we'll play on the TV"}).json()
A = owner.get(f"/api/apps/{r['app']['id']}").json()["spec"] if r.get("app") else {}
expect(A.get("kind") == "quiz" and A.get("quiz", {}).get("mode") == "host" and [f.get("answer") for f in A["fields"]] == ["Frozen", "Green"],
       f"the team builds a host-led quiz with right answers ({r.get('error')})")
fake.scripts = {"builder": [[tool("save_app", spec={"title": "Party lights", "kind": "party", "fields": [],
                                                   "party": {"palette": ["#ff2d55", "#ffcc00"], "message": "Let's dance"}},
                                  reason="A light show needs no questions, so I saved it directly.")],
                            text("Made your party lights. Open the host screen, then share the link.")]}
r = owner.post("/api/agent/build", json={"message": "turn everyone's phones into party lights"}).json()
P = owner.get(f"/api/apps/{r['app']['id']}").json()["spec"] if r.get("app") else {}
expect(P.get("kind") == "party" and P["party"]["message"] == "Let's dance" and "strobe" not in P["party"]["scenes"],
       f"the Builder makes a party light show by itself, without strobe ({r.get('error')})")
expect("data" not in fake.calls[-2:], "...without calling the Data agent (nothing to collect)")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
