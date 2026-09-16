"""Toolchain checks (spec pillar 2): required vs installed Python and Node."""

from __future__ import annotations

import re
from collections.abc import Iterable

from envdoctor.core.models import Evidence, Finding, FixSuggestion, ScanContext, Severity
from envdoctor.core.scan.language import extract_language_reqs
from envdoctor.core.scan.tools import InstalledTool, probe_node, probe_python, probe_python_launcher

CHECK_ID = "toolchain"

_SPEC_RE = re.compile(r"^\s*(===|==|!=|<=|>=|<|>|~=)?\s*(?P<ver>[0-9][0-9A-Za-z.\-+*]*)\s*$")

def _parse_requirement(req: str) -> tuple[str, str] | None:
    """Return (op, version) for a simple single-clause specifier, else None."""
    match = _SPEC_RE.match(req)
    if not match:
        return None
    op = match.group(1) or ">="
    return op, match.group("ver")

def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in re.split(r"[.\-+]", version):
        if token.isdigit():
            parts.append(int(token))
        else:
            break
    return tuple(parts) if parts else (0,)

def _compare(version: str, op: str, required: str) -> bool:
    vt = _version_tuple(version)
    rt = _version_tuple(required)
    if required.endswith("*"):
        # `3.10.*` style: prefix equality (the star token was dropped already).
        return vt[: len(rt)] == rt
    base = {
        ">=": vt >= rt,
        "<=": vt <= rt,
        ">": vt > rt,
        "<": vt < rt,
        "==": vt[: len(rt)] == rt,
        "===": vt[: len(rt)] == rt,
        "!=": vt[: len(rt)] != rt,
        "~=": vt[: len(rt)] == rt,
    }
    return base.get(op, True)

def _runtime_available(ctx: ScanContext, tool: str, required_version: str) -> tuple[bool, str, str]:
    """Return (available, version, how_detected)."""
    if tool == "python":
        installed = probe_python()
        if _compare(installed.version, ">=", required_version):
            return True, installed.version, f"python {installed.version} ({installed.path})"
        # Check the Windows py launcher and common versioned binaries before failing.
        for interp in probe_python_launcher():
            if _compare(interp.version, ">=", required_version):
                return True, interp.version, f"{interp.name} via py launcher"
        for minor in range(8, 14):
            found = probe_tool_versioned("python3." + str(minor))
            if found.version and _compare(found.version, ">=", required_version):
                return True, found.version, f"{found.name} at {found.path}"
        return False, installed.version, f"python {installed.version or 'not found'}"
    installed_node = probe_node()
    if installed_node.version and _compare(
        installed_node.version.lstrip("v"), ">=", required_version
    ):
        return (
            True,
            installed_node.version,
            f"node {installed_node.version} ({installed_node.path})",
        )
    return (
        False,
        installed_node.version or "not found",
        f"node {installed_node.version or 'not found'}",
    )

def probe_tool_versioned(name: str) -> InstalledTool:
    """Imported lazily to keep the module import graph clean."""
    from envdoctor.core.scan.tools import probe_tool

    return probe_tool(name)

def _install_fix(tool: str, ctx: ScanContext) -> FixSuggestion:
    if tool == "python":
        if ctx.system == "Windows":
            return FixSuggestion(
                summary="Install the required Python from python.org or via the Microsoft Store",
                command="winget install Python.Python.3.12",
                safety="caution",
                applies_to="windows",
            )
        if ctx.system == "Darwin":
            return FixSuggestion(
                summary="Install the required Python via Homebrew",
                command="brew install python@3.12",
                safety="caution",
                applies_to="macos",
            )
        return FixSuggestion(
            summary="Install the required Python via your package manager or pyenv",
            command="sudo apt-get install python3.12  # or: pyenv install 3.12",
            safety="caution",
            applies_to="linux",
        )
    # Node
    if ctx.system == "Windows":
        return FixSuggestion(
            summary="Install Node via winget or nvm-windows",
            command="winget install OpenJS.NodeJS.LTS",
            safety="caution",
            applies_to="windows",
        )
    if ctx.system == "Darwin":
        return FixSuggestion(
            summary="Install Node via Homebrew or nvm",
            command="brew install node@20",
            safety="caution",
            applies_to="macos",
        )
    return FixSuggestion(
        summary="Install Node via nvm or your package manager",
        command="nvm install 20 && nvm use 20",
        safety="caution",
        applies_to="linux",
    )

def run_toolchain_check(ctx: ScanContext) -> list[Finding]:
    findings: list[Finding] = []
    reqs = extract_language_reqs(
        package_json=ctx.files.package_json,
        pyproject=ctx.files.pyproject,
        nvmrc=ctx.files.nvmrc,
        python_version_files=ctx.files.python_version_files,
    )
    for req in reqs.python + reqs.node:
        parsed = _parse_requirement(req.specifier)
        if parsed is None:
            findings.append(
                Finding(
                    id=f"toolchain/{req.tool}/unparsed",
                    severity=Severity.INFO,
                    title=f"Could not parse {req.tool} requirement {req.specifier!r}",
                    detail=f"Source: {req.source}",
                    evidence=(
                        Evidence(source="toolchain", location=req.source, snippet=req.specifier),
                    ),
                )
            )
            continue
        op, version = parsed
        ok, found_version, how = _runtime_available(ctx, req.tool, version)
        evidence = (
            Evidence(
                source="toolchain", location=req.source, snippet=f"{req.tool} {req.specifier}"
            ),
        )
        if ok:
            findings.append(
                Finding(
                    id=f"toolchain/{req.tool}/ok",
                    severity=Severity.OK,
                    title=f"{req.tool} {req.specifier} satisfied ({how})",
                    detail=f"Found {req.tool} {found_version} on this machine.",
                    evidence=evidence,
                )
            )
        else:
            findings.append(
                Finding(
                    id=f"toolchain/{req.tool}/missing",
                    severity=Severity.ERROR,
                    title=f"Required {req.tool} {op}{version} not satisfied",
                    detail=f"Source: {req.source}. {how}",
                    evidence=evidence,
                    fix=_install_fix(req.tool, ctx),
                )
            )
    return findings

def applies_toolchain(ctx: ScanContext) -> bool:
    return bool(
        ctx.files.package_json
        or ctx.files.pyproject
        or ctx.files.nvmrc
        or ctx.files.python_version_files
    )

class ToolchainCheck:
    id = CHECK_ID

    @staticmethod
    def applies(ctx: ScanContext) -> bool:
        return applies_toolchain(ctx)

    @staticmethod
    def run(ctx: ScanContext) -> Iterable[Finding]:
        return run_toolchain_check(ctx)
