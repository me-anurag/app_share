"""Record real model replies once, replay them any time.

`Recorder` wraps the real API call and saves every reply (content blocks, token usage, stop reason, time taken)
per agent, in call order. `Player` feeds those replies back in the same order, so a replay runs the real tools,
Validator, database and checks again without an API key, and must reproduce the recorded results exactly.
Times in a replay are the recorded times (the replay itself takes milliseconds).
"""
import json
import threading
import time

from tests.fake_claude import Block, Response, Usage


def agent_of(agents, system):
    table = {agents.BUILDER_SYSTEM: "builder", agents.DATA_SYSTEM: "data", agents.DESIGN_SYSTEM: "design",
             agents.ACCESS_SYSTEM: "access", agents.REVIEW_SYSTEM: "review", agents.REMINDER_SYSTEM: "reminder"}
    if system in table:
        return table[system]
    return "insights" if system.startswith(agents.INSIGHTS_SYSTEM) else "unknown"


class Recorder:
    def __init__(self, agents, real_call):
        self.agents, self.real = agents, real_call
        self.calls, self._lock = {}, threading.Lock()

    def __call__(self, model, effort, system, tools, messages):
        agent = agent_of(self.agents, system)
        t0 = time.time()
        try:
            resp = self.real(model, effort, system, tools, messages)
        except Exception as e:  # failed calls are recorded too, so a replay reproduces retries and failures
            with self._lock:
                self.calls.setdefault(agent, []).append({"error": type(e).__name__, "message": str(e)[:300],
                                                         "status": getattr(e, "status_code", None), "ms": int((time.time() - t0) * 1000)})
            raise
        ms = int((time.time() - t0) * 1000)
        u = resp.usage
        rec = {"content": [b.model_dump(mode="json", exclude_none=True) for b in resp.content], "stop_reason": resp.stop_reason,
               "model": getattr(resp, "model", model), "ms": ms,
               "usage": {k: getattr(u, k, 0) or 0 for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}}
        with self._lock:
            self.calls.setdefault(agent, []).append(rec)
        return resp

    def dump(self, path, meta):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**meta, "calls": self.calls}, f, ensure_ascii=False, indent=1)


class CassetteExhausted(Exception):
    pass


class Player:
    def __init__(self, agents, path):
        with open(path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.agents = agents
        self.queues = {a: list(v) for a, v in self.data["calls"].items()}
        self._lock = threading.Lock()
        self.recorded_ms = 0

    def __call__(self, model, effort, system, tools, messages):
        agent = agent_of(self.agents, system)
        with self._lock:
            q = self.queues.get(agent) or []
            if not q:
                raise CassetteExhausted(f"no recorded reply left for the {agent} agent")
            rec = q.pop(0)
            self.recorded_ms += rec["ms"]
        if "error" in rec:
            raise _rebuild_error(rec)
        blocks = [Block(**b) for b in rec["content"]]
        return Response(blocks, rec["stop_reason"], Usage(**rec["usage"]), rec["model"])


def _rebuild_error(rec):
    """The same kind of exception the API raised when recording (so retry and failure handling replay identically)."""
    import anthropic
    import httpx
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    if rec["error"] in ("APIConnectionError", "APITimeoutError"):
        return anthropic.APIConnectionError(request=req)
    if rec.get("status"):
        resp = httpx.Response(rec["status"], request=req)
        cls = {429: anthropic.RateLimitError, 401: anthropic.AuthenticationError}.get(rec["status"], anthropic.APIStatusError)
        if rec["status"] >= 500 and cls is anthropic.APIStatusError:
            cls = anthropic.InternalServerError
        return cls(rec["message"], response=resp, body=None)
    return RuntimeError(f"{rec['error']}: {rec['message']}")
