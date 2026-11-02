import json
from pathlib import Path

import pytest

from agentflow import Orchestrator, load_agents, load_workflow
from agentflow.agent import AgentError, AgentRunner
from agentflow.orchestrator import WorkflowError
from agentflow.workspace import Workspace
from fakes import FakeClient, message, text, tool_call

ROOT = Path(__file__).parent.parent
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def design_workflow():
    wf = load_workflow(ROOT / "workflows" / "design_only.yaml")
    return wf, load_agents(wf.agents_dir)


def finish(files, summary="done", notes="none"):
    return message(tool_call("complete_task", summary=summary, files=files, notes_for_next_agent=notes))


def review(verdict, issues=()):
    return message(tool_call("submit_review", verdict=verdict, summary=f"{verdict}!", issues=list(issues)))


ISSUE = {"severity": "major", "location": "design/pages/home.html", "problem": "low contrast", "fix": "darken text"}


def test_design_review_loop_revises_until_approved(tmp_path):
    ref = tmp_path / "moodboard.png"
    ref.write_bytes(PNG)
    client = FakeClient(
        {
            "ux_designer": [
                message(tool_call("write_file", path="design/pages/home.html", content="<h1 style='color:#aaa'>Hi</h1>")),
                finish(["design/pages/home.html"], summary="first pass"),
                message(
                    tool_call("edit_file", path="design/pages/home.html", old_str="#aaa", new_str="#222"),
                ),
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
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path / "runs", printer=lambda *_: None)
    result = orch.run({"brief": "A landing page", "references": str(ref)}, base_dir=tmp_path, run_id="t1")

    assert result.status == "done"
    assert (result.workspace / "design/pages/home.html").read_text() == "<h1 style='color:#222'>Hi</h1>"
    # Reference image staged into the workspace for later agents.
    assert (result.workspace / "inputs/references/moodboard.png").exists()

    step = result.steps[0]
    assert step.status == "done" and step.rounds == 2
    assert [r.verdict for r in step.reviews] == ["revise", "approve"]
    assert step.result.summary == "fixed contrast"

    # The designer saw the image and the brief in its first message.
    first = client.calls_for("ux_designer")[0]
    content = first["messages"][0]["content"]
    assert any(b["type"] == "image" for b in content)
    assert any("A landing page" in b.get("text", "") for b in content)
    # Feedback was appended to the designer's own conversation (append-only).
    revision_call = client.calls_for("ux_designer")[2]
    feedback = revision_call["messages"][-1]["content"][0]["text"]
    assert "low contrast" in feedback and "darken text" in feedback

    # The reviewer received the hand-off as its `work` input; round 2 is a fresh conversation.
    reviewer_calls = client.calls_for("design_reviewer")
    assert any("Work to review" in b.get("text", "") for b in reviewer_calls[0]["messages"][0]["content"])
    assert "fixed contrast" in json.dumps(reviewer_calls[2]["messages"][0]["content"])
    assert len(reviewer_calls[2]["messages"]) == 1

    # Request shape: adaptive thinking, effort, caching, fallbacks.
    assert first["thinking"] == {"type": "adaptive"}
    assert first["output_config"] == {"effort": "high"}
    assert first["cache_control"] == {"type": "ephemeral"}
    assert first["fallbacks"] == "default" and first["betas"] == ["server-side-fallback-2026-07-01"]
    assert {t["name"] for t in first["tools"]} >= {"write_file", "complete_task"}

    state = json.loads((result.run_dir / "run.json").read_text())
    assert state["status"] == "done"
    assert state["steps"][0]["usage"]["requests"] == 7
    assert len(list((result.run_dir / "transcripts").iterdir())) == 4


def test_rejected_review_can_fail_the_run(tmp_path):
    client = FakeClient(
        {
            "ux_designer": [
                message(tool_call("write_file", path="a.html", content="x")),
                finish(["a.html"]),
            ],
            "design_reviewer": [review("revise", [ISSUE])],
        }
    )
    wf, agents = design_workflow()
    wf.steps[0].review.max_rounds = 1
    wf.steps[0].review.on_reject = "fail"
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path, printer=lambda *_: None)
    with pytest.raises(WorkflowError, match="not approved"):
        orch.run({"brief": "x"}, run_id="t2")
    state = json.loads((tmp_path / "t2" / "run.json").read_text())
    assert state["status"] == "failed" and state["steps"][0]["status"] == "failed"


def test_handoff_flows_between_steps(tmp_path):
    wf = load_workflow(ROOT / "workflows" / "webapp.yaml")
    agents = load_agents(wf.agents_dir)
    client = FakeClient(
        {
            "product_planner": [
                message(tool_call("write_file", path="docs/spec.md", content="# Spec")),
                finish(["docs/spec.md"], summary="SPEC-SUMMARY", notes="mind the streaks"),
            ],
            "ux_designer": [message(tool_call("write_file", path="design/tokens.css", content=":root{}")), finish(["design/tokens.css"])],
            "design_reviewer": [review("approve")],
            "frontend_engineer": [message(tool_call("write_file", path="app/index.html", content="<html>")), finish(["app/index.html"])],
            "code_reviewer": [review("approve")],
            "qa_tester": [message(tool_call("write_file", path="qa/report.md", content="ok")), finish(["qa/report.md"])],
        }
    )
    orch = Orchestrator(wf, agents, client=client, runs_dir=tmp_path, printer=lambda *_: None)
    result = orch.run({"brief": "habit tracker"}, run_id="t3")
    assert result.status == "done"

    designer_msg = json.dumps(client.calls_for("ux_designer")[0]["messages"][0]["content"])
    assert "SPEC-SUMMARY" in designer_msg and "mind the streaks" in designer_msg and "docs/spec.md" in designer_msg
    # The engineer's `stack` was not given, so the agent's default is used.
    engineer_msg = json.dumps(client.calls_for("frontend_engineer")[0]["messages"][0]["content"])
    assert "Vanilla HTML" in engineer_msg
    assert "approved after 1 round" in engineer_msg


def _runner(tmp_path, responses, role="producer"):
    wf, agents = design_workflow()
    spec = agents["ux_designer" if role == "producer" else "design_reviewer"]
    client = FakeClient({spec.name: responses})
    return AgentRunner(spec, client, Workspace(tmp_path)), client


def test_agent_rejects_handoff_listing_missing_files(tmp_path):
    runner, client = _runner(
        tmp_path,
        [
            finish(["ghost.html"]),
            message(tool_call("write_file", path="ghost.html", content="boo")),
            finish(["ghost.html"]),
        ],
    )
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
        tmp_path,
        [
            message(tool_call("write_file", path="a.html")),  # missing content
            message(tool_call("write_file", path="a.html", content="ok")),
            finish(["a.html"]),
        ],
    )
    runner.start([{"type": "text", "text": "go"}])
    bad = client.calls_for("ux_designer")[1]["messages"][-1]["content"][0]
    assert bad["is_error"] and "INVALID_INPUT" in bad["content"]


