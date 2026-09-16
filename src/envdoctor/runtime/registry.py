"""Runtime selection: Docker first, Podman fallback, honest failure otherwise."""

from __future__ import annotations

from envdoctor.platform.system import docker_install_hint
from envdoctor.runtime.base import RuntimeBackend, RuntimeKind, RuntimeStatus
from envdoctor.runtime.docker_backend import DockerBackend
from envdoctor.runtime.podman_backend import PodmanBackend

def best_backend(prefer: str | None = None) -> RuntimeBackend:
    """Return the first available backend; never raises.

    Selection order: explicit preference, then Docker, then Podman.
    A backend with a runtime present but the daemon stopped still counts as
    the chosen backend so we can show its exact error message.
    """
    candidates: list[RuntimeBackend] = []
    if prefer == "podman":
        candidates = [PodmanBackend(), DockerBackend()]
    elif prefer == "docker":
        candidates = [DockerBackend(), PodmanBackend()]
    else:
        candidates = [DockerBackend(), PodmanBackend()]

    for backend in candidates:
        status = backend.status()
        if status.available:
            return backend
    # Nothing available: hand back docker backend so callers get its detail.
    return candidates[0]

def runtime_status_of(backend: RuntimeBackend) -> RuntimeStatus:
    return backend.status()

def no_runtime_message(backend: RuntimeBackend, system: str) -> str:
    status = backend.status()
    if status.kind is RuntimeKind.NONE or not status.detail:
        detail = "No container runtime is installed or reachable."
    else:
        detail = status.detail
    return f"{detail}\n{docker_install_hint(system)}"
