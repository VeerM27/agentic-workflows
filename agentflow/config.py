"""Loading and validating agent and workflow definitions (YAML).

Files are checked strictly: unknown keys are errors (a typo such as `reveiw:` must not be
silently ignored), and every file may carry a `version:` so the format can evolve safely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1

AGENT_INPUT_TYPES = {"text", "file", "image", "images", "integer"}
# Workflow inputs can also be `profile`: a name looked up in a library folder (e.g. an industry).
WORKFLOW_INPUT_TYPES = AGENT_INPUT_TYPES | {"profile"}
ROLES = {"producer", "reviewer"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
ON_REJECT = {"continue", "fail"}

# Fields of a finished step that later steps can reference: ${steps.<id>.<field>}
STEP_FIELDS = {"handoff", "summary", "files", "notes", "verdict", "issues"}

# Reserved argument that a reviewer receives automatically: the work it must check.
REVIEW_WORK_ARG = "work"

REF_PATTERN = re.compile(r"\$\{\s*(inputs|steps)\.([A-Za-z0-9_\-]+)(?:\.([A-Za-z0-9_]+))?\s*\}")

_AGENT_KEYS = {"version", "name", "description", "role", "model", "effort", "max_tokens", "max_turns",
               "tools", "skills", "inputs", "system_prompt", "instructions"}
_INPUT_KEYS = {"type", "required", "description", "default", "library"}
_WORKFLOW_KEYS = {"version", "name", "description", "agents_dir", "inputs", "steps", "checkpoints"}
_STEP_KEYS = {"id", "agent", "inputs", "instructions", "review", "skills", "variants", "checkpoint"}
_REVIEW_KEYS = {"agent", "max_rounds", "inputs", "on_reject"}
_VARIANT_KEYS = {"count", "directions", "parallel"}


class ConfigError(Exception):
    """Raised when an agent or workflow definition is invalid."""


def _check_keys(raw: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigError(f"{where}: unknown keys {unknown} (allowed: {sorted(allowed)})")


def _check_version(raw: dict, where: str) -> None:
    version = raw.get("version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ConfigError(f"{where}: version {version} is not supported by this agentflow (expects {SCHEMA_VERSION})")


@dataclass
class InputSpec:
    name: str
    type: str = "text"
    required: bool = False
    description: str = ""
    default: Any = None
    library: str | None = None  # for type: profile

    @classmethod
    def parse(cls, name: str, raw: Any, where: str, allowed_types: set[str]) -> "InputSpec":
        if raw is None:
            raw = {}
        if isinstance(raw, str):  # shorthand: `brief: text`
            raw = {"type": raw}
        if not isinstance(raw, dict):
            raise ConfigError(f"{where}: input '{name}' must be a mapping or a type name")
        _check_keys(raw, _INPUT_KEYS, f"{where}: input '{name}'")
        spec = cls(
            name=name,
            type=raw.get("type", "text"),
            required=bool(raw.get("required", False)),
            description=raw.get("description", ""),
            default=raw.get("default"),
            library=raw.get("library"),
        )
        if spec.type not in allowed_types:
            raise ConfigError(
                f"{where}: input '{name}' has unknown type '{spec.type}' (expected one of {sorted(allowed_types)})"
            )
        if spec.type == "profile" and not spec.library:
            raise ConfigError(f"{where}: profile input '{name}' needs a 'library' folder")
        return spec


@dataclass
class AgentSpec:
    name: str
    description: str
    system_prompt: str
    role: str = "producer"
    model: str | None = None  # model ID or alias from agentflow.yaml; None = project default
    effort: str | None = None  # None = project default
    max_tokens: int = 64000
    max_turns: int = 40
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    inputs: dict[str, InputSpec] = field(default_factory=dict)
    source: Path | None = None


@dataclass
class ReviewSpec:
    agent: str
    max_rounds: int = 3
    inputs: dict[str, Any] = field(default_factory=dict)
    on_reject: str = "continue"


@dataclass
class VariantSpec:
    count: Any = 1  # int, or a ${inputs.x} reference resolved at run time
    directions: Any = None  # list of strings, or a reference
    parallel: bool = True


@dataclass
class StepSpec:
    id: str
    agent: str
    inputs: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""
    review: ReviewSpec | None = None
    skills: list[str] = field(default_factory=list)
    variants: VariantSpec | None = None
    checkpoint: bool | None = None  # None = follow workflow / project setting


@dataclass
class WorkflowSpec:
    name: str
    description: str
    inputs: dict[str, InputSpec]
    steps: list[StepSpec]
    agents_dir: Path
    checkpoints: Any = None  # "all" | "none" | [step ids]; None = project setting
    source: Path | None = None

    def step(self, step_id: str) -> StepSpec:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    return data


def _str_list(value: Any, where: str, what: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"{where}: '{what}' must be a list of names")
    return list(value)


def load_agent(path: str | Path) -> AgentSpec:
    from .tools import AGENT_TOOLS

    path = Path(path)
    data = _read_yaml(path)
    where = str(path)
    _check_keys(data, _AGENT_KEYS, where)
    _check_version(data, where)

    name = data.get("name") or path.stem
    prompt = data.get("system_prompt") or data.get("instructions")
    if not prompt:
        raise ConfigError(f"{where}: 'system_prompt' is required")

    role = data.get("role", "producer")
    if role not in ROLES:
        raise ConfigError(f"{where}: role must be one of {sorted(ROLES)}, got '{role}'")

    effort = data.get("effort")
    if effort is not None and effort not in EFFORTS:
        raise ConfigError(f"{where}: effort must be one of {sorted(EFFORTS)}, got '{effort}'")

    tools = _str_list(data.get("tools", ["list_files", "read_file", "write_file", "edit_file"]), where, "tools")
    unknown = [t for t in tools if t not in AGENT_TOOLS]
    if unknown:
        raise ConfigError(f"{where}: unknown tools {unknown} (available: {sorted(AGENT_TOOLS)})")

    inputs = {
        arg: InputSpec.parse(arg, raw, where, AGENT_INPUT_TYPES)
        for arg, raw in (data.get("inputs") or {}).items()
    }
    if REVIEW_WORK_ARG in inputs and role == "reviewer":
        raise ConfigError(f"{where}: '{REVIEW_WORK_ARG}' is reserved for reviewers; it is filled in automatically")

    return AgentSpec(
        name=name,
        description=data.get("description", ""),
        system_prompt=prompt.strip(),
        role=role,
        model=data.get("model"),
        effort=effort,
        max_tokens=int(data.get("max_tokens", 64000)),
        max_turns=int(data.get("max_turns", 40)),
        tools=tools,
        skills=_str_list(data.get("skills"), where, "skills"),
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
    _check_keys(raw, _REVIEW_KEYS, f"{where} review")
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


def _parse_variants(raw: Any, where: str) -> VariantSpec | None:
    if raw is None:
        return None
    if isinstance(raw, (int, str)):  # shorthand: `variants: 3` or `variants: ${inputs.variants}`
        raw = {"count": raw}
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: 'variants' must be a number or a mapping")
    _check_keys(raw, _VARIANT_KEYS, f"{where} variants")
    spec = VariantSpec(count=raw.get("count", 2), directions=raw.get("directions"), parallel=bool(raw.get("parallel", True)))
    if isinstance(spec.count, int) and not 1 <= spec.count <= 8:
        raise ConfigError(f"{where}: variants.count must be between 1 and 8")
    return spec


def load_workflow(path: str | Path, agents_dir: str | Path | None = None) -> WorkflowSpec:
    path = Path(path)
    data = _read_yaml(path)
    where = str(path)
    _check_keys(data, _WORKFLOW_KEYS, where)
    _check_version(data, where)

    if agents_dir is None:
        agents_dir = path.parent / data.get("agents_dir", "../agents")
    agents_dir = Path(agents_dir)

    inputs = {
        arg: InputSpec.parse(arg, raw, where, WORKFLOW_INPUT_TYPES)
        for arg, raw in (data.get("inputs") or {}).items()
    }

    raw_steps = data.get("steps")
    if not raw_steps or not isinstance(raw_steps, list):
        raise ConfigError(f"{where}: 'steps' must be a non-empty list")

    steps: list[StepSpec] = []
    for i, raw in enumerate(raw_steps):
        step_where = f"{where}: step {i + 1}"
        if not isinstance(raw, dict) or "agent" not in raw:
            raise ConfigError(f"{step_where}: each step needs an 'agent'")
        _check_keys(raw, _STEP_KEYS, step_where)
        checkpoint = raw.get("checkpoint")
        if checkpoint is not None and not isinstance(checkpoint, bool):
            raise ConfigError(f"{step_where}: 'checkpoint' must be true or false")
        steps.append(
            StepSpec(
                id=str(raw.get("id") or raw["agent"]),
                agent=raw["agent"],
                inputs=dict(raw.get("inputs") or {}),
                instructions=(raw.get("instructions") or "").strip(),
                review=_parse_review(raw.get("review"), step_where),
                skills=_str_list(raw.get("skills"), step_where, "skills"),
                variants=_parse_variants(raw.get("variants"), step_where),
                checkpoint=checkpoint,
            )
        )

    return WorkflowSpec(
        name=data.get("name") or path.stem,
        description=data.get("description", ""),
        inputs=inputs,
        steps=steps,
        agents_dir=agents_dir,
        checkpoints=data.get("checkpoints"),
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


def validate_workflow(
    workflow: WorkflowSpec, agents: dict[str, AgentSpec], skill_names: set[str] | None = None
) -> list[str]:
    """Return a list of human-readable problems; empty means the workflow is runnable.

    Pass `skill_names` (the skills in the manifest) to also check skill references.
    """
    errors: list[str] = []
    seen_steps: list[str] = []

    def check_refs(value: Any, where: str) -> None:
        for scope, name, fld in iter_refs(value):
            if scope == "inputs":
                if name not in workflow.inputs:
                    errors.append(f"{where}: unknown workflow input '${{inputs.{name}}}'")
                if fld:
                    errors.append(f"{where}: workflow inputs have no fields ('{name}.{fld}')")
            else:
                if name not in seen_steps:
                    errors.append(f"{where}: '${{steps.{name}}}' does not refer to an earlier step")
                if fld and fld not in STEP_FIELDS:
                    errors.append(f"{where}: unknown step field '{fld}' (use one of {sorted(STEP_FIELDS)})")

    def check_args(agent: AgentSpec, mapping: dict[str, Any], where: str, auto: set[str]) -> None:
        for arg in mapping:
            if arg not in agent.inputs:
                errors.append(
                    f"{where}: agent '{agent.name}' has no input '{arg}' (declared: {sorted(agent.inputs) or 'none'})"
                )
        for arg, spec in agent.inputs.items():
            if spec.required and arg not in mapping and arg not in auto and spec.default is None:
                errors.append(f"{where}: required input '{arg}' of agent '{agent.name}' is not set")

    def check_skills(names: list[str], where: str) -> None:
        if skill_names is None:
            return
        for s in names:
            if s not in skill_names:
                errors.append(f"{where}: skill '{s}' is not in the skills manifest")

    for name, agent in agents.items():
        check_skills(agent.skills, f"agent '{name}'")

    cp = workflow.checkpoints
    if cp is not None and cp not in ("all", "none") and not isinstance(cp, list):
        errors.append("workflow: 'checkpoints' must be 'all', 'none' or a list of step ids")

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
        check_skills(step.skills, where)

        if step.variants:
            check_refs([step.variants.count, step.variants.directions], f"{where} variants")
            if agent is not None and agent.role != "producer":
                errors.append(f"{where}: only producer steps can have variants")

        if step.review:
            rwhere = f"{where} review"
            reviewer = agents.get(step.review.agent)
            if reviewer is None:
                errors.append(f"{rwhere}: unknown agent '{step.review.agent}'")
            else:
                if reviewer.role != "reviewer":
                    errors.append(f"{rwhere}: agent '{reviewer.name}' must have role 'reviewer' to be used in a review loop")
                check_args(reviewer, step.review.inputs, rwhere, auto={REVIEW_WORK_ARG})
            if agent is not None and agent.role != "producer":
                errors.append(f"{rwhere}: only producer steps can have a review loop")
            check_refs(step.review.inputs, rwhere)

        seen_steps.append(step.id)

    if isinstance(cp, list):
        for sid in cp:
            if sid not in seen_steps:
                errors.append(f"workflow: checkpoint step '{sid}' does not exist")

    return errors
