"""Human checkpoints: how the operator is shown a finished step and decides what happens next.

At a checkpoint the operator can
  - approve the step (choosing one variant if the step produced several),
  - request changes with free-text feedback (sent to the agent that did the work, which keeps
    its context; the reviewer loop then runs again),
  - stop the run (it can be resumed later with `agentflow resume`).

Approvers decide how the question is asked:
  TerminalApprover  asks in the terminal and waits
  PauseApprover     saves the run and exits; answer later with `agentflow resume <run> ...`
  AutoApprover      approves automatically (CI, or steps where you opted out of checkpoints)
"""

from __future__ import annotations

import html
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


@dataclass
class Decision:
    action: str  # approve | revise | stop | pause
    lane: str | None = None  # variant key ("v2") or "main"
    feedback: str = ""


@dataclass
class LaneView:
    key: str
    direction: str | None
    status: str
    summary: str
    files: list[str]
    verdicts: list[str]
    workspace: Path
    error: str | None = None

    @property
    def approved(self) -> bool:
        return bool(self.verdicts) and self.verdicts[-1] == "approve"


@dataclass
class CheckpointView:
    step_id: str
    agent: str
    lanes: list[LaneView]
    gallery: Path | None
    run_dir: Path

    @property
    def has_variants(self) -> bool:
        return len(self.lanes) > 1


class Approver(Protocol):
    def confirm_start(self, plan: str) -> bool: ...

    def decide(self, view: CheckpointView) -> Decision: ...


def default_lane(view: CheckpointView) -> str | None:
    """The lane an automatic approval picks: the first approved one, else the first that finished."""
    usable = [lane for lane in view.lanes if lane.status != "failed"]
    for lane in usable:
        if lane.approved:
            return lane.key
    return usable[0].key if usable else None


class AutoApprover:
    def confirm_start(self, plan: str) -> bool:
        return True

    def decide(self, view: CheckpointView) -> Decision:
        lane = default_lane(view)
        return Decision("approve", lane) if lane else Decision("stop")


class PauseApprover:
    def confirm_start(self, plan: str) -> bool:
        return True

    def decide(self, view: CheckpointView) -> Decision:
        return Decision("pause")


class ScriptedApprover:
    """Uses the given decisions first (e.g. from `agentflow resume --approve`), then defers to `then`."""

    def __init__(self, decisions: list[Decision], then: Approver):
        self.decisions = list(decisions)
        self.then = then

    def confirm_start(self, plan: str) -> bool:
        return self.then.confirm_start(plan)

    def decide(self, view: CheckpointView) -> Decision:
        if self.decisions:
            return self.decisions.pop(0)
        return self.then.decide(view)


class TerminalApprover:
    def __init__(self, input_fn: Callable[[str], str] = input, print_fn: Callable[[str], None] = print):
        self.input = input_fn
        self.print = print_fn

    def confirm_start(self, plan: str) -> bool:
        self.print(plan)
        answer = self.input("\nStart this run? [Y/n] ").strip().lower()
        return answer in ("", "y", "yes")

    def decide(self, view: CheckpointView) -> Decision:
        self.print(render_view(view))
        keys = [lane.key for lane in view.lanes if lane.status != "failed"]
        help_text = (
            "  a [variant]            approve" + (" and continue with that variant" if view.has_variants else "") + "\n"
            "  r [variant] <feedback> request changes (the agent revises, the reviewer re-checks)\n"
            "  s                      stop here (resume later with `agentflow resume`)"
        )
        self.print(help_text)
        while True:
            raw = self.input("\n> ").strip()
            if not raw:
                continue
            cmd, _, rest = raw.partition(" ")
            cmd = cmd.lower()
            lane, rest = _take_lane(rest, keys)
            if cmd in ("a", "approve"):
                if lane is None and len(keys) > 1:
                    self.print(f"Which variant? e.g. `a {keys[0]}`")
                    continue
                return Decision("approve", lane or (keys[0] if keys else None))
            if cmd in ("r", "revise"):
                if lane is None and len(keys) > 1:
                    self.print(f"Which variant should change? e.g. `r {keys[0]} make the hero larger`")
                    continue
                feedback = rest.strip() or self.input("Feedback: ").strip()
                if not feedback:
                    self.print("Feedback can't be empty.")
                    continue
                return Decision("revise", lane or keys[0], feedback)
            if cmd in ("s", "stop", "q", "quit"):
                return Decision("stop")
            self.print(help_text)


