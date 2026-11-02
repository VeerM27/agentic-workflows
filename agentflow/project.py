"""Project-wide settings (`agentflow.yaml`): the one place to personalise and future-proof a setup.

Everything that changes over time (which model to use, your house style, how you want to be kept in
the loop, where skills come from) lives here rather than being repeated in every agent file.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_NAME = "agentflow.yaml"
SUPPORTED_VERSION = 1

APPROVAL_MODES = {"terminal", "pause", "auto"}
BACKENDS = {"claude-code", "api"}
SKILL_AUDIT_MODES = {"on_change", "always", "off"}

# Used when there is no agentflow.yaml at all.
BUILTIN_MODELS = {"default": "claude-opus-5-5", "fast": "claude-sonnet-5-5"}


class ProjectError(Exception):
    pass


@dataclass
class ProjectConfig:
    root: Path
    models: dict[str, str] = field(default_factory=lambda: dict(BUILTIN_MODELS))
    default_model: str = "default"
    default_effort: str = "high"
    fallbacks: bool = True
    house_style_path: Path | None = None
    skills_manifest: Path | None = None
    approval_mode: str = "terminal"
    checkpoints: Any = "all"  # "all" | "none" | [step ids]
    notify_command: str | None = None
    runs_dir: Path = Path("runs")
    backend: str = "api"  # "claude-code" runs agents on your Claude subscription; "api" uses an API key
    skill_audit: str = "on_change"
    source: Path | None = None

    def resolve_model(self, name: str | None) -> str:
        """Map an alias (e.g. `default`, `fast`) to a model ID. Full IDs pass through."""
        name = name or self.default_model
        seen = set()
        while name in self.models and name not in seen:  # aliases may point at aliases
            seen.add(name)
            name = self.models[name]
        return name

    @property
    def house_style(self) -> str:
        if self.house_style_path and self.house_style_path.is_file():
            return self.house_style_path.read_text(encoding="utf-8").strip()
        return ""

    def notify(self, event: str, **info: str) -> None:
        """Run the user's notify command (if any) so they hear about checkpoints and results."""
        if not self.notify_command:
            return
        env = dict(os.environ)
        env["AGENTFLOW_EVENT"] = event
        for key, value in info.items():
            env[f"AGENTFLOW_{key.upper()}"] = str(value)
        try:
            subprocess.run(self.notify_command, shell=True, env=env, timeout=30, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass  # a broken notifier must never break a run


_KNOWN_KEYS = {"version", "backend", "models", "defaults", "house_style", "skills", "approvals", "notify", "runs_dir"}


def find_config(start: Path) -> Path | None:
    start = start.resolve()
    for directory in [start, *start.parents]:
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def load_project(path: str | Path | None = None, *, search_from: str | Path = ".") -> ProjectConfig:
    """Load agentflow.yaml (explicit path, or the nearest one above `search_from`)."""
    cfg_path = Path(path) if path else find_config(Path(search_from))
    if cfg_path is None:
        return ProjectConfig(root=Path(search_from).resolve())

    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    where = str(cfg_path)
    if not isinstance(data, dict):
        raise ProjectError(f"{where}: expected a mapping")
    version = data.get("version", SUPPORTED_VERSION)
    if version != SUPPORTED_VERSION:
        raise ProjectError(f"{where}: config version {version} is not supported (expected {SUPPORTED_VERSION})")
    unknown = sorted(set(data) - _KNOWN_KEYS)
    if unknown:
        raise ProjectError(f"{where}: unknown keys {unknown} (known: {sorted(_KNOWN_KEYS)})")

    root = cfg_path.parent.resolve()
    defaults = data.get("defaults") or {}
    approvals = data.get("approvals") or {}
    skills = data.get("skills") or {}
    notify = data.get("notify") or {}

    models = dict(BUILTIN_MODELS)
    models.update(data.get("models") or {})

    mode = approvals.get("mode", "terminal")
    if mode not in APPROVAL_MODES:
        raise ProjectError(f"{where}: approvals.mode must be one of {sorted(APPROVAL_MODES)}")

    def rel(p: str | None) -> Path | None:
        return (root / Path(p).expanduser()).resolve() if p else None

    backend = data.get("backend", "api")
    if backend not in BACKENDS:
        raise ProjectError(f"{where}: backend must be one of {sorted(BACKENDS)}")
    skill_audit = skills.get("audit", "on_change")
    if skill_audit not in SKILL_AUDIT_MODES:
        raise ProjectError(f"{where}: skills.audit must be one of {sorted(SKILL_AUDIT_MODES)}")

    house_style = rel(data.get("house_style"))
    if house_style and not house_style.is_file():
        raise ProjectError(f"{where}: house_style file not found: {house_style}")

    return ProjectConfig(
        root=root,
        models=models,
        default_model=defaults.get("model", "default"),
        default_effort=defaults.get("effort", "high"),
        fallbacks=bool(defaults.get("fallbacks", True)),
        house_style_path=house_style,
        skills_manifest=rel(skills.get("manifest")),
        approval_mode=mode,
        checkpoints=approvals.get("checkpoints", "all"),
        notify_command=notify.get("command"),
        runs_dir=rel(data.get("runs_dir", "runs")),
        backend=backend,
        skill_audit=skill_audit,
        source=cfg_path,
    )
