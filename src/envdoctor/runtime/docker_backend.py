"""Docker backend via the docker SDK (primary runtime, per DESIGN.md section 3).

Teardown contract (zero leftover state):
- containers are created with our management labels,
- `run_session` owns the attach/wait/finally-remove cycle,
- `sweep()` reaps any labeled container whose owner PID is dead,
- the CLI layer additionally registers an atexit hook as belt-and-braces.

Interactive sessions always use a TTY, so container output is a raw stream
(no multiplexing headers) and can be piped straight to the terminal.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tarfile
import threading
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from envdoctor import constants
from envdoctor.runtime.base import RuntimeKind, RuntimeStatus, SessionResult, SessionSpec

class DockerBackend:
    name = "docker"

    def __init__(self) -> None:
        self._client: Any | None = None  # lazy docker.APIClient; import stays inside methods

    # --- status ---------------------------------------------------------------

    def status(self) -> RuntimeStatus:
        try:
            import docker
        except ImportError:
            return RuntimeStatus(RuntimeKind.DOCKER, False, "docker SDK not installed")
        try:
            client = docker.APIClient(version="auto")
            client.ping()
            self._client = client
            info = client.version()
            return RuntimeStatus(
                RuntimeKind.DOCKER, True, f"Docker {info.get('Version', '')}".strip()
            )
        except Exception as exc:  # noqa: BLE001 - any failure means "unavailable"
            detail = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown error"
            return RuntimeStatus(RuntimeKind.DOCKER, False, detail)

    def _client_or_none(self) -> Any:
        if self._client is None:
            self.status()
        return self._client

    # --- session lifecycle ------------------------------------------------------

    def run_session(self, spec: SessionSpec) -> SessionResult:
        client = self._client_or_none()
        if client is None:
            status = self.status()
            return SessionResult(
                exit_code=constants.EXIT_NO_RUNTIME,
                session_id=spec.session_id,
                detail=status.detail,
            )

        container = self._create_container(client, spec)
        labels = spec.labels
        session_id = labels.get(constants.LABEL_SESSION, spec.session_id)
        exit_code: object = 1

        try:
            client.start(container)
            if spec.tty and spec.stdin_open:
                self._attach_interactive(client, container)
            else:
                self._follow_output(client, container)
            exit_code = client.wait(container)["StatusCode"]
        finally:
            removed = self._force_remove_quietly(client, container)
        return SessionResult(
            exit_code=int(exit_code) if isinstance(exit_code, int) else 1,
            session_id=session_id,
            container_id=str(container.get("Id", "")),
            removed=removed,
        )

    def _create_container(self, client: Any, spec: SessionSpec) -> Any:
        self._ensure_image(client, spec)

        host_kwargs: dict[str, object] = {}
        volumes: list[str] | None = None
        if spec.mount_host is not None and spec.mount_mode == "bind":
            host_kwargs["binds"] = {str(spec.mount_host): {"bind": spec.workdir, "mode": "rw"}}
        elif spec.mount_host is not None and spec.mount_mode == "copy":
            volumes = [spec.workdir]
        if spec.ports:
            host_kwargs["port_bindings"] = {c: h for h, c in spec.ports}
        host_config = client.create_host_config(**host_kwargs)

        command = spec.command or ["/bin/sh"]
        container = client.create_container(
            image=spec.image,
            command=command,
            stdin_open=spec.stdin_open,
            tty=spec.tty,
            working_dir=spec.workdir,
            environment=dict(spec.env),
            labels={**spec.labels, constants.LABEL_MANAGED: "1"},
            host_config=host_config,
            name=spec.name,
            volumes=volumes,
        )
        if spec.mount_host is not None and spec.mount_mode == "copy":
            self._copy_directory_into(client, container, spec.mount_host, spec.workdir)
        return container

    def _ensure_image(self, client: Any, spec: SessionSpec) -> None:
        try:
            client.inspect_image(spec.image)
            return
        except Exception:  # noqa: BLE001 - not found (or probe failure) -> pull below
            if spec.pull == "never":
                raise
        for _ in client.pull(spec.image, stream=True, decode=True):
            continue  # consume progress; failures raise naturally

    def _attach_interactive(self, client: Any, container: Any) -> None:
        """Attach with stdin/stdout forwarding over a TTY container."""
        sock = client.attach_socket(
            container,
            params={"stdout": 1, "stderr": 1, "stdin": 1, "stream": 1, "logs": 1},
        )
        stop = threading.Event()

        def pump_stdin() -> None:
            try:
                while not stop.is_set():
                    data = sys.stdin.buffer.read1(4096)  # type: ignore[union-attr]
                    if not data:
                        break
                    sock.sendall(data)
            except (OSError, ValueError):
                pass
            finally:
                with contextlib.suppress(Exception):  # best-effort half-close
                    sock.shutdown(__import__("socket").SHUT_WR)

        thread = threading.Thread(target=pump_stdin, daemon=True)
        thread.start()
        try:
            while True:
                try:
                    chunk = sock.recv(4096)
                except AttributeError:
                    chunk = sock.read(4096)
                if not chunk:
                    break
                _write_out(chunk)
        finally:
            stop.set()
            with contextlib.suppress(Exception):
                sock.close()

    def _follow_output(self, client: Any, container: Any) -> None:
        """Non-interactive: stream logs until the container stops."""
        for chunk in client.logs(container, stream=True, follow=True):
            _write_out(chunk)

    def _copy_directory_into(self, client: Any, container: Any, source: Path, target: str) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    tar.add(os.fspath(path), arcname=path.relative_to(source).as_posix())
        buffer.seek(0)
        client.put_archive(container, target, buffer.getvalue())

    @staticmethod
    def _force_remove_quietly(client: Any, container: Any) -> bool:
        try:
            client.remove_container(container, force=True)
            return True
        except Exception:  # noqa: BLE001 - auto-remove may have raced us; gone == good
            return True

    # --- session management -----------------------------------------------------

    def list_sessions(self) -> list[dict[str, str]]:
        client = self._client_or_none()
        if client is None:
            return []
        out: list[dict[str, str]] = []
        for container in client.containers(
            all=True, filters={"label": f"{constants.LABEL_MANAGED}=1"}
        ):
            labels = container.get("Labels") or {}
            names = container.get("Names") or [""]
            out.append(
                {
                    "session": labels.get(constants.LABEL_SESSION, ""),
                    "name": (names[0] or "").lstrip("/"),
                    "image": container.get("Image", ""),
                    "state": container.get("State", ""),
                }
            )
        return out

    def kill_session(self, session_id: str) -> bool:
        client = self._client_or_none()
        if client is None:
            return False
        found = False
        for container in client.containers(
            all=True, filters={"label": f"{constants.LABEL_SESSION}={session_id}"}
        ):
            client.remove_container(container, force=True)
            found = True
        return found

    def sweep(self, owner_pid_alive: Callable[[int], bool]) -> int:
        """Remove managed containers whose owner PID is no longer alive."""
        client = self._client_or_none()
        if client is None:
            return 0
        reaped = 0
        for container in client.containers(
            all=True, filters={"label": f"{constants.LABEL_MANAGED}=1"}
        ):
            labels = container.get("Labels") or {}
            owner = labels.get(constants.LABEL_OWNER, "")
            if owner.isdigit() and not owner_pid_alive(int(owner)):
                try:
                    client.remove_container(container["Id"], force=True)
                    reaped += 1
                except Exception:  # noqa: BLE001 - best-effort sweep
                    continue
        return reaped

def _write_out(chunk: bytes | str) -> None:
    data = chunk.encode("utf-8", errors="replace") if isinstance(chunk, str) else chunk
    out = sys.stdout.buffer
    if out is None:  # pragma: no cover - closed stdout
        return
    out.write(data)
    out.flush()

# --- module-level helpers used by the session layer ---------------------------

def new_session_id() -> str:
    return uuid.uuid4().hex

def container_name_for(session_id: str, slug: str) -> str:
    clean = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug)[:32].strip("-") or "env"
    return f"envdoctor-{clean}-{session_id[:8]}"

def labels_for(
    session_id: str, image: str, owner_pid: int, extra: dict[str, str] | None = None
) -> dict[str, str]:
    labels = {
        constants.LABEL_MANAGED: "1",
        constants.LABEL_SESSION: session_id,
        constants.LABEL_OWNER: str(owner_pid),
        constants.LABEL_BASE_IMAGE: image,
    }
    if extra:
        labels.update(extra)
    return labels

def iter_named_sessions(
    sessions: Iterable[dict[str, str]],
) -> Iterable[dict[str, str]]:  # pragma: no cover
    """Hook for tests/filters; keeps list shape stable."""
    return sessions
