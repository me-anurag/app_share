"""Which AI provider each agent uses: Claude (default, unchanged) or Groq's free tier, or a mix per agent.

Settings (in .env, applied when the server starts):
  APPSHARE_AI_MODE         claude (default) | groq | mixed
  APPSHARE_AGENT_PROVIDERS for mixed: JSON {"builder": "claude", "data": "groq", ...}; agents not listed use Claude
  GROQ_API_KEY             from console.groq.com (free sign-up); never shown or logged
  APPSHARE_GROQ_MODEL      default Groq model id (the Control Center lists the models Groq offers)
  APPSHARE_GROQ_MODELS     optional JSON {"builder": "<model>", "data": "<model>", ...}: a model per agent. Groq counts
                           its free-tier limits per model, so agents on different models don't share one allowance.
  APPSHARE_GROQ_PARALLEL   at most this many calls in flight per Groq model at once (default 3)

The agents keep one calling convention (Claude's message format). For Groq, this module translates the messages
and tools into Groq's OpenAI-compatible chat format and the reply back into the same shape, and maps HTTP errors
onto the same exception types, so retries, tracing, the Validator, guardrails and limits all work unchanged.
Claude-only features (adaptive thinking, prompt caching, effort, server-side fallback) are simply not used for Groq.
"""
import json
import os
import re
import secrets
import threading
import time

import httpx

AGENTS = ("builder", "data", "design", "access", "insights", "review", "reminder")
MODE = (os.environ.get("APPSHARE_AI_MODE") or "claude").strip().lower()
GROQ_URL = os.environ.get("APPSHARE_GROQ_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.environ.get("APPSHARE_GROQ_MODEL") or "openai/gpt-oss-120b"
GROQ_MAX_TOKENS = int(os.environ.get("APPSHARE_GROQ_MAX_TOKENS", "4096"))
GROQ_PARALLEL = int(os.environ.get("APPSHARE_GROQ_PARALLEL", "3"))
MAX_WAIT_S = float(os.environ.get("APPSHARE_GROQ_MAX_WAIT", "20"))     # never make a person wait longer than this
PREFIX = "groq:"            # model ids routed to Groq look like "groq:openai/gpt-oss-120b"
_transport = None          # tests inject an httpx.MockTransport here


def _mixed():
    try:
        m = json.loads(os.environ.get("APPSHARE_AGENT_PROVIDERS") or "{}")
        return {k: v for k, v in m.items() if k in AGENTS and v in ("claude", "groq")}
    except ValueError:
        return {}


def provider_for(agent):
    if MODE == "groq":
        return "groq"
    if MODE == "mixed":
        return _mixed().get(agent, "claude")
    return "claude"


def _per_agent_models():
    try:
        m = json.loads(os.environ.get("APPSHARE_GROQ_MODELS") or "{}")
        return {k: v for k, v in m.items() if k in AGENTS and isinstance(v, str) and v.strip()}
    except ValueError:
        return {}


def groq_model_for(agent):
    return _per_agent_models().get(agent) or GROQ_MODEL


def model_for(agent, claude_model):
    """The model id run_loop should use for this agent: the Claude model, or "groq:<model>"."""
    return PREFIX + groq_model_for(agent) if provider_for(agent) == "groq" else claude_model


def is_groq(model):
    return str(model or "").startswith(PREFIX)


def keys_ok():
    """Whether every provider in use has a key."""
    need = {provider_for(a) for a in AGENTS}
    ok = True
    if "claude" in need:
        ok &= bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if "groq" in need:
        ok &= bool(os.environ.get("GROQ_API_KEY"))
    return ok


def describe():
    return {"mode": MODE, "groq_model": GROQ_MODEL, "agents": {a: provider_for(a) for a in AGENTS},
            "groq_models": {a: groq_model_for(a) for a in AGENTS if provider_for(a) == "groq"},
            "groq_key": bool(os.environ.get("GROQ_API_KEY")), "groq_limits": throttle_status()}


# --------------------------------------------------------------------------- throttle: stay inside Groq's allowance
# Every Groq reply says how many requests and tokens are left for that model and when they reset. Before a call we
# wait (briefly) if the allowance is used up, and at most GROQ_PARALLEL calls per model are in flight at once.

_state, _gates, _slock = {}, {}, threading.Lock()
_sleep = time.sleep          # tests replace this


def parse_reset(v):
    """Groq's reset times look like "7.66s", "2m59.56s", "120ms", "1h2m3s" -> seconds."""
    if not v:
        return 0.0
    v = str(v).strip()
    if re.fullmatch(r"[\d.]+", v):
        return float(v)
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)(ms|h|m|s)", v):
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total


