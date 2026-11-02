"""A scripted stand-in for the Anthropic client, so workflows can be tested offline."""

from __future__ import annotations

import copy
import itertools
from types import SimpleNamespace

_ids = itertools.count(1)


def tool_call(name: str, **args) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=f"toolu_{next(_ids)}", name=name, input=args)


def text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def message(*blocks, stop_reason: str | None = None) -> SimpleNamespace:
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    usage = SimpleNamespace(input_tokens=100, output_tokens=50, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, usage=usage, stop_details=None)


class _Stream:
    def __init__(self, msg):
        self._msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if isinstance(self._msg, Exception):
            raise self._msg
        return self._msg


class FakeClient:
    """Returns scripted responses per agent, chosen by the agent name in the system prompt.

    ``script`` maps agent name -> list of responses (each a message() or an Exception),
    consumed in order on each request that agent makes.
    """

    def __init__(self, script: dict[str, list]):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        agent = next(name for name in self.script if f'"{name}" agent' in params["system"])
        self.calls.append({"agent": agent, **copy.deepcopy({k: v for k, v in params.items() if k != "messages"}),
                           "messages": copy.deepcopy(params["messages"])})
        if not self.script[agent]:
            raise AssertionError(f"no scripted response left for {agent}")
        return _Stream(self.script[agent].pop(0))

    def calls_for(self, agent: str) -> list[dict]:
        return [c for c in self.calls if c["agent"] == agent]