def test_agent_retries_truncated_tool_call_with_more_tokens(tmp_path):
    runner, client = _runner(
        tmp_path,
        [
            message(tool_call("write_file", path="a.html", content="trunc"), stop_reason="max_tokens"),
            message(tool_call("write_file", path="a.html", content="full")),
            finish(["a.html"]),
        ],
    )
    runner.start([{"type": "text", "text": "go"}])
    calls = client.calls_for("ux_designer")
    assert calls[1]["max_tokens"] == 2 * calls[0]["max_tokens"]
    assert (tmp_path / "a.html").read_text() == "full"  # truncated call never ran


def test_agent_retries_unparseable_stream(tmp_path):
    runner, _ = _runner(tmp_path, [ValueError("bad json"), message(tool_call("write_file", path="a", content="x")), finish(["a"])])
    assert runner.start([{"type": "text", "text": "go"}]).files == ["a"]


def test_refusal_raises(tmp_path):
    runner, _ = _runner(tmp_path, [message(text(""), stop_reason="refusal")])
    with pytest.raises(AgentError, match="declined"):
        runner.start([{"type": "text", "text": "go"}])


def test_missing_required_workflow_input(tmp_path):
    wf, agents = design_workflow()
    orch = Orchestrator(wf, agents, client=FakeClient({}), runs_dir=tmp_path, printer=lambda *_: None)
    from agentflow.inputs import InputError

    with pytest.raises(InputError, match="brief"):
        orch.run({})
