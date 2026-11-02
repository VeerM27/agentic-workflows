"""Run agents through Claude Code (`claude -p`), using the operator's Claude subscription (Pro/Max).

Each agent is one Claude Code session working in its lane's workspace folder:

- its instructions (role, house style, skills) are appended to Claude Code's system prompt;
- its tools are limited to file tools plus two agentflow helper commands (screenshots, contrast);
  everything else is denied automatically, and file tools are confined to the workspace;
- it returns its hand-off as JSON validated against the same schema the API backend uses;
- feedback resumes the same session, so the agent keeps its context;
- API-key variables are removed from its environment, so usage always comes from the subscription.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from ..agent import AgentError, AgentResult, Usage, check_handoff, result_from_handoff, system_prompt_for
from ..config import AgentSpec
from ..tools import COMPLETE_TASK, schema_for, terminal_tool_for, validate_input
from ..workspace import Workspace

# Removed from the environment of every `claude` process: with any of these set, Claude Code
# would bill the API instead of using the subscription.
API_CREDENTIAL_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

MAX_HANDOFF_RETRIES = 2
DEFAULT_TIMEOUT = 60 * 60  # one agent turn; long builds can take a while

_LIMIT_PATTERN = re.compile(r"usage limit|limit reached|hit your limit|rate limit|out of (extra )?usage|resets? (at|in)", re.I)

HELPER_COMMANDS = """\
# Helper commands

You can run exactly these two shell commands (nothing else is allowed):

- `agentflow screenshot <file.html> --out .shots/<name>.png [--width 1280] [--scroll-y <px>] [--full-page]`
  renders a page in a headless browser; then open the PNG with the Read tool to see it. Use several
  `--scroll-y` values to inspect scroll-driven animations frame by frame, and `--width 375` for mobile.
- `agentflow contrast <foreground> <background> [<fg> <bg> ...]` prints exact WCAG contrast ratios.

If a helper reports it is unavailable, continue without it and say so in your hand-off.
"""


class UsageLimitReached(AgentError):
    """The subscription's usage limit was hit; the run should pause and resume after it resets."""


def claude_binary() -> str:
    return os.environ.get("AGENTFLOW_CLAUDE_BIN", "claude")


def subscription_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in API_CREDENTIAL_VARS}
    # Make the `agentflow` helper command resolvable from inside the session.
    bin_dir = str(Path(sys.executable).parent)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    return env