def _note_limits(model, headers):
    now = time.time()
    g = lambda k: headers.get(k)
    with _slock:
        st = _state.setdefault(model, {})
        if g("x-ratelimit-remaining-requests") is not None:
            st["req_left"] = int(float(g("x-ratelimit-remaining-requests")))
            st["req_reset_at"] = now + parse_reset(g("x-ratelimit-reset-requests"))
        if g("x-ratelimit-remaining-tokens") is not None:
            st["tok_left"] = int(float(g("x-ratelimit-remaining-tokens")))
            st["tok_reset_at"] = now + parse_reset(g("x-ratelimit-reset-tokens"))
        st["seen_at"] = now


def _wait_needed(model, est_tokens):
    now = time.time()
    with _slock:
        st = _state.get(model) or {}
    waits = []
    if st.get("req_left") is not None and st["req_left"] <= 0:
        waits.append(st.get("req_reset_at", now) - now)
    if st.get("tok_left") is not None and st["tok_left"] < est_tokens:
        waits.append(st.get("tok_reset_at", now) - now)
    return max([0.0] + waits)


def _gate(model):
    with _slock:
        if model not in _gates:
            _gates[model] = threading.BoundedSemaphore(GROQ_PARALLEL)
        return _gates[model]


def throttle_status():
    now = time.time()
    with _slock:
        return {m: {"requests_left": s.get("req_left"), "tokens_left": s.get("tok_left"),
                    "resets_in_s": round(max(0.0, max(s.get("req_reset_at", now), s.get("tok_reset_at", now)) - now), 1)}
                for m, s in _state.items()}


# --------------------------------------------------------------------------- the reply, in the shape the agents expect

class Block:
    def __init__(self, type, **kw):
        self.type = type
        self.__dict__.update(kw)

    def model_dump(self, mode="json", exclude_none=True):
        return {k: v for k, v in self.__dict__.items() if not (exclude_none and v is None)}


class Usage:
    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        self.cache_read_input_tokens = self.cache_creation_input_tokens = 0


class Reply:
    def __init__(self, content, stop_reason, usage, model):
        self.content, self.stop_reason, self.usage, self.model = content, stop_reason, usage, model


# --------------------------------------------------------------------------- translation

def to_openai(system, tools, messages):
    """Claude-format system prompt, tools and messages -> OpenAI chat format (as Groq expects)."""
    out = [{"role": "system", "content": system}]
    for m in messages:
        c = m["content"]
        if m["role"] == "user":
            if isinstance(c, str):
                out.append({"role": "user", "content": c})
                continue
            texts = []
            for b in c:
                if b.get("type") == "tool_result":
                    content = b.get("content")
                    if isinstance(content, list):
                        content = "\n".join(x.get("text", "") for x in content if isinstance(x, dict))
                    if b.get("is_error"):
                        content = f"ERROR: {content}"
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": str(content)})
                elif b.get("type") == "text":
                    texts.append(b.get("text", ""))
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
        else:
            text = "\n".join(b.get("text", "") for b in c if b.get("type") == "text").strip()
            calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})}}
                     for b in c if b.get("type") == "tool_use"]
            msg = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)                                   # thinking blocks are Claude-only: dropped
    fns = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                             "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}}
           for t in tools or []]
    return out, fns


