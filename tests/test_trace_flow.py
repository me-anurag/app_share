"""End to end: a request becomes a fully traced journey (offline, no API key, no cost).

Run:  python -m tests.test_trace_flow

Uses a throwaway data folder, the real server code, and FakeClaude in place of the API. Checks that the journey
records the request, every agent run (nested under the Builder), every model call with tokens and calculated cost,
every tool call, the Validator's verdicts (one rejection, then valid), a retried API failure, the app's parameters,
the share, a response, the Review agent's run, and that answers never reach the trace store.
"""
import json
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="appshare-trace-")
os.environ.update(APPSHARE_DATA=TMP, APPSHARE_MODE="university", ANTHROPIC_API_KEY="offline-test-not-a-key",
                  APPSHARE_MODEL="claude-opus-5-5", APPSHARE_SPECIALIST_MODEL="claude-haiku-5-5")

from fastapi.testclient import TestClient  # noqa: E402

from backend import agents, main, trace  # noqa: E402
from backend.db import connect  # noqa: E402
from tests.fake_claude import FakeClaude, text, tool  # noqa: E402

SECRET_ANSWER = "my-secret-answer-7731"

FIELDS = [{"id": "roll_no", "type": "short_text", "label": "Roll number", "required": True},
          {"id": "topic", "type": "radio", "label": "Topic", "options": ["AI", "Networks"], "required": True},
          {"id": "notes", "type": "long_text", "label": "Notes"}]

SCRIPTS = {
    "builder": [
        [tool("ask_data_agent", brief="Topic sign-up for 34ML: roll number, topic AI/Networks, notes. Closes 2099-01-10 23:59."),
         tool("ask_design_agent", brief="Topic sign-up for 34ML."),
         tool("ask_access_agent", brief="For section 34ML.")],
        # first save: an invalid rule (a status workflow needs 2 to 6 statuses) -> the Validator rejects it
        [tool("save_app", use_team_draft=True, spec={"statuses": ["Only one"]}, reason="Adding a status workflow.")],
        [tool("save_app", use_team_draft=True, reason="The Validator needs 2+ statuses; a sign-up needs none, so I saved the team's draft as is.")],
        text("Built “Project topic sign-up” for 34ML, closing 10 Jan. Check the preview and press Share."),
    ],
    "data": [
        [tool("check_fields", fields=FIELDS)],
        [tool("submit_fields", fields=FIELDS, closes_at="2099-01-10T23:59", notes="three fields",
                              reason="A topic sign-up only needs who (roll number) and which topic; notes are optional.")],
    ],
    "design": [
        [tool("get_fields")],
        [tool("check_color", hex="#1d4ed8")],
        [tool("submit_design", title="Project topic sign-up", description="Pick your project topic.",
              theme_color="#1d4ed8", kind="registration", style="academic", pattern="grid",
              reason="A course sign-up for students: academic style, calm blue.")],
    ],
    "access": [
        [tool("list_groups")],
        [tool("search_people", query="Diya")],
        [tool("submit_access", share_suggestions=[{"type": "group", "name": "34ML", "role": "submitter"}],
              reason="The request names section 34ML, which exists as a group.")],
    ],
    "review": [
        [tool("get_assignment"), tool("read_submission")],
        [tool("submit_review", verdict="ok", summary="Complete and on topic.", reason="All required answers present; no files to compare.")],
    ],
}


