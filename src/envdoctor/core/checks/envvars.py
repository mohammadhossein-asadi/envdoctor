"""Env-var gap analysis (spec pillar 1).

Merges requirements from .env.example files, compose files, doc mentions, and
scripts, then diffs against the actual process environment. Classifies each
variable as MISSING / SET-BUT-DOCUMENTED-ONLY / PRESENT with file:line evidence.
"""

from __future__ import annotations

from collections.abc import Iterable

from envdoctor.core.models import Evidence, Finding, FixSuggestion, ScanContext, Severity
from envdoctor.core.scan import compose as compose_scan
from envdoctor.core.scan import docs as docs_scan
from envdoctor.core.scan import dotenv as dotenv_scan

CHECK_ID = "env-vars"


def _fix_envvar(name: str, ctx: ScanContext) -> FixSuggestion:
    """OS/shell-correct export suggestion (never echoes real values)."""
    if ctx.is_windows() and ctx.shell in ("powershell",):
        return FixSuggestion(
            summary=f"Set {name} for this session, or add it to .env",
            command=f'$env:{name} = "<value>"',
            safety="manual",
        )
    if ctx.is_windows():
        return FixSuggestion(
            summary=f"Set {name} for this session, or add it to .env",
            command=f"set {name}=<value>",
            safety="manual",
        )
    return FixSuggestion(
        summary=f"Set {name} for this session, or add it to .env",
        command=f"export {name}=<value>",
        safety="manual",
    )


def run_envvar_check(ctx: ScanContext) -> list[Finding]:
    findings: list[Finding] = []

    # --- Gather requirements -------------------------------------------------
    dotenv_vars: dict[str, tuple[str, int, str]] = {}  # name -> (file, line, example)
    for path in ctx.files.dotenv_examples:
        parsed = dotenv_scan.parse_dotenv(path)
        rel = path.name
        for entry in parsed.entries:
            if entry.name not in dotenv_vars:
                dotenv_vars[entry.name] = (rel, entry.line, entry.example_value)
            else:
                file, line, _ = dotenv_vars[entry.name]
                dotenv_vars[entry.name] = (file, line, entry.example_value)

    compose_refs: dict[str, str] = {}  # name -> "compose.yml"
    for path in ctx.files.compose_files:
        for ref in compose_scan.extract_compose_env(path):
            compose_refs.setdefault(ref.name, path.name)

    doc = docs_scan.scan_docs(ctx.files.markdown_docs)
    docs_scan.merge_script_mentions(doc, ctx.files.shell_scripts)

    # --- Classify ------------------------------------------------------------
    missing: dict[str, list[Evidence]] = {}
    documented_only: dict[str, list[Evidence]] = {}
    present: list[str] = []

    candidates = set(dotenv_vars) | set(compose_refs) | set(doc.mentions)
    for name in sorted(candidates):
        if ctx.is_ignored_var(name) or len(name) < 3:
            continue
        evidence: list[Evidence] = []
        if name in dotenv_vars:
            file, line, _example = dotenv_vars[name]
            evidence.append(Evidence(source="file", location=f"{file}:{line}", kind="dotenv"))
        if name in compose_refs:
            evidence.append(
                Evidence(source="file", location=compose_refs[name], kind="compose-env")
            )
        for mention in doc.mentions.get(name, [])[:3]:
            evidence.append(
                Evidence(
                    source="doc", location=f"{mention.file}:{mention.line}", kind="doc-mention"
                )
            )

        if name in ctx.env:
            # Present in the environment: healthy whether or not it is in .env.
            present.append(name)
            findings.append(
                Finding(
                    id=f"env/{name}/present",
                    severity=Severity.OK,
                    title=name,
                    detail="Present in the current environment.",
                    evidence=tuple(evidence),
                )
            )
            continue

        # Not in the process env: is it expected to live in .env?
        if name in dotenv_vars:
            # Declared in .env.example -> the user must create/populate .env.
            missing[name] = evidence
        elif name in compose_refs:
            # Declared only in compose (no .env.example entry) -> required.
            missing[name] = evidence
        else:
            # Mentioned in docs/scripts only -> informational, may be optional.
            documented_only[name] = evidence

    # --- Emit findings --------------------------------------------------------
    for name, evidence in missing.items():
        findings.append(
            Finding(
                id=f"env/{name}/missing",
                severity=Severity.ERROR if not ctx.is_secret_like(name) else Severity.WARNING,
                title=f"Missing environment variable {name}",
                detail=(
                    "Referenced by the repository (via .env.example or compose) but not set "
                    "in your environment or any .env file we could find."
                ),
                evidence=tuple(evidence),
                fix=_fix_envvar(name, ctx),
            )
        )
    for name, evidence in documented_only.items():
        findings.append(
            Finding(
                id=f"env/{name}/documented-only",
                severity=Severity.INFO,
                title=f"{name} is documented but never applied",
                detail=(
                    "Mentioned in docs/scripts but present in neither .env.example "
                    "nor your environment; verify whether it is required."
                ),
                evidence=tuple(evidence),
            )
        )

    if not missing and not documented_only and present:
        findings.append(
            Finding(
                id="env/all-present",
                severity=Severity.OK,
                title="All documented environment variables are set.",
                detail=f"{len(present)} variables checked.",
            )
        )
    return findings


def applies_envvar(ctx: ScanContext) -> bool:
    return bool(
        ctx.files.dotenv_examples
        or ctx.files.compose_files
        or ctx.files.markdown_docs
        or ctx.files.shell_scripts
    )


class EnvVarCheck:
    id = CHECK_ID

    @staticmethod
    def applies(ctx: ScanContext) -> bool:
        return applies_envvar(ctx)

    @staticmethod
    def run(ctx: ScanContext) -> Iterable[Finding]:
        return run_envvar_check(ctx)