class ClaudeCodeRunner:
    """Same interface as agentflow.agent.AgentRunner, backed by Claude Code sessions."""

    def __init__(
        self,
        spec: AgentSpec,
        client: Any,  # unused; kept for interface compatibility
        workspace: Workspace,
        *,
        on_event: Callable[..., None] | None = None,
        use_fallbacks: bool = True,
        renderer: Any = None,
        model: str | None = None,
        effort: str | None = None,
        house_style: str = "",
        skills: list | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.spec = spec
        self.workspace = workspace
        self.on_event = on_event or (lambda *a, **k: None)
        self.model = model or spec.model or "opus"
        self.effort = effort or spec.effort or "high"
        self.skills = list(skills or [])
        self.terminal = terminal_tool_for(spec.role)
        self.schema = schema_for(self.terminal)
        self.timeout = timeout
        self.system = (
            system_prompt_for(spec, house_style, self.skills, skill_reader="open them with the Read tool under `{root}`")
            + "\n"
            + HELPER_COMMANDS
            + "\n# Finishing\n\nWhen your work is complete, end with your hand-off as the structured result "
            + f"(the `{self.terminal}` fields), listing file paths relative to the workspace root (e.g. `site/index.html`). "
            + "It is how the next agent and the human see what you did.\n"
        )
        self.session_id: str | None = None
        self.history: list[dict] = []  # prompts sent and results received, for transcripts
        self.usage = Usage()
        self.turns = 0

    # --- interface ------------------------------------------------------------------------

    def start(self, content: list[dict]) -> AgentResult:
        if self.session_id:
            raise AgentError("agent already started; use follow_up()")
        self.session_id = str(uuid.uuid4())
        return self._turn(blocks_to_prompt(content), new_session=True)

    def follow_up(self, text: str) -> AgentResult:
        if not self.session_id:
            raise AgentError("agent has not started yet")
        return self._turn(text, new_session=False)

    def restore(self, state: Any) -> None:
        if isinstance(state, dict) and state.get("session_id"):
            self.session_id = state["session_id"]
            self.history = list(state.get("history", []))
        else:
            raise AgentError("no Claude Code session to resume")

    def transcript(self) -> dict:
        return {"backend": "claude-code", "session_id": self.session_id, "history": self.history}

    def pop_usage(self) -> Usage:
        usage, self.usage = self.usage, Usage()
        return usage

    @property
    def started(self) -> bool:
        return bool(self.session_id)

    # --- one turn ---------------------------------------------------------------------------

    def _turn(self, prompt: str, *, new_session: bool) -> AgentResult:
        output = self._invoke(prompt, new_session=new_session)
        for _attempt in range(MAX_HANDOFF_RETRIES + 1):
            data, problem = self._handoff_from(output)
            if problem is None:
                return result_from_handoff(self.spec, self.terminal, data, self.turns, self.usage)
            if _attempt == MAX_HANDOFF_RETRIES:
                break
            self.on_event("tool_error", agent=self.spec.name, tool=self.terminal, error=problem)
            output = self._invoke(
                f"Your hand-off could not be accepted: {problem}\nFix this, then give the corrected hand-off.",
                new_session=False,
            )
        raise AgentError(f"{self.spec.name}: could not produce a valid hand-off ({problem})")

    def _handoff_from(self, output: dict) -> tuple[dict | None, str | None]:
        data = output.get("structured_output")
        if data is None:
            data = _json_from_text(output.get("result", ""))
        if not isinstance(data, dict):
            return None, f"no structured hand-off was returned; return the `{self.terminal}` fields as JSON"
        if isinstance(data.get("files"), list):
            data = {**data, "files": [self._relative(f) for f in data["files"]]}
        error = validate_input(self.schema, data, "hand-off")
        if error:
            return None, error
        problem = check_handoff(self.terminal, data, self.workspace)
        return (data, None) if problem is None else (None, problem)

    def _relative(self, path: Any) -> Any:
        """Claude Code often reports absolute paths; hand-offs use workspace-relative ones."""
        if not isinstance(path, str) or not os.path.isabs(path):
            return path
        try:
            return Path(path).resolve().relative_to(self.workspace.root).as_posix()
        except ValueError:
            return path  # outside the workspace: left as-is so the check reports it

    def command(self, prompt: str, *, new_session: bool) -> list[str]:
        writer = self.spec.role != "reviewer"
        file_tools = ["Read", "Glob", "Grep"] + (["Write", "Edit"] if writer else [])
        allowed = file_tools + ["Bash(agentflow screenshot *)", "Bash(agentflow contrast *)"]
        cmd = [
            claude_binary(), "-p", prompt,
            "--output-format", "json",
            "--json-schema", json.dumps(self.schema),
            "--model", self.model,
            "--effort", self.effort,
            "--append-system-prompt", self.system,
            "--restricted",
            "--tools", ",".join(file_tools + ["Bash"]),
            "--allowedTools", ",".join(allowed),
            "--permission-mode", "acceptEdits",
            "--permission-prompts", "none",
        ]
        cmd += ["--session-id", self.session_id] if new_session else ["--resume", self.session_id]
        for skill in self.skills:
            cmd += ["--add-dir", str(skill.root.resolve())]
        return cmd

    def _invoke(self, prompt: str, *, new_session: bool) -> dict:
        if shutil.which(claude_binary()) is None and not Path(claude_binary()).is_file():
            raise AgentError("Claude Code (`claude`) was not found; install it and log in with `claude auth login`")
        self.turns += 1
        self.history.append({"role": "user", "content": prompt})
        self.on_event("tool", agent=self.spec.name, tool="working in Claude Code",
                      args={"path": "(new session)" if new_session else "(same session)"})
        try:
            proc = subprocess.run(
                self.command(prompt, new_session=new_session),
                cwd=self.workspace.root,
                env=subscription_env(),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise AgentError(f"{self.spec.name}: Claude Code did not finish within {self.timeout}s") from exc

        output = _parse_output(proc.stdout)
        text = " ".join(str(x) for x in (output.get("result", ""), proc.stderr, output.get("subtype", "")))
        self.history.append({"role": "assistant", "content": output.get("result", ""), "structured": output.get("structured_output")})
        self.usage.add(_UsageView(output.get("usage") or {}))

        if output.get("is_error") or proc.returncode != 0 or not output:
            if _LIMIT_PATTERN.search(text):
                raise UsageLimitReached(f"{self.spec.name}: your Claude usage limit was reached ({_one_line(text)})")
            raise AgentError(f"{self.spec.name}: Claude Code failed ({_one_line(text) or f'exit {proc.returncode}'})")
        return output


class _UsageView:
    def __init__(self, data: dict):
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            setattr(self, key, int(data.get(key) or 0))


def _parse_output(stdout: str) -> dict:
    stdout = (stdout or "").strip()
    if not stdout:
        return {}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        # Take the last JSON object line (some versions print notices first).
        for line in reversed(stdout.splitlines()):
            try:
                data = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        else:
            return {"result": stdout, "is_error": True}
    if isinstance(data, list):  # stream-style array: use the final result event
        data = next((e for e in reversed(data) if isinstance(e, dict) and e.get("type") == "result"), {})
    return data if isinstance(data, dict) else {}


def _json_from_text(text: str) -> Any:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _one_line(text: str, limit: int = 200) -> str:
    text = " ".join(str(text).split())
    return text[:limit]


def blocks_to_prompt(content: list[dict]) -> str:
    """Flatten content blocks into a text prompt; images become instructions to open the file."""
    parts: list[str] = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block["text"])
        elif block.get("type") == "image":
            src = block.get("source", {})
            if src.get("type") == "workspace":
                parts.append(f"(Open `{src['path']}` with the Read tool to see this image.)")
            elif src.get("type") == "url":
                parts.append(f"(Image at {src['url']} could not be downloaded; work from the description.)")
    return "\n\n".join(parts)


def is_claude_code_runner(runner: Any) -> bool:
    return isinstance(runner, ClaudeCodeRunner)


__all__ = ["ClaudeCodeRunner", "UsageLimitReached", "claude_binary", "subscription_env", "blocks_to_prompt", "COMPLETE_TASK"]
