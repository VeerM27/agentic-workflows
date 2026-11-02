"""Project config, skills, profiles, strict config checks, and the terminal checkpoint UI."""

import subprocess
from pathlib import Path

import pytest

from agentflow.checkpoints import CheckpointView, Decision, LaneView, TerminalApprover
from agentflow.config import ConfigError, load_agent, load_workflow
from agentflow.inputs import coerce_workflow_inputs, load_profile
from agentflow.project import ProjectError, load_project
from agentflow.skills import SkillLibrary, parse_skill_dir
from agentflow.tools import ToolExecutor, contrast_ratio
from agentflow.workspace import Workspace

ROOT = Path(__file__).parent.parent


# --- project config ---------------------------------------------------------------------


def test_repo_project_config_loads():
    project = load_project(ROOT / "agentflow.yaml")
    assert project.resolve_model(None) == "claude-opus-5-5"
    assert project.resolve_model("fast") == "claude-sonnet-5-5"
    assert project.resolve_model("claude-haiku-5-5") == "claude-haiku-5-5"
    assert "Quality bar" in project.house_style


def test_model_aliases_can_chain_and_unknown_keys_fail(tmp_path):
    (tmp_path / "agentflow.yaml").write_text("version: 1\nmodels:\n  default: smart\n  smart: claude-fable-5-1\n")
    assert load_project(tmp_path / "agentflow.yaml").resolve_model(None) == "claude-fable-5-1"
    (tmp_path / "agentflow.yaml").write_text("version: 1\napprovels: {}\n")
    with pytest.raises(ProjectError, match="unknown keys"):
        load_project(tmp_path / "agentflow.yaml")
    (tmp_path / "agentflow.yaml").write_text("version: 2\n")
    with pytest.raises(ProjectError, match="version"):
        load_project(tmp_path / "agentflow.yaml")


def test_notify_command_receives_event(tmp_path):
    out = tmp_path / "note.txt"
    (tmp_path / "agentflow.yaml").write_text(f"version: 1\nnotify:\n  command: 'echo $AGENTFLOW_EVENT $AGENTFLOW_STEP > {out}'\n")
    load_project(tmp_path / "agentflow.yaml").notify("checkpoint", step="design")
    assert out.read_text().strip() == "checkpoint design"


# --- strict config ------------------------------------------------------------------------


def test_typo_in_workflow_is_an_error(tmp_path):
    p = tmp_path / "wf.yaml"
    p.write_text("name: wf\nsteps:\n  - agent: a\n    reveiw: b\n")
    with pytest.raises(ConfigError, match="reveiw"):
        load_workflow(p)


def test_typo_in_agent_is_an_error(tmp_path):
    p = tmp_path / "a.yaml"
    p.write_text("name: a\nsystem_prompt: hi\nskils: [x]\n")
    with pytest.raises(ConfigError, match="skils"):
        load_agent(p)


# --- profiles ------------------------------------------------------------------------------


def test_profiles_load_by_name_or_pass_through_free_text():
    library = ROOT / "profiles" / "industries"
    text, found = load_profile("Real Estate", library)
    assert found and "Industry: Real estate" in text
    text, found = load_profile("artisanal cheese shop", library)
    assert not found and text == "artisanal cheese shop"


def test_integer_inputs_are_checked(tmp_path):
    wf = load_workflow(ROOT / "workflows" / "palettes.yaml")
    out = coerce_workflow_inputs(wf.inputs, {"brief": "x", "count": "3"}, tmp_path, library_root=ROOT)
    assert out["count"] == 3
    from agentflow.inputs import InputError

    with pytest.raises(InputError, match="whole number"):
        coerce_workflow_inputs(wf.inputs, {"brief": "x", "count": "lots"}, tmp_path, library_root=ROOT)


# --- skills ----------------------------------------------------------------------------------


