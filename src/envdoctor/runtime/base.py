"""Runtime contracts shared by all container backends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

class RuntimeKind(str, Enum):
    DOCKER = "docker"
    PODMAN = "podman"
    NONE = "none"

@dataclass(frozen=True)
class RuntimeStatus:
    kind: RuntimeKind
    available: bool
    detail: str = ""  # human-readable explanation, never contains secrets

@dataclass(frozen=True)
class SessionSpec:
    """Everything needed to create one ephemeral environment."""

    image: str
    name: str
    session_id: str
    owner_pid: int
    command: list[str] = field(default_factory=list)  # interactive shell by default
    workdir: str = "/workspace"
    mount_host: Path | None = None  # bind/copy source; None => pure clean room
    mount_mode: str = "bind"  # "bind" | "copy"
    env: dict[str, str] = field(default_factory=dict)  # injected via API, never argv
    ports: tuple[tuple[int, int], ...] = ()  # (host, container) pairs
    labels: dict[str, str] = field(default_factory=dict)
    auto_remove: bool = True
    tty: bool = True
    stdin_open: bool = True
    pull: str = "missing"  # missing | always | never

@dataclass(frozen=True)
class SessionResult:
    exit_code: int
    session_id: str
    container_id: str = ""
    removed: bool = False
    detail: str = ""

class RuntimeBackend(Protocol):
    """All container access in EnvDoctor flows through this protocol."""

    name: str

    def status(self) -> RuntimeStatus: ...

    def run_session(self, spec: SessionSpec) -> SessionResult: ...

    def list_sessions(self) -> list[dict[str, str]]: ...

    def kill_session(self, session_id: str) -> bool: ...

    def sweep(self, owner_pid_alive: Callable[[int], bool]) -> int: ...
