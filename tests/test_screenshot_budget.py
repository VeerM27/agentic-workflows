"""Screenshot budgets: a warning once the budget is used, a refusal at twice the budget."""

import argparse

import pytest

from agentflow import cli
from agentflow.config import ConfigError, load_agent, load_agents
from agentflow.tools import ScreenshotBudget, ToolError, ToolExecutor
from agentflow.workspace import Workspace

from test_claude_code import ROOT, done, fake_claude  # noqa: F401  (fixture)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def test_budget_warns_then_refuses():
    budget = ScreenshotBudget(2)
    assert "1 of 2" in budget.take()
    assert "budget reached" in budget.take()
    budget.take()
    budget.take()
    with pytest.raises(ToolError, match="budget used up"):
        budget.take()
    assert ScreenshotBudget(None).take() == ""


def test_render_page_tool_enforces_the_budget(tmp_path):
    ws = Workspace(tmp_path)
    ws.write_text("p.html", "<p>hi</p>")
    executor = ToolExecutor(ws, renderer=lambda *a, **k: PNG, screenshot_budget=1)
    first = executor.run("render_page", {"path": "p.html"})
    assert not first.is_error and "budget reached" in first.content[-1]["text"]
    assert not executor.run("render_page", {"path": "p.html"}).is_error
    refused = executor.run("render_page", {"path": "p.html"})
    assert refused.is_error and "budget used up" in str(refused.content)


def test_cli_screenshot_counts_across_calls(tmp_path, monkeypatch, capsys):
    page = tmp_path / "p.html"
    page.write_text("<p>hi</p>")
    counter = tmp_path / "scratch" / "screenshots"
    monkeypatch.setenv("AGENTFLOW_SCREENSHOT_BUDGET", "1")
    monkeypatch.setenv("AGENTFLOW_SCREENSHOT_COUNTER", str(counter))
    monkeypatch.setattr("agentflow.tools.render_html_screenshot", lambda *a, **k: PNG)
    args = argparse.Namespace(html=str(page), out=str(tmp_path / "s.png"), width=1280, full_page=False, scroll_y=None)
    assert cli.cmd_screenshot(args) == 0 and "budget reached" in capsys.readouterr().out
    assert cli.cmd_screenshot(args) == 0
    assert counter.read_text() == "2"
    assert cli.cmd_screenshot(args) == 3
    assert "budget used up" in capsys.readouterr().err


def test_screenshot_budget_is_validated(tmp_path):
    bad = tmp_path / "a.yaml"
    bad.write_text("version: 1\nname: a\nscreenshot_budget: 0\nsystem_prompt: hi\n")
    with pytest.raises(ConfigError, match="screenshot_budget"):
        load_agent(bad)
    agents = load_agents(ROOT / "agents")
    assert agents["landing_designer"].screenshot_budget == 10
    assert agents["landing_coder"].screenshot_budget == 12


def test_claude_code_sessions_get_a_fresh_budget_outside_the_workspace(tmp_path, fake_claude):  # noqa: F811
    from agentflow.backends.claude_code import ClaudeCodeRunner

    spec = load_agents(ROOT / "agents")["landing_designer"]
    fake_claude.script({"landing_designer": [done(write={"design/a.md": "a"}), done(write={"design/a.md": "b"})]})
    ws = Workspace(tmp_path / "ws")
    runner = ClaudeCodeRunner(spec, None, ws, model="m", effort="high")
    runner.start([{"type": "text", "text": "design it"}])
    runner.follow_up("again")
    first, second = fake_claude.calls("landing_designer")
    assert first["screenshot_budget"] == "10"
    assert first["screenshot_counter"] != second["screenshot_counter"]
    assert not first["screenshot_counter"].startswith(str(ws.root))
