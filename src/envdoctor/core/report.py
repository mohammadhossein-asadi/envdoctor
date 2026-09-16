"""Report aggregation and exit-code policy."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from envdoctor import constants
from envdoctor.core.models import Finding, Severity

_ORDER = {
    Severity.OK: 0,
    Severity.INFO: 1,
    Severity.WARNING: 2,
    Severity.ERROR: 3,
    Severity.CRITICAL: 4,
}


@dataclass
class Report:
    """An ordered collection of findings plus scan metadata."""

    findings: list[Finding] = field(default_factory=list)
    scanned_path: str = ""
    checks_run: list[str] = field(default_factory=list)
    partial: bool = False  # True when some requested checks could not run

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, findings: list[Finding]) -> None:
        self.findings.extend(findings)

    def worst(self) -> Severity:
        if not self.findings:
            return Severity.OK
        return max((f.severity for f in self.findings), key=lambda s: _ORDER[s])

    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    def exit_code(self) -> int:
        """Exit-code policy per DESIGN.md section 5."""
        if self.partial:
            return constants.EXIT_PARTIAL
        if self.worst() >= Severity.CRITICAL:
            return constants.EXIT_FINDINGS
        if self.worst() >= Severity.ERROR and self.findings:
            return constants.EXIT_FINDINGS
        return constants.EXIT_OK

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.scanned_path,
            "checks": list(self.checks_run),
            "partial": self.partial,
            "summary": {
                "critical": self.count(Severity.CRITICAL),
                "error": self.count(Severity.ERROR),
                "warning": self.count(Severity.WARNING),
                "info": self.count(Severity.INFO),
                "ok": self.count(Severity.OK),
            },
            "findings": [f.as_dict() for f in self.findings],
        }

    def as_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent)
