"""Running a workflow: steps in order, variants, review loops, human checkpoints, pause/resume.

A step runs in one or more *lanes*. A normal step has one lane (`main`) that works directly in the
run's workspace. A step with `variants: N` runs N lanes (`v1`..`vN`), each in its own copy of the
workspace, each with a different creative direction; the lane chosen at the checkpoint is copied
back into the main workspace and the run continues from it.

Everything needed to continue a run (step results, every agent conversation, inputs) is saved in
the run directory after every change, so a run can pause for a human, survive a crash, and be
resumed with `agentflow resume`.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agent import AgentResult, AgentRunner, Usage
from .checkpoints import (
    Approver,
    AutoApprover,
    CheckpointView,
    Decision,
    LaneView,
    PauseApprover,
    ScriptedApprover,
    TerminalApprover,
    build_gallery,
)
from .config import (
    REF_PATTERN,
    REVIEW_WORK_ARG,
    AgentSpec,
    ConfigError,
    StepSpec,
    WorkflowSpec,
    load_agents,
    load_workflow,
    validate_workflow,
)
from .inputs import InputError, build_task_content, coerce_workflow_inputs, stage_inputs
from .project import ProjectConfig, load_project
from .skills import SkillLibrary
from .workspace import Workspace

STATE_VERSION = 1

# Distinct creative directions used when a variant step is not given its own.
DEFAULT_DIRECTIONS = [
    "Minimal and editorial: generous whitespace, a restrained palette, typography-led hierarchy.",
    "Bold and expressive: strong colour, oversized type, confident asymmetric layouts.",
    "Warm and approachable: soft shapes, friendly tone, illustrative touches.",
    "Premium and dark: deep backgrounds, refined accents, cinematic contrast.",
    "Playful and kinetic: vivid accents, motion-forward details, unexpected compositions.",
    "Structured and data-forward: clear grids, dense but calm information design.",
    "Organic and tactile: natural textures, earthy tones, hand-made details.",
    "Retro-modern: a contemporary take on a past design era that suits the subject.",
]


class WorkflowError(Exception):
    """A workflow could not be completed."""


class RunPaused(Exception):
    """The run is waiting for a human decision."""


class RunStopped(Exception):
    """The operator stopped the run (at a checkpoint, or before it started)."""


# --- records -----------------------------------------------------------------------


def _result_from_dict(data: dict | None) -> AgentResult | None:
    if not data:
        return None
    data = dict(data)
    data["usage"] = Usage(**data.get("usage", {}))
    return AgentResult(**data)


@dataclass
class Lane:
    key: str  # "main" or "v1".."vN"
    workspace: str
    direction: str | None = None
    status: str = "pending"  # pending | running | done | rejected | failed
    rounds: int = 0
    result: AgentResult | None = None
    reviews: list[AgentResult] = field(default_factory=list)
    human_feedback: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Lane":
        data = dict(data)
        data["result"] = _result_from_dict(data.get("result"))
        data["reviews"] = [_result_from_dict(r) for r in data.get("reviews", [])]
        data["usage"] = Usage(**data.get("usage", {}))
        return cls(**data)

    def view(self) -> LaneView:
        r = self.result
        return LaneView(
            key=self.key,
            direction=self.direction,
            status=self.status,
            summary=r.summary if r else "",
            files=list(r.files) if r else [],
            verdicts=[v.verdict for v in self.reviews if v.verdict],
            workspace=Path(self.workspace),
            error=self.error,
        )


@dataclass
class StepRecord:
    id: str
    agent: str
    status: str = "pending"  # pending | running | awaiting_approval | done | rejected | failed
    lanes: list[Lane] = field(default_factory=list)
    chosen: str | None = None
    approved_by: str | None = None  # human | auto
    seconds: float = 0.0
    error: str | None = None

    def lane(self, key: str | None) -> Lane:
        for lane in self.lanes:
            if lane.key == key:
                return lane
        raise KeyError(key)

    @property
    def chosen_lane(self) -> Lane | None:
        if self.chosen:
            return self.lane(self.chosen)
        return self.lanes[0] if self.lanes else None

    @property
    def result(self) -> AgentResult | None:
        lane = self.chosen_lane
        return lane.result if lane else None

    @property
    def reviews(self) -> list[AgentResult]:
        lane = self.chosen_lane
        return lane.reviews if lane else []

    @property
    def rounds(self) -> int:
        lane = self.chosen_lane
        return lane.rounds if lane else 0

    @property
    def usage(self) -> Usage:
        total = Usage()
        for lane in self.lanes:
            total.merge(lane.usage)
        return total

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "status": self.status,
            "chosen": self.chosen,
            "approved_by": self.approved_by,
            "seconds": self.seconds,
            "error": self.error,
            "lanes": [lane.to_dict() for lane in self.lanes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StepRecord":
        return cls(
            id=data["id"],
            agent=data["agent"],
            status=data.get("status", "pending"),
            lanes=[Lane.from_dict(lane) for lane in data.get("lanes", [])],
            chosen=data.get("chosen"),
            approved_by=data.get("approved_by"),
            seconds=data.get("seconds", 0.0),
            error=data.get("error"),
        )

    # Values for ${steps.<id>.<field>} references.
    def field_value(self, name: str | None) -> Any:
        r = self.result
        if name in (None, "handoff"):
            return self.handoff()
        if name == "summary":
            return r.summary if r else ""
        if name == "files":
            return list(r.files) if r else []
        if name == "notes":
            return r.notes if r else ""
        last_review = self.reviews[-1] if self.reviews else None
        source = last_review if (r and r.role == "producer") else r
        if name == "verdict":
            return source.verdict if source else None
        if name == "issues":
            return format_issues(source.issues) if source else ""
        raise KeyError(name)

    def handoff(self) -> str:
        lane = self.chosen_lane
        r = lane.result if lane else None
        if r is None:
            return ""
        lines = [f"### Output of step `{self.id}` (agent: {self.agent})", ""]
        if len(self.lanes) > 1:
            lines += [f"Variant {lane.key} of {len(self.lanes)} was chosen. Direction: {lane.direction}", ""]
        lines.append(r.summary.strip())
        if r.role == "reviewer":
            lines += ["", f"Verdict: **{r.verdict}**"]
            if r.issues:
                lines += ["", format_issues(r.issues)]
            return "\n".join(lines)
        if r.files:
            lines += ["", "Files:"] + [f"- `{f}`" for f in r.files]
        if r.notes.strip():
            lines += ["", "Notes for the next agent:", r.notes.strip()]
        if lane.reviews:
            review = lane.reviews[-1]
            outcome = "approved" if review.verdict == "approve" else "NOT approved"
            lines += ["", f"Review by {review.agent}: {outcome} after {len(lane.reviews)} round(s)."]
            if review.verdict != "approve" and review.issues:
                lines += ["Unresolved issues:", format_issues(review.issues)]
        if lane.human_feedback:
            lines += ["", "The human operator asked for these changes, which were made:"]
            lines += [f"- {fb}" for fb in lane.human_feedback]
        if self.approved_by == "human":
            lines += ["", "The human operator approved this step."]
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
    status: str  # done | paused | stopped | failed


def resolve_refs(value: Any, inputs: dict[str, Any], steps: dict[str, StepRecord]) -> Any:
    """Substitute ${inputs.x} / ${steps.y.field} references.

    A string that is exactly one reference keeps the referenced value's type (e.g. a list of
    image paths, an integer); references inside longer strings are interpolated as text.
    Missing optional inputs resolve to None.
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


