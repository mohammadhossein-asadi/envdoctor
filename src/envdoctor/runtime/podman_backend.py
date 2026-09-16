"""Podman backend (best-effort): talks the Docker-compatible API.

Podman exposes a Docker-compatible socket on macOS/Linux; on Windows Podman
runs via WSL2, which we detect and flag rather than half-support.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S603 - fixed argv probes only
import sys

from envdoctor.runtime.base import RuntimeKind, RuntimeStatus
from envdoctor.runtime.docker_backend import DockerBackend


class PodmanBackend(DockerBackend):
    """Docker SDK pointed at the Podman socket; session logic is inherited."""

    name = "podman"

    def __init__(self, socket_path: str | None = None) -> None:
        super().__init__()
        self._socket_override = socket_path

    def status(self) -> RuntimeStatus:
        exe = shutil.which("podman")
        if exe is None:
            return RuntimeStatus(RuntimeKind.PODMAN, False, "podman CLI not found on PATH")
        if sys.platform == "win32":
            return RuntimeStatus(
                RuntimeKind.PODMAN,
                False,
                "Podman on Windows runs via WSL2; "
                "EnvDoctor currently requires Docker Desktop there.",
            )
        try:
            import docker

            client = docker.APIClient(
                version="auto",
                base_url=self._socket_url(),
            )
            client.ping()
            self._client = client
            return RuntimeStatus(RuntimeKind.PODMAN, True, "Podman (docker-compatible socket)")
        except Exception as exc:  # noqa: BLE001 - unreachable service or bad socket
            detail = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown error"
            return RuntimeStatus(RuntimeKind.PODMAN, False, f"Podman socket unreachable: {detail}")

    def _socket_url(self) -> str:
        import os
        from pathlib import Path

        if self._socket_override:
            path = self._socket_override
        else:
            candidates = [
                os.environ.get("PODMAN_SOCKET", ""),
                os.path.expanduser("~/.local/share/containers/podman.sock"),
                "/run/user/1000/podman/podman.sock",
                "/var/run/podman/podman.sock",
            ]
            path = next((p for p in candidates if p and Path(p).exists()), "")
        if not path:
            return "unix:///run/user/1000/podman/podman.sock"
        if path.startswith("unix://"):
            return path
        return "unix://" + path


def probe_podman_service() -> RuntimeStatus:
    """Public probe used by the CLI when Docker is unavailable."""
    backend = PodmanBackend()
    return backend.status()


def _podman_machine_list() -> str:  # pragma: no cover - informational helper
    try:
        out = subprocess.run(
            ["podman", "machine", "list"],  # noqa: S607 - fixed literal argv
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return out.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
