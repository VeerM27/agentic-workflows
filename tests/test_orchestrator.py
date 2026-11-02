import json
from pathlib import Path

import pytest

from agentflow import (
    AutoApprover,
    Decision,
    Orchestrator,
    PauseApprover,
    ScriptedApprover,
    load_agents,
    load_workflow,
)
from agentflow.agent import AgentError, AgentRunner
from agentflow.orchestrator import WorkflowError
from agentflow.workspace import Workspace
from fakes import FakeClient, message, text, tool_call

ROOT = Path(__file__).parent.parent
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
ISSUE = {"severity": "major", "location": "design/pages/home.html", "problem": "low contrast", "fix": "darken text"}
QUIET = {"printer": lambda *_: None}


def design_workflow():
    wf = load_workflow(ROOT / "workflows" / "design_only.yaml")
    return wf, load_agents(wf.agents_dir)


def finish(files, summary="done", notes="none"):
    return message(tool_call("complete_task", summary=summary, files=files, notes_for_next_agent=notes))


def review(verdict, issues=()):
    return message(tool_call("submit_review", verdict=verdict, summary=f"{verdict}!", issues=list(issues)))


def write(path, content):
    return message(tool_call("write_file", path=path, content=content))


def test_design_review_loop_revises_until_approved(tmp_path):
    ref = tmp_path / "moodboard.png"
    ref.write_bytes(PNG)
    client = FakeClient(
        {
            "ux_designer": [
                write("design/pages/home.html", "<h1 style='color:#aaa'>Hi</h1>"),
                finish(["design/pages/home.html"], summary="first pass"),
                message(tool_call("edit_file", path="design/pages/home.html", old_str="#aaa", new_str="#222")),
                finish(["design/pages/home.html"], summary="fixed contrast"),
            ],
            "design_reviewer": [
                message(tool_call("read_file", path="design/pages/home.html")),
                review("revise", [ISSUE]),
                review("approve"),
            ],
        }
    )
    wf, agents = design_workflow()
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path / "runs", approver=AutoApprover(), **QUIET)
    result = orch.run(
        {"brief": "A landing page", "references": str(ref), "industry": "fintech"}, base_dir=tmp_path, run_id="t1"
    )

    assert result.status == "done"
    assert (result.workspace / "design/pages/home.html").read_text() == "<h1 style='color:#222'>Hi</h1>"
    assert (result.workspace / "inputs/references/moodboard.png").exists()

    step = result.steps[0]
    assert step.status == "done" and step.rounds == 2
    assert [r.verdict for r in step.reviews] == ["revise", "approve"]
    assert step.result.summary == "fixed contrast"

    first = client.calls_for("ux_designer")[0]
    content = first["messages"][0]["content"]
    assert any(b["type"] == "image" for b in content)
    assert any("A landing page" in b.get("text", "") for b in content)
    # The fintech industry profile was loaded from profiles/industries.
    assert "Fintech & personal finance" in json.dumps(content)

    revision_call = client.calls_for("ux_designer")[2]
    feedback = revision_call["messages"][-1]["content"][0]["text"]
    assert "low contrast" in feedback and "darken text" in feedback

    reviewer_calls = client.calls_for("design_reviewer")
    assert any("Work to review" in b.get("text", "") for b in reviewer_calls[0]["messages"][0]["content"])
    assert "fixed contrast" in json.dumps(reviewer_calls[2]["messages"][0]["content"])
    assert len(reviewer_calls[2]["messages"]) == 1

    # Request shape: model from agentflow.yaml alias, adaptive thinking, caching, fallbacks.
    assert first["model"] == "claude-opus-5-5"
    assert first["thinking"] == {"type": "adaptive"}
    assert first["output_config"] == {"effort": "high"}
    assert first["cache_control"] == {"type": "ephemeral"}
    assert first["fallbacks"] == "default" and first["betas"] == ["server-side-fallback-2026-07-01"]
    # Skills and house style are in the system prompt, plus the skill-file tool.
    assert "## Skill: frontend-design" in first["system"]
    assert "# House style" in first["system"]
    assert "read_skill_file" in {t["name"] for t in first["tools"]}

    state = json.loads((result.run_dir / "run.json").read_text())
    assert state["status"] == "done"
    assert state["skills"]["frontend-design"] != "local"
    assert state["steps"][0]["lanes"][0]["usage"]["requests"] == 7


