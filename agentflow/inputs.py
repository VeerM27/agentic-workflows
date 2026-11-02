"""Turning workflow/agent arguments (text, files, images) into Claude content blocks."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from .config import REVIEW_WORK_ARG, InputSpec
from .tools import IMAGE_MEDIA_TYPES, image_block_from_bytes
from .workspace import Workspace


class InputError(Exception):
    """A workflow or agent argument is missing or cannot be loaded."""


def is_url(ref: str) -> bool:
    return ref.startswith(("http://", "https://"))


def as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v not in (None, "")]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def list_profiles(library: Path) -> list[str]:
    return sorted(p.stem for p in library.glob("*.md") if not p.stem.startswith("_"))


def load_profile(name: str, library: Path) -> tuple[str, bool]:
    """Return (text, from_library). Unknown names are used as a free-text description."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    path = library / f"{slug}.md"
    if slug and path.is_file():
        return path.read_text(encoding="utf-8").strip(), True
    return name.strip(), False


def coerce_workflow_inputs(
    specs: dict[str, InputSpec], given: dict[str, Any], base_dir: Path, library_root: Path | None = None
) -> dict[str, Any]:
    """Apply defaults, check required inputs, and normalise values by type.

    - text: a string; "@path" reads the string from a file
    - integer: a whole number
    - file: a path to a text file (kept as a path; read when the agent runs)
    - image / images: one or more local paths or URLs (comma-separated string or list)
    - profile: a name looked up in the input's library folder (e.g. `fintech` ->
      profiles/industries/fintech.md); anything else is used as a free-text description
    """
    unknown = sorted(set(given) - set(specs))
    if unknown:
        raise InputError(f"unknown workflow inputs {unknown} (declared: {sorted(specs)})")

    resolved: dict[str, Any] = {}
    for name, spec in specs.items():
        value = given.get(name, spec.default)
        if value in (None, "", []):
            if spec.required:
                hint = f" ({spec.description})" if spec.description else ""
                raise InputError(f"missing required input '{name}'{hint}")
            continue

        if spec.type == "text":
            if isinstance(value, str) and value.startswith("@"):
                path = _local_path(value[1:], base_dir)
                value = path.read_text(encoding="utf-8")
            resolved[name] = str(value)
        elif spec.type == "integer":
            try:
                resolved[name] = int(value)
            except (TypeError, ValueError):
                raise InputError(f"input '{name}' must be a whole number, got '{value}'")
        elif spec.type == "profile":
            library = (library_root or base_dir) / spec.library
            text, _ = load_profile(str(value), library)
            resolved[name] = text
        elif spec.type == "file":
            resolved[name] = str(_local_path(str(value), base_dir))
        else:
            refs = as_list(value)
            if spec.type == "image" and len(refs) > 1:
                raise InputError(f"input '{name}' takes a single image; use type 'images' for several")
            for ref in refs:
                if not is_url(str(ref)):
                    path = _local_path(str(ref), base_dir)
                    if path.suffix.lower() not in IMAGE_MEDIA_TYPES:
                        raise InputError(
                            f"input '{name}': {path.name} is not a supported image "
                            f"({', '.join(sorted(IMAGE_MEDIA_TYPES))})"
                        )
            resolved[name] = [
                str(ref) if is_url(str(ref)) else str(_local_path(str(ref), base_dir)) for ref in refs
            ]
    return resolved


def _local_path(ref: str, base_dir: Path) -> Path:
    path = Path(ref).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    if not path.is_file():
        raise InputError(f"file not found: {ref}")
    return path.resolve()


def stage_inputs(inputs: dict[str, Any], specs: dict[str, InputSpec], workspace: Workspace) -> dict[str, str]:
    """Copy local file/image inputs into ``inputs/<name>/`` in the workspace.

    Agents can then reference them (e.g. use a supplied logo in a page) and later
    agents can read them. Returns {original local path: workspace path}.
    """
    staged: dict[str, str] = {}
    for name, value in inputs.items():
        spec = specs[name]
        if spec.type not in ("file", "image", "images"):
            continue
        for i, ref in enumerate(as_list(value), 1):
            if is_url(ref):
                rel = _download(ref, name, i, workspace)
                if rel:
                    staged[ref] = rel
                continue
            src = Path(ref)
            rel = f"inputs/{name}/{src.name}"
            dest = workspace.resolve(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            staged[str(src)] = rel
    return staged


def _download(url: str, name: str, index: int, workspace: Workspace) -> str | None:
    """Save a URL input into the workspace (best effort), so file-based agents can open it."""
    import urllib.request
    from urllib.parse import urlparse

    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix not in IMAGE_MEDIA_TYPES:
        suffix = ".png"
    rel = f"inputs/{name}/url-{index}{suffix}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - user-supplied input URL
            data = resp.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            return None
        workspace.write_bytes(rel, data)
        return rel
    except Exception:
        return None


def _image_block(ref: str, staged_path: str | None = None, inline: bool = True) -> dict:
    if not inline:
        if staged_path:
            return {"type": "image", "source": {"type": "workspace", "path": staged_path}}
        return {"type": "image", "source": {"type": "url", "url": ref}}
    return _inline_image_block(ref)


def _inline_image_block(ref: str) -> dict:
    if is_url(ref):
        return {"type": "image", "source": {"type": "url", "url": ref}}
    path = Path(ref)
    media_type = IMAGE_MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise InputError(f"unsupported image type: {path.name}")
    return image_block_from_bytes(path.read_bytes(), media_type)


def build_task_content(
    agent_inputs: dict[str, InputSpec],
    args: dict[str, Any],
    *,
    staged: dict[str, str] | None = None,
    instructions: str = "",
    closing: str = "",
    inline_images: bool = True,
) -> list[dict]:
    """Render an agent's arguments as the content of its first user message."""
    staged = staged or {}
    blocks: list[dict] = [
        {"type": "text", "text": "You have been given the following inputs for this task."}
    ]

    for name, value in args.items():
        spec = agent_inputs.get(name) or InputSpec(name=name)
        title = name.replace("_", " ")
        desc = f" — {spec.description}" if spec.description else ""

        if name == REVIEW_WORK_ARG:
            blocks.append({"type": "text", "text": f"## Work to review\n\n{value}"})
        elif spec.type in ("image", "images"):
            refs = as_list(value)
            blocks.append({"type": "text", "text": f"## {title}{desc}\n\n{len(refs)} image(s) follow."})
            for i, ref in enumerate(refs, 1):
                label = f"Image {i} of {len(refs)}"
                ws_path = _staged_path(ref, staged)
                if ws_path:
                    label += f" (also saved in the workspace at `{ws_path}`)"
                blocks.append({"type": "text", "text": label})
                blocks.append(_image_block(ref, ws_path, inline_images))
        elif spec.type == "file":
            path = Path(value)
            text = path.read_text(encoding="utf-8")
            ws_path = _staged_path(str(path), staged)
            where = f" (workspace: `{ws_path}`)" if ws_path else ""
            blocks.append(
                {"type": "text", "text": f"## {title}{desc}\n\nFile `{path.name}`{where}:\n\n```\n{text}\n```"}
            )
        else:
            if isinstance(value, list):
                value = "\n".join(f"- {v}" for v in value)
            value = str(value)
            blocks.append({"type": "text", "text": f"## {title}{desc}\n\n{value}"})

    if instructions:
        blocks.append({"type": "text", "text": f"## Instructions for this step\n\n{instructions}"})
    if closing:
        blocks.append({"type": "text", "text": closing})
    return blocks


def _staged_path(ref: str, staged: dict[str, str]) -> str | None:
    return staged.get(str(ref))
