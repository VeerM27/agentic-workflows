"""Claude Code skills (SKILL.md folders) from GitHub or local folders, pinned and verified.

    skills/skills.yaml        what you want: name -> repo + path + ref (or a local folder)
    skills/skills.lock.json   what you have: the exact commit and a content hash per skill
    skills/vendor/<name>/     the skill's files, committed to your repo

`agentflow skills sync` installs exactly what the lockfile says (reproducible).
`agentflow skills update` moves a skill to the newest commit of its ref and shows what changed.
Runs refuse to start if a vendored skill no longer matches its locked hash.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPT_SUFFIXES = {".py", ".sh", ".js", ".ts", ".rb", ".mjs"}
TEXT_SUFFIXES = {".md", ".txt", ".css", ".html", ".svg", ".json", ".yaml", ".yml", ".csv", ".xml", *SCRIPT_SUFFIXES}


class SkillError(Exception):
    pass


@dataclass
class SkillSource:
    name: str
    repo: str | None = None  # "owner/repo" (GitHub) or any git URL
    path: str = ""  # folder inside the repo
    ref: str = "main"
    local: Path | None = None  # a skill folder in your own repo

    @property
    def git_url(self) -> str:
        if self.repo is None:
            raise SkillError(f"{self.name} is a local skill")
        if "://" in self.repo or self.repo.startswith("git@"):
            return self.repo
        return f"https://github.com/{self.repo}.git"

    def describe(self) -> str:
        if self.local:
            return f"local:{self.local}"
        return f"{self.repo}/{self.path}@{self.ref}"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    root: Path
    files: list[str] = field(default_factory=list)

    @property
    def scripts(self) -> list[str]:
        return [f for f in self.files if Path(f).suffix in SCRIPT_SUFFIXES]

    def read(self, rel: str) -> str:
        target = (self.root / rel).resolve()
        if self.root.resolve() not in target.parents or not target.is_file():
            raise SkillError(f"skill '{self.name}' has no file '{rel}'")
        if target.suffix.lower() not in TEXT_SUFFIXES:
            raise SkillError(f"{rel} is a binary file; only text files can be read")
        return target.read_text(encoding="utf-8")

    def prompt_section(self) -> str:
        lines = [f"## Skill: {self.name}", f"_{self.description}_", ""]
        others = [f for f in self.files if f not in ("SKILL.md", "LICENSE.txt", "LICENSE")]
        if others:
            lines.append(
                "Supporting files (read them with `read_skill_file` when the instructions refer to them): "
                + ", ".join(f"`{f}`" for f in others)
            )
            lines.append("")
        if self.scripts:
            lines.append(
                "This skill includes scripts. You cannot execute them here; read them for reference "
                "and apply what they do by hand."
            )
            lines.append("")
        lines.append(self.body.strip())
        return "\n".join(lines)


def parse_skill_dir(root: Path, name: str | None = None) -> Skill:
    skill_md = root / "SKILL.md"
    if not skill_md.is_file():
        raise SkillError(f"{root} has no SKILL.md")
    text = skill_md.read_text(encoding="utf-8")
    meta: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2]
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    return Skill(
        name=name or meta.get("name") or root.name,
        description=str(meta.get("description", "")).strip(),
        body=body.strip(),
        root=root,
        files=files,
    )


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


class SkillLibrary:
    """The skills manifest, lockfile and vendored copies of one project."""

    def __init__(self, manifest_path: str | Path):
        self.manifest_path = Path(manifest_path).resolve()
        self.base = self.manifest_path.parent
        self.lock_path = self.base / "skills.lock.json"
        self.vendor_dir = self.base / "vendor"
        self.sources = self._read_manifest()
        self.lock = json.loads(self.lock_path.read_text()) if self.lock_path.is_file() else {}
        self._cache: dict[str, Skill] = {}

    def _read_manifest(self) -> dict[str, SkillSource]:
        if not self.manifest_path.is_file():
            raise SkillError(f"skills manifest not found: {self.manifest_path}")
        data = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8")) or {}
        if data.get("version", 1) != 1:
            raise SkillError(f"{self.manifest_path}: unsupported version {data.get('version')}")
        sources: dict[str, SkillSource] = {}
        for name, raw in (data.get("skills") or {}).items():
            raw = raw or {}
            unknown = set(raw) - {"repo", "path", "ref", "local", "note"}
            if unknown:
                raise SkillError(f"{self.manifest_path}: skill '{name}' has unknown keys {sorted(unknown)}")
            if bool(raw.get("repo")) == bool(raw.get("local")):
                raise SkillError(f"{self.manifest_path}: skill '{name}' needs exactly one of 'repo' or 'local'")
            sources[name] = SkillSource(
                name=name,
                repo=raw.get("repo"),
                path=str(raw.get("path", "")).strip("/"),
                ref=str(raw.get("ref", "main")),
                local=(self.base / raw["local"]).resolve() if raw.get("local") else None,
            )
        return sources

    # --- using skills ------------------------------------------------------------

    def skill_dir(self, name: str) -> Path:
        src = self.sources[name]
        return src.local if src.local else self.vendor_dir / name

    def get(self, name: str) -> Skill:
        if name not in self.sources:
            raise SkillError(f"unknown skill '{name}' (in manifest: {sorted(self.sources)})")
        if name not in self._cache:
            directory = self.skill_dir(name)
            if not directory.is_dir():
                raise SkillError(f"skill '{name}' is not installed; run `agentflow skills sync`")
            self._cache[name] = parse_skill_dir(directory, name=name)
        return self._cache[name]

    def verify(self, names: list[str] | None = None) -> list[str]:
        """Return problems: missing installs, or vendored files that differ from the lockfile."""
        problems = []
        for name in names or list(self.sources):
            src = self.sources.get(name)
            if src is None:
                problems.append(f"unknown skill '{name}'")
                continue
            directory = self.skill_dir(name)
            if not (directory / "SKILL.md").is_file():
                problems.append(f"skill '{name}' is not installed (run `agentflow skills sync`)")
                continue
            if src.local:
                continue
            entry = self.lock.get(name)
            if entry is None:
                problems.append(f"skill '{name}' is not in the lockfile (run `agentflow skills sync`)")
            elif entry.get("source") != src.describe():
                problems.append(f"skill '{name}' changed in the manifest; run `agentflow skills update {name}`")
            elif tree_hash(directory) != entry["hash"]:
                problems.append(f"skill '{name}' files differ from the locked hash (edited or corrupted)")
        return problems

    # --- installing ----------------------------------------------------------------

    def sync(self, log=print) -> None:
        """Install every remote skill at its locked commit (or lock it at first install)."""
        for name, src in self.sources.items():
            if src.local:
                continue
            entry = self.lock.get(name)
            directory = self.vendor_dir / name
            if entry and entry.get("source") == src.describe() and directory.is_dir() and tree_hash(directory) == entry["hash"]:
                log(f"  ✓ {name} @ {entry['commit'][:10]}")
                continue
            commit = entry["commit"] if entry and entry.get("source") == src.describe() else src.ref
            self._install(src, commit, log)
        self._write_lock()

    def update(self, names: list[str] | None = None, log=print) -> None:
        """Move skills to the newest commit of their ref, showing which files changed."""
        for name in names or list(self.sources):
            src = self.sources[name]
            if src.local:
                log(f"  - {name} is local; nothing to update")
                continue
            before = _file_hashes(self.vendor_dir / name)
            self._install(src, src.ref, log)
            after = _file_hashes(self.vendor_dir / name)
            for f in sorted(set(before) | set(after)):
                if before.get(f) != after.get(f):
                    state = "added" if f not in before else "removed" if f not in after else "changed"
                    log(f"      {state}: {f}")
        self._write_lock()

    def _install(self, src: SkillSource, ref: str, log) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            commit = _git_fetch(src.git_url, ref, repo_dir)
            source_dir = repo_dir / src.path if src.path else repo_dir
            if not (source_dir / "SKILL.md").is_file():
                raise SkillError(f"{src.describe()}: no SKILL.md at '{src.path or '/'}' in commit {commit[:10]}")
            staging = self.vendor_dir / f".{src.name}.tmp"
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(source_dir, staging, ignore=shutil.ignore_patterns(".git"))
            target = self.vendor_dir / src.name
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
        self.lock[src.name] = {
            "source": src.describe(),
            "commit": commit,
            "hash": tree_hash(target),
            "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._cache.pop(src.name, None)
        log(f"  ↓ {src.name} @ {commit[:10]}")

    def _write_lock(self) -> None:
        self.lock = {k: v for k, v in sorted(self.lock.items()) if k in self.sources}
        self.lock_path.write_text(json.dumps(self.lock, indent=2) + "\n", encoding="utf-8")


def _file_hashes(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def _git(args: list[str], cwd: Path) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=180)
    except FileNotFoundError as exc:
        raise SkillError("git is required to install skills from repositories") from exc
    except subprocess.CalledProcessError as exc:
        raise SkillError(f"git {' '.join(args)} failed: {exc.stderr.strip()}") from exc
    return out.stdout.strip()


def _git_fetch(url: str, ref: str, dest: Path) -> str:
    """Shallow-fetch one ref (branch, tag or full commit SHA) and return the resolved commit."""
    dest.mkdir(parents=True)
    _git(["init", "-q"], dest)
    _git(["remote", "add", "origin", url], dest)
    _git(["fetch", "-q", "--depth", "1", "origin", ref], dest)
    _git(["checkout", "-q", "FETCH_HEAD"], dest)
    return _git(["rev-parse", "HEAD"], dest)