def test_rejected_review_can_fail_the_run(tmp_path):
    client = FakeClient({"ux_designer": [write("a.html", "x"), finish(["a.html"])], "design_reviewer": [review("revise", [ISSUE])]})
    wf, agents = design_workflow()
    wf.steps[0].review.max_rounds = 1
    wf.steps[0].review.on_reject = "fail"
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path, approver=AutoApprover(), **QUIET)
    with pytest.raises(WorkflowError, match="not approved"):
        orch.run({"brief": "x"}, run_id="t2")
    state = json.loads((tmp_path / "t2" / "run.json").read_text())
    assert state["status"] == "failed" and state["steps"][0]["status"] == "failed"


def webapp_script(**overrides):
    script = {
        "product_planner": [write("docs/spec.md", "# Spec"), finish(["docs/spec.md"], summary="SPEC-SUMMARY", notes="mind the streaks")],
        "ux_designer": [write("design/tokens.css", ":root{}"), finish(["design/tokens.css"])],
        "design_reviewer": [review("approve")],
        "frontend_engineer": [write("app/index.html", "<html>"), finish(["app/index.html"])],
        "code_reviewer": [review("approve")],
        "qa_tester": [write("qa/report.md", "ok"), finish(["qa/report.md"])],
    }
    script.update(overrides)
    return script


def test_handoff_flows_between_steps(tmp_path):
    wf = load_workflow(ROOT / "workflows" / "webapp.yaml")
    client = FakeClient(webapp_script())
    orch = Orchestrator(wf, client=client, runs_dir=tmp_path, approver=AutoApprover(), **QUIET)
    result = orch.run({"brief": "habit tracker", "industry": "artisan bakery"}, run_id="t3")
    assert result.status == "done"

    designer_msg = json.dumps(client.calls_for("ux_designer")[0]["messages"][0]["content"])
    assert "SPEC-SUMMARY" in designer_msg and "mind the streaks" in designer_msg and "docs/spec.md" in designer_msg
    assert "artisan bakery" in designer_msg  # free-text industry passes through
    engineer_msg = json.dumps(client.calls_for("frontend_engineer")[0]["messages"][0]["content"])
    assert "house style" in engineer_msg.lower()  # the `stack` default
    assert "approved after 1 round" in engineer_msg


def test_human_feedback_at_checkpoint_goes_to_producer_then_reviewer(tmp_path):
    client = FakeClient(
        {
            "ux_designer": [
                write("p.html", "small hero"), finish(["p.html"], summary="v-one"),
                write("p.html", "BIG hero"), finish(["p.html"], summary="v-two"),
            ],
            "design_reviewer": [review("approve"), review("approve")],
        }
    )
    wf, agents = design_workflow()
    approver = ScriptedApprover([Decision("revise", None, "make the hero much bigger"), Decision("approve")], AutoApprover())
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path, approver=approver, **QUIET)
    result = orch.run({"brief": "x"}, run_id="h1")

    assert result.status == "done"
    assert (result.workspace / "p.html").read_text() == "BIG hero"
    calls = client.calls_for("ux_designer")
    assert "make the hero much bigger" in calls[2]["messages"][-1]["content"][0]["text"]
    assert len(calls[2]["messages"]) > 1  # same conversation, context kept
    assert len(client.calls_for("design_reviewer")) == 2  # reviewer re-checked after the human change
    rec = result.steps[0]
    assert rec.approved_by == "human"
    assert "make the hero much bigger" in rec.handoff()
    assert (result.run_dir / "checkpoints" / "design.html").exists()


