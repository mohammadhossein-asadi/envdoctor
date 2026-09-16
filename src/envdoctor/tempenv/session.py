"""TempEnv session orchestration: the "clean room" lifecycle.

Security contract (DESIGN.md section 7):
- environment variables are injected through the container API, never argv,
- secret *values* are never logged; only names and presence are reported,
- sensitive host directories are refused unless explicitly allowed,
- teardown removes the container even when the session crashes.
"""

from __future__ import annotations

import os
from pathlib import Path

from envdoctor.platform.system import sensitive_dir_warning
from envdoctor.runtime.base import RuntimeBackend, SessionResult, SessionSpec
from envdoctor.runtime.docker_backend import container_name_for, labels_for, new_session_id

# Host directories we refuse to mount by default.
SENSITIVE_HOST_DIRS = (".ssh", ".aws", ".gnupg", ".kube", ".docker", ".config/gcloud")


class SensitiveMountError(RuntimeError):
    pass


def guard_sensitive_mount(mount_path: Path, allow: bool = False) -> None:
    """Refuse to mount obvious credential stores unless explicitly allowed."""
    home = Path.home()
    try:
        rel = mount_path.resolve().relative_to(home)
    except ValueError:
        return  # outside home: not one of the default-sensitive locations
    parts = rel.parts
    if not parts:
        return
    if (
        parts[0] in SENSITIVE_HOST_DIRS or "/".join(parts[:2]) in SENSITIVE_HOST_DIRS
    ) and not allow:
        raise SensitiveMountError(sensitive_dir_warning(parts[0]))


def slug_for(path: Path | None, image: str) -> str:
    base = path.name if path is not None else image.split(":")[0].split("/")[-1]
    return base or "env"


def image_for_repo(path: Path | None) -> str:
    """Best-effort default image for a repository (MVP heuristic)."""

    def has(name: str) -> bool:
        return (path / name).exists()  # type: ignore[operator]  # narrowed by callers

    if path is None:
        return "alpine:3.20"
    if has("package.json"):
        return "node:20-bookworm"
    if has("pyproject.toml") or has("requirements.txt"):
        return "python:3.12-bookworm"
    if has("go.mod"):
        return "golang:1.22-bookworm"
    if has("Cargo.toml"):
        return "rust:1-bookworm"
    return "ubuntu:24.04"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a user-provided env file for injection (values stay in memory)."""
    from dotenv import dotenv_values

    values = dotenv_values(path)
    return {str(k): str(v) for k, v in values.items() if k is not None}


def build_spec(
    *,
    image: str,
    mount: Path | None,
    mount_mode: str,
    env_vars: dict[str, str],
    env_file_vars: dict[str, str],
    inherit_env: bool,
    shell: str,
    ports: tuple[tuple[int, int], ...],
    keep: bool,
    allow_sensitive: bool = False,
) -> SessionSpec:
    """Assemble the SessionSpec with all safety rails applied."""
    session_id = new_session_id()
    if mount is not None:
        guard_sensitive_mount(mount, allow=allow_sensitive)
    merged_env: dict[str, str] = {}
    if inherit_env:
        merged_env.update(os.environ)
    merged_env.update(env_file_vars)
    merged_env.update(env_vars)
    if mount is not None:
        merged_env.setdefault("ENVDOCTOR_MOUNT_MODE", mount_mode)
    labels = labels_for(session_id, image, owner_pid=os.getpid())
    return SessionSpec(
        image=image,
        name=container_name_for(session_id, slug_for(mount, image)),
        session_id=session_id,
        owner_pid=os.getpid(),
        command=[shell],
        workdir="/workspace",
        mount_host=mount,
        mount_mode=mount_mode if mount is not None else "bind",
        env=merged_env,
        ports=ports,
        labels=labels,
        auto_remove=not keep,
    )


def run_session(backend: RuntimeBackend, spec: SessionSpec) -> SessionResult:
    """Run a session to completion; teardown is owned by the backend."""
    return backend.run_session(spec)


def sweep_orphans(backend: RuntimeBackend) -> int:
    """Reap containers whose owner process is gone; called on CLI startup."""
    from envdoctor.platform.system import pid_alive

    return backend.sweep(pid_alive)


def teardown_note(result: SessionResult) -> str:
    if result.removed:
        return "Environment removed. No leftovers."
    return "Environment already gone."
