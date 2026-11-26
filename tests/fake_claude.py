"""A scripted stand-in for the Claude API, for repeatable tests without an API key.

It replaces only `agents._call_model`. Everything else is the real code: the tool loop, the tools, the Validator,
the database, access rules and tracing. Each agent is recognised by its system prompt and answered from a script:
a list of turns, each a list of tool calls (name, input) or a final text. Token counts are fixed per turn so cost
arithmetic can be checked exactly. Responses are clearly marked model="fake-claude" so they can never be mistaken
for real measurements.
"""
import itertools
import threading

_ids = itertools.count(1)


class Block:
    def __init__(self, type, **kw):
        self.type = type
        self.__dict__.update(kw)

    def model_dump(self, mode="json", exclude_none=True):
        return {k: v for k, v in self.__dict__.items() if not (exclude_none and v is None)}


class Usage:
    def __init__(self, input_tokens, output_tokens, cache_read_input_tokens=0, cache_creation_input_tokens=0):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        self.cache_read_input_tokens, self.cache_creation_input_tokens = cache_read_input_tokens, cache_creation_input_tokens


class Response:
    def __init__(self, blocks, stop_reason, usage, model):
        self.content, self.stop_reason, self.usage, self.model = blocks, stop_reason, usage, model


def tool(name, **inp):
    return ("tool", name, inp)


def text(t):
    return ("text", t)


class FakeClaude:
    """scripts: {agent_name: [turn, turn, ...]}; a turn is a list of tool(...) or a single text(...).
    fail_first: {agent_name: exception} raised once on that agent's first call (to exercise retries)."""

    def __init__(self, agents_module, scripts, usage=(1000, 200, 0, 0), fail_first=None):
        self.agents, self.scripts, self.usage = agents_module, scripts, usage
        self.fail_first = dict(fail_first or {})
        self.calls = []
        self._lock = threading.Lock()
        self._systems = {
            agents_module.BUILDER_SYSTEM: "builder", agents_module.DATA_SYSTEM: "data",
            agents_module.DESIGN_SYSTEM: "design", agents_module.ACCESS_SYSTEM: "access",
            agents_module.REVIEW_SYSTEM: "review", agents_module.REMINDER_SYSTEM: "reminder",
            agents_module.SITE_SYSTEM: "site", agents_module.SITE_EXTRA_SYSTEM: "site",
        }

    def agent_of(self, system):
        if system in self._systems:
            return self._systems[system]
        return "insights" if system.startswith(self.agents.INSIGHTS_SYSTEM) else "unknown"

    def __call__(self, model, effort, system, tools, messages):
        agent = self.agent_of(system)
        with self._lock:
            exc = self.fail_first.pop(agent, None)
            self.calls.append(agent)
        if exc is not None:
            raise exc
        # which turn of this agent's script: count assistant turns since the last plain user message
        turn = 0
        for m in reversed(messages):
            if m["role"] == "user" and isinstance(m["content"], str):
                break
            if m["role"] == "assistant":
                turn += 1
        script = self.scripts.get(agent) or [[text("Done.")]]
        step = script[min(turn, len(script) - 1)]
        if isinstance(step, tuple) and step[0] == "text":
            step = [step]
        blocks = []
        for item in step:
            if item[0] == "text":
                blocks.append(Block("text", text=item[1]))
            else:
                blocks.append(Block("tool_use", id=f"toolu_{next(_ids)}", name=item[1], input=item[2]))
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return Response(blocks, stop, Usage(*self.usage), "fake-claude")