def _take_lane(text: str, keys: list[str]) -> tuple[str | None, str]:
    first, _, rest = text.strip().partition(" ")
    if not first:
        return None, ""
    candidate = first.lower()
    if candidate.isdigit():
        candidate = f"v{candidate}"
    if candidate in keys:
        return candidate, rest
    return None, text


def render_view(view: CheckpointView) -> str:
    bar = "═" * 72
    lines = [f"\n{bar}", f"  CHECKPOINT · step '{view.step_id}' ({view.agent})", bar]
    for lane in view.lanes:
        label = f"[{lane.key}]" if view.has_variants else ""
        direction = f" {lane.direction}" if lane.direction else ""
        lines.append(f"\n{label}{direction}".rstrip() or "")
        if lane.status == "failed":
            lines.append(f"  ✖ failed: {lane.error}")
            continue
        lines.append(f"  {lane.summary.strip()}")
        if lane.files:
            shown = ", ".join(lane.files[:10]) + (" …" if len(lane.files) > 10 else "")
            lines.append(f"  files: {shown}")
        if lane.verdicts:
            lines.append(f"  review: {' → '.join(lane.verdicts)}")
        lines.append(f"  workspace: {lane.workspace}")
    if view.gallery:
        lines.append(f"\nOpen to look and compare: {view.gallery}")
    return "\n".join(lines)


def build_gallery(view: CheckpointView, out: Path) -> Path:
    """A static page showing each lane's HTML output side by side, for reviewing a checkpoint."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    for lane in view.lanes:
        html_files = [f for f in lane.files if f.endswith((".html", ".svg"))]
        title = html.escape(f"{lane.key} — {lane.direction}" if lane.direction else lane.key)
        if lane.status == "failed":
            body = f"<p class='err'>Failed: {html.escape(lane.error or '')}</p>"
        else:
            links = "".join(
                f"<li><a href='{html.escape(_rel(lane.workspace / f, out))}' target='_blank'>{html.escape(f)}</a></li>"
                for f in html_files
            )
            preview = (
                f"<iframe src='{html.escape(_rel(lane.workspace / html_files[0], out))}' loading='lazy'></iframe>"
                if html_files
                else "<p class='muted'>No HTML output to preview.</p>"
            )
            verdicts = " → ".join(lane.verdicts) or "not reviewed"
            body = (
                f"{preview}<p>{html.escape(lane.summary)}</p>"
                f"<p class='muted'>Review: {html.escape(verdicts)}</p><ul>{links}</ul>"
            )
        cards.append(f"<section><h2>{title}</h2>{body}</section>")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Checkpoint: {html.escape(view.step_id)}</title>
<style>
  :root {{ color-scheme: light dark; --bg:#f6f6f4; --card:#fff; --text:#1b1b1b; --muted:#666; --line:#ddd; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141414; --card:#1e1e1e; --text:#eee; --muted:#aaa; --line:#333; }} }}
  body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--text); font:15px/1.5 system-ui, sans-serif; }}
  h1 {{ font-size:20px; margin:0 0 16px; }}
  .grid {{ display:grid; gap:16px; grid-template-columns:repeat(auto-fit, minmax(min(100%, 420px), 1fr)); }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
  h2 {{ font-size:16px; margin:0 0 12px; }}
  iframe {{ width:100%; height:560px; border:1px solid var(--line); border-radius:8px; background:#fff; }}
  .muted {{ color:var(--muted); }} .err {{ color:#c62828; }}
</style></head>
<body><h1>Step “{html.escape(view.step_id)}” · {html.escape(view.agent)}</h1><div class="grid">{''.join(cards)}</div></body></html>
"""
    out.write_text(page, encoding="utf-8")
    return out


def _rel(target: Path, page: Path) -> str:
    return Path(os.path.relpath(target, page.parent)).as_posix()
