"""Documentation scanning: env-var mentions and platform coverage."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# The (?![A-Za-z0-9_.]) lookahead skips filenames like CODE_OF_CONDUCT.md.
ENV_MENTION_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,}(?:_[A-Z0-9]+)+)(?![A-Za-z0-9_.])")

SETUP_KEYWORDS = (
    "install",
    "setup",
    "getting started",
    "quickstart",
    "prerequisites",
    "requirements",
)

PLATFORM_KEYWORDS: dict[str, tuple[str, ...]] = {
    "windows": ("windows", "powershell", "pwsh", "cmd.exe", "winget", "choco", "chocolatey", "wsl"),
    "macos": ("macos", "mac os", "osx", "darwin", "brew", "homebrew"),
    "linux": (
        "linux",
        "apt-get",
        "apt install",
        "dnf install",
        "yum install",
        "pacman -s",
        "apk add",
    ),
}

CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


@dataclass(frozen=True)
class DocMention:
    var: str
    file: str
    line: int


@dataclass
class DocScan:
    mentions: dict[str, list[DocMention]] = field(default_factory=dict)
    platform_hits: dict[str, list[str]] = field(
        default_factory=lambda: {"windows": [], "macos": [], "linux": []}
    )
    setup_sections: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.setup_sections is None:
            self.setup_sections = []


def _strip_code_fences(text: str) -> str:
    """Mentions inside fenced blocks are usually commands, not declarations."""
    stripped = CODE_FENCE_RE.sub(" ", text)
    return stripped


def scan_docs(files: list[Path]) -> DocScan:
    """Extract ALL_CAPS var mentions and platform coverage from markdown docs."""
    scan = DocScan()
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.name
        prose = _strip_code_fences(text)

        for lineno, raw in enumerate(prose.splitlines(), start=1):
            for match in ENV_MENTION_RE.finditer(raw):
                var = match.group(1)
                scan.mentions.setdefault(var, []).append(DocMention(var=var, file=rel, line=lineno))

        lowered = text.lower()
        for platform, keywords in PLATFORM_KEYWORDS.items():
            for kw in keywords:
                if kw in lowered:
                    scan.platform_hits[platform].append(f"{rel}: {kw}")
                    break

        for line in text.splitlines():
            stripped = line.strip().lower().lstrip("#").strip()
            if (
                any(stripped.startswith(k) or k in stripped for k in SETUP_KEYWORDS)
                and len(stripped) < 80
            ):
                scan.setup_sections.append(f"{rel}: {line.strip()}")
    return scan


def merge_script_mentions(scan: DocScan, script_files: list[Path]) -> None:
    """Scripts also declare requirements (`export FOO=`, `$FOO` usage)."""
    for path in script_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.name
        for lineno, raw in enumerate(text.splitlines(), start=1):
            for match in ENV_MENTION_RE.finditer(raw):
                var = match.group(1)
                scan.mentions.setdefault(var, []).append(DocMention(var=var, file=rel, line=lineno))