def test_vendored_skills_match_the_lockfile():
    library = SkillLibrary(ROOT / "skills" / "skills.yaml")
    assert library.verify() == []
    skill = library.get("theme-factory")
    assert "themes/ocean-depths.md" in skill.files
    assert "Skill: theme-factory" in skill.prompt_section()


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_skill_repo(path: Path, body: str) -> None:
    (path / "skills" / "demo").mkdir(parents=True, exist_ok=True)
    (path / "skills" / "demo" / "SKILL.md").write_text(f"---\nname: demo\ndescription: A demo skill\n---\n{body}\n")
    (path / "skills" / "demo" / "notes.md").write_text("extra notes")
    _git(path, "add", "-A")
    _git(path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", body)


def test_sync_pins_commit_verify_detects_tampering_and_update_moves_forward(tmp_path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q", "-b", "main")
    _make_skill_repo(upstream, "Version one")

    project = tmp_path / "project" / "skills"
    project.mkdir(parents=True)
    (project / "skills.yaml").write_text(
        f"version: 1\nskills:\n  demo:\n    repo: file://{upstream}\n    path: skills/demo\n    ref: main\n"
    )
    lib = SkillLibrary(project / "skills.yaml")
    lib.sync(log=lambda *_: None)
    first_commit = lib.lock["demo"]["commit"]
    assert "Version one" in lib.get("demo").body
    assert lib.verify() == []

    # Upstream moves on; sync stays on the pinned commit (reproducible).
    _make_skill_repo(upstream, "Version two")
    lib = SkillLibrary(project / "skills.yaml")
    lib.sync(log=lambda *_: None)
    assert lib.lock["demo"]["commit"] == first_commit and "Version one" in lib.get("demo").body

    # Local edits to vendored files are detected.
    (project / "vendor" / "demo" / "SKILL.md").write_text("tampered")
    assert any("differ" in p for p in SkillLibrary(project / "skills.yaml").verify())

    # update deliberately moves to the newest commit and reports what changed.
    lib = SkillLibrary(project / "skills.yaml")
    changes = []
    lib.update(log=changes.append)
    assert lib.lock["demo"]["commit"] != first_commit
    assert "Version two" in lib.get("demo").body
    assert any("changed: SKILL.md" in c for c in changes)
    assert SkillLibrary(project / "skills.yaml").verify() == []


def test_read_skill_file_tool(tmp_path):
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\nbody")
    (skill_dir / "ref.md").write_text("reference text")
    skill = parse_skill_dir(skill_dir)
    ex = ToolExecutor(Workspace(tmp_path / "ws"), skills={"s": skill})
    assert ex.run("read_skill_file", {"skill": "s", "path": "ref.md"}).content == "reference text"
    assert ex.run("read_skill_file", {"skill": "s", "path": "../../etc/passwd"}).is_error
    assert ex.run("read_skill_file", {"skill": "nope", "path": "ref.md"}).is_error


# --- contrast --------------------------------------------------------------------------------


def test_contrast_ratio_matches_wcag_reference_values():
    assert round(contrast_ratio("#000", "#fff"), 1) == 21.0
    assert round(contrast_ratio("#777777", "#ffffff"), 2) == 4.48
    assert round(contrast_ratio("#0000ff", "#ffffff"), 2) == 8.59


# --- terminal approver -------------------------------------------------------------------------


def _view(tmp_path, keys):
    lanes = [LaneView(k, f"dir {k}", "done", f"summary {k}", [f"{k}.html"], ["approve"], tmp_path) for k in keys]
    return CheckpointView("design", "ux_designer", lanes, None, tmp_path)


def test_terminal_approver_parses_commands(tmp_path):
    answers = iter(["a", "a 2"])  # bare approve is ambiguous with variants, then picks v2
    approver = TerminalApprover(input_fn=lambda _: next(answers), print_fn=lambda *_: None)
    assert approver.decide(_view(tmp_path, ["v1", "v2"])) == Decision("approve", "v2")

    answers = iter(["r v1 bigger logo please"])
    approver = TerminalApprover(input_fn=lambda _: next(answers), print_fn=lambda *_: None)
    assert approver.decide(_view(tmp_path, ["v1", "v2"])) == Decision("revise", "v1", "bigger logo please")

    answers = iter(["r", "tighter spacing"])  # feedback asked for separately
    approver = TerminalApprover(input_fn=lambda _: next(answers), print_fn=lambda *_: None)
    assert approver.decide(_view(tmp_path, ["main"])) == Decision("revise", "main", "tighter spacing")

    approver = TerminalApprover(input_fn=lambda _: "s", print_fn=lambda *_: None)
    assert approver.decide(_view(tmp_path, ["main"])).action == "stop"
