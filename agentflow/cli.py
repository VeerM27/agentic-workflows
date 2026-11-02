"""Command line interface: `agentflow run | validate | agents`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .config import ConfigError, load_agents, load_workflow, validate_workflow
from .inputs import InputError


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


def _load(args) -> tuple:
    workflow = load_workflow(args.workflow, agents_dir=args.agents_dir)
    agents = load_agents(workflow.agents_dir)
    return workflow, agents


def cmd_validate(args) -> int:
    workflow, agents = _load(args)
    problems = validate_workflow(workflow, agents)
    if problems:
        print(f"{args.workflow}: {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"{args.workflow}: OK ({len(workflow.steps)} steps, {len(agents)} agents available)")
    return 0


def cmd_agents(args) -> int:
    agents = load_agents(args.agents_dir or "agents")
    for spec in agents.values():
        print(f"{spec.name}  [{spec.role}, {spec.model}, effort {spec.effort}]")
        if spec.description:
            print(f"    {spec.description.strip()}")
        for name, inp in spec.inputs.items():
            req = "required" if inp.required else "optional"
            print(f"    - {name} ({inp.type}, {req}){': ' + inp.description if inp.description else ''}")
        print(f"    tools: {', '.join(spec.tools)}")
    return 0


def cmd_run(args) -> int:
    from .orchestrator import Orchestrator, plan

    workflow, agents = _load(args)
    inputs = _parse_inputs(args.input, args.inputs_file)

    if args.dry_run:
        problems = validate_workflow(workflow, agents)
        print(plan(workflow, agents))
        if problems:
            print("\nProblems:\n  - " + "\n  - ".join(problems))
            return 1
        from .inputs import coerce_workflow_inputs

        coerce_workflow_inputs(workflow.inputs, inputs, Path.cwd())
        print("\nInputs OK. Remove --dry-run to execute.")
        return 0

    orchestrator = Orchestrator(
        workflow,
        agents,
        runs_dir=args.runs_dir,
        use_fallbacks=not args.no_fallbacks,
    )
    result = orchestrator.run(inputs, base_dir=Path.cwd(), run_id=args.run_id)
    return 0 if result.status == "done" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentflow", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a workflow")
    run.add_argument("workflow", help="path to a workflow YAML file")
    run.add_argument(
        "-i",
        "--input",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="workflow input; text values may be '@file.md', images a comma-separated list of paths/URLs",
    )
    run.add_argument("--inputs-file", help="YAML file with workflow inputs")
    run.add_argument("--agents-dir", help="override the agents directory")
    run.add_argument("--runs-dir", default="runs", help="where run directories are created (default: runs)")
    run.add_argument("--run-id", help="name for the run directory (default: timestamp + workflow name)")
    run.add_argument("--no-fallbacks", action="store_true", help="disable server-side refusal fallbacks")
    run.add_argument("--dry-run", action="store_true", help="validate and print the plan without calling the API")
    run.set_defaults(func=cmd_run)

    val = sub.add_parser("validate", help="check a workflow and its agents for errors")
    val.add_argument("workflow")
    val.add_argument("--agents-dir")
    val.set_defaults(func=cmd_validate)

    ag = sub.add_parser("agents", help="list available agents and their inputs")
    ag.add_argument("--agents-dir", default="agents")
    ag.set_defaults(func=cmd_agents)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, InputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # API and workflow errors: report without a traceback wall
        import anthropic

        from .orchestrator import WorkflowError

        cause = exc.__cause__ if isinstance(exc, WorkflowError) and exc.__cause__ else exc
        if isinstance(cause, anthropic.AuthenticationError):
            print("error: authentication failed — set ANTHROPIC_API_KEY or run `ant auth login`", file=sys.stderr)
            return 2
        if isinstance(cause, anthropic.APIStatusError):
            print(f"error: {exc} (HTTP {cause.status_code})", file=sys.stderr)
            return 1
        if isinstance(cause, anthropic.APIConnectionError):
            print("error: could not reach the Claude API — check your network", file=sys.stderr)
            return 1
        if isinstance(exc, WorkflowError):
            print(f"error: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
