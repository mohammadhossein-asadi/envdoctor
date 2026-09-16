"""ScanContext assembly: the single entry point checks consume."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from envdoctor.core.models import ScanContext
from envdoctor.core.scan import build_inventory
from envdoctor.platform.system import detect_shell, detect_system

def build_context(
    root: Path,
    env: Mapping[str, str] | None = None,
    system: str | None = None,
    shell: str | None = None,
    docker_status: str | None = None,
) -> ScanContext:
    """Assemble a ScanContext.

    `docker_status` is injected by the CLI after the runtime probe so checks
    stay pure (no container I/O inside check functions).
    """
    root = root.expanduser().resolve()
    return ScanContext(
        root=root,
        files=build_inventory(root),
        system=system if system is not None else detect_system(),
        shell=shell if shell is not None else detect_shell(env),
        env=dict(os.environ) if env is None else dict(env),
        config={"docker_status": docker_status} if docker_status else {},
    )
