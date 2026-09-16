"""Shared fixtures: isolated temp repos and pre-built ScanContexts."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from envdoctor.core.models import ScanContext
from envdoctor.core.scan import build_inventory


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Path]:
    """An empty repository directory that is removed after the test."""
    yield tmp_path


def make_context(
    root: Path, env: dict[str, str] | None = None, system: str = "Linux", shell: str = "bash"
) -> ScanContext:
    return ScanContext(
        root=root,
        files=build_inventory(root),
        system=system,
        shell=shell,
        env=env or {},
        config={},
    )


@pytest.fixture
def context_factory(repo: Path):
    def _make(
        files: dict[str, str], env: dict[str, str] | None = None, system: str = "Linux"
    ) -> ScanContext:
        for name, content in files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return make_context(repo, env=env, system=system)

    return _make
