"""The Claude Code (subscription) backend, the scroll-landing workflow, fixes routing and the skill audit.

Everything runs against tests/fake_claude.py; no API or subscription usage.
"""

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from agentflow import AutoApprover, Decision, Orchestrator, PauseApprover, ScriptedApprover, load_agents, load_workflow
from agentflow.agent import AgentError
from agentflow.backends.claude_code import ClaudeCodeRunner, UsageLimitReached
from agentflow.project import load_project
from agentflow.workspace import Workspace

ROOT = Path(__file__).parent.parent
QUIET = {"printer": lambda *_: None}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Install the fake CLI. Returns (set_script, calls) helpers."""
    exe = Path(__file__).parent / "fake_claude.py"
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    wrapper = tmp_path / "claude"
    wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {exe} \"$@\"\n")
    wrapper.chmod(0o755)
    script, state, log = tmp_path / "script.json", tmp_path / "state.json", tmp_path / "log.jsonl"
    monkeypatch.setenv("AGENTFLOW_CLAUDE_BIN", str(wrapper))
    monkeypatch.setenv("FAKE_CLAUDE_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_CLAUDE_STATE", str(state))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-reach-claude-code")

    class Fake:
        def script(self, data):
            script.write_text(json.dumps(data))
            if state.exists():
                state.unlink()

        def calls(self, agent=None):
            if not log.exists():
                return []
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            return [r for r in rows if agent is None or r["agent"] == agent]

    return Fake()


def done(files=None, summary="done", notes="-", write=None):
    return {"write": write or {}, "handoff": {"summary": summary, "files": files or list((write or {}).keys()), "notes_for_next_agent": notes}}


def verdict(v="approve", issues=None, summary=None):
    return {"handoff": {"verdict": v, "summary": summary or f"{v}!", "issues": issues or []}}


ISSUE = {"severity": "major", "location": "site/index.html", "problem": "hero image has no alt text", "fix": "add alt"}


def cc_project(tmp_path):
    project = load_project(ROOT / "agentflow.yaml")
    assert project.backend == "claude-code"
    project.root = tmp_path  # keeps the audit cache out of the repo
    project.runs_dir = tmp_path / "runs"
    return project


# --- the runner ---------------------------------------------------------------------------


def test_runner_uses_subscription_session_and_resumes(tmp_path, fake_claude):
    agents = load_agents(ROOT / "agents")
    fake_claude.script({"landing_coder": [
        done(write={"site/index.html": "<h1>v1</h1>"}, summary="built"),
        done(write={"site/index.html": "<h1>v2</h1>"}, summary="fixed"),
    ]})
    ws = Workspace(tmp_path / "ws")
    from agentflow.skills import SkillLibrary

    library = SkillLibrary(ROOT / "skills" / "skills.yaml")
    spec = agents["landing_coder"]
    runner = ClaudeCodeRunner(spec, None, ws, model="claude-opus-5-5", effort="high",
                              skills=[library.get(n) for n in spec.skills])
    result = runner.start([{"type": "text", "text": "build it"},
                           {"type": "image", "source": {"type": "workspace", "path": "inputs/photos/shoe.jpg"}}])
    assert result.summary == "built" and result.files == ["site/index.html"]
    runner.follow_up("make it v2")
    assert (ws.root / "site/index.html").read_text() == "<h1>v2</h1>"

    first, second = fake_claude.calls("landing_coder")
    assert first["new_session"] and not second["new_session"] and first["session"] == second["session"]
    assert first["cwd"] == str(ws.root)
    assert not first["api_key_present"]  # API key stripped: the subscription is used
    argv = first["argv"]
    for flag in ("--restricted", "--json-schema", "--append-system-prompt", "--permission-prompts"):
        assert flag in argv
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert "Write" in argv[argv.index("--tools") + 1]
    assert "Bash(agentflow screenshot *)" in argv[argv.index("--allowedTools") + 1]
    assert "Bash(agentflow image *)" in argv[argv.index("--allowedTools") + 1]
    assert "agentflow image export" in argv[argv.index("--append-system-prompt") + 1]
    assert "Open `inputs/photos/shoe.jpg` with the Read tool" in first["prompt"]
    # skills: preloaded in the system prompt, folders readable
    system = argv[argv.index("--append-system-prompt") + 1]
    assert "## Skill: svg-scroll-animation" in system
    assert argv.count("--add-dir") == 2
    assert runner.transcript()["session_id"] == first["session"]


def test_reviewer_cannot_write(tmp_path, fake_claude):
    agents = load_agents(ROOT / "agents")
    fake_claude.script({"security_reviewer": [verdict()]})
    runner = ClaudeCodeRunner(agents["security_reviewer"], None, Workspace(tmp_path))
    runner.start([{"type": "text", "text": "review"}])
    argv = fake_claude.calls()[0]["argv"]
    assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep,Bash"
    allowed = argv[argv.index("--allowedTools") + 1]
    assert "Bash(agentflow image info *)" in allowed and "Bash(agentflow image *)" not in allowed
    assert "agentflow image export" not in argv[argv.index("--append-system-prompt") + 1]


def test_invalid_handoff_is_corrected_in_the_same_session(tmp_path, fake_claude):
    agents = load_agents(ROOT / "agents")
    fake_claude.script({"landing_coder": [done(files=["site/missing.html"]), done(write={"site/ok.html": "ok"})]})
    runner = ClaudeCodeRunner(agents["landing_coder"], None, Workspace(tmp_path))
    assert runner.start([{"type": "text", "text": "go"}]).files == ["site/ok.html"]
    calls = fake_claude.calls()
    assert "not in the workspace" in calls[1]["prompt"] and calls[1]["session"] == calls[0]["session"]


def test_absolute_paths_in_handoff_are_made_relative(tmp_path, fake_claude):
    agents = load_agents(ROOT / "agents")
    ws = Workspace(tmp_path / "ws")
    fake_claude.script({"landing_coder": [
        {"write": {"site/index.html": "x"}, "handoff": {"summary": "s", "files": [str(ws.root / "site/index.html")],
                                                        "notes_for_next_agent": "-"}},
    ]})
    result = ClaudeCodeRunner(agents["landing_coder"], None, ws).start([{"type": "text", "text": "go"}])
    assert result.files == ["site/index.html"]
    assert len(fake_claude.calls()) == 1  # accepted first time, no correction round


def test_usage_limit_is_recognised(tmp_path, fake_claude):
    agents = load_agents(ROOT / "agents")
    fake_claude.script({"landing_coder": [{"error": "Claude AI usage limit reached. Your limit resets at 5pm."}]})
    runner = ClaudeCodeRunner(agents["landing_coder"], None, Workspace(tmp_path))
    with pytest.raises(UsageLimitReached):
        runner.start([{"type": "text", "text": "go"}])


def test_other_failures_are_agent_errors(tmp_path, fake_claude):
    agents = load_agents(ROOT / "agents")
    fake_claude.script({"landing_coder": [{"error": "something broke"}]})
    with pytest.raises(AgentError) as exc:
        ClaudeCodeRunner(agents["landing_coder"], None, Workspace(tmp_path)).start([{"type": "text", "text": "go"}])
    assert not isinstance(exc.value, UsageLimitReached)


# --- the scroll landing workflow ---------------------------------------------------------------


def landing_script(**overrides):
    script = {
        "skill_auditor": [verdict("approve", summary="Skills look fine")],
        "brief_reviewer": [done(write={"docs/brief.md": "# Brief", "docs/brief-review.md": "# Review"}, summary="brief refined")],
        "planner": [done(write={"docs/plan.md": "# Plan\n## Designer\n## Coder"}, summary="PLAN-SUMMARY")],
        "landing_designer": [done(write={"design/tokens.css": ":root{}", "design/frames/stage-1.html": "<p>1</p>"})],
        "landing_coder": [
            done(write={"site/index.html": "<img src=hero.jpg>"}, summary="built page"),
            done(write={"site/index.html": "<img src=hero.jpg alt='Trail shoe'>"}, summary="added alt text"),
        ],
        "page_checker": [verdict("revise", [ISSUE]), verdict("approve")],
        "security_reviewer": [verdict("approve", summary="No issues; CSP: default-src 'self'")],
        "final_reviewer": [verdict("approve", summary="Ready to publish")],
    }
    script.update(overrides)
    return script


def test_scroll_landing_end_to_end_with_fix_routing(tmp_path, fake_claude):
    photo = tmp_path / "shoe.jpg"
    photo.write_bytes(b"\xff\xd8\xff fake jpeg")
    fake_claude.script(landing_script())
    wf = load_workflow(ROOT / "workflows" / "scroll_landing.yaml")
    decisions = [Decision("approve")] * 5 + [Decision("revise", None, "all")]  # preflight, 4 steps, then fix at check
    out = []
    orch = Orchestrator(wf, project=cc_project(tmp_path), approver=ScriptedApprover(decisions, AutoApprover()),
                        printer=out.append)
    result = orch.run({"idea": "Shoe built from materials as you scroll", "photos": str(photo)}, base_dir=tmp_path, run_id="r")

    assert result.status == "done"
    ws = result.workspace
    assert (ws / "site/index.html").read_text() == "<img src=hero.jpg alt='Trail shoe'>"
    assert (ws / "inputs/photos/shoe.jpg").exists()

    # Pipeline order, with the skill audit first.
    order = [c["agent"] for c in fake_claude.calls()]
    assert order[:6] == ["skill_auditor", "brief_reviewer", "planner", "landing_designer", "landing_coder", "page_checker"]
    # The fix went to the coder's own session (resumed), then the checker ran again.
    coder = fake_claude.calls("landing_coder")
    assert len(coder) == 2 and not coder[1]["new_session"] and coder[1]["session"] == coder[0]["session"]
    assert "hero image has no alt text" in coder[1]["prompt"] and "Fix every issue in the report" in coder[1]["prompt"]
    checker = fake_claude.calls("page_checker")
    assert len(checker) == 2 and checker[1]["new_session"] and "re-check" in checker[1]["prompt"]
    # Later agents see the updated build hand-off.
    final_prompt = fake_claude.calls("final_reviewer")[0]["prompt"]
    assert "added alt text" in final_prompt and "PLAN-SUMMARY" in final_prompt
    # Reports and models.
    assert "approve" in (ws / "reports/check.md").read_text() and "Fixes requested so far" in (ws / "reports/check.md").read_text()
    assert (ws / "reports/security.md").exists()
    models = {c["agent"]: c["argv"][c["argv"].index("--model") + 1] for c in fake_claude.calls()}
    assert models["landing_coder"] == "claude-opus-5-5" and models["page_checker"] == "claude-sonnet-5-5"
    assert all(not c["api_key_present"] for c in fake_claude.calls())
    assert any("agentflow serve" in line for line in out)
    # Claude Code's reported cost (0.01 per call in the fake) is summed and shown.
    calls = len(fake_claude.calls())
    assert result.usage.cost_usd == pytest.approx(0.01 * calls)
    assert any(f"≈ ${0.01 * calls:,.2f} at API list prices" in line for line in out)
    state = json.loads((result.run_dir / "run.json").read_text())
    assert state["preflight"]["status"] == "done"
    assert state["steps"][4]["lanes"][0]["human_feedback"] == ["Fix every issue in the report."]


def test_skill_audit_is_skipped_when_nothing_changed(tmp_path, fake_claude):
    fake_claude.script(landing_script())
    wf = load_workflow(ROOT / "workflows" / "scroll_landing.yaml")
    project = cc_project(tmp_path)
    Orchestrator(wf, project=project, approver=AutoApprover(), **QUIET).run({"idea": "x"}, run_id="a")
    fake_claude.script(landing_script(page_checker=[verdict("approve")]))
    Orchestrator(wf, project=project, approver=AutoApprover(), **QUIET).run({"idea": "x"}, run_id="b")
    assert [c["agent"] for c in fake_claude.calls()].count("skill_auditor") == 1


def test_usage_limit_pauses_and_resume_continues_the_same_session(tmp_path, fake_claude):
    fake_claude.script(landing_script(
        landing_designer=[{"error": "You've hit your usage limit · resets 5pm"},
                          done(write={"design/tokens.css": ":root{}"}, summary="designed after reset")],
        page_checker=[verdict("approve")],
    ))
    wf = load_workflow(ROOT / "workflows" / "scroll_landing.yaml")
    out = []
    paused = Orchestrator(wf, project=cc_project(tmp_path), approver=AutoApprover(), printer=out.append).run(
        {"idea": "x"}, run_id="u")
    assert paused.status == "paused"
    assert any("usage limit was reached" in line for line in out)
    state = json.loads((paused.run_dir / "run.json").read_text())
    assert [s["status"] for s in state["steps"]][:3] == ["done", "done", "interrupted"]

    done_run = Orchestrator.resume(paused.run_dir, project=cc_project(tmp_path), approval_mode="auto", **QUIET)
    assert done_run.status == "done"
    designer = fake_claude.calls("landing_designer")
    assert len(designer) == 2 and not designer[1]["new_session"] and designer[1]["session"] == designer[0]["session"]
    assert "interrupted" in designer[1]["prompt"]


def test_pause_mode_at_a_report_step_then_send_fixes_on_resume(tmp_path, fake_claude):
    fake_claude.script(landing_script())
    wf = load_workflow(ROOT / "workflows" / "scroll_landing.yaml")
    decisions = [Decision("approve")] * 5  # preflight + 4 steps; then pause at `check`
    paused = Orchestrator(wf, project=cc_project(tmp_path), approver=ScriptedApprover(decisions, PauseApprover()),
                          **QUIET).run({"idea": "x"}, run_id="p")
    assert paused.status == "paused"
    assert "hero image has no alt text" in (paused.workspace / "reports/check.md").read_text()
    resumed = Orchestrator.resume(paused.run_dir, project=cc_project(tmp_path), approval_mode="auto",
                                  decisions=[Decision("revise", None, "add the alt text")], **QUIET)
    assert resumed.status == "done"
    assert "add the alt text" in fake_claude.calls("landing_coder")[1]["prompt"]


# --- skill audit with an upstream update ---------------------------------------------------


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_skill_audit_offers_and_applies_upstream_updates(tmp_path, fake_claude):
    upstream = tmp_path / "upstream"
    (upstream / "demo").mkdir(parents=True)
    _git(upstream, "init", "-q", "-b", "main")

    def commit(body):
        (upstream / "demo" / "SKILL.md").write_text(f"---\nname: demo\ndescription: demo\n---\n{body}\n")
        _git(upstream, "add", "-A")
        _git(upstream, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", body)

    commit("Version one")
    proj = tmp_path / "proj"
    (proj / "skills").mkdir(parents=True)
    (proj / "agents").mkdir()
    (proj / "workflows").mkdir()
    (proj / "skills" / "skills.yaml").write_text(
        f"version: 1\nskills:\n  demo:\n    repo: file://{upstream}\n    path: demo\n    ref: main\n")
    (proj / "agentflow.yaml").write_text(
        "version: 1\nbackend: claude-code\nskills:\n  manifest: skills/skills.yaml\nruns_dir: runs\n")
    for name in ("skill_auditor",):
        (proj / "agents" / f"{name}.yaml").write_text((ROOT / "agents" / f"{name}.yaml").read_text())
    (proj / "agents" / "maker.yaml").write_text("version: 1\nname: maker\nsystem_prompt: make\nskills: [demo]\n")
    (proj / "workflows" / "wf.yaml").write_text(
        "version: 1\nname: wf\npreflight: [skill_audit]\ncheckpoints: none\nsteps:\n  - agent: maker\n")
    from agentflow.skills import SkillLibrary

    SkillLibrary(proj / "skills" / "skills.yaml").sync(log=lambda *_: None)
    commit("Version two")

    fake_claude.script({
        "skill_auditor": [verdict("revise", [{"severity": "minor", "location": "maker / demo", "problem": "update available",
                                               "fix": "take the demo update"}])],
        "maker": [done(write={"out.txt": "made"})],
    })
    seen = {}

    class Approver(AutoApprover):
        def decide_preflight(self, view):
            seen["updatable"] = view.updatable
            seen["report"] = view.report
            return Decision("update", feedback="demo")

    project = load_project(proj / "agentflow.yaml")
    wf = load_workflow(proj / "workflows" / "wf.yaml")
    result = Orchestrator(wf, project=project, approver=Approver(), **QUIET).run({}, run_id="s")
    assert result.status == "done"
    assert seen["updatable"] == ["demo"] and "take the demo update" in seen["report"]
    assert "Version two" in (proj / "skills" / "vendor" / "demo" / "SKILL.md").read_text()
    # The maker ran with the updated skill.
    system = fake_claude.calls("maker")[0]["argv"]
    assert "Version two" in system[system.index("--append-system-prompt") + 1]


# --- CLI ------------------------------------------------------------------------------------


def test_doctor_reports_login(fake_claude, capsys):
    from agentflow.cli import main

    assert main(["--config", str(ROOT / "agentflow.yaml"), "doctor"]) in (0, 1)
    out = capsys.readouterr().out
    assert "Logged in to Claude Code (claude.ai)" in out
    assert "ANTHROPIC_API_KEY is set" in out


def test_contrast_command(capsys):
    from agentflow.cli import main

    assert main(["contrast", "#777", "#fff"]) == 0
    assert "4.48:1" in capsys.readouterr().out


def test_agent_skill_assignments_follow_the_skill_audit():
    agents = load_agents(ROOT / "agents")
    assert agents["landing_designer"].skills == ["frontend-design", "svg-scroll-animation"]
    assert agents["planner"].skills == []
    assert agents["landing_coder"].skills == ["svg-scroll-animation", "web-security-checklist"]
    assert "accessibility-qa-checklist" in agents["page_checker"].skills
    for name in ("landing_coder", "landing_designer", "brief_reviewer", "security_reviewer"):
        assert "prepare_image" in agents[name].tools


def test_old_run_files_without_cost_still_resume(tmp_path, fake_claude):
    fake_claude.script(landing_script(page_checker=[verdict("approve")]))
    wf = load_workflow(ROOT / "workflows" / "scroll_landing.yaml")
    decisions = [Decision("approve")] * 2  # preflight + brief, then pause at plan
    paused = Orchestrator(wf, project=cc_project(tmp_path), approver=ScriptedApprover(decisions, PauseApprover()),
                          **QUIET).run({"idea": "x"}, run_id="old")
    state_path = paused.run_dir / "run.json"
    state = json.loads(state_path.read_text())
    for step in state["steps"]:  # simulate a run.json written before cost tracking existed
        for lane in step["lanes"]:
            lane["usage"].pop("cost_usd", None)
            for r in [lane["result"], *lane["reviews"]]:
                if r:
                    r["usage"].pop("cost_usd", None)
    state["preflight"].get("usage", {}).pop("cost_usd", None)
    state_path.write_text(json.dumps(state))
    done = Orchestrator.resume(paused.run_dir, project=cc_project(tmp_path), approval_mode="auto", **QUIET)
    assert done.status == "done"
