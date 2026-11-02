import pytest

from agentflow.tools import ToolExecutor, schema_for, tool_params, validate_input
from agentflow.workspace import Workspace, WorkspaceError


def test_workspace_blocks_escape(tmp_path):
    ws = Workspace(tmp_path / "ws")
    for bad in ["../x.txt", "a/../../x.txt", "/etc/passwd/../../.."]:
        with pytest.raises(WorkspaceError):
            ws.write_text(bad, "nope")
    # Leading slash is treated as workspace-relative, not absolute.
    ws.write_text("/inside.txt", "ok")
    assert (tmp_path / "ws" / "inside.txt").read_text() == "ok"


def test_edit_requires_unique_match(tmp_path):
    ws = Workspace(tmp_path)
    ws.write_text("a.css", "color: red;\ncolor: red;\n")
    with pytest.raises(WorkspaceError, match="2 times"):
        ws.edit("a.css", "color: red;", "color: blue;")
    ws.edit("a.css", "color: red;\ncolor: red;", "color: blue;")
    assert ws.read_text("a.css") == "color: blue;\n"


def test_executor_reports_errors_as_tool_errors(tmp_path):
    ex = ToolExecutor(Workspace(tmp_path))
    assert ex.run("write_file", {"path": "d/x.html", "content": "<p>hi</p>"}).is_error is False
    assert ex.run("read_file", {"path": "d/x.html"}).content == "<p>hi</p>"
    assert ex.run("list_files", {}).content == "d/x.html"
    out = ex.run("read_file", {"path": "missing.txt"})
    assert out.is_error and "not found" in out.content


def test_read_image_returns_image_block(tmp_path):
    ws = Workspace(tmp_path)
    ws.write_bytes("logo.png", b"\x89PNG\r\n\x1a\nfake")
    out = ToolExecutor(ws).run("read_file", {"path": "logo.png"})
    assert out.content[0]["type"] == "image"
    assert out.content[0]["source"]["media_type"] == "image/png"


def test_render_page_uses_renderer(tmp_path):
    ws = Workspace(tmp_path)
    ws.write_text("p.html", "<h1>x</h1>")
    seen = {}

    def renderer(path, width, full_page, scroll_y=None):
        seen.update(path=path, width=width)
        return b"png-bytes"

    out = ToolExecutor(ws, renderer=renderer).run("render_page", {"path": "p.html", "width": 375})
    assert not out.is_error and out.content[0]["type"] == "image"
    assert seen["width"] == 375


def test_validate_input():
    s = schema_for("submit_review")
    assert validate_input(s, {"verdict": "approve", "summary": "ok", "issues": []}) is None
    assert "one of" in validate_input(s, {"verdict": "maybe", "summary": "ok", "issues": []})
    assert "missing required field 'summary'" in validate_input(s, {"verdict": "approve", "issues": []})
    bad_issue = {"verdict": "revise", "summary": "x", "issues": [{"severity": "major"}]}
    assert "issues[0]" in validate_input(s, bad_issue)
    assert "unexpected fields" in validate_input(schema_for("read_file"), {"path": "a", "extra": 1})


def test_tool_params_add_terminal_and_eager_streaming():
    params = tool_params(["read_file"], "complete_task")
    assert [p["name"] for p in params] == ["read_file", "complete_task"]
    assert all(p["eager_input_streaming"] for p in params)
