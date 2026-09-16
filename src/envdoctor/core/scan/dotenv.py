"""dotenv parsing helpers built on python-dotenv."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class DotenvEntry:
    name: str
    line: int
    example_value: str  # may be empty; NEVER a real secret in example files


@dataclass(frozen=True)
class DotenvParse:
    entries: list[DotenvEntry]
    warnings: list[str]


def parse_dotenv(path: Path) -> DotenvParse:
    """Parse a dotenv file into entries plus lints.

    python-dotenv handles quoting, comments, and `export` prefixes; we add
    line numbers and lightweight validation the library does not provide.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    values = dotenv_values(stream=io.StringIO(text))

    line_of: dict[str, int] = {}
    warnings: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("export "):
            stripped = stripped[len("export ") :]
        candidate = stripped.split("=", 1)[0].strip()
        if candidate and candidate not in line_of:
            line_of[candidate] = lineno

    entries: list[DotenvEntry] = []
    for name, value in values.items():
        if name is None:
            continue
        entries.append(DotenvEntry(name=name, line=line_of.get(name, 0), example_value=value or ""))
        if value is None or value == "":
            warnings.append(f"{path.name}:{line_of.get(name, 0)} {name} has an empty example value")
        elif not name.startswith("#") and name.upper() != name and "_" in name:
            warnings.append(f"{path.name}:{line_of.get(name, 0)} {name} is not UPPER_SNAKE_CASE")

    return DotenvParse(entries=entries, warnings=warnings)
