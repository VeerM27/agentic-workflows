"""Running a workflow: steps in order, hand-offs between agents, and review loops."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agent import AgentResult, AgentRunner, Usage
from .config import (
    REF_PATTERN,
    REVIEW_WORK_ARG,
    AgentSpec,
    ConfigError,
    StepSpec,
    WorkflowSpec,
    load_agents,
    validate_workflow,
)
from .inputs import InputError, build_task_content, coerce_workflow_inputs, stage_inputs
from .workspace import Workspace


class WorkflowError(Exception):
    """A workflow could not be completed."""


@dataclass
class StepRecord:
    id: str
    agent: str
    status: str = "pending"  # pending | running | done | rejected | failed
    rounds: int = 0
    result: AgentResult | None = None
    reviews: list[AgentResult] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    seconds: float = 0.0
    error: str | None = None

    @property
    def last_review(self) -> AgentResult | None:
        return self.reviews[-1] if self.reviews else None

    def field_value(self, name: str | None) -> Any:
        """Value for ${steps.<id>.<name>} references."""
        r = self.result
        if name in (None, "handoff"):
            return self.handoff()
        if name == "summary":
            return r.summary if r else ""
        if name == "files":
            return list(r.files) if r else []
        if name == "notes":
            return r.notes if r else ""
        source = self.last_review if (r and r.role == "producer") else r
        if name == "verdict":
            return source.verdict if source else None
        if name == "issues":
            return format_issues(source.issues) if source else ""
        raise KeyError(name)

    def handoff(self) -> str:
        r = self.result
        if r is None:
            return ""
        lines = [f"### Output of step `{self.id}` (agent: {self.agent})", "", r.summary.strip()]
        if r.role == "reviewer":
            lines += ["", f"Verdict: **{r.verdict}**"]
            if r.issues:
                lines += ["", format_issues(r.issues)]
            return "\n".join(lines)
        if r.files:
            lines += ["", "Files:"] + [f"- `{f}`" for f in r.files]
        if r.notes.strip():
            lines += ["", "Notes for the next agent:", r.notes.strip()]
        review = self.last_review
        if review:
            outcome = "approved" if review.verdict == "approve" else "NOT approved"
            lines += ["", f"Review by {review.agent}: {outcome} after {len(self.reviews)} round(s)."]
            if review.verdict != "approve" and review.issues:
                lines += ["Unresolved issues:", format_issues(review.issues)]
        return "\n".join(lines)


def format_issues(issues: list[dict]) -> str:
    if not issues:
        return "(no issues)"
    return "\n".join(
        f"{i}. [{it['severity']}] {it['location']}: {it['problem']}\n   Fix: {it['fix']}"
        for i, it in enumerate(issues, 1)
    )


@dataclass
class RunResult:
    run_dir: Path
    workspace: Path
    steps: list[StepRecord]
    usage: Usage
    status: str


def resolve_refs(value: Any, inputs: dict[str, Any], steps: dict[str, StepRecord]) -> Any:
    """Substitute ${inputs.x} / ${steps.y.field} references.

    A string that is exactly one reference keeps the referenced value's type
    (e.g. a list of image paths); references inside longer strings are
    interpolated as text. Missing optional inputs resolve to None.
    """

    def lookup(scope: str, name: str, fld: str | None) -> Any:
        if scope == "inputs":
            return inputs.get(name)
        return steps[name].field_value(fld)

    if isinstance(value, str):
        m = REF_PATTERN.fullmatch(value.strip())
        if m:
            return lookup(*m.groups())

        def sub(match: re.Match) -> str:
            v = lookup(*match.groups())
            if v is None:
                return ""
            if isinstance(v, list):
                return ", ".join(str(x) for x in v)
            return str(v)

        return REF_PATTERN.sub(sub, value)
    if isinstance(value, dict):
        return {k: resolve_refs(v, inputs, steps) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_refs(v, inputs, steps) for v in value]
    return value


def _clean_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in args.items() if v not in (None, "", [])}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "run"


class Orchestrator:
    def __init__(
        self,
        workflow: WorkflowSpec,
        agents: dict[str, AgentSpec] | None = None,
        *,
        client: Any = None,
        runs_dir: str | Path = "runs",
        use_fallbacks: bool = True,
        printer: Callable[[str], None] = print,
        renderer: Callable[..., bytes] | None = None,
    ):
        self.workflow = workflow
        self.agents = agents if agents is not None else load_agents(workflow.agents_dir)
        problems = validate_workflow(workflow, self.agents)
        if problems:
            raise ConfigError("workflow is invalid:\n  - " + "\n  - ".join(problems))
        self._client = client
        self.runs_dir = Path(runs_dir)
        self.use_fallbacks = use_fallbacks
        self.print = printer
        self.renderer = renderer

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    # --- running ---------------------------------------------------------------

    def run(self, inputs: dict[str, Any], *, base_dir: str | Path = ".", run_id: str | None = None) -> RunResult:
        resolved_inputs = coerce_workflow_inputs(self.workflow.inputs, inputs, Path(base_dir))

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.run_dir = self.runs_dir / (run_id or f"{stamp}-{_slug(self.workflow.name)}")
        self.run_dir.mkdir(parents=True, exist_ok=False)
        (self.run_dir / "transcripts").mkdir()
        self.workspace = Workspace(self.run_dir / "workspace")
        self.staged = stage_inputs(resolved_inputs, self.workflow.inputs, self.workspace)
        self.inputs = resolved_inputs
        self.records: dict[str, StepRecord] = {s.id: StepRecord(id=s.id, agent=s.agent) for s in self.workflow.steps}
        self._events = (self.run_dir / "events.jsonl").open("a", encoding="utf-8")

        self.print(f"Run directory: {self.run_dir}")
        self._event("run_started", workflow=self.workflow.name, inputs=_printable(resolved_inputs))
        status = "done"
        try:
            for step in self.workflow.steps:
                self._run_step(step)
                if self.records[step.id].status == "failed":
                    status = "failed"
                    break
        except Exception as exc:
            status = "failed"
            self._event("run_failed", error=str(exc))
            raise
        finally:
            self._save_state(status)
            self._event("run_finished", status=status)
            self._events.close()

        total = Usage()
        for rec in self.records.values():
            total.merge(rec.usage)
        self.print(
            f"\nFinished ({status}). Workspace: {self.workspace.root}\n"
            f"Tokens: {total.input_tokens:,} in (+{total.cache_read_input_tokens:,} cached reads, "
            f"{total.cache_creation_input_tokens:,} cache writes), {total.output_tokens:,} out "
            f"over {total.requests} requests"
        )
        return RunResult(self.run_dir, self.workspace.root, list(self.records.values()), total, status)

    def _run_step(self, step: StepSpec) -> None:
        rec = self.records[step.id]
        spec = self.agents[step.agent]
        rec.status = "running"
        started = time.monotonic()
        self.print(f"\n▶ Step '{step.id}' — {spec.name} ({spec.role})")
        self._event("step_started", step=step.id, agent=spec.name)

        runner: AgentRunner | None = None
        try:
            args = _clean_args(resolve_refs(step.inputs, self.inputs, self.records))
            self._check_required(spec, args, step.id)
            runner = self._runner(spec)
            content = build_task_content(
                spec.inputs,
                args,
                staged=self.staged,
                instructions=step.instructions,
                closing=f"Carry out your role on these inputs. When you are done, call `{runner.terminal}`.",
            )
            rec.rounds = 1
            rec.result = runner.start(content)
            self._report_result(rec.result)
            self._save_transcript(step.id, spec.name, 1, runner)

            if step.review:
                self._review_loop(step, rec, runner)
            elif rec.result.role == "reviewer" and rec.result.verdict != "approve":
                self.print(f"  ⚠ {spec.name} did not approve; continuing")
            if rec.status == "running":
                rec.status = "done"
        except Exception as exc:
            rec.status = "failed"
            rec.error = str(exc)
            self._event("step_failed", step=step.id, error=str(exc))
            self.print(f"  ✖ Step '{step.id}' failed: {exc}")
            raise WorkflowError(f"step '{step.id}' failed: {exc}") from exc
        finally:
            if runner is not None:
                rec.usage.merge(runner.usage)
            rec.seconds = round(time.monotonic() - started, 1)
            self._save_state("running")
        self._event("step_finished", step=step.id, status=rec.status)

    def _review_loop(self, step: StepSpec, rec: StepRecord, producer: AgentRunner) -> None:
        review = step.review
        reviewer_spec = self.agents[review.agent]
        for round_no in range(1, review.max_rounds + 1):
            self.print(f"  ↳ Review round {round_no}/{review.max_rounds} — {reviewer_spec.name}")
            args = _clean_args(resolve_refs(review.inputs, self.inputs, self.records))
            args[REVIEW_WORK_ARG] = rec.handoff()
            self._check_required(reviewer_spec, args, f"{step.id} review")
            reviewer = self._runner(reviewer_spec)
            content = build_task_content(
                reviewer_spec.inputs,
                args,
                staged=self.staged,
                closing="Review the work above against your criteria, then call `submit_review`.",
            )
            verdict = reviewer.start(content)
            rec.reviews.append(verdict)
            rec.usage.merge(reviewer.usage)
            self._report_result(verdict)
            self._save_transcript(step.id, reviewer_spec.name, round_no, reviewer)

            if verdict.verdict == "approve":
                return
            if round_no == review.max_rounds:
                break

            rec.rounds += 1
            self.print(f"  ↻ Revising ({producer.spec.name}), round {rec.rounds}")
            feedback = (
                f"The {reviewer_spec.name} agent reviewed your work and asked for changes.\n\n"
                f"Reviewer summary: {verdict.summary}\n\nIssues to address:\n{format_issues(verdict.issues)}\n\n"
                "Fix these issues in the workspace files. If you disagree with an issue, explain why in your "
                "notes instead of changing it. Then call `complete_task` again with an updated summary and "
                "the full list of files you have created or changed."
            )
            rec.result = producer.follow_up(feedback)
            self._report_result(rec.result)
            self._save_transcript(step.id, producer.spec.name, rec.rounds, producer)

        msg = f"review not approved after {review.max_rounds} round(s)"
        self._event("review_rejected", step=step.id, rounds=review.max_rounds)
        if review.on_reject == "fail":
            rec.status = "failed"
            raise WorkflowError(msg)
        rec.status = "rejected"
        self.print(f"  ⚠ {msg}; continuing (set on_reject: fail to stop instead)")

    # --- helpers ----------------------------------------------------------------

    def _runner(self, spec: AgentSpec) -> AgentRunner:
        return AgentRunner(
            spec,
            self.client,
            self.workspace,
            on_event=self._agent_event,
            use_fallbacks=self.use_fallbacks,
            renderer=self.renderer,
        )

    def _check_required(self, spec: AgentSpec, args: dict[str, Any], where: str) -> None:
        for name, inp in spec.inputs.items():
            if name not in args and inp.default is not None:
                args[name] = inp.default
            if inp.required and name not in args:
                raise InputError(f"{where}: required input '{name}' of agent '{spec.name}' resolved to nothing")

    def _report_result(self, r: AgentResult) -> None:
        if r.role == "reviewer":
            icon = "✔" if r.verdict == "approve" else "✎"
            self.print(f"  {icon} {r.agent}: {r.verdict} ({len(r.issues)} issue(s)) — {_one_line(r.summary)}")
        else:
            self.print(f"  ✔ {r.agent}: {_one_line(r.summary)}")
            if r.files:
                self.print(f"    files: {', '.join(r.files[:8])}{' …' if len(r.files) > 8 else ''}")
        self._event("agent_result", **asdict(r))

    def _agent_event(self, kind: str, **data: Any) -> None:
        if kind == "tool":
            path = data["args"].get("path", "")
            self.print(f"    · {data['tool']} {path}".rstrip())
        elif kind == "tool_error":
            self.print(f"    ! {data['tool']}: {_one_line(data['error'], 100)}")
        elif kind == "retry":
            self.print(f"    ↺ retrying ({data['reason']})")
        self._event(kind, **data)

    def _event(self, kind: str, **data: Any) -> None:
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": kind, **data}
        self._events.write(json.dumps(record, default=str) + "\n")
        self._events.flush()

    def _save_transcript(self, step_id: str, agent: str, round_no: int, runner: AgentRunner) -> None:
        path = self.run_dir / "transcripts" / f"{step_id}.{agent}.round{round_no}.json"
        data = {"system": runner.system, "messages": runner.transcript()}
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _save_state(self, status: str) -> None:
        state = {
            "workflow": self.workflow.name,
            "status": status,
            "inputs": _printable(self.inputs),
            "workspace": str(self.workspace.root),
            "steps": [
                {
                    "id": rec.id,
                    "agent": rec.agent,
                    "status": rec.status,
                    "rounds": rec.rounds,
                    "seconds": rec.seconds,
                    "error": rec.error,
                    "result": asdict(rec.result) if rec.result else None,
                    "reviews": [asdict(r) for r in rec.reviews],
                    "usage": asdict(rec.usage),
                }
                for rec in self.records.values()
            ],
        }
        (self.run_dir / "run.json").write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _one_line(text: str, limit: int = 140) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _printable(inputs: dict[str, Any]) -> dict[str, Any]:
    return {k: (v if len(str(v)) < 300 else str(v)[:297] + "...") for k, v in inputs.items()}


def plan(workflow: WorkflowSpec, agents: dict[str, AgentSpec]) -> str:
    """A human-readable outline of what a workflow will do (for --dry-run)."""
    lines = [f"Workflow: {workflow.name}", workflow.description.strip(), ""]
    if workflow.inputs:
        lines.append("Inputs:")
        for name, spec in workflow.inputs.items():
            req = "required" if spec.required else "optional"
            lines.append(f"  - {name} ({spec.type}, {req}){': ' + spec.description if spec.description else ''}")
        lines.append("")
    lines.append("Steps:")
    for i, step in enumerate(workflow.steps, 1):
        agent = agents.get(step.agent)
        model = f"{agent.model}, effort {agent.effort}" if agent else "?"
        lines.append(f"  {i}. {step.id}: {step.agent} [{model}]")
        for arg, value in step.inputs.items():
            lines.append(f"       {arg} ← {value}")
        if step.review:
            lines.append(
                f"       reviewed by {step.review.agent} (up to {step.review.max_rounds} rounds, "
                f"on_reject: {step.review.on_reject})"
            )
    return "\n".join(lines)
