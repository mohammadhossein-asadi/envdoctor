"""Check protocol and registry (DESIGN.md section 6)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from envdoctor.core.models import Finding, ScanContext

class Check(Protocol):
    """A pure diagnosis unit: ScanContext in, findings out. No I/O here."""

    id: str

    def applies(self, ctx: ScanContext) -> bool: ...

    def run(self, ctx: ScanContext) -> Iterable[Finding]: ...

REGISTRY: list[Check] = []

def register(check: Check) -> Check:
    """Registry used by the CLI; keeps ordering stable for tests."""
    REGISTRY.append(check)
    return check

def all_checks() -> list[Check]:
    return list(REGISTRY)
