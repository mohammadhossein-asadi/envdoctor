"""Rich terminal rendering: grouped findings, evidence, and next steps.

Secret safety: renderers only ever show variable *names*, file:line evidence,
and severity — never values.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from envdoctor.core.models import Finding, FixSuggestion, ScanContext, Severity
from envdoctor.core.report import Report

# Plain glyphs; color comes from the style argument when appended to Text.
SEVERITY_ICONS = {
    Severity.OK: "OK",
    Severity.INFO: "i",
    Severity.WARNING: "!",
    Severity.ERROR: "x",
    Severity.CRITICAL: "X",
}

# ASCII-only fallback for legacy Windows consoles (cp1252 and friends).
SEVERITY_ICONS_ASCII = {
    Severity.OK: "OK",
    Severity.INFO: "i",
    Severity.WARNING: "!",
    Severity.ERROR: "x",
    Severity.CRITICAL: "X",
}

def severity_icons(console: Console) -> dict[Severity, str]:
    """Pick icon set the terminal can actually encode (cp1252-safe fallback)."""
    encoding = (getattr(console.file, "encoding", "") or "").lower().replace("-", "")
    if encoding and encoding not in ("utf8", "utf", "unicode"):
        try:
            "✓ℹ✗".encode(encoding)
        except (UnicodeEncodeError, LookupError):
            return SEVERITY_ICONS_ASCII
    return SEVERITY_ICONS

SEVERITY_STYLES = {
    Severity.OK: "green",
    Severity.INFO: "blue",
    Severity.WARNING: "yellow",
    Severity.ERROR: "red",
    Severity.CRITICAL: "bold red",
}

CATEGORY_TITLES = {
    "env": "Environment variables",
    "toolchain": "Toolchain",
    "container": "Containers",
    "docs": "Documentation",
}

def get_console() -> Console:
    return Console()

def category_of(finding: Finding) -> str:
    return finding.id.split("/", 1)[0]

def _evidence_text(finding: Finding) -> str:
    if not finding.evidence:
        return ""
    return ", ".join(e.location for e in finding.evidence[:3])

def _fix_lines(fix: FixSuggestion, ctx: ScanContext) -> list[str]:
    if fix is None or not fix.for_os(ctx.system):
        return []
    lines = [f"-> {fix.summary}"]
    if fix.command:
        lines.append(f"   $ {fix.command}")
    return lines

def render_report(report: Report, ctx: ScanContext, console: Console) -> None:
    console.print()
    title = f"[bold]EnvDoctor report[/bold] - [dim]{report.scanned_path or str(ctx.root)}[/dim]"
    console.print(title)
    runtime_note = (
        f" | runtime: {ctx.config.get('docker_status')}" if ctx.config.get("docker_status") else ""
    )
    console.print(f"OS: {ctx.system} | shell: {ctx.shell}" + runtime_note)
    console.print()

    if report.partial:
        console.print("[yellow]Some requested checks could not run; results are partial.[/yellow]")

    groups: dict[str, list[Finding]] = {}
    for finding in report.findings:
        groups.setdefault(category_of(finding), []).append(finding)

    ordered: list[str] = [k for k in ("env", "toolchain", "container", "docs") if k in groups]
    ordered += [k for k in groups if k not in ordered]

    icons = severity_icons(console)
    for key in ordered:
        findings = groups[key]
        title = CATEGORY_TITLES.get(key, key)
        body = Text()
        for finding in findings:
            icon = icons.get(finding.severity, "")
            line = f" {icon} {finding.title}"
            body.append(line + "\n", style=SEVERITY_STYLES.get(finding.severity, ""))
            evidence = _evidence_text(finding)
            if evidence:
                body.append(f"     {evidence}\n", style="dim")
            if finding.detail and finding.severity != Severity.OK:
                body.append(f"     {finding.detail}\n")
            if finding.fix is not None:
                for fix_line in _fix_lines(finding.fix, ctx):
                    body.append(fix_line + "\n")
        console.print(Panel(body, title=title, title_align="left", expand=False))

    summary = report.as_dict()["summary"]
    counts = ", ".join(f"{v} {k}" for k, v in summary.items() if v) or "no findings"
    console.print(f"[bold]Summary:[/bold] {counts}")
    console.print()

def render_next_steps(report: Report, ctx: ScanContext, console: Console) -> None:
    """Top actionable fixes, OS-filtered, ready to copy-paste."""
    steps: list[str] = []
    for finding in report.findings:
        if finding.fix is None or finding.severity < Severity.ERROR:
            continue
        fix = finding.fix
        if not fix.for_os(ctx.system) or fix.command in steps:
            continue
        steps.append(fix.command or fix.summary)
    if not steps:
        return
    console.print("[bold]Suggested next steps[/bold]")
    for idx, step in enumerate(steps[:5], start=1):
        console.print(f"  {idx}. {step}")
    console.print()

def render_env_table(rows: list[dict[str, str]], console: Console) -> None:
    table = Table(expand=False)
    for column in ("session", "name", "image", "state"):
        table.add_column(column)
    for row in rows:
        table.add_row(
            row.get("session", "")[:8],
            row.get("name", ""),
            row.get("image", ""),
            row.get("state", ""),
        )
    console.print(table)
