"""Core package: models, report aggregation, scanning, checks, and fixes."""

from envdoctor.core.models import (
    Evidence,
    Finding,
    FixSuggestion,
    ScanContext,
    Severity,
)

__all__ = [
    "Evidence",
    "Finding",
    "FixSuggestion",
    "ScanContext",
    "Severity",
]
