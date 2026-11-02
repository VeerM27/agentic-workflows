from pathlib import Path

import pytest

from agentflow.config import ConfigError, load_agent, load_agents, load_workflow, validate_workflow

ROOT = Path(__file__).parent.parent


@pytest.mark.parametrize("name", ["webapp.yaml", "design_only.yaml"])
def test_bundled_workflows_are_valid(name):
    wf = load_workflow(ROOT / "workflows" / name)
    assert validate_workflow(wf, load_agents(wf.agents_dir)) == []


def test_bundled_agents_load():
    agents = load_agents(ROOT / "agents")
    assert {"product_planner", "ux_designer", "design_reviewer"} <= set(agents)
    assert agents["design_reviewer"].role == "reviewer"
    assert agents["ux_designer"].inputs["references"].type == "images"


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_agent_rejects_unknown_tool(tmp_path):
    p = _write(tmp_path, "a.yaml", "name: a\nsystem_prompt: hi\ntools: [read_file, launch_rockets]\n")
    with pytest.raises(ConfigError, match="launch_rockets"):
        load_agent(p)


def test_agent_rejects_bad_input_type(tmp_path):
    p = _write(tmp_path, "a.yaml", "name: a\nsystem_prompt: hi\ninputs:\n  x: video\n")
    with pytest.raises(ConfigError, match="unknown type"):
        load_agent(p)


def test_validation_catches_reference_and_argument_errors(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write(agents_dir, "maker.yaml", "name: maker\nsystem_prompt: make\ninputs:\n  brief: {type: text, required: true}\n")
    _write(agents_dir, "checker.yaml", "name: checker\nrole: reviewer\nsystem_prompt: check\n")
    wf_path = _write(
        tmp_path,
        "wf.yaml",
        """
name: wf
agents_dir: agents
inputs:
  brief: text
steps:
  - id: one
    agent: maker
    inputs:
      brief: ${inputs.nope}
      colour: red
    review: maker
  - id: two
    agent: maker
    inputs:
      brief: ${steps.three.summary} and ${steps.one.bogus}
""",
    )
    wf = load_workflow(wf_path)
    problems = "\n".join(validate_workflow(wf, load_agents(agents_dir)))
    assert "unknown workflow input '${inputs.nope}'" in problems
    assert "has no input 'colour'" in problems
    assert "must have role 'reviewer'" in problems
    assert "does not refer to an earlier step" in problems
    assert "unknown step field 'bogus'" in problems


def test_missing_required_argument(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write(agents_dir, "maker.yaml", "name: maker\nsystem_prompt: make\ninputs:\n  brief: {type: text, required: true}\n")
    wf_path = _write(tmp_path, "wf.yaml", "name: wf\nagents_dir: agents\nsteps:\n  - agent: maker\n")
    wf = load_workflow(wf_path)
    assert any("required input 'brief'" in p for p in validate_workflow(wf, load_agents(agents_dir)))
