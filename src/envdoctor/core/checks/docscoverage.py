"""Doc-coverage analysis (spec pillar 4): platform-specific instructions."""

from __future__ import annotations

from collections.abc import Iterable

from envdoctor.core.models import Evidence, Finding, FixSuggestion, ScanContext, Severity
from envdoctor.core.scan.docs import scan_docs

CHECK_ID = "docs"

def run_docs_check(ctx: ScanContext) -> list[Finding]:
    findings: list[Finding] = []
    if not ctx.files.markdown_docs:
        findings.append(
            Finding(
                id="docs/none",
                severity=Severity.INFO,
                title="No markdown documentation found",
                detail="Contributors rely entirely on code discovery; consider adding a README.",
            )
        )
        return findings

    scan = scan_docs(ctx.files.markdown_docs)

    current_platform = {  # platform.system() -> our keyword bucket
        "Windows": "windows",
        "Darwin": "macos",
        "Linux": "linux",
    }.get(ctx.system, "linux")

    covered = {p: bool(hits) for p, hits in scan.platform_hits.items()}
    other_platforms = [p for p in ("windows", "macos", "linux") if p != current_platform]

    missing_current = not covered[current_platform]
    if missing_current:
        findings.append(
            Finding(
                id="docs/platform-missing-current",
                severity=Severity.INFO,
                title=f"No {current_platform}-specific setup instructions found in docs",
                detail=(
                    "Docs mention other platforms "
                    f"({', '.join(p for p in other_platforms if covered[p]) or 'none'}) "
                    "but not yours; setup may require undocumented steps on this OS."
                ),
                evidence=tuple(
                    Evidence(source="doc", location=loc, kind="platform-hint")
                    for loc in scan.platform_hits[current_platform][:3]
                ),
                fix=FixSuggestion(
                    summary="Document the setup steps you needed on this OS",
                    safety="manual",
                ),
            )
        )
    else:
        findings.append(
            Finding(
                id="docs/platform-covered",
                severity=Severity.OK,
                title=f"Docs include {current_platform} setup instructions.",
                detail="",
            )
        )

    if not scan.setup_sections:
        findings.append(
            Finding(
                id="docs/no-setup-section",
                severity=Severity.INFO,
                title="No explicit setup/install section detected",
                detail="Look for headings like 'Getting Started', 'Install', or 'Prerequisites'.",
            )
        )
    else:
        findings.append(
            Finding(
                id="docs/setup-found",
                severity=Severity.OK,
                title=f"Setup documentation found ({len(scan.setup_sections)} sections).",
                detail="; ".join(scan.setup_sections[:3]),
            )
        )
    return findings

def applies_docs(ctx: ScanContext) -> bool:
    return True  # docs coverage applies even when there are no docs (that's the finding)

class DocsCheck:
    id = CHECK_ID

    @staticmethod
    def applies(ctx: ScanContext) -> bool:
        return True

    @staticmethod
    def run(ctx: ScanContext) -> Iterable[Finding]:
        return run_docs_check(ctx)
