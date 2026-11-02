"""Running a single agent: the tool-use loop against the Claude API."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import AgentSpec
from .tools import (
    COMPLETE_TASK,
    SKILL_TOOL,
    SUBMIT_REVIEW,
    ToolExecutor,
    invalid_json_result,
    schema_for,
    terminal_tool_for,
    tool_params,
    validate_input,
)
from .workspace import Workspace

# Models that accept server-side refusal fallbacks with `fallbacks: "default"`.
# Claude Haiku models have no server-side fallback, so they are left out.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

MAX_OUTPUT_TOKENS = 128_000
MAX_NUDGES = 2
MAX_STREAM_RETRIES = 2

PIPELINE_PREAMBLE = """\
You are the "{name}" agent in a multi-agent pipeline that builds software products. \
Other specialised agents work before and after you. You communicate with them only through \
files in the shared workspace and through the hand-off you submit when you finish.

The file tools operate on that shared workspace; paths are relative to its root. Files written \
by earlier agents are already there, so read what you need instead of guessing. Keep your work \
inside the scope of your role.
"""

PRODUCER_RULES = """\
When your work is complete, call `complete_task` exactly once with a concise summary, the list \
of files you created or changed, and notes for the next agent. Your turn ends when you call it. \
If you receive review feedback afterwards, address it in the files, then call `complete_task` again.
"""

REVIEWER_RULES = """\
You review work; you do not fix it yourself. Inspect the actual files in the workspace rather than \
trusting the summary. When your review is complete, call `submit_review` exactly once. Approve work \
that meets the bar: block only on issues that matter, and make every issue specific and actionable \
(where it is, what is wrong, what to change).
"""


SKILLS_PREAMBLE = """\
# Skills

You have been equipped with the skills below. Follow them where they apply to your task. They were \
written for interactive use: where a skill says to ask the user or wait for their choice, make the \
best decision yourself, state it in your hand-off notes, and continue. A human reviews your work at \
the end of this step and can send it back.
"""


class AgentError(Exception):
    """The agent could not finish its task."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    requests: int = 0

    def add(self, usage: Any) -> None:
        if usage is None:
            return
        self.requests += 1
        for name in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            setattr(self, name, getattr(self, name) + (getattr(usage, name, 0) or 0))

    def merge(self, other: "Usage") -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))


@dataclass
class AgentResult:
    agent: str
    role: str
    summary: str = ""
    files: list[str] = field(default_factory=list)
    notes: str = ""
    verdict: str | None = None
    issues: list[dict] = field(default_factory=list)
    turns: int = 0
    usage: Usage = field(default_factory=Usage)


def system_prompt_for(spec: AgentSpec, house_style: str = "", skills: list | None = None) -> str:
    rules = REVIEWER_RULES if spec.role == "reviewer" else PRODUCER_RULES
    parts = [PIPELINE_PREAMBLE.format(name=spec.name), rules, f"# Your role\n\n{spec.system_prompt}\n"]
    if house_style:
        parts.append(
            "# House style\n\nThe operator of this pipeline applies these preferences to all work. "
            f"Follow them unless your inputs say otherwise.\n\n{house_style}\n"
        )
    if skills:
        parts.append(SKILLS_PREAMBLE + "\n" + "\n\n".join(s.prompt_section() for s in skills) + "\n")
    return "\n".join(parts)


def _block_to_dict(block: Any) -> Any:
    if hasattr(block, "to_dict"):
        return block.to_dict()
    if hasattr(block, "model_dump"):
        return block.model_dump()
    return block


