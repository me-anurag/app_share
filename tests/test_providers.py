"""AI provider switch: Claude (default) / Groq free tier / mixed per agent — offline, against a simulated Groq API.

  python -m tests.test_providers

Proves the translation both ways, error mapping, routing per mode, and a full agent-team build running on (simulated)
Groq end to end: app saved, traced as Groq at $0, no Claude-only fields sent, the key only in the Authorization header.
"""
import json
import os
import sys
import tempfile

os.environ.update(APPSHARE_DATA=tempfile.mkdtemp(prefix="appshare-prov-"), APPSHARE_MODE="university",
                  APPSHARE_AI_MODE="groq", GROQ_API_KEY="gsk_offline_test_key", ANTHROPIC_API_KEY="")
import httpx  # noqa: E402

from backend import providers  # noqa: E402

failed = 0


def expect(cond, label):
    global failed
    print(("  PASS  " if cond else "  FAIL  ") + label)
    failed += 0 if cond else 1


print("Translation (Claude format -> Groq's OpenAI format):")
msgs, fns = providers.to_openai("SYS", [{"name": "save_app", "description": "d", "input_schema": {"type": "object", "properties": {}}}], [
    {"role": "user", "content": "build a poll"},
    {"role": "assistant", "content": [{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Saving."},
                                      {"type": "tool_use", "id": "t1", "name": "save_app", "input": {"reason": "x"}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{\"saved\": true}", "is_error": False}]},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "t2", "name": "save_app", "input": {}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "bad", "is_error": True}]},
])
expect(msgs[0] == {"role": "system", "content": "SYS"} and msgs[1] == {"role": "user", "content": "build a poll"}, "system prompt and user turn")
expect(msgs[2]["role"] == "assistant" and msgs[2]["content"] == "Saving." and msgs[2]["tool_calls"][0]["function"]["name"] == "save_app"
       and json.loads(msgs[2]["tool_calls"][0]["function"]["arguments"]) == {"reason": "x"}, "assistant text + tool call; thinking dropped")
expect(msgs[3] == {"role": "tool", "tool_call_id": "t1", "content": "{\"saved\": true}"}, "tool result becomes a tool message")
expect(msgs[5]["content"].startswith("ERROR:"), "a failed tool result is marked as an error")
expect(fns[0]["type"] == "function" and fns[0]["function"]["parameters"]["type"] == "object", "tools become functions with JSON schemas")

print("Translation (Groq reply -> the agents' format):")
r = providers.from_openai({"model": "m", "choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [
    {"id": "c1", "type": "function", "function": {"name": "list_groups", "arguments": "{}"}},
    {"id": "c2", "type": "function", "function": {"name": "search_people", "arguments": "{not json"}}]}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 30}}, "m")
expect(r.stop_reason == "tool_use" and [b.name for b in r.content] == ["list_groups", "search_people"], "parallel tool calls")
expect("_unparsed_arguments" in r.content[1].input, "malformed arguments are passed on so the tool reports the error")
expect(r.usage.input_tokens == 120 and r.usage.output_tokens == 30 and r.model == "groq:m", "token usage and model id")
r = providers.from_openai({"choices": [{"finish_reason": "length", "message": {"content": "cut off"}}]}, "m")
expect(r.stop_reason == "max_tokens", "a truncated reply is reported as max_tokens")

print("Errors map to the same types as Claude's (so retries work):")
import anthropic  # noqa: E402
from backend import agents  # noqa: E402
for code, cls, retry in ((429, anthropic.RateLimitError, True), (401, anthropic.AuthenticationError, False), (503, anthropic.InternalServerError, True)):
    providers._transport = httpx.MockTransport(lambda req, c=code: httpx.Response(c, json={"error": {"message": "x"}}))
    try:
        providers.groq_call("groq:m", "s", [], [{"role": "user", "content": "hi"}])
        expect(False, f"HTTP {code}")
    except Exception as e:  # noqa: BLE001
        expect(isinstance(e, cls) and agents._retryable(e) == retry, f"HTTP {code} -> {type(e).__name__} (retried: {retry})")

print("Routing:")
expect(providers.model_for("builder", "claude-opus-5-5") == "groq:" + providers.GROQ_MODEL, "groq mode: every agent on Groq")
providers.MODE = "mixed"
os.environ["APPSHARE_AGENT_PROVIDERS"] = json.dumps({"builder": "claude", "data": "groq"})
expect(providers.model_for("builder", "claude-opus-5-5") == "claude-opus-5-5" and providers.model_for("data", "claude-haiku-5-5").startswith("groq:")
       and providers.model_for("design", "claude-haiku-5-5") == "claude-haiku-5-5", "mixed mode: per agent, unlisted agents stay on Claude")
expect(not providers.keys_ok(), "mixed mode needs both keys (Claude key missing -> agents report not configured)")
providers.MODE = "claude"
expect(providers.model_for("data", "claude-haiku-5-5") == "claude-haiku-5-5", "claude mode: unchanged")
providers.MODE = "groq"

print("A model per agent (Groq counts limits per model):")
os.environ["APPSHARE_GROQ_MODELS"] = json.dumps({"data": "small-fast-model", "design": "small-fast-model"})
expect(providers.model_for("data", "x") == "groq:small-fast-model" and providers.model_for("builder", "x") == "groq:" + providers.GROQ_MODEL,
       "agents with their own model use it; the rest use the default")
os.environ["APPSHARE_GROQ_MODELS"] = "{}"

print("Throttle (stays inside Groq's allowance instead of failing):")
import threading  # noqa: E402
import time  # noqa: E402
waited = []
providers._sleep = lambda s: waited.append(s)
providers._transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"model": "m", "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]},
                                                                      headers={"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "4.5s",
                                                                               "x-ratelimit-remaining-tokens": "50000", "x-ratelimit-reset-tokens": "1s"}))