def from_openai(data, model):
    """Groq's chat completion -> a reply the agents' tool loop understands."""
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    blocks = []
    if (msg.get("content") or "").strip():
        blocks.append(Block("text", text=msg["content"]))
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
            if not isinstance(args, dict):
                args = {"value": args}
        except ValueError:
            args = {"_unparsed_arguments": (fn.get("arguments") or "")[:500]}   # the tool will report the error to the model
        blocks.append(Block("tool_use", id=tc.get("id") or "call_" + secrets.token_hex(6), name=fn.get("name", ""), input=args))
    finish = choice.get("finish_reason")
    stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "max_tokens" if finish == "length" else "end_turn"
    u = data.get("usage") or {}
    return Reply(blocks, stop, Usage(u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0), PREFIX + (data.get("model") or model))


def _raise_for(resp, req):
    """Map Groq's HTTP errors onto the same exceptions the Claude path raises, so retries and messages stay the same.
    A rate-limit error carries Groq's own advice on how long to wait (retry_after, seconds)."""
    import anthropic
    try:
        msg = (resp.json().get("error") or {}).get("message") or resp.text
    except ValueError:
        msg = resp.text
    msg = f"Groq: {str(msg)[:300]}"
    cls = {401: anthropic.AuthenticationError, 403: anthropic.PermissionDeniedError, 429: anthropic.RateLimitError}.get(resp.status_code)
    if cls is None:
        cls = anthropic.InternalServerError if resp.status_code >= 500 else anthropic.BadRequestError
    err = cls(msg, response=resp, body=None)
    ra = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-requests") or resp.headers.get("x-ratelimit-reset-tokens")
    if resp.status_code == 429 and ra:
        err.retry_after = min(MAX_WAIT_S, parse_reset(ra))
    raise err


def groq_call(model, system, tools, messages, timeout=90):
    import anthropic
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise anthropic.AuthenticationError("No Groq API key is set. Add one in the Control Center (AI provider).",
                                            response=httpx.Response(401, request=httpx.Request("POST", GROQ_URL)), body=None)
    msgs, fns = to_openai(system, tools, messages)
    name = model[len(PREFIX):] if is_groq(model) else model
    payload = {"model": name, "messages": msgs, "max_completion_tokens": GROQ_MAX_TOKENS}
    if fns:
        payload.update(tools=fns, tool_choice="auto")
    req_url = GROQ_URL.rstrip("/") + "/chat/completions"
    # Throttle: wait for this model's allowance if it is used up (a short wait beats a failed request).
    est = len(json.dumps(payload)) // 4 + GROQ_MAX_TOKENS // 4
    wait = _wait_needed(name, est)
    if wait > 0:
        _sleep(min(wait, MAX_WAIT_S))
    with _gate(name):                                   # at most GROQ_PARALLEL calls in flight per model
        try:
            with httpx.Client(timeout=timeout, transport=_transport) as c:
                resp = c.post(req_url, json=payload, headers={"Authorization": f"Bearer {key}"})
        except httpx.TimeoutException as e:
            raise anthropic.APITimeoutError(request=httpx.Request("POST", req_url)) from e
        except httpx.HTTPError as e:
            raise anthropic.APIConnectionError(request=httpx.Request("POST", req_url)) from e
    _note_limits(name, resp.headers)
    if resp.status_code >= 400:
        _raise_for(resp, None)
    return from_openai(resp.json(), name)


def list_groq_models(key, timeout=10):
    """Models Groq currently offers for chat (for the Control Center's model picker)."""
    with httpx.Client(timeout=timeout, transport=_transport) as c:
        r = c.get(GROQ_URL.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
    r.raise_for_status()
    skip = ("whisper", "tts", "guard", "embed", "orpheus", "distil")
    return sorted(m["id"] for m in r.json().get("data", []) if m.get("active", True) and not any(s in m["id"].lower() for s in skip))