class AgentRunner:
    """Runs one agent's conversation. Keeps history so it can be resumed with feedback."""

    def __init__(
        self,
        spec: AgentSpec,
        client: Any,
        workspace: Workspace,
        *,
        on_event: Callable[..., None] | None = None,
        use_fallbacks: bool = True,
        renderer: Callable[..., bytes] | None = None,
        model: str | None = None,
        effort: str | None = None,
        house_style: str = "",
        skills: list | None = None,
    ):
        self.spec = spec
        self.client = client
        self.workspace = workspace
        self.on_event = on_event or (lambda *a, **k: None)
        self.use_fallbacks = use_fallbacks
        self.model = model or spec.model or "claude-opus-5-5"
        self.effort = effort or spec.effort or "high"
        self.skills = list(skills or [])
        self.terminal = terminal_tool_for(spec.role)
        tool_names = list(spec.tools) + ([SKILL_TOOL] if self.skills else [])
        self.tools = tool_params(tool_names, self.terminal)
        self.executor = ToolExecutor(workspace, renderer=renderer, skills={s.name: s for s in self.skills})
        self.system = system_prompt_for(spec, house_style, self.skills)
        self._tool_names = {t["name"] for t in self.tools}
        self.messages: list[dict] = []
        self.usage = Usage()
        self.turns = 0
        self._max_tokens = spec.max_tokens

    # --- public API --------------------------------------------------------

    def start(self, content: list[dict]) -> AgentResult:
        if self.messages:
            raise AgentError("agent already started; use follow_up()")
        self.messages.append({"role": "user", "content": content})
        return self._loop()

    def follow_up(self, text: str) -> AgentResult:
        """Continue the same conversation with new instructions (e.g. review feedback)."""
        if not self.messages:
            raise AgentError("agent has not started yet")
        self.messages.append({"role": "user", "content": [{"type": "text", "text": text}]})
        return self._loop()

    def restore(self, messages: list[dict]) -> None:
        """Load a saved conversation (from transcript()) so follow_up() can continue it."""
        if self.messages:
            raise AgentError("agent already has a conversation")
        self.messages = list(messages)

    def pop_usage(self) -> Usage:
        """Return usage since the last call and reset the counter."""
        usage, self.usage = self.usage, Usage()
        return usage

    def transcript(self) -> list[dict]:
        out = []
        for msg in self.messages:
            content = msg["content"]
            if isinstance(content, list):
                content = [_block_to_dict(b) for b in content]
            out.append({"role": msg["role"], "content": content})
        return out

    # --- the loop -------------------------------------------------------------

    def _loop(self) -> AgentResult:
        nudges = 0
        turns_this_call = 0
        while True:
            if turns_this_call >= self.spec.max_turns:
                raise AgentError(f"{self.spec.name}: reached max_turns ({self.spec.max_turns}) without finishing")
            turns_this_call += 1
            self.turns += 1

            response = self._create()
            self.usage.add(getattr(response, "usage", None))
            stop = response.stop_reason
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if stop == "refusal":
                details = getattr(response, "stop_details", None)
                category = getattr(details, "category", None) if details else None
                raise AgentError(f"{self.spec.name}: the model declined the request (category: {category})")

            if stop == "max_tokens" and tool_uses:
                # A tool input cut off at max_tokens can still parse as a valid-looking
                # partial object. Never run it: retry the same request with more room.
                if self._max_tokens >= MAX_OUTPUT_TOKENS:
                    raise AgentError(f"{self.spec.name}: output exceeded {MAX_OUTPUT_TOKENS} tokens")
                self._max_tokens = min(MAX_OUTPUT_TOKENS, self._max_tokens * 2)
                self.on_event("retry", agent=self.spec.name, reason="max_tokens", max_tokens=self._max_tokens)
                continue

            self.messages.append({"role": "assistant", "content": response.content})

            if stop == "pause_turn":
                continue

            if not tool_uses:
                nudges += 1
                if nudges > MAX_NUDGES:
                    raise AgentError(f"{self.spec.name}: stopped without calling `{self.terminal}`")
                self.messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Continue your task. When it is complete, call `{self.terminal}`.",
                            }
                        ],
                    }
                )
                continue

            results, finished = self._run_tools(tool_uses)
            # All results go back in a single user message.
            self.messages.append({"role": "user", "content": results})
            if finished is not None:
                return self._result(finished)

    def _create(self):
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "system": self.system,
            "messages": self.messages,
            "tools": self.tools,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
            # Automatic prompt caching: caches the growing conversation prefix so
            # each loop iteration only pays full price for new content.
            "cache_control": {"type": "ephemeral"},
        }
        if self.use_fallbacks and self.model in FALLBACK_MODELS:
            # If a safety classifier declines, the API re-runs the request on
            # Anthropic's recommended fallback model instead of returning a refusal.
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"

        for attempt in range(MAX_STREAM_RETRIES + 1):
            try:
                with self.client.beta.messages.stream(**params) as stream:
                    return stream.get_final_message()
            except ValueError as exc:
                # With eager input streaming the SDK raises ValueError for tool
                # input JSON it cannot parse at all. No tool_use id to answer, so
                # re-issue the request. (Typed API errors propagate unchanged.)
                if attempt == MAX_STREAM_RETRIES:
                    raise AgentError(f"{self.spec.name}: model produced unparseable tool input: {exc}") from exc
                self.on_event("retry", agent=self.spec.name, reason="invalid tool JSON")

    def _run_tools(self, tool_uses: list[Any]) -> tuple[list[dict], dict | None]:
        results: list[dict] = []
        finished: dict | None = None
        for block in tool_uses:
            args = block.input if isinstance(block.input, dict) else None
            try:
                schema = schema_for(block.name)
            except KeyError:
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": f"Unknown tool '{block.name}'"}
                )
                continue
            error = "input must be a JSON object" if args is None else validate_input(schema, args)
            if error:
                results.append(invalid_json_result(block.id, block.input, error))
                self.on_event("tool_error", agent=self.spec.name, tool=block.name, error=error)
                continue

            if block.name not in self._tool_names:
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": f"You do not have the tool '{block.name}'."}
                )
                continue

            if block.name in (COMPLETE_TASK, SUBMIT_REVIEW):
                if block.name != self.terminal:
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": f"Use `{self.terminal}` instead."}
                    )
                    continue
                problem = self._check_handoff(args)
                if problem:
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": problem})
                    self.on_event("tool_error", agent=self.spec.name, tool=block.name, error=problem)
                    continue
                finished = args
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": "Recorded."})
                continue

            self.on_event("tool", agent=self.spec.name, tool=block.name, args=_short_args(args))
            outcome = self.executor.run(block.name, args)
            result = {"type": "tool_result", "tool_use_id": block.id, "content": outcome.content}
            if outcome.is_error:
                result["is_error"] = True
                self.on_event("tool_error", agent=self.spec.name, tool=block.name, error=str(outcome.content))
            results.append(result)
        return results, finished

    def _check_handoff(self, args: dict) -> str | None:
        if self.terminal == COMPLETE_TASK:
            missing = [f for f in args["files"] if not self.workspace.exists(f)]
            if missing:
                return f"These files are not in the workspace: {missing}. Write them first or remove them from `files`."
        else:
            if args["verdict"] == "revise" and not args["issues"]:
                return "A 'revise' verdict needs at least one issue describing what to fix."
        return None

    def _result(self, data: dict) -> AgentResult:
        result = AgentResult(agent=self.spec.name, role=self.spec.role, turns=self.turns, usage=self.usage)
        if self.terminal == COMPLETE_TASK:
            result.summary = data["summary"]
            result.files = list(dict.fromkeys(data["files"]))
            result.notes = data["notes_for_next_agent"]
        else:
            result.summary = data["summary"]
            result.verdict = data["verdict"]
            result.issues = data["issues"]
        return result


def _short_args(args: dict) -> dict:
    """Arguments for logging, with long strings abbreviated."""
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 80:
            out[k] = f"<{len(v)} chars>"
        else:
            out[k] = v
    return json.loads(json.dumps(out, default=str))