def test_pause_then_resume_with_feedback_and_approval(tmp_path):
    wf = load_workflow(ROOT / "workflows" / "webapp.yaml")
    wf.checkpoints = ["spec"]  # only the spec step asks the human
    first = FakeClient({"product_planner": [write("docs/spec.md", "# v1"), finish(["docs/spec.md"], summary="first spec")]})
    orch = Orchestrator(wf, client=first, runs_dir=tmp_path, approver=PauseApprover(), **QUIET)
    paused = orch.run({"brief": "habit tracker"}, run_id="p1")

    assert paused.status == "paused"
    state = json.loads((tmp_path / "p1" / "run.json").read_text())
    assert state["status"] == "paused" and state["steps"][0]["status"] == "awaiting_approval"
    assert (tmp_path / "p1" / "state" / "spec.main.json").exists()

    # Later, in a new process: ask for a change, then (after it) approve automatically.
    second = FakeClient(
        webapp_script(product_planner=[write("docs/spec.md", "# v2 with streaks"), finish(["docs/spec.md"], summary="second spec")])
    )
    done = Orchestrator.resume(
        tmp_path / "p1",
        decisions=[Decision("revise", None, "add streak tracking")],
        approval_mode="auto",
        client=second,
        **QUIET,
    )
    assert done.status == "done"
    planner_call = second.calls_for("product_planner")[0]
    # The restored conversation includes the first round, then the human's request.
    assert len(planner_call["messages"]) == 6
    assert "add streak tracking" in planner_call["messages"][-1]["content"][0]["text"]
    assert (done.workspace / "docs/spec.md").read_text() == "# v2 with streaks"
    assert [s.status for s in done.steps] == ["done"] * 4
    with pytest.raises(WorkflowError, match="already finished"):
        Orchestrator.resume(tmp_path / "p1", client=second, **QUIET)


def test_variants_run_in_isolated_workspaces_and_the_chosen_one_is_adopted(tmp_path):
    client = FakeClient(
        {
            "ux_designer@v1": [write("design/home.html", "one"), finish(["design/home.html"], summary="design v1")],
            "ux_designer@v2": [write("design/home.html", "two"), finish(["design/home.html"], summary="design v2")],
            "ux_designer@v3": [write("design/home.html", "three"), finish(["design/home.html"], summary="design v3")],
            "design_reviewer": [review("approve")] * 3,
        }
    )
    wf, agents = design_workflow()
    approver = ScriptedApprover([Decision("approve", "v2")], AutoApprover())
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path, approver=approver, **QUIET)
    result = orch.run({"brief": "x", "variants": 3, "directions": "Brutalist\nPastel"}, run_id="v")

    rec = result.steps[0]
    assert [lane.key for lane in rec.lanes] == ["v1", "v2", "v3"]
    assert rec.chosen == "v2"
    assert (result.workspace / "design/home.html").read_text() == "two"
    for k, content in (("v1", "one"), ("v3", "three")):
        assert (result.run_dir / "variants" / "design" / k / "design/home.html").read_text() == content
    # Given directions first, then built-in ones.
    assert rec.lanes[0].direction == "Brutalist" and rec.lanes[1].direction == "Pastel"
    assert rec.lanes[2].direction.startswith("Minimal and editorial")
    prompt = json.dumps(client.calls_for("ux_designer@v2")[0]["messages"][0]["content"])
    assert "variant v2 of 3" in prompt and "Pastel" in prompt
    assert "Variant v2 of 3 was chosen" in rec.handoff()
    gallery = (result.run_dir / "checkpoints" / "design.html").read_text()
    assert gallery.count("<iframe") == 3


def test_failed_variant_does_not_sink_the_others(tmp_path):
    client = FakeClient(
        {
            "ux_designer@v1": [message(text(""), stop_reason="refusal")],
            "ux_designer@v2": [write("a.html", "ok"), finish(["a.html"])],
            "design_reviewer": [review("approve")],
        }
    )
    wf, agents = design_workflow()
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path, approver=AutoApprover(), **QUIET)
    result = orch.run({"brief": "x", "variants": 2}, run_id="f")
    rec = result.steps[0]
    assert rec.lanes[0].status == "failed" and rec.chosen == "v2"


