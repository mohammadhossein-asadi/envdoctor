"""Language toolchain requirements: Python and Node version constraints."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 path
    import tomli as tomllib  # type: ignore[import-not-found]

@dataclass(frozen=True)
class ToolchainReq:
    tool: str  # "python" | "node"
    specifier: str  # e.g. ">=3.10", ">=18"
    source: str  # "pyproject.toml:12" style reference

@dataclass
class LanguageReqs:
    python: list[ToolchainReq] = field(default_factory=list)
    node: list[ToolchainReq] = field(default_factory=list)

def _specifier_from_nvmrc(raw: str) -> str:
    token = raw.strip().lstrip("v")
    if token in ("node", ""):
        return ""
    if token[0].isdigit():
        return f"=={token}" if token.count(".") == 2 else f">={token}"
    return token

def _specifier_from_runtime_txt(raw: str) -> str:
    token = raw.strip()
    if token.lower().startswith("python-"):
        return ">=" + token[len("python-") :]
    return ""

def extract_language_reqs(
    package_json: Path | None,
    pyproject: Path | None,
    nvmrc: Path | None,
    python_version_files: list[Path],
) -> LanguageReqs:
    """Read required toolchain versions from the files repos actually use."""
    reqs = LanguageReqs()

    if package_json is not None and package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            data = {}
        engines = data.get("engines") or {}
        node_spec = engines.get("node") if isinstance(engines, dict) else None
        if node_spec:
            reqs.node.append(ToolchainReq("node", str(node_spec), "package.json (engines.node)"))

    if nvmrc is not None and nvmrc.exists():
        spec = _specifier_from_nvmrc(
            nvmrc.read_text(encoding="utf-8", errors="replace").splitlines()[0]
            if nvmrc.read_text(encoding="utf-8", errors="replace").splitlines()
            else ""
        )
        if spec:
            reqs.node.append(ToolchainReq("node", spec, ".nvmrc"))

    if pyproject is not None and pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            data = {}
        project = data.get("project") or {}
        requires_python = project.get("requires-python")
        if isinstance(requires_python, str):
            reqs.python.append(
                ToolchainReq("python", requires_python, "pyproject.toml (requires-python)")
            )
        tool_sections = data.get("tool") or {}
        poetry = tool_sections.get("poetry") or {}
        if isinstance(poetry, dict):
            deps = poetry.get("dependencies") or {}
            py_value = deps.get("python")
            if isinstance(py_value, str):
                reqs.python.append(
                    ToolchainReq("python", py_value, "pyproject.toml (poetry.dependencies.python)")
                )

    for path in python_version_files:
        if not path.exists():
            continue
        lines = [
            ln.strip()
            for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip()
        ]
        if not lines:
            continue
        first = lines[0]
        name = path.name
        if name == ".python-version":
            reqs.python.append(ToolchainReq("python", f">={first}", ".python-version"))
        elif name == "runtime.txt":
            spec = _specifier_from_runtime_txt(first)
            if spec:
                reqs.python.append(ToolchainReq("python", spec, "runtime.txt"))
        elif name == ".tool-versions":
            for line in lines:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "python":
                    reqs.python.append(ToolchainReq("python", f">={parts[1]}", ".tool-versions"))
                elif len(parts) >= 2 and parts[0] == "nodejs":
                    reqs.node.append(ToolchainReq("node", f">={parts[1]}", ".tool-versions"))

    return reqs