def _file_hash(path: Path | str | None) -> str | None:
    if path is None or not Path(path).is_file():
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _replace_tree(src: Path, dst: Path) -> None:
    """Make dst an exact copy of src."""
    if dst.exists():
        for child in dst.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    shutil.copytree(src, dst, dirs_exist_ok=True)


# --- orchestrator ---------------------------------------------------------------------


class Orchestrator:
    def __init__(
        self,
        workflow: WorkflowSpec,
        agents: dict[str, AgentSpec] | None = None,
        *,
        project: ProjectConfig | None = None,
        client: Any = None,
        runs_dir: str | Path | None = None,
        use_fallbacks: bool | None = None,
        printer: Callable[[str], None] = print,
        renderer: Callable[..., bytes] | None = None,
        approver: Approver | None = None,
        approval_mode: str | None = None,
        skills: SkillLibrary | None = None,
    ):
        self.workflow = workflow
        self.project = project or load_project(search_from=workflow.source.parent if workflow.source else ".")
        self.agents = agents if agents is not None else load_agents(workflow.agents_dir)
        self.print = printer

        if skills is None and self.project.skills_manifest and self.project.skills_manifest.is_file():
            skills = SkillLibrary(self.project.skills_manifest)
        self.skills = skills

        problems = validate_workflow(workflow, self.agents, set(skills.sources) if skills else None)
        problems += self._check_skills_installed()
        if problems:
            raise ConfigError("workflow is invalid:\n  - " + "\n  - ".join(problems))

        self._client = client
        self.runs_dir = Path(runs_dir) if runs_dir else self.project.runs_dir
        self.use_fallbacks = self.project.fallbacks if use_fallbacks is None else use_fallbacks
        self.renderer = renderer
        self.approver = approver or self._approver_for(approval_mode or self.project.approval_mode)
        self._runners: dict[tuple[str, str], AgentRunner] = {}
        self._lock = threading.RLock()

    # --- setup helpers -----------------------------------------------------------------

    def _skills_used(self) -> set[str]:
        used = {s for step in self.workflow.steps for s in step.skills}
        names = {step.agent for step in self.workflow.steps}
        names |= {step.review.agent for step in self.workflow.steps if step.review}
        for name in names:
            if name in self.agents:
                used |= set(self.agents[name].skills)
        return used

    def _check_skills_installed(self) -> list[str]:
        used = self._skills_used()
        if not used:
            return []
        if self.skills is None:
            return [f"skills {sorted(used)} are used but no skills manifest is configured in agentflow.yaml"]
        return self.skills.verify(sorted(used))

    def _approver_for(self, mode: str) -> Approver:
        if mode == "auto":
            return AutoApprover()
        if mode == "pause":
            return PauseApprover()
        if not sys.stdin.isatty():
            # Nobody can answer a terminal prompt; pausing is the safe equivalent.
            self.print("(no interactive terminal: checkpoints will pause the run instead of asking)")
            return PauseApprover()
        return TerminalApprover(print_fn=self.print)

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def _checkpoint_enabled(self, step: StepSpec) -> bool:
        if step.checkpoint is not None:
            return step.checkpoint
        setting = self.workflow.checkpoints if self.workflow.checkpoints is not None else self.project.checkpoints
        if setting == "all":
            return True
        if setting in ("none", None):
            return False
        return step.id in setting

    # --- starting and resuming -----------------------------------------------------------

    def run(self, inputs: dict[str, Any], *, base_dir: str | Path = ".", run_id: str | None = None) -> RunResult:
        resolved = coerce_workflow_inputs(self.workflow.inputs, inputs, Path(base_dir), library_root=self.project.root)
        if not self.approver.confirm_start(plan(self.workflow, self.agents, self.project)):
            self.print("Not started.")
            raise RunStopped("not started")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.run_dir = (self.runs_dir / (run_id or f"{stamp}-{_slug(self.workflow.name)}")).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=False)
        for sub in ("transcripts", "state", "checkpoints"):
            (self.run_dir / sub).mkdir()
        self.workspace = Workspace(self.run_dir / "workspace")
        self.staged = stage_inputs(resolved, self.workflow.inputs, self.workspace)
        self.inputs = resolved
        self.records = {s.id: StepRecord(id=s.id, agent=s.agent) for s in self.workflow.steps}
        self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.print(f"Run directory: {self.run_dir}")
        self._event("run_started", workflow=self.workflow.name)
        return self._execute()

    @classmethod
    def resume(
        cls,
        run_dir: str | Path,
        *,
        decisions: list[Decision] | None = None,
        approval_mode: str | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """Continue a paused, stopped or crashed run. `decisions` answer the pending checkpoint."""
        run_dir = Path(run_dir).resolve()
        state_path = run_dir / "run.json"
        if not state_path.is_file():
            raise WorkflowError(f"{run_dir} is not a run directory (no run.json)")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("version") != STATE_VERSION:
            raise WorkflowError(f"run state version {state.get('version')} is not supported")
        if state["status"] == "done":
            raise WorkflowError("this run already finished")

        workflow = load_workflow(state["workflow_source"])
        project = load_project(state["project_source"]) if state.get("project_source") else None
        if _file_hash(state["workflow_source"]) != state.get("workflow_hash"):
            if [s["id"] for s in state["steps"]] != [s.id for s in workflow.steps]:
                raise WorkflowError("the workflow's steps changed since this run started; it cannot be resumed")
            kwargs.get("printer", print)("(note: the workflow file changed since this run started)")

        orch = cls(workflow, project=project, approval_mode=approval_mode, **kwargs)
        if decisions:
            orch.approver = ScriptedApprover(decisions, orch.approver)
        orch.run_dir = run_dir
        orch.workspace = Workspace(run_dir / "workspace")
        orch.inputs = state["inputs"]
        orch.staged = state.get("staged", {})
        orch.started_at = state.get("started_at")
        orch.records = {s["id"]: StepRecord.from_dict(s) for s in state["steps"]}
        orch.print(f"Resuming {run_dir}")
        orch._event("run_resumed")
        return orch._execute()

    def _execute(self) -> RunResult:
        status = "done"
        try:
            for step in self.workflow.steps:
                rec = self.records[step.id]
                if rec.status in ("done", "rejected"):
                    continue
                if rec.status == "awaiting_approval":
                    self._checkpoint_loop(step, rec)
                else:
                    self._run_step(step, rec)  # pending, or unfinished after a crash: (re)run
        except RunPaused:
            status = "paused"
        except RunStopped:
            status = "stopped"
        except KeyboardInterrupt:
            self._save_state("stopped")
            self._event("run_interrupted")
            raise
        except Exception as exc:
            self._event("run_failed", error=str(exc))
            self._save_state("failed")
            self.project.notify("failed", run_dir=self.run_dir, error=str(exc))
            raise
        self._save_state(status)
        self._event("run_" + status)

        total = Usage()
        for rec in self.records.values():
            total.merge(rec.usage)
        usage_line = (
            f"Tokens so far: {total.input_tokens:,} in (+{total.cache_read_input_tokens:,} cache reads, "
            f"{total.cache_creation_input_tokens:,} cache writes), {total.output_tokens:,} out over {total.requests} requests"
        )
        if status in ("paused", "stopped"):
            pending = next((r for r in self.records.values() if r.status == "awaiting_approval"), None)
            where = f" at step '{pending.id}'" if pending else ""
            self.print(
                f"\n⏸  Run {status}{where}. Look at: {self.run_dir / 'checkpoints'}\n"
                f"   Continue with one of:\n"
                f"     agentflow resume {self.run_dir} --approve [--choose v2]\n"
                f"     agentflow resume {self.run_dir} --feedback \"what to change\" [--lane v2]\n"
                f"     agentflow resume {self.run_dir}          (asks you in the terminal)\n{usage_line}"
            )
            self.project.notify("paused", run_dir=self.run_dir, step=pending.id if pending else "")
        else:
            self.print(f"\n✔ Finished. Workspace: {self.workspace.root}\n{usage_line}")
            self.project.notify("finished", run_dir=self.run_dir, workspace=self.workspace.root)
        return RunResult(self.run_dir, self.workspace.root, list(self.records.values()), total, status)

    # --- steps -------------------------------------------------------------------------

    def _run_step(self, step: StepSpec, rec: StepRecord) -> None:
        spec = self.agents[step.agent]
        rec.status = "running"
        rec.error = None
        rec.chosen = None
        started = time.monotonic()
        self.print(f"\n▶ Step '{step.id}' — {spec.name} ({spec.role})")
        self._event("step_started", step=step.id, agent=spec.name)

        try:
            args = _clean_args(resolve_refs(step.inputs, self.inputs, self.records))
            self._apply_defaults(spec, args, step.id)
            rec.lanes = self._make_lanes(step)
            self._save_state("running")

            if len(rec.lanes) == 1:
                self._run_lane(step, rec, rec.lanes[0], args)
            else:
                parallel = step.variants.parallel if step.variants else True
                self.print(f"  ⑂ {len(rec.lanes)} variants{' in parallel' if parallel else ''}")
                if parallel:
                    with ThreadPoolExecutor(max_workers=len(rec.lanes)) as pool:
                        list(pool.map(lambda lane: self._run_lane(step, rec, lane, args), rec.lanes))
                else:
                    for lane in rec.lanes:
                        self._run_lane(step, rec, lane, args)

            if all(lane.status == "failed" for lane in rec.lanes):
                raise WorkflowError("; ".join(
                    (f"{lane.key}: " if len(rec.lanes) > 1 else "") + str(lane.error) for lane in rec.lanes
                ))
            self._checkpoint_loop(step, rec)
        except (RunPaused, RunStopped):
            raise
        except Exception as exc:
            rec.status = "failed"
            rec.error = str(exc)
            self._event("step_failed", step=step.id, error=str(exc))
            self.print(f"  ✖ Step '{step.id}' failed: {exc}")
            raise WorkflowError(f"step '{step.id}' failed: {exc}") from exc
        finally:
            rec.seconds = round(rec.seconds + time.monotonic() - started, 1)
            self._save_state("running")

    def _make_lanes(self, step: StepSpec) -> list[Lane]:
        main = [Lane(key="main", workspace=str(self.workspace.root))]
        if not step.variants:
            return main
        count = resolve_refs(step.variants.count, self.inputs, self.records)
        try:
            count = int(count or 1)
        except (TypeError, ValueError):
            raise InputError(f"step '{step.id}': variants.count must be a number, got '{count}'")
        if not 1 <= count <= 8:
            raise InputError(f"step '{step.id}': variants.count must be between 1 and 8")
        if count == 1:
            return main

        directions = resolve_refs(step.variants.directions, self.inputs, self.records)
        if isinstance(directions, str):
            directions = [d.strip() for d in re.split(r"\n|;", directions) if d.strip()]
        directions = list(directions or [])
        directions += [d for d in DEFAULT_DIRECTIONS if d not in directions]

        lanes = []
        for k in range(1, count + 1):
            ws = self.run_dir / "variants" / step.id / f"v{k}"
            if ws.exists():
                shutil.rmtree(ws)
            shutil.copytree(self.workspace.root, ws)
            lanes.append(Lane(key=f"v{k}", workspace=str(ws), direction=directions[k - 1]))
        return lanes

    def _run_lane(self, step: StepSpec, rec: StepRecord, lane: Lane, args: dict[str, Any]) -> None:
        spec = self.agents[step.agent]
        lane.status = "running"
        try:
            runner = self._new_runner(spec, lane, step)
            self._runners[(step.id, lane.key)] = runner
            instructions = step.instructions
            if lane.direction:
                variant_note = (
                    f"You are producing variant {lane.key} of {len(rec.lanes)}. Other agents are producing the "
                    f"other variants in parallel; yours must be clearly distinct. Creative direction for this "
                    f"variant: {lane.direction}"
                )
                instructions = f"{instructions}\n\n{variant_note}" if instructions else variant_note
            content = build_task_content(
                spec.inputs,
                args,
                staged=self.staged,
                instructions=instructions,
                closing=f"Carry out your role on these inputs. When you are done, call `{runner.terminal}`.",
            )
            lane.rounds = 1
            lane.result = runner.start(content)
            lane.usage.merge(runner.pop_usage())
            self._report_result(lane.result, lane)
            self._save_runner(step.id, lane, runner)
            if step.review:
                self._review_loop(step, rec, lane, runner)
            if lane.status == "running":
                lane.status = "done"
        except Exception as exc:
            lane.status = "failed"
            lane.error = str(exc)
            self.print(f"  ✖ {self._prefix(rec, lane)}failed: {exc}")
            self._event("lane_failed", step=step.id, lane=lane.key, error=str(exc))
        finally:
            self._save_state("running")

    def _review_loop(self, step: StepSpec, rec: StepRecord, lane: Lane, producer: AgentRunner) -> None:
        review = step.review
        reviewer_spec = self.agents[review.agent]
        prefix = self._prefix(rec, lane)
        for round_no in range(1, review.max_rounds + 1):
            self.print(f"  ↳ {prefix}review round {round_no}/{review.max_rounds} — {reviewer_spec.name}")
            args = _clean_args(resolve_refs(review.inputs, self.inputs, self.records))
            args[REVIEW_WORK_ARG] = StepRecord(id=rec.id, agent=rec.agent, lanes=[lane]).handoff()
            self._apply_defaults(reviewer_spec, args, f"{step.id} review")
            reviewer = self._new_runner(reviewer_spec, lane, step, reviewer=True)
            content = build_task_content(
                reviewer_spec.inputs,
                args,
                staged=self.staged,
                closing="Review the work above against your criteria, then call `submit_review`.",
            )
            verdict = reviewer.start(content)
            lane.usage.merge(reviewer.pop_usage())
            lane.reviews.append(verdict)
            self._report_result(verdict, lane)
            self._save_transcript(f"{step.id}.{lane.key}.{reviewer_spec.name}.review{len(lane.reviews)}", reviewer)

            if verdict.verdict == "approve":
                lane.status = "done"
                return
            if round_no == review.max_rounds:
                break
            lane.rounds += 1
            self.print(f"  ↻ {prefix}revising ({producer.spec.name}), round {lane.rounds}")
            feedback = (
                f"The {reviewer_spec.name} agent reviewed your work and asked for changes.\n\n"
                f"Reviewer summary: {verdict.summary}\n\nIssues to address:\n{format_issues(verdict.issues)}\n\n"
                "Fix these issues in the workspace files. If you disagree with an issue, explain why in your "
                "notes instead of changing it. Then call `complete_task` again with an updated summary and "
                "the full list of files you have created or changed."
            )
            lane.result = producer.follow_up(feedback)
            lane.usage.merge(producer.pop_usage())
            self._report_result(lane.result, lane)
            self._save_runner(step.id, lane, producer)

        msg = f"review not approved after {review.max_rounds} round(s)"
        self._event("review_rejected", step=step.id, lane=lane.key)
        if review.on_reject == "fail":
            lane.status = "failed"
            lane.error = msg
            return
        lane.status = "rejected"
        self.print(f"  ⚠ {prefix}{msg}; continuing (set on_reject: fail to stop instead)")

    def _checkpoint_loop(self, step: StepSpec, rec: StepRecord) -> None:
        spec = self.agents[step.agent]
        while True:
            view = CheckpointView(
                step_id=step.id,
                agent=spec.name,
                lanes=[lane.view() for lane in rec.lanes],
                gallery=None,
                run_dir=self.run_dir,
            )
            if self._checkpoint_enabled(step):
                view.gallery = build_gallery(view, self.run_dir / "checkpoints" / f"{step.id}.html")
                rec.status = "awaiting_approval"
                self._save_state("awaiting_approval")
                self._event("checkpoint", step=step.id)
                first = rec.lanes[0].result if rec.lanes else None
                self.project.notify(
                    "checkpoint", run_dir=self.run_dir, step=step.id, gallery=view.gallery,
                    summary=first.summary if first else "",
                )
                decision = self.approver.decide(view)
                approved_by = "auto" if isinstance(self.approver, AutoApprover) else "human"
            else:
                decision = AutoApprover().decide(view)
                approved_by = "auto"
            self._event("decision", step=step.id, action=decision.action, lane=decision.lane, feedback=decision.feedback)

            if decision.action == "pause":
                raise RunPaused(step.id)
            if decision.action == "stop":
                rec.status = "awaiting_approval"
                raise RunStopped(step.id)

            try:
                lane = rec.lane(decision.lane) if decision.lane else rec.lanes[0]
            except KeyError:
                if isinstance(self.approver, TerminalApprover):
                    self.print(f"  ! no variant '{decision.lane}' (have: {[x.key for x in rec.lanes]})")
                    continue
                raise WorkflowError(f"step '{step.id}': unknown variant '{decision.lane}'")

            if decision.action == "approve":
                if lane.status == "failed" or lane.result is None:
                    raise WorkflowError(f"step '{step.id}': {lane.key} failed and cannot be approved")
                self._adopt(rec, lane)
                rec.approved_by = approved_by
                rec.status = "rejected" if lane.status == "rejected" else "done"
                self.print(
                    f"  ✔ Step '{step.id}' {'approved' if approved_by == 'human' else 'accepted'}"
                    + (f" — continuing with {lane.key}" if len(rec.lanes) > 1 else "")
                )
                self._save_state("running")
                self._event("step_finished", step=step.id, status=rec.status, lane=lane.key)
                return

            if decision.action == "revise":
                self._human_revision(step, rec, lane, decision.feedback)
                continue

            raise WorkflowError(f"unknown checkpoint decision '{decision.action}'")

    def _human_revision(self, step: StepSpec, rec: StepRecord, lane: Lane, feedback: str) -> None:
        rec.status = "running"
        self.print(f"  ✎ {self._prefix(rec, lane)}revising with your feedback")
        runner = self._runners.get((step.id, lane.key)) or self._restore_runner(step, lane)
        lane.human_feedback.append(feedback)
        lane.status = "running"
        lane.error = None
        lane.rounds += 1
        message = (
            "The human operator reviewed your work and asked for these changes:\n\n"
            f"{feedback}\n\n"
            "Their direction takes priority over earlier reviewer feedback. Update the workspace files, "
            f"then call `{runner.terminal}` again with an updated summary and the full list of files."
        )
        lane.result = runner.follow_up(message)
        lane.usage.merge(runner.pop_usage())
        self._report_result(lane.result, lane)
        self._save_runner(step.id, lane, runner)
        if step.review:
            self._review_loop(step, rec, lane, runner)
        if lane.status == "running":
            lane.status = "done"
        self._save_state("running")

    def _adopt(self, rec: StepRecord, lane: Lane) -> None:
        rec.chosen = lane.key
        if Path(lane.workspace).resolve() != self.workspace.root:
            _replace_tree(Path(lane.workspace), self.workspace.root)

    # --- runners ---------------------------------------------------------------------------

    def _new_runner(self, spec: AgentSpec, lane: Lane, step: StepSpec, reviewer: bool = False) -> AgentRunner:
        skill_names = list(dict.fromkeys(spec.skills + ([] if reviewer else step.skills)))
        skills = [self.skills.get(n) for n in skill_names] if skill_names else []
        return AgentRunner(
            spec,
            self.client,
            Workspace(lane.workspace),
            on_event=self._agent_event_for(lane),
            use_fallbacks=self.use_fallbacks,
            renderer=self.renderer,
            model=self.project.resolve_model(spec.model),
            effort=spec.effort or self.project.default_effort,
            house_style=self.project.house_style,
            skills=skills,
        )

    def _runner_state_path(self, step_id: str, lane: Lane) -> Path:
        return self.run_dir / "state" / f"{step_id}.{lane.key}.json"

    def _save_runner(self, step_id: str, lane: Lane, runner: AgentRunner) -> None:
        self._runner_state_path(step_id, lane).write_text(
            json.dumps({"messages": runner.transcript()}, default=str), encoding="utf-8"
        )
        self._save_transcript(f"{step_id}.{lane.key}.{runner.spec.name}", runner)

    def _restore_runner(self, step: StepSpec, lane: Lane) -> AgentRunner:
        path = self._runner_state_path(step.id, lane)
        if not path.is_file():
            raise WorkflowError(f"no saved conversation for step '{step.id}' {lane.key}; cannot revise")
        runner = self._new_runner(self.agents[step.agent], lane, step)
        runner.restore(json.loads(path.read_text(encoding="utf-8"))["messages"])
        self._runners[(step.id, lane.key)] = runner
        return runner

    def _apply_defaults(self, spec: AgentSpec, args: dict[str, Any], where: str) -> None:
        for name, inp in spec.inputs.items():
            if name not in args and inp.default is not None:
                args[name] = inp.default
            if inp.required and name not in args:
                raise InputError(f"{where}: required input '{name}' of agent '{spec.name}' resolved to nothing")

    # --- output -----------------------------------------------------------------------------

    @staticmethod
    def _prefix(rec: StepRecord, lane: Lane) -> str:
        return f"[{lane.key}] " if len(rec.lanes) > 1 else ""

    def _report_result(self, r: AgentResult, lane: Lane) -> None:
        tag = f"[{lane.key}] " if lane.key != "main" else ""
        if r.role == "reviewer":
            icon = "✔" if r.verdict == "approve" else "✎"
            self.print(f"  {icon} {tag}{r.agent}: {r.verdict} ({len(r.issues)} issue(s)) — {_one_line(r.summary)}")
        else:
            self.print(f"  ✔ {tag}{r.agent}: {_one_line(r.summary)}")
            if r.files:
                self.print(f"    files: {', '.join(r.files[:8])}{' …' if len(r.files) > 8 else ''}")
        self._event("agent_result", lane=lane.key, **asdict(r))

    def _agent_event_for(self, lane: Lane) -> Callable[..., None]:
        tag = f"[{lane.key}] " if lane.key != "main" else ""

        def handler(kind: str, **data: Any) -> None:
            if kind == "tool":
                path = data["args"].get("path", "")
                self.print(f"    · {tag}{data['tool']} {path}".rstrip())
            elif kind == "tool_error":
                self.print(f"    ! {tag}{data['tool']}: {_one_line(data['error'], 100)}")
            elif kind == "retry":
                self.print(f"    ↺ {tag}retrying ({data['reason']})")
            self._event(kind, lane=lane.key, **data)

        return handler

    def _event(self, kind: str, **data: Any) -> None:
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": kind, **data}
        with self._lock:
            with (self.run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")

    def _save_transcript(self, name: str, runner: AgentRunner) -> None:
        path = self.run_dir / "transcripts" / f"{name}.json"
        data = {"model": runner.model, "system": runner.system, "messages": runner.transcript()}
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _save_state(self, status: str) -> None:
        with self._lock:
            agent_names = {s.agent for s in self.workflow.steps} | {s.review.agent for s in self.workflow.steps if s.review}
            state = {
                "version": STATE_VERSION,
                "workflow": self.workflow.name,
                "workflow_source": str(Path(self.workflow.source).resolve()) if self.workflow.source else None,
                "workflow_hash": _file_hash(self.workflow.source),
                "project_source": str(self.project.source) if self.project.source else None,
                "status": status,
                "started_at": getattr(self, "started_at", None),
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "inputs": self.inputs,
                "staged": self.staged,
                "workspace": str(self.workspace.root),
                # Snapshot of what produced this run, for reproducibility.
                "models": {n: self.project.resolve_model(self.agents[n].model) for n in sorted(agent_names)},
                "skills": (
                    {n: self.skills.lock.get(n, {}).get("commit", "local") for n in sorted(self._skills_used())}
                    if self.skills else {}
                ),
                "steps": [rec.to_dict() for rec in self.records.values()],
            }
            tmp = self.run_dir / "run.json.tmp"
            tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
            tmp.replace(self.run_dir / "run.json")


def _one_line(text: str, limit: int = 140) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def plan(workflow: WorkflowSpec, agents: dict[str, AgentSpec], project: ProjectConfig | None = None) -> str:
    """A human-readable outline of what a workflow will do (for --dry-run and the start prompt)."""
    project = project or ProjectConfig(root=Path("."))
    lines = [f"Workflow: {workflow.name}", workflow.description.strip(), ""]
    if workflow.inputs:
        lines.append("Inputs:")
        for name, spec in workflow.inputs.items():
            req = "required" if spec.required else "optional"
            lines.append(f"  - {name} ({spec.type}, {req}){': ' + spec.description if spec.description else ''}")
        lines.append("")
    lines.append("Steps:")
    setting = workflow.checkpoints if workflow.checkpoints is not None else project.checkpoints
    for i, step in enumerate(workflow.steps, 1):
        agent = agents.get(step.agent)
        if agent:
            model = f"{project.resolve_model(agent.model)}, effort {agent.effort or project.default_effort}"
            skills = list(dict.fromkeys(agent.skills + step.skills))
        else:
            model, skills = "?", []
        lines.append(f"  {i}. {step.id}: {step.agent} [{model}]")
        if skills:
            lines.append(f"       skills: {', '.join(skills)}")
        for arg, value in step.inputs.items():
            lines.append(f"       {arg} ← {value}")
        if step.variants:
            lines.append(f"       variants: {step.variants.count}")
        if step.review:
            lines.append(
                f"       reviewed by {step.review.agent} (up to {step.review.max_rounds} rounds, on_reject: {step.review.on_reject})"
            )
        cp = step.checkpoint if step.checkpoint is not None else (
            setting == "all" or (isinstance(setting, list) and step.id in setting)
        )
        lines.append(f"       checkpoint: {'you approve this step' if cp else 'automatic'}")
    return "\n".join(lines)