providers.groq_call("groq:throttle-model", "s", [], [{"role": "user", "content": "hi"}])
expect(not waited, "first call goes straight through")
providers.groq_call("groq:throttle-model", "s", [], [{"role": "user", "content": "hi"}])
expect(waited and 3.5 <= waited[0] <= 4.6, f"when Groq says 0 requests are left, the next call waits for the reset ({waited[0] if waited else 0:.1f} s)")
st = providers.throttle_status().get("throttle-model", {})
expect(st.get("requests_left") == 0 and st.get("tokens_left") == 50000, "the remaining allowance is visible (Control Center / snapshot)")

providers._transport = httpx.MockTransport(lambda req: httpx.Response(429, json={"error": {"message": "rate limited"}}, headers={"retry-after": "3"}))
try:
    providers.groq_call("groq:other-model", "s", [], [{"role": "user", "content": "hi"}])
except Exception as e:  # noqa: BLE001
    expect(isinstance(e, anthropic.RateLimitError) and getattr(e, "retry_after", None) == 3.0, "a 429 carries Groq's retry-after (3 s)")

active, peak, lock = [0], [0], threading.Lock()


def slow(req):
    with lock:
        active[0] += 1
        peak[0] = max(peak[0], active[0])
    time.sleep(0.15)
    with lock:
        active[0] -= 1
    return httpx.Response(200, json={"model": "m", "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]})


providers._transport = httpx.MockTransport(slow)
th = [threading.Thread(target=providers.groq_call, args=("groq:busy-model", "s", [], [{"role": "user", "content": "hi"}])) for _ in range(8)]
[t.start() for t in th]
[t.join() for t in th]
expect(peak[0] <= providers.GROQ_PARALLEL, f"8 simultaneous calls: at most {providers.GROQ_PARALLEL} in flight per model (peak {peak[0]})")
providers._sleep = time.sleep

print("A full team build on (simulated) Groq:")
SENT = []
SPECS = {"Builder": None, "Data agent": None, "Design agent": None, "Access agent": None}


def call(name, args, i):
    return {"id": f"call_{name}_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def fake_groq(req):
    body = json.loads(req.content)
    SENT.append({"body": body, "auth": req.headers.get("authorization"), "raw": req.content.decode()})
    system, n = body["messages"][0]["content"], sum(1 for m in body["messages"] if m["role"] == "assistant")
    who = next(k for k in SPECS if f"You are the {k}" in system)
    fields = [{"id": "topic", "type": "radio", "label": "Topic", "options": ["AI", "Web"], "required": True}]
    script = {
        "Builder": [[call("ask_data_agent", {"brief": "b"}, 1), call("ask_design_agent", {"brief": "b"}, 2), call("ask_access_agent", {"brief": "b"}, 3)],
                    [call("save_app", {"use_team_draft": True, "reason": "the team's draft fits the request"}, 4)], "Built it. Press Share when ready."],
        "Data agent": [[call("submit_fields", {"fields": fields, "reason": "one choice is all a topic poll needs"}, 5)]],
        "Design agent": [[call("get_fields", {}, 6)], [call("submit_design", {"title": "Topic poll", "description": "Pick one.", "theme_color": "#1d4ed8", "reason": "simple and calm"}, 7)]],
        "Access agent": [[call("submit_access", {"share_suggestions": [{"type": "group", "name": "34ML", "role": "submitter"}], "reason": "the request names 34ML"}, 8)]],
    }[who]
    step = script[min(n, len(script) - 1)]
    msg = {"role": "assistant", "content": step} if isinstance(step, str) else {"role": "assistant", "content": None, "tool_calls": step}
    return httpx.Response(200, json={"model": body["model"], "choices": [{"finish_reason": "stop" if isinstance(step, str) else "tool_calls", "message": msg}],
                                     "usage": {"prompt_tokens": 900, "completion_tokens": 60}})


providers._transport = httpx.MockTransport(fake_groq)
from fastapi.testclient import TestClient  # noqa: E402

from backend import main, trace  # noqa: E402
c = TestClient(main.app)
c.post("/api/login", json={"email": "dr.mehta@riverside.edu"}).raise_for_status()
res = c.post("/api/agent/build", json={"message": "A topic poll for 34ML: AI or Web"}).json()
expect(res["error"] is None and res["app"] and res["app"]["title"] == "Topic poll", f"the team built and saved the app ({res.get('error') or 'ok'})")
j = trace.get_journey(trace.list_journeys()[0]["id"])
models = {s["model"] for r in j["runs"] for s in r["steps"] if s["kind"] == "llm"}
expect(models == {"groq:" + providers.GROQ_MODEL} and {r["agent"] for r in j["runs"]} == {"builder", "data", "design", "access"},
       f"all four agents ran on Groq ({len(SENT)} calls), traced as {sorted(models)}")
expect(j["totals"]["cost"] == 0 and j["totals"]["tokens_in"] > 0, "tokens are measured; cost is $0 (free tier)")
expect(all(not any(k in s["body"] for k in ("thinking", "cache_control", "output_config", "betas")) for s in SENT), "no Claude-only fields sent to Groq")
expect(all(s["auth"] == "Bearer gsk_offline_test_key" for s in SENT) and not any("gsk_offline_test_key" in s["raw"] for s in SENT),
       "the key is only in the Authorization header, never in the request body")
expect("gsk_offline_test_key" not in json.dumps(j) and b"gsk_offline_test_key" not in open(trace.PATH, "rb").read(), "the key never reaches the trace store")

print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'}")
sys.exit(failed)
