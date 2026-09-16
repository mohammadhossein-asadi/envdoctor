"""Core dataclasses shared by the scan, check, fix, and CLI layers."""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from envdoctor.constants import IGNORED_ENV_VARS, SECRET_HINTS

class Severity(str, Enum):
    """Finding severity, in increasing order."""

    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass(frozen=True)
class Evidence:
    """Where a finding came from. Never contains secret *values*."""

    source: str  # "file" | "env" | "runtime" | "doc" | "toolchain"
    location: str  # e.g. ".env.example:1" | "process env" | "docker"
    snippet: str = ""  # short, redacted snippet
    kind: str = ""  # free-form sub-kind, e.g. "dotenv", "compose-env", "doc-mention"

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "location": self.location,
            "snippet": self.snippet,
            "kind": self.kind,
        }

@dataclass(frozen=True)
class FixSuggestion:
    """A suggested remedy. `command` may be empty (manual instructions only)."""

    summary: str
    command: str = ""
    safety: str = "safe"  # safe | caution | manual
    applies_to: str = "all"  # "all" | "windows" | "macos" | "linux" | "unix"

    def for_os(self, system: str) -> bool:
        if self.applies_to == "all":
            return True
        if self.applies_to == "unix":
            return system in ("darwin", "linux")
        return self.applies_to == system

    def as_dict(self) -> dict[str, str]:
        return {
            "summary": self.summary,
            "command": self.command,
            "safety": self.safety,
            "applies_to": self.applies_to,
        }

@dataclass(frozen=True)
class Finding:
    """One diagnosed issue (or healthy result) with evidence and optional fix."""

    id: str
    severity: Severity
    title: str
    detail: str = ""
    evidence: tuple[Evidence, ...] = ()
    fix: FixSuggestion | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "title": self.title,
            "detail": self.detail,
            "evidence": [e.as_dict() for e in self.evidence],
            "fix": None if self.fix is None else self.fix.as_dict(),
        }

@dataclass
class EnvVarInfo:
    """A required environment variable and everywhere it was referenced."""

    name: str
    sources: list[str] = field(default_factory=list)  # "file:line" refs
    kinds: set[str] = field(default_factory=set)  # dotenv / compose / doc / script
    example_hint: str = ""  # redacted, for name context only
    secret_like: bool = False

    def merge(self, other: EnvVarInfo) -> None:
        self.sources.extend(other.sources)
        self.kinds |= other.kinds
        if other.example_hint and not self.example_hint:
            self.example_hint = other.example_hint
        self.secret_like = self.secret_like or other.secret_like

@dataclass
class FileInventory:
    """Files of interest discovered in the repository root."""

    root: Path
    dotenv_examples: list[Path] = field(default_factory=list)
    dotenv_actual: list[Path] = field(default_factory=list)
    compose_files: list[Path] = field(default_factory=list)
    dockerfiles: list[Path] = field(default_factory=list)
    package_json: Path | None = None
    pyproject: Path | None = None
    requirements: list[Path] = field(default_factory=list)
    makefile: Path | None = None
    nvmrc: Path | None = None
    python_version_files: list[Path] = field(default_factory=list)
    ci_workflows: list[Path] = field(default_factory=list)
    markdown_docs: list[Path] = field(default_factory=list)
    shell_scripts: list[Path] = field(default_factory=list)
    devcontainer: Path | None = None

    def has(self, marker: str) -> bool:
        """True when a file with this name (basename match) is in the inventory."""
        return any(path.name == marker for path in self.all_files())

    def all_files(self) -> list[Path]:
        files: list[Path] = []
        for group in (
            self.dotenv_examples,
            self.dotenv_actual,
            self.compose_files,
            self.dockerfiles,
            self.requirements,
            self.python_version_files,
            self.ci_workflows,
            self.markdown_docs,
            self.shell_scripts,
        ):
            files.extend(group)
        for maybe in (
            self.package_json,
            self.pyproject,
            self.makefile,
            self.nvmrc,
            self.devcontainer,
        ):
            if maybe is not None:
                files.append(maybe)
        return files

@dataclass
class ScanContext:
    """Everything a check may need. Checks receive this and stay pure."""

    root: Path
    files: FileInventory
    system: str  # platform.system(): Windows | Darwin | Linux
    shell: str  # detected shell name: powershell | cmd | bash | zsh | fish | sh
    env: Mapping[str, str]
    config: Mapping[str, Any] = field(default_factory=dict)

    def is_windows(self) -> bool:
        return self.system == "Windows"

    def is_secret_like(self, name: str) -> bool:
        upper = name.upper()
        return any(hint in upper for hint in SECRET_HINTS)

    def is_ignored_var(self, name: str) -> bool:
        upper = name.upper()
        return any(fnmatch.fnmatch(upper, pattern) for pattern in IGNORED_ENV_VARS)
