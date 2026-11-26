"""LOAD TESTING ONLY. A stand-in for the Claude API with a fixed delay per call, so a load test measures the
server's own concurrency (threads, database, agent pool) without paying for or depending on the real API.
Installed only when APPSHARE_LOAD_TEST_FAKE_LLM_MS is set (never in a real deployment). Every reply is marked
model="load-test-fake" and the whole team (Builder + Data/Design/Access in parallel) runs as in a real build.
"""
import os
import time

from tests.fake_claude import FakeClaude, text, tool

FIELDS = [{"id": "name_of_team", "type": "short_text", "label": "Team", "required": True},
          {"id": "track", "type": "radio", "label": "Track", "options": ["AI", "Web"], "required": True}]


def install(agents):
    delay = int(os.environ["APPSHARE_LOAD_TEST_FAKE_LLM_MS"]) / 1000
    fake = FakeClaude(agents, {
        "builder": [[tool("ask_data_agent", brief="b"), tool("ask_design_agent", brief="b"), tool("ask_access_agent", brief="b")],
                    [tool("save_app", use_team_draft=True, reason="load test")], text("Built. Press Share.")],
        "data": [[tool("submit_fields", fields=FIELDS, reason="load test")]],
        "design": [[tool("get_fields")], [tool("submit_design", title="Load test app", description="Test.", theme_color="#1d4ed8", reason="load test")]],
        "access": [[tool("submit_access", share_suggestions=[{"type": "group", "name": "34ML", "role": "submitter"}], reason="load test")]],
    }, usage=(1000, 100, 0, 0))

    def slow(*a, **k):
        time.sleep(delay)
        r = fake(*a, **k)
        r.model = "load-test-fake"
        return r
    agents._call_model = slow