def test_checkpoints_none_never_asks(tmp_path):
    client = FakeClient({"ux_designer": [write("a.html", "x"), finish(["a.html"])], "design_reviewer": [review("approve")]})
    wf, agents = design_workflow()
    wf.checkpoints = "none"
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path, approver=PauseApprover(), **QUIET)
    assert orch.run({"brief": "x"}, run_id="n").status == "done"


# --- single agent behaviour ---------------------------------------------------------------


def _runner(tmp_path, responses, role="producer"):
    wf, agents = design_workflow()
    spec = agents["ux_designer" if role == "producer" else "design_reviewer"]
    client = FakeClient({spec.name: responses})
    return AgentRunner(spec, client, Workspace(tmp_path)), client


def test_agent_rejects_handoff_listing_missing_files(tmp_path):
    runner, client = _runner(tmp_path, [finish(["ghost.html"]), write("ghost.html", "boo"), finish(["ghost.html"])])
    result = runner.start([{"type": "text", "text": "go"}])
    assert result.files == ["ghost.html"]
    error_result = client.calls_for("ux_designer")[1]["messages"][-1]["content"][0]
    assert error_result["is_error"] and "not in the workspace" in error_result["content"]


def test_agent_nudges_then_gives_up_without_terminal_tool(tmp_path):
    runner, _ = _runner(tmp_path, [message(text("thinking aloud"))] * 3)
    with pytest.raises(AgentError, match="without calling `complete_task`"):
        runner.start([{"type": "text", "text": "go"}])


def test_agent_returns_invalid_input_as_tool_error(tmp_path):
    runner, client = _runner(
        tmp_path, [message(tool_call("write_file", path="a.html")), write("a.html", "ok"), finish(["a.html"])]
    )
    runner.start([{"type": "text", "text": "go"}])
    bad = client.calls_for("ux_designer")[1]["messages"][-1]["content"][0]
    assert bad["is_error"] and "INVALID_INPUT" in bad["content"]


def test_agent_cannot_use_tools_it_was_not_given(tmp_path):
    runner, client = _runner(tmp_path, [message(tool_call("delete_file", path="x")), finish([])])
    runner.start([{"type": "text", "text": "go"}])
    result = client.calls_for("ux_designer")[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "do not have the tool" in result["content"]


def test_agent_retries_truncated_tool_call_with_more_tokens(tmp_path):
    runner, client = _runner(
        tmp_path,
        [
            message(tool_call("write_file", path="a.html", content="trunc"), stop_reason="max_tokens"),
            write("a.html", "full"),
            finish(["a.html"]),
        ],
    )
    runner.start([{"type": "text", "text": "go"}])
    calls = client.calls_for("ux_designer")
    assert calls[1]["max_tokens"] == 2 * calls[0]["max_tokens"]
    assert (tmp_path / "a.html").read_text() == "full"


def test_agent_retries_unparseable_stream(tmp_path):
    runner, _ = _runner(tmp_path, [ValueError("bad json"), write("a", "x"), finish(["a"])])
    assert runner.start([{"type": "text", "text": "go"}]).files == ["a"]


def test_refusal_raises(tmp_path):
    runner, _ = _runner(tmp_path, [message(text(""), stop_reason="refusal")])
    with pytest.raises(AgentError, match="declined"):
        runner.start([{"type": "text", "text": "go"}])


def test_missing_required_workflow_input(tmp_path):
    wf, agents = design_workflow()
    orch = Orchestrator(wf, agents, client=FakeClient({}), runs_dir=tmp_path, approver=AutoApprover(), **QUIET)
    from agentflow.inputs import InputError

    with pytest.raises(InputError, match="brief"):
        orch.run({})
