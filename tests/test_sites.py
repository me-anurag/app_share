"""Sites: the creator gets exactly what they asked for, and controls the rest.   python -m tests.test_sites

Offline (scripted fake model, no API key, no cost). Checks the site validator, a full build through the Builder
and the Site agent, that suggested extras are never added by themselves, that the theme changes for free, that an
extra is written only when the owner switches it on (and removed when switched off), and that the page renders.
"""
import json
import os
import sys
import tempfile

os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-sites-"), APPSHARE_MODE="university",
                  ANTHROPIC_API_KEY="offline-test-not-a-key", APPSHARE_SPECIALIST_MODEL="claude-haiku-5-5")
from fastapi.testclient import TestClient  # noqa: E402

from backend import agents, main  # noqa: E402
from backend.site import block_types_used, validate_site  # noqa: E402
from backend.spec import validate_spec  # noqa: E402
from tests.fake_claude import FakeClaude, text, tool  # noqa: E402

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


print("== Validator ==")
site, err = validate_site({"theme": "bold", "pages": [{"title": "Home", "blocks": [{"type": "hero", "title": "Fest"}]}],
                           "suggested": [{"type": "faq", "label": "FAQ"}]}, "Fest", has_fields=False)
expect(not err and block_types_used(site) == ["hero"], "a one-block site stays one block (nothing added)")
expect(site["suggested"] == [{"type": "faq", "label": "FAQ", "why": ""}] and "faq" not in block_types_used(site),
       "suggested extras are kept as suggestions, never placed on the page")
site, err = validate_site({"pages": [{"blocks": [{"type": "hero", "title": "Fest"}]}]}, "Fest", has_fields=True)
expect(block_types_used(site) == ["hero", "form"], "a site that collects answers always shows its form")
_, err = validate_site({"pages": [{"blocks": [{"type": "buttons", "items": [{"label": "x", "to": "javascript:alert(1)"}]}]}]}, "F", False)
expect(any("links must start" in e for e in err), "javascript: links are rejected")
_, err = validate_site({"pages": [{"blocks": [{"type": "text", "body": "<script>x</script>"}]}]}, "F", False)
expect(not err, "HTML in text is allowed as plain text (the page escapes it)")
_, err = validate_site({"pages": [{"blocks": [{"type": "countdown", "to": "next friday"}]}]}, "F", False)
expect(any("YYYY-MM-DDTHH:MM" in e for e in err), "a countdown needs a real date")
_, err = validate_site({"pages": [{"blocks": []}] * 7}, "F", False)
expect(any("at most 6 pages" in e for e in err), "at most 6 pages")
spec, err = validate_spec({"title": "Notice", "kind": "site", "fields": [],
                           "site": {"pages": [{"blocks": [{"type": "text", "heading": "Library closed Friday"}]}]}})
expect(not err and spec["kind"] == "site", "an information-only site needs no questions")

print("\n== Build through the Builder and the Site agent ==")
FIELDS = [{"id": "team", "type": "short_text", "label": "Team name", "required": True}]
SITE = {"theme": "bold", "background": "dusk", "pages": [{"title": "Home", "blocks": [
    {"type": "hero", "title": "Hack Night", "subtitle": "Friday 7 pm, Lab 3", "button": {"label": "Register", "to": "#form"}},
    {"type": "form", "heading": "Register your team"}]}],
    "suggested": [{"type": "faq", "label": "FAQ", "why": "people often ask what to bring"},
                  {"type": "timeline", "label": "Schedule", "why": "a night event has phases"}]}
SCRIPTS = {
    "builder": [[tool("ask_data_agent", brief="Hack night registration: team name."),
                 tool("ask_design_agent", brief="Hack night page."),
                 tool("ask_site_agent", brief="A site for Hack Night, Friday 7 pm, Lab 3, with team registration.")],
                [tool("save_app", use_team_draft=True, reason="The team's draft as is.")],
                text("Built the Hack Night site with team registration. Check the preview and press Share.")],
    "data": [[tool("submit_fields", fields=FIELDS, reason="Registration needs the team's name.")]],
    "design": [[tool("submit_design", title="Hack Night", description="Register your team.", theme_color="#1d4ed8",
                     kind="registration", reason="An event page.")]],
    "site": [[tool("get_fields")], [tool("check_site", site=SITE)],
             [tool("submit_site", site=SITE, reason="They asked for an event page with registration: a hero and the form.")]],
}
fake = FakeClaude(agents, SCRIPTS)
agents._call_model = fake
c = TestClient(main.app)
c.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
r = c.post("/api/agent/build", json={"message": "A site for Hack Night on Friday 7 pm in Lab 3 where teams register"}).json()
expect(not r.get("error") and r.get("app"), f"the Builder saved it ({r.get('error')})")
app_id, slug = r["app"]["id"], r["app"]["slug"]
A = c.get(f"/api/apps/{app_id}").json()
S = A["spec"].get("site") or {}
expect(A["spec"]["kind"] == "site", "the app is a site")
expect(block_types_used(S) == ["hero", "form"], f"exactly the blocks asked for: {block_types_used(S)}")
expect([x["type"] for x in S["suggested"]] == ["faq", "timeline"], "the extras are offered as suggestions only")
expect("site" in fake.calls, "the Site agent ran")

print("\n== Owner controls ==")
before = len(fake.calls)
r2 = c.post(f"/api/apps/{app_id}/site/look", json={"theme": "night", "footer": "CS Society"})
expect(r2.status_code == 200 and r2.json()["site"]["theme"] == "night", "theme and footer change by tapping")
expect(len(fake.calls) == before, "...with no AI call")
expect(c.post(f"/api/apps/{app_id}/site/look", json={"theme": "rainbow"}).status_code == 400, "an unknown theme is refused")
fake.scripts["site"] = [[tool("submit_block", block={"type": "faq", "items": [{"q": "What do I bring?", "a": "[add what to bring]"}]},
                              reason="The site does not say what to bring, so the answer is a placeholder.")]]
r3 = c.post(f"/api/apps/{app_id}/site/extra", json={"type": "faq", "on": True}).json()
blocks = r3["site"]["pages"][0]["blocks"]
expect([b["type"] for b in blocks] == ["hero", "faq", "form"] and blocks[1].get("extra"), "switching FAQ on adds it above the form, marked extra")
expect(fake.calls[-1] == "site" and len(fake.calls) == before + 1, "...with exactly one small model call")
r4 = c.post(f"/api/apps/{app_id}/site/extra", json={"type": "faq", "on": False}).json()
expect([b["type"] for b in r4["site"]["pages"][0]["blocks"]] == ["hero", "form"] and r4["removed"] == 1, "switching it off removes it")
expect(len(fake.calls) == before + 1, "...with no model call")
expect(c.post(f"/api/apps/{app_id}/site/extra", json={"type": "form", "on": True}).status_code == 400, "a second form can't be added")

print("\n== The page ==")
html = c.get(f"/a/{slug}").text
expect("/static/site.js?v=" in html and "/static/site.css?v=" in html, "the app page loads the site renderer (fingerprinted)")
D = c.get(f"/api/a/{slug}").json()
expect(D["spec"]["site"]["theme"] == "night" and D["spec"]["kind"] == "site", "people opening it get the site spec")
story = c.get(f"/api/apps/{app_id}/story")
expect(story.status_code == 200, "the owner's build story still works with a Site agent in it")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
