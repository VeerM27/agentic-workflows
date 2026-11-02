"""Loading and validating agent and workflow definitions (YAML)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "high"

INPUT_TYPES = {"text", "file", "image", "images"}
ROLES = {"producer", "reviewer"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
ON_REJECT = {"continue", "fail"}

# Fields of a finished step that later steps can reference: ${steps.<id>.<field>}
STEP_FIELDS = {"handoff", "summary", "files", "notes", "verdict", "issues"}

# Reserved argument that a reviewer receives automatically: the work it must check.
REVIEW_WORK_ARG = "work"

REF_PATTERN = re.compile(r"\$\{\s*(inputs|steps)\.([A-Za-z0-9_\-]+)(?:\.([A-Za-z0-9_]+))?\s*\}")


class ConfigError(Exception):
    """Raised when an agent or workflow definition is invalid."""


@dataclass
class InputSpec:
    name: str
    type: str = "text"
    required: bool = False
    description: str = ""
    default: Any = None

    @classmethod
    def parse(cls, name: str, raw: Any, where: str) -> "InputSpec":
        if raw is None:
            raw = {}
        if isinstance(raw, str):  # shorthand: `brief: text`
            raw = {"type": raw}
        if not isinstance(raw, dict):
            raise ConfigError(f"{where}: input '{name}' must be a mapping or a type name")
        spec = cls(
            name=name,
            type=raw.get("type", "text"),
            required=bool(raw.get("required", False)),
            description=raw.get("description", ""),
            default=raw.get("default"),
        )
        if spec.type not in INPUT_TYPES:
            raise ConfigError(
                f"{where}: input '{name}' has unknown type '{spec.type}' "
                f"(expected one of {sorted(INPUT_TYPES)})"
            )
        return spec


@dataclass
class AgentSpec:
    name: str
    description: str
    system_prompt: str
    role: str = "producer"
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    max_tokens: int = 64000
    max_turns: int = 40
    tools: list[str] = field(default_factory=list)
    inputs: dict[str, InputSpec] = field(default_factory=dict)
    source: Path | None = None


@dataclass
class ReviewSpec:
    agent: str
    max_rounds: int = 3
    inputs: dict[str, Any] = field(default_factory=dict)
    on_reject: str = "continue"


@dataclass
class StepSpec:
    id: str
    agent: str
    inputs: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""
    review: ReviewSpec | None = None


@dataclass
class WorkflowSpec:
    name: str
    description: str
    inputs: dict[str, InputSpec]
    steps: list[StepSpec]
    agents_dir: Path
    source: Path | None = None


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    return data


def load_agent(path: str | Path) -> AgentSpec:
    # Imported here to avoid a circular import (tools -> workspace -> config is fine,
    # but tools is the single source of truth for tool names).
    from .tools import WORKSPACE_TOOLS

    path = Path(path)
    data = _read_yaml(path)
    where = str(path)

    name = data.get("name") or path.stem
    prompt = data.get("system_prompt") or data.get("instructions")
    if not prompt:
        raise ConfigError(f"{where}: 'system_prompt' is required")

    role = data.get("role", "producer")
    if role not in ROLES:
        raise ConfigError(f"{where}: role must be one of {sorted(ROLES)}, got '{role}'")

    effort = data.get("effort", DEFAULT_EFFORT)
    if effort not in EFFORTS:
        raise ConfigError(f"{where}: effort must be one of {sorted(EFFORTS)}, got '{effort}'")

    tools = list(data.get("tools", ["list_files", "read_file", "write_file", "edit_file"]))
    unknown = [t for t in tools if t not in WORKSPACE_TOOLS]
    if unknown:
        raise ConfigError(
            f"{where}: unknown tools {unknown} (available: {sorted(WORKSPACE_TOOLS)})"
        )

    inputs = {
        arg: InputSpec.parse(arg, raw, where) for arg, raw in (data.get("inputs") or {}).items()
    }
    if REVIEW_WORK_ARG in inputs and role == "reviewer":
        raise ConfigError(
            f"{where}: '{REVIEW_WORK_ARG}' is reserved for reviewers; it is filled in automatically"
        )

    return AgentSpec(
        name=name,
        description=data.get("description", ""),
        system_prompt=prompt.strip(),
        role=role,
        model=data.get("model", DEFAULT_MODEL),
        effort=effort,
        max_tokens=int(data.get("max_tokens", 64000)),
        max_turns=int(data.get("max_turns", 40)),
        tools=tools,
        inputs=inputs,
        source=path,
    )


def load_agents(agents_dir: str | Path) -> dict[str, AgentSpec]:
    agents_dir = Path(agents_dir)
    if not agents_dir.is_dir():
        raise ConfigError(f"agents directory not found: {agents_dir}")
    agents: dict[str, AgentSpec] = {}
    for path in sorted([*agents_dir.glob("*.yaml"), *agents_dir.glob("*.yml")]):
        spec = load_agent(path)
        if spec.name in agents:
            raise ConfigError(f"duplicate agent name '{spec.name}' in {path}")
        agents[spec.name] = spec
    return agents


def _parse_review(raw: Any, where: str) -> ReviewSpec | None:
    if raw is None:
        return None
    if isinstance(raw, str):  # shorthand: `review: design_reviewer`
        raw = {"agent": raw}
    if not isinstance(raw, dict) or "agent" not in raw:
        raise ConfigError(f"{where}: 'review' needs at least an 'agent'")
    review = ReviewSpec(
        agent=raw["agent"],
        max_rounds=int(raw.get("max_rounds", 3)),
        inputs=dict(raw.get("inputs") or {}),
        on_reject=raw.get("on_reject", "continue"),
    )
    if review.max_rounds < 1:
        raise ConfigError(f"{where}: review.max_rounds must be at least 1")
    if review.on_reject not in ON_REJECT:
        raise ConfigError(f"{where}: review.on_reject must be one of {sorted(ON_REJECT)}")
    if REVIEW_WORK_ARG in review.inputs:
        raise ConfigError(f"{where}: review input '{REVIEW_WORK_ARG}' is filled in automatically")
    return review


def load_workflow(path: str | Path, agents_dir: str | Path | None = None) -> WorkflowSpec:
    path = Path(path)
    data = _read_yaml(path)
    where = str(path)

    if agents_dir is None:
        agents_dir = path.parent / data.get("agents_dir", "../agents")
    agents_dir = Path(agents_dir)

    inputs = {
        arg: InputSpec.parse(arg, raw, where) for arg, raw in (data.get("inputs") or {}).items()
    }

    raw_steps = data.get("steps")
    if not raw_steps or not isinstance(raw_steps, list):
        raise ConfigError(f"{where}: 'steps' must be a non-empty list")

    steps: list[StepSpec] = []
    for i, raw in enumerate(raw_steps):
        step_where = f"{where}: step {i + 1}"
        if not isinstance(raw, dict) or "agent" not in raw:
            raise ConfigError(f"{step_where}: each step needs an 'agent'")
        steps.append(
            StepSpec(
                id=str(raw.get("id") or raw["agent"]),
                agent=raw["agent"],
                inputs=dict(raw.get("inputs") or {}),
                instructions=(raw.get("instructions") or "").strip(),
                review=_parse_review(raw.get("review"), step_where),
            )
        )

    return WorkflowSpec(
        name=data.get("name") or path.stem,
        description=data.get("description", ""),
        inputs=inputs,
        steps=steps,
        agents_dir=agents_dir,
        source=path,
    )


def iter_refs(value: Any):
    """Yield (scope, name, field) for every ${...} reference inside a value."""
    if isinstance(value, str):
        for m in REF_PATTERN.finditer(value):
            yield m.group(1), m.group(2), m.group(3)
    elif isinstance(value, dict):
        for v in value.values():
            yield from iter_refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from iter_refs(v)


def validate_workflow(workflow: WorkflowSpec, agents: dict[str, AgentSpec]) -> list[str]:
    """Return a list of human-readable problems; empty means the workflow is runnable."""
    errors: list[str] = []
    seen_steps: list[str] = []

    def check_refs(mapping: dict[str, Any], where: str) -> None:
        for scope, name, fld in iter_refs(mapping):
            if scope == "inputs":
                if name not in workflow.inputs:
                    errors.append(f"{where}: unknown workflow input '${{inputs.{name}}}'")
                if fld:
                    errors.append(f"{where}: workflow inputs have no fields ('{name}.{fld}')")
            else:
                if name not in seen_steps:
                    errors.append(
                        f"{where}: '${{steps.{name}}}' does not refer to an earlier step"
                    )
                if fld and fld not in STEP_FIELDS:
                    errors.append(
                        f"{where}: unknown step field '{fld}' (use one of {sorted(STEP_FIELDS)})"
                    )

    def check_args(agent: AgentSpec, mapping: dict[str, Any], where: str, auto: set[str]) -> None:
        for arg in mapping:
            if arg not in agent.inputs:
                errors.append(
                    f"{where}: agent '{agent.name}' has no input '{arg}' "
                    f"(declared: {sorted(agent.inputs) or 'none'})"
                )
        for arg, spec in agent.inputs.items():
            if spec.required and arg not in mapping and arg not in auto and spec.default is None:
                errors.append(f"{where}: required input '{arg}' of agent '{agent.name}' is not set")

    for step in workflow.steps:
        where = f"step '{step.id}'"
        if step.id in seen_steps:
            errors.append(f"{where}: duplicate step id")
        agent = agents.get(step.agent)
        if agent is None:
            errors.append(f"{where}: unknown agent '{step.agent}'")
        else:
            check_args(agent, step.inputs, where, auto=set())
        check_refs(step.inputs, where)

        if step.review:
            rwhere = f"{where} review"
            reviewer = agents.get(step.review.agent)
            if reviewer is None:
                errors.append(f"{rwhere}: unknown agent '{step.review.agent}'")
            else:
                if reviewer.role != "reviewer":
                    errors.append(
                        f"{rwhere}: agent '{reviewer.name}' must have role 'reviewer' "
                        f"to be used in a review loop"
                    )
                check_args(reviewer, step.review.inputs, rwhere, auto={REVIEW_WORK_ARG})
            if agent is not None and agent.role != "producer":
                errors.append(f"{rwhere}: only producer steps can have a review loop")
            check_refs(step.review.inputs, rwhere)

        seen_steps.append(step.id)

    return errors