def check(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        check.failed += 1


check.failed = 0


def main_test():
    import anthropic
    import httpx
    agents.RETRY_WAITS = (0.05, 0.05)
    conn_err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    fake = FakeClaude(agents, SCRIPTS, usage=(1200, 300, 0, 0), fail_first={"builder": conn_err})
    agents._call_model = fake

    c = TestClient(main.app)
    c.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
    t0 = time.time()
    r = c.post("/api/agent/build", json={"message": "A project topic sign-up for 34ML, closes 10 Jan 2099"}).json()
    print(f"\nBuilder reply: {r['reply']!r}  (error={r['error']})  in {time.time() - t0:.2f}s")
    app_id = r["app"]["id"]

    conn = connect()
    gid = conn.execute("SELECT id FROM groups WHERE name = '34ML'").fetchone()[0]
    conn.close()
    c.post(f"/api/apps/{app_id}/share", json={"entries": [{"type": "group", "id": gid, "role": "submitter"}],
                                              "link_access": "restricted", "publish": True}).raise_for_status()
    slug = r["app"]["slug"]

    s = TestClient(main.app)
    s.post("/api/login", json={"email": "diya@riverside.edu"}).raise_for_status()
    s.post(f"/a/{slug}/submit".replace("/a/", "/api/a/"), data={"roll_no": "34ML-07", "topic": "AI", "notes": SECRET_ANSWER}).raise_for_status()
    time.sleep(2.5)  # the Review agent runs in the background; parameters refresh after 1.5 s

    lap = TestClient(main.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))   # the server laptop
    check(c.get("/api/trace/journeys").status_code == 403, "traces are refused to anyone but the server laptop")
    j = lap.get("/api/trace/journeys").json()["journeys"]
    jid = next(x["id"] for x in j if x["app_id"] == app_id)
    J = lap.get(f"/api/trace/journeys/{jid}").json()

    print("\n== Journey ==")
    print(f"{J['title']}  (app {J['app_id']}, origin {J['origin']}, owner {J['owner']})")
    print(f"request: {J['request']}")
    print("params:", json.dumps(J["params"]))
    print("totals:", json.dumps(J["totals"]))
    for run in J["runs"]:
        t = run["totals"]
        print(f"\n  [{run['agent']}] round {run['round']} · {run['status']} · {run['ms']} ms · trigger {run['trigger']}"
              f" · parent {run['parent_id'] or '-'} · model {run['model']}")
        print(f"     llm {t['llm_calls']} · tools {t['tool_calls']} · retries {t['retries']} · validator ✓{t['valid']} ✗{t['rejected']}"
              f" · tokens {t['tokens_in']}/{t['tokens_out']} · cost ${t['cost']}")
        for st in run["steps"]:
            d = st["detail"]
            extra = d.get("verdict") or (",".join(d.get("tool_calls", [])) if st["kind"] == "llm" else "") or d.get("error", "")
            print(f"       {st['seq']:>2}. {st['kind']:<9} {st['name']:<28} {'ok' if st['ok'] else 'NO':<3} {st['ms'] or 0:>5} ms  {extra}")
    print("\n  events:", [(e["type"], e["detail"]) for e in J["events"]])

    print("\n== Checks ==")
    runs = {r["agent"]: r for r in J["runs"]}
    b = runs.get("builder")
    check(J["request"].startswith("A project topic sign-up"), "journey keeps the user's original request")
    check(set(runs) >= {"builder", "data", "design", "access", "review"}, "Builder, Data, Design, Access and Review runs recorded")
    check(all(runs[a]["parent_id"] == b["id"] for a in ("data", "design", "access")), "specialists are nested under the Builder run")
    check(b["totals"]["retries"] == 1, "the failed API call was retried once and recorded")
    check(b["totals"]["rejected"] == 1 and b["totals"]["valid"] == 1, "Validator: one rejection, then valid (on save_app)")
    rej = next(s for s in b["steps"] if s["kind"] == "validator" and not s["ok"])
    check(any("statuses" in p for p in rej["detail"]["problems"]), "the rejection carries the Validator's reason")
    llm = [s for r in J["runs"] for s in r["steps"] if s["kind"] == "llm"]
    check(len(llm) == J["totals"]["llm_calls"] == len(fake.calls) - 1, f"every model call recorded ({len(llm)} = fake calls - 1 failed)")
    check(J["totals"]["tokens_in"] == 1200 * len(llm) and J["totals"]["tokens_out"] == 300 * len(llm), "token totals add up exactly")
    expect = sum(trace.cost_of(s["model"], 1200, 300) for s in llm)
    check(abs(J["totals"]["cost"] - expect) < 1e-9, f"cost = tokens x price table exactly (${J['totals']['cost']:.6f})")
    check(J["params"] and J["params"]["fields"] == 3 and J["params"]["rules"]["deadline"], "app parameters measured from the saved spec")
    types = [e["type"] for e in J["events"]]
    check(types[:1] == ["app_created"] and "app_shared" in types and "submission" in types and "review_done" in types,
          "lifecycle: created → shared → response → review")
    shared = next(e for e in J["events"] if e["type"] == "app_shared")
    check(shared["detail"].get("audience", 0) > 0, f"share records the audience size ({shared['detail'].get('audience')})")
    raw = open(trace.PATH, "rb").read()
    check(SECRET_ANSWER.encode() not in raw and b"34ML-07" not in raw, "submitted answers never reach the trace database")
    check(b"diya@riverside.edu" not in raw, "full email addresses never reach the trace database")
    reasons = [s["detail"].get("reason") for r in J["runs"] for s in r["steps"] if s["kind"] == "tool" and s["detail"].get("reason")]
    check(len(reasons) == 6, f"every decision carries the agent's stated reason ({len(reasons)}/6)")
    St = c.get(f"/api/apps/{app_id}/story").json()
    r1 = St["rounds"][0]
    print("\n== Owner's story ==")
    for x in r1["steps"]:
        print(f"  {x['agent']:<8} {x['did']}\n           why: {x['reason']}")
    print(f"  validator: {r1['validator']}\n  {r1['ms']} ms · {r1['model_calls']} calls · ${r1['cost']}")
    check({x["agent"] for x in r1["steps"]} == {"builder", "data", "design", "access"} and all(x["reason"] for x in r1["steps"]),
          "owner's story: each agent's decision with its reason")
    check(r1["validator"]["rejected"] == 1 and any("statuses" in p for p in r1["validator"]["problems_fixed"]), "owner's story shows the Validator fix")
    check(s.get(f"/api/apps/{app_id}/story").status_code == 403, "a student cannot see how the app was built")
    check(trace.health()["failures"] == 0, "no tracing failures")
    print(f"\n{'ALL PASSED' if not check.failed else str(check.failed) + ' FAILED'}  (data folder: {TMP})")
    return check.failed


if __name__ == "__main__":
    sys.exit(main_test())
