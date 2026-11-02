"""Tools the agents can call, their JSON schemas, and their implementations.

Workspace tools act on the shared project directory. Every agent also gets one
*terminal* tool that ends its turn and carries its structured hand-off:

- producers call ``complete_task`` (summary, files, notes for the next agent)
- reviewers call ``submit_review`` (verdict, issues)
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Callable

from .workspace import Workspace, WorkspaceError

MAX_READ_BYTES = 200_000
IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # API limit for a base64 image

COMPLETE_TASK = "complete_task"
SUBMIT_REVIEW = "submit_review"


def _schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


WORKSPACE_TOOLS: dict[str, dict] = {
    "list_files": {
        "description": "List files in the shared workspace (recursively). Use it to see what earlier agents produced.",
        "input_schema": _schema(
            {"path": {"type": "string", "description": "Directory to list, relative to the workspace root. Defaults to '.'."}},
            [],
        ),
    },
    "read_file": {
        "description": "Read a file from the workspace. Text files are returned as text; PNG/JPEG/GIF/WebP images are returned as images you can see.",
        "input_schema": _schema(
            {"path": {"type": "string", "description": "File path relative to the workspace root."}},
            ["path"],
        ),
    },
    "write_file": {
        "description": "Create or overwrite a text file in the workspace with the full contents given. Parent directories are created automatically.",
        "input_schema": _schema(
            {
                "path": {"type": "string", "description": "File path relative to the workspace root."},
                "content": {"type": "string", "description": "The complete file contents."},
            },
            ["path", "content"],
        ),
    },
    "edit_file": {
        "description": "Replace one exact, unique occurrence of old_str with new_str in a workspace file. Prefer this over rewriting a whole file for small changes.",
        "input_schema": _schema(
            {
                "path": {"type": "string"},
                "old_str": {"type": "string", "description": "Exact text to replace; must occur exactly once."},
                "new_str": {"type": "string", "description": "Replacement text."},
            },
            ["path", "old_str", "new_str"],
        ),
    },
    "delete_file": {
        "description": "Delete a file from the workspace.",
        "input_schema": _schema({"path": {"type": "string"}}, ["path"]),
    },
    "render_page": {
        "description": (
            "Render an HTML file from the workspace in a headless browser and return a screenshot, "
            "so you can see the page as a user would. Use different widths to check responsive layouts "
            "(e.g. 375 for mobile, 1280 for desktop)."
        ),
        "input_schema": _schema(
            {
                "path": {"type": "string", "description": "HTML file relative to the workspace root."},
                "width": {"type": "integer", "description": "Viewport width in CSS pixels (default 1280)."},
                "full_page": {"type": "boolean", "description": "Capture the whole scrollable page (default true, capped at 5000px tall)."},
            },
            ["path"],
        ),
    },
}

TERMINAL_TOOLS: dict[str, dict] = {
    COMPLETE_TASK: {
        "description": (
            "Finish your task and hand off to the next agent. Call this exactly once, after all your files are written. "
            "Your turn ends when you call it."
        ),
        "input_schema": _schema(
            {
                "summary": {"type": "string", "description": "What you produced and the key decisions you made (a few sentences to a short list)."},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Workspace paths of the files you created or changed.",
                },
                "notes_for_next_agent": {
                    "type": "string",
                    "description": "Anything the next agent must know: open questions, assumptions, known gaps, where to start.",
                },
            },
            ["summary", "files", "notes_for_next_agent"],
        ),
    },
    SUBMIT_REVIEW: {
        "description": (
            "Submit your review verdict. Call this exactly once when your review is complete. "
            "Use 'approve' when the work meets the bar (minor nits alone are not a reason to block), "
            "'revise' when there are issues that must be fixed."
        ),
        "input_schema": _schema(
            {
                "verdict": {"type": "string", "enum": ["approve", "revise"]},
                "summary": {"type": "string", "description": "Overall assessment in a few sentences."},
                "issues": {
                    "type": "array",
                    "description": "Concrete problems, most important first. Empty when approving with nothing to fix.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string", "enum": ["blocker", "major", "minor"]},
                            "location": {"type": "string", "description": "File and element/section the issue is in."},
                            "problem": {"type": "string"},
                            "fix": {"type": "string", "description": "What to change, specifically."},
                        },
                        "required": ["severity", "location", "problem", "fix"],
                        "additionalProperties": False,
                    },
                },
            },
            ["verdict", "summary", "issues"],
        ),
    },
}


def terminal_tool_for(role: str) -> str:
    return SUBMIT_REVIEW if role == "reviewer" else COMPLETE_TASK


def tool_params(names: list[str], terminal: str, eager: bool = True) -> list[dict]:
    """Build the `tools` request parameter for an agent.

    Requests are streamed, so each tool sets ``eager_input_streaming``: large file
    contents stream as they are generated instead of arriving in one burst. The
    server then no longer validates inputs, which is why every input is checked
    with :func:`validate_input` before a tool runs.
    """
    params = []
    for name in [*names, terminal]:
        spec = WORKSPACE_TOOLS.get(name) or TERMINAL_TOOLS[name]
        param = {"name": name, "description": spec["description"], "input_schema": spec["input_schema"]}
        if eager:
            param["eager_input_streaming"] = True
        params.append(param)
    return params


def schema_for(name: str) -> dict:
    spec = WORKSPACE_TOOLS.get(name) or TERMINAL_TOOLS.get(name)
    if spec is None:
        raise KeyError(name)
    return spec["input_schema"]


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def validate_input(schema: dict, value: Any, path: str = "input") -> str | None:
    """Check a value against the subset of JSON Schema used by our tools.

    Returns an error message, or None when the value is valid.
    """
    expected = schema.get("type")
    if expected:
        types = _JSON_TYPES[expected]
        is_bool = isinstance(value, bool)
        if not isinstance(value, types) or (is_bool and expected in ("integer", "number")):
            return f"{path} must be of type {expected}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} must be one of {schema['enum']}"
    if expected == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                return f"{path} is missing required field '{key}'"
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                return f"{path} has unexpected fields {extra}"
        for key, sub in props.items():
            if key in value:
                err = validate_input(sub, value[key], f"{path}.{key}")
                if err:
                    return err
    if expected == "array" and "items" in schema:
        for i, item in enumerate(value):
            err = validate_input(schema["items"], item, f"{path}[{i}]")
            if err:
                return err
    return None


def image_block_from_bytes(data: bytes, media_type: str) -> dict:
    if len(data) > MAX_IMAGE_BYTES:
        raise WorkspaceError(
            f"image is {len(data) / 1e6:.1f} MB; the limit is {MAX_IMAGE_BYTES / 1e6:.0f} MB"
        )
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    }


class ToolError(Exception):
    """An error returned to the model as an `is_error` tool result."""


@dataclass
class ToolOutcome:
    content: str | list[dict]
    is_error: bool = False


class ToolExecutor:
    """Runs workspace tools for one agent."""

    def __init__(self, workspace: Workspace, renderer: Callable[..., bytes] | None = None):
        self.workspace = workspace
        self._renderer = renderer
        self.files_written: set[str] = set()

    def run(self, name: str, args: dict) -> ToolOutcome:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolOutcome(f"Unknown tool '{name}'", is_error=True)
        try:
            return ToolOutcome(handler(**args))
        except (WorkspaceError, ToolError) as exc:
            return ToolOutcome(f"Error: {exc}", is_error=True)

    # --- workspace tools -------------------------------------------------

    def _tool_list_files(self, path: str = ".") -> str:
        files = self.workspace.list_files(path)
        if not files:
            return "(no files)"
        return "\n".join(files)

    def _tool_read_file(self, path: str) -> str | list[dict]:
        resolved = self.workspace.resolve(path)
        media_type = IMAGE_MEDIA_TYPES.get(resolved.suffix.lower())
        data = self.workspace.read_bytes(path)
        if media_type:
            return [image_block_from_bytes(data, media_type), {"type": "text", "text": f"Image: {path}"}]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ToolError(f"{path} is a binary file and cannot be read as text")
        if len(data) > MAX_READ_BYTES:
            return text[:MAX_READ_BYTES] + f"\n\n[truncated: file is {len(data)} bytes, showing the first {MAX_READ_BYTES}]"
        return text

    def _tool_write_file(self, path: str, content: str) -> str:
        size = self.workspace.write_text(path, content)
        self.files_written.add(self.workspace.relative(self.workspace.resolve(path)))
        return f"Wrote {path} ({size} bytes)"

    def _tool_edit_file(self, path: str, old_str: str, new_str: str) -> str:
        self.workspace.edit(path, old_str, new_str)
        self.files_written.add(self.workspace.relative(self.workspace.resolve(path)))
        return f"Edited {path}"

    def _tool_delete_file(self, path: str) -> str:
        self.workspace.delete(path)
        self.files_written.discard(self.workspace.relative(self.workspace.resolve(path)))
        return f"Deleted {path}"

    def _tool_render_page(self, path: str, width: int = 1280, full_page: bool = True) -> list[dict]:
        target = self.workspace.resolve(path)
        if not target.is_file():
            raise ToolError(f"file not found: {path}")
        if not 200 <= width <= 3000:
            raise ToolError("width must be between 200 and 3000")
        renderer = self._renderer or render_html_screenshot
        png = renderer(target, width=width, full_page=full_page)
        return [
            image_block_from_bytes(png, "image/png"),
            {"type": "text", "text": f"Screenshot of {path} at {width}px wide."},
        ]


def render_html_screenshot(path, width: int = 1280, full_page: bool = True, max_height: int = 5000) -> bytes:
    """Screenshot a local HTML file with Playwright (optional dependency)."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ToolError(
            "render_page is unavailable: install the optional dependency with "
            "`pip install 'agentflow[render]' && playwright install chromium`"
        ) from exc
    # Point AGENTFLOW_CHROMIUM at an existing Chrome/Chromium binary to skip `playwright install`.
    executable = os.environ.get("AGENTFLOW_CHROMIUM") or None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=executable)
            try:
                page = browser.new_page(viewport={"width": width, "height": 800})
                page.goto(path.as_uri(), wait_until="networkidle", timeout=20_000)
                if full_page:
                    height = min(int(page.evaluate("document.documentElement.scrollHeight")), max_height)
                    page.set_viewport_size({"width": width, "height": max(height, 1)})
                return page.screenshot(full_page=False)
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise ToolError(f"could not render {path.name}: {exc}") from exc


def invalid_json_result(tool_use_id: str, raw_input: Any, reason: str) -> dict:
    """Error result for a tool call whose input failed validation (see eager input streaming)."""
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "is_error": True,
        "content": json.dumps({"INVALID_INPUT": reason, "received": raw_input}, default=str),
    }
