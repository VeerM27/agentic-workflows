"""agentflow: run multi-agent workflows, keep a human in the loop, manage skills."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .config import ConfigError, load_agents, load_workflow, validate_workflow
from .inputs import InputError, coerce_workflow_inputs, list_profiles
from .project import ProjectError, load_project
from .skills import SkillError, SkillLibrary


def _parse_inputs(pairs: list[str], inputs_file: str | None) -> dict:
    values: dict = {}
    if inputs_file:
        data = yaml.safe_load(Path(inputs_file).read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise InputError(f"{inputs_file}: expected a mapping of input names to values")
        values.update(data)
    for pair in pairs:
        if "=" not in pair:
            raise InputError(f"--input expects name=value, got '{pair}'")
        name, value = pair.split("=", 1)
        values[name.strip()] = value
    return values


def _project(args):
    return load_project(getattr(args, "config", None), search_from=Path.cwd())


def _library(project) -> SkillLibrary:
    if not project.skills_manifest:
        raise SkillError("no skills manifest configured (set skills.manifest in agentflow.yaml)")
    return SkillLibrary(project.skills_manifest)


def _load(args):
    project = _project(args)
    workflow = load_workflow(args.workflow, agents_dir=getattr(args, "agents_dir", None))
    agents = load_agents(workflow.agents_dir)
    return project, workflow, agents


def _approval_mode(args) -> str | None:
    if getattr(args, "yes", False):
        return "auto"
    return getattr(args, "approve_mode", None)


# --- commands ----------------------------------------------------------------------------


def cmd_validate(args) -> int:
    project, workflow, agents = _load(args)
    library = SkillLibrary(project.skills_manifest) if project.skills_manifest and project.skills_manifest.is_file() else None
    problems = validate_workflow(workflow, agents, set(library.sources) if library else None)
    if library:
        used = {s for st in workflow.steps for s in st.skills}
        for st in workflow.steps:
            for name in [st.agent] + ([st.review.agent] if st.review else []):
                if name in agents:
                    used |= set(agents[name].skills)
        problems += library.verify(sorted(used)) if used else []
    if problems:
        print(f"{args.workflow}: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"{args.workflow}: OK ({len(workflow.steps)} steps)")
    return 0


def cmd_agents(args) -> int:
    project = _project(args)
    agents = load_agents(args.agents_dir or (project.root / "agents"))
    for spec in agents.values():
        model = project.resolve_model(spec.model)
        print(f"{spec.name}  [{spec.role}, {model}, effort {spec.effort or project.default_effort}]")
        if spec.description:
            print(f"    {spec.description.strip()}")
        for name, inp in spec.inputs.items():
            req = "required" if inp.required else "optional"
            print(f"    - {name} ({inp.type}, {req}){': ' + inp.description if inp.description else ''}")
        print(f"    tools: {', '.join(spec.tools)}")
        if spec.skills:
            print(f"    skills: {', '.join(spec.skills)}")
    return 0


def cmd_profiles(args) -> int:
    project = _project(args)
    base = project.root / "profiles"
    for library in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        print(f"{library.relative_to(project.root)}: {', '.join(list_profiles(library)) or '(empty)'}")
    return 0


def cmd_run(args) -> int:
    from .orchestrator import Orchestrator, RunStopped, plan

    project, workflow, agents = _load(args)
    inputs = _parse_inputs(args.input, args.inputs_file)

    if args.dry_run:
        library = SkillLibrary(project.skills_manifest) if project.skills_manifest and project.skills_manifest.is_file() else None
        problems = validate_workflow(workflow, agents, set(library.sources) if library else None)
        print(plan(workflow, agents, project))
        if problems:
            print("\nProblems:\n  - " + "\n  - ".join(problems))
            return 1
        coerce_workflow_inputs(workflow.inputs, inputs, Path.cwd(), library_root=project.root)
        print("\nInputs OK. Remove --dry-run to execute.")
        return 0

    orchestrator = Orchestrator(
        workflow,
        agents,
        project=project,
        runs_dir=args.runs_dir,
        use_fallbacks=False if args.no_fallbacks else None,
        approval_mode=_approval_mode(args),
    )
    try:
        result = orchestrator.run(inputs, base_dir=Path.cwd(), run_id=args.run_id)
    except RunStopped:
        return 0
    return 0 if result.status in ("done", "paused", "stopped") else 1


def cmd_resume(args) -> int:
    from .checkpoints import Decision
    from .orchestrator import Orchestrator

    decisions = []
    if args.feedback:
        decisions.append(Decision("revise", args.lane, args.feedback))
    if args.approve or args.choose:
        decisions.append(Decision("approve", args.choose or args.lane))
    result = Orchestrator.resume(
        args.run_dir,
        decisions=decisions,
        approval_mode=_approval_mode(args),
        use_fallbacks=False if args.no_fallbacks else None,
    )
    return 0 if result.status in ("done", "paused", "stopped") else 1


def cmd_skills(args) -> int:
    project = _project(args)
    library = _library(project)
    if args.action == "sync":
        print("Syncing skills to the lockfile:")
        library.sync()
    elif args.action == "update":
        print("Updating skills to the newest commit of their ref:")
        library.update(args.names or None)
        print("Review the changes (git diff skills/) before committing.")
    elif args.action == "verify":
        problems = library.verify()
        if problems:
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"All {len(library.sources)} skills match the lockfile.")
    else:  # list
        agents = load_agents(project.root / "agents") if (project.root / "agents").is_dir() else {}
        for name, src in library.sources.items():
            lock = library.lock.get(name, {})
            pinned = lock.get("commit", "local" if src.local else "not installed")[:10]
            users = [a.name for a in agents.values() if name in a.skills]
            print(f"{name}  [{pinned}]  {src.describe()}")
            try:
                skill = library.get(name)
                print(f"    {skill.description[:160]}")
                if skill.scripts:
                    print(f"    note: contains scripts ({', '.join(skill.scripts[:3])}); agents can read but not run them")
            except SkillError as exc:
                print(f"    {exc}")
            print(f"    used by: {', '.join(users) or '(no agents; can be attached per step)'}")
    return 0


# --- parser ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentflow", description=__doc__)
    parser.add_argument("--config", help="path to agentflow.yaml (default: nearest one above the current directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    def approval_flags(p):
        p.add_argument("--approve-mode", choices=["terminal", "pause", "auto"],
                       help="how checkpoints ask you (default: approvals.mode in agentflow.yaml)")
        p.add_argument("-y", "--yes", action="store_true", help="approve every checkpoint automatically")
        p.add_argument("--no-fallbacks", action="store_true", help="disable server-side refusal fallbacks")

    run = sub.add_parser("run", help="run a workflow")
    run.add_argument("workflow", help="path to a workflow YAML file")
    run.add_argument("-i", "--input", action="append", default=[], metavar="NAME=VALUE",
                     help="workflow input; text may be '@file.md', images a comma-separated list of paths/URLs")
    run.add_argument("--inputs-file", help="YAML file with workflow inputs")
    run.add_argument("--agents-dir", help="override the agents directory")
    run.add_argument("--runs-dir", help="where run directories are created (default: runs_dir in agentflow.yaml)")
    run.add_argument("--run-id", help="name for the run directory (default: timestamp + workflow name)")
    run.add_argument("--dry-run", action="store_true", help="validate and print the plan without calling the API")
    approval_flags(run)
    run.set_defaults(func=cmd_run)

    res = sub.add_parser("resume", help="continue a paused, stopped or interrupted run")
    res.add_argument("run_dir")
    res.add_argument("--approve", action="store_true", help="approve the pending checkpoint")
    res.add_argument("--choose", metavar="VARIANT", help="approve and continue with this variant (e.g. v2)")
    res.add_argument("--feedback", help="request changes at the pending checkpoint")
    res.add_argument("--lane", metavar="VARIANT", help="which variant the feedback is for")
    approval_flags(res)
    res.set_defaults(func=cmd_resume)

    val = sub.add_parser("validate", help="check a workflow, its agents and skills for errors")
    val.add_argument("workflow")
    val.add_argument("--agents-dir")
    val.set_defaults(func=cmd_validate)

    ag = sub.add_parser("agents", help="list agents, their inputs, tools and skills")
    ag.add_argument("--agents-dir")
    ag.set_defaults(func=cmd_agents)

    pr = sub.add_parser("profiles", help="list profile libraries (e.g. industries)")
    pr.set_defaults(func=cmd_profiles)

    sk = sub.add_parser("skills", help="manage pinned Claude Code skills")
    sk.add_argument("action", choices=["list", "sync", "update", "verify"])
    sk.add_argument("names", nargs="*", help="skills to update (default: all)")
    sk.set_defaults(func=cmd_skills)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, InputError, ProjectError, SkillError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted — progress is saved; continue with `agentflow resume <run dir>`", file=sys.stderr)
        return 130
    except Exception as exc:  # API and workflow errors: report without a traceback wall
        import anthropic

        from .orchestrator import WorkflowError

        cause = exc.__cause__ if isinstance(exc, WorkflowError) and exc.__cause__ else exc
        if isinstance(cause, anthropic.AuthenticationError):
            print("error: authentication failed — set ANTHROPIC_API_KEY or run `ant auth login`", file=sys.stderr)
            return 2
        if isinstance(cause, anthropic.APIStatusError):
            print(f"error: {exc} (HTTP {cause.status_code}); progress is saved — fix and `agentflow resume`", file=sys.stderr)
            return 1
        if isinstance(cause, anthropic.APIConnectionError):
            print("error: could not reach the Claude API; progress is saved — `agentflow resume` when back online", file=sys.stderr)
            return 1
        if isinstance(exc, WorkflowError):
            print(f"error: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
