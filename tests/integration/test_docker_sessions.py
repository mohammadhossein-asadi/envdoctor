"""Real-container tests. Skipped unless a runtime answers (pytest -m docker)."""

from __future__ import annotations

import pytest

from envdoctor.runtime.base import SessionSpec
from envdoctor.runtime.docker_backend import (
    DockerBackend,
    container_name_for,
    labels_for,
    new_session_id,
)
from envdoctor.tempenv.session import sweep_orphans

docker_available = DockerBackend().status().available
requires_docker = pytest.mark.skipif(not docker_available, reason="no container runtime available")


@requires_docker
@pytest.mark.docker
def test_noninteractive_session_runs_and_removes() -> None:
    backend = DockerBackend()
    session_id = new_session_id()
    spec = SessionSpec(
        image="alpine:3.20",
        name=container_name_for(session_id, "test"),
        session_id=session_id,
        owner_pid=0,
        command=["/bin/sh", "-c", "echo hello-from-envdoctor"],
        tty=False,
        stdin_open=False,
        labels=labels_for(session_id, "alpine:3.20", owner_pid=0),
    )
    result = backend.run_session(spec)
    assert result.exit_code == 0
    assert result.removed
    assert backend.list_sessions() == [] or all(
        row["session"] != session_id for row in backend.list_sessions()
    )


@requires_docker
@pytest.mark.docker
def test_kill_session_by_id() -> None:
    backend = DockerBackend()
    session_id = new_session_id()
    spec = SessionSpec(
        image="alpine:3.20",
        name=container_name_for(session_id, "killtest"),
        session_id=session_id,
        owner_pid=0,
        command=["/bin/sh", "-c", "sleep 30"],
        tty=False,
        stdin_open=False,
        labels=labels_for(session_id, "alpine:3.20", owner_pid=0),
    )
    # Run in a thread so we can kill it from the test thread.
    import threading

    outcome: list[object] = []

    def runner() -> None:
        outcome.append(backend.run_session(spec))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    import time

    time.sleep(1.5)
    assert backend.kill_session(session_id)
    thread.join(timeout=15)
    assert not backend.list_sessions() or all(
        row["session"] != session_id for row in backend.list_sessions()
    )


@requires_docker
@pytest.mark.docker
def test_sweep_reaps_dead_owner() -> None:
    backend = DockerBackend()
    session_id = new_session_id()
    dead_pid = 999999999
    spec = SessionSpec(
        image="alpine:3.20",
        name=container_name_for(session_id, "sweep"),
        session_id=session_id,
        owner_pid=dead_pid,
        command=["/bin/sh", "-c", "sleep 30"],
        tty=False,
        stdin_open=False,
        labels=labels_for(session_id, "alpine:3.20", owner_pid=dead_pid),
    )
    import threading
    import time

    def runner() -> None:
        backend.run_session(spec)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    time.sleep(1.5)
    reaped = sweep_orphans(backend)
    assert reaped >= 1
    thread.join(timeout=15)
