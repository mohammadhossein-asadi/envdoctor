"""Container sanity checks (spec pillar 3)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from envdoctor.core.models import Evidence, Finding, FixSuggestion, ScanContext, Severity
from envdoctor.core.scan.tools import port_in_use, probe_compose, probe_docker_cli

CHECK_ID = "container"

IMAGE_PORT_RE = re.compile(r"['\"]?(\d{1,5})['\"]?:\d{1,5}")


def run_container_check(ctx: ScanContext) -> list[Finding]:
    findings: list[Finding] = []
    docker = probe_docker_cli()

    if docker.path == "":
        if ctx.files.compose_files or ctx.files.dockerfiles:
            findings.append(
                Finding(
                    id="container/docker-absent",
                    severity=Severity.WARNING,
                    title="Docker is not installed but this repo ships container files",
                    detail=(
                        "compose files and Dockerfiles were found; "
                        "without a runtime you cannot use them."
                    ),
                    evidence=(
                        Evidence(
                            source="runtime",
                            location="PATH",
                            kind="probe",
                        ),
                    ),
                    fix=FixSuggestion(
                        summary="Install Docker (see docs for your OS)",
                        command="https://docs.docker.com/get-docker/",
                        safety="manual",
                    ),
                )
            )
        return findings

    # Docker CLI exists; probe the daemon through the SDK.
    daemon_ok, daemon_detail = _probe_daemon()
    if not daemon_ok:
        findings.append(
            Finding(
                id="container/docker-not-running",
                severity=Severity.ERROR,
                title="Docker is installed but not reachable",
                detail=daemon_detail,
                evidence=(Evidence(source="runtime", location="docker daemon", kind="probe"),),
                fix=FixSuggestion(
                    summary="Start Docker Desktop (or the dockerd service)",
                    command="sudo systemctl start docker  # or launch Docker Desktop",
                    safety="manual",
                ),
            )
        )
        return findings

    compose = probe_compose()
    has_compose_files = bool(ctx.files.compose_files)
    if has_compose_files and compose.version == "":
        findings.append(
            Finding(
                id="container/compose-missing",
                severity=Severity.WARNING,
                title="compose files found but the docker compose plugin is missing",
                detail="Install the compose plugin to use these files.",
                evidence=(
                    Evidence(
                        source="file",
                        location=", ".join(p.name for p in ctx.files.compose_files),
                        kind="compose",
                    ),
                ),
                fix=FixSuggestion(
                    summary="Install the compose plugin",
                    command="docker-compose v2 ships with Docker Desktop; on Linux see https://docs.docker.com/compose/install/",
                    safety="manual",
                ),
            )
        )

    findings.extend(_image_pins(ctx))
    findings.extend(_port_warnings(ctx))
    return findings


def _probe_daemon() -> tuple[bool, str]:
    """Import-guarded SDK probe; returns (ok, human detail)."""
    try:
        import docker  # noqa: PLC0415 - deliberate lazy import

        client = docker.from_env()
        client.ping()
        return True, ""
    except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown error"
        return False, f"Docker daemon probe failed: {detail}"


def _image_pins(ctx: ScanContext) -> list[Finding]:
    findings: list[Finding] = []
    for path in ctx.files.compose_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, raw in enumerate(text.splitlines(), start=1):
            match = re.search(r"image:\s*['\"]?([^'\"\s]+)", raw)
            if not match:
                continue
            image = match.group(1)
            if image.endswith(":latest") or ":" not in image:
                findings.append(
                    Finding(
                        id=f"container/unpinned-image/{path.name}:{lineno}",
                        severity=Severity.INFO,
                        title=f"Image {image!r} is not pinned to a digest or version",
                        detail="Unpinned images drift over time and break reproducibility.",
                        evidence=(
                            Evidence(
                                source="file",
                                location=f"{path.name}:{lineno}",
                                snippet=image,
                                kind="compose",
                            ),
                        ),
                    )
                )
    return findings


def _port_warnings(ctx: ScanContext) -> list[Finding]:
    findings: list[Finding] = []
    common_dev_ports = {3000, 5432, 6379, 8000, 8080, 5173, 9000}
    for path in ctx.files.compose_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ports: set[int] = set()
        for lineno, raw in enumerate(text.splitlines(), start=1):
            match = IMAGE_PORT_RE.search(raw)
            if not match:
                continue
            host_port = int(match.group(1))
            ports.add(host_port)
            if host_port in common_dev_ports and port_in_use("127.0.0.1", host_port):
                findings.append(
                    Finding(
                        id=f"container/port-in-use/{path.name}:{lineno}",
                        severity=Severity.WARNING,
                        title=f"Host port {host_port} is already in use",
                        detail=(
                            f"Referenced by {path.name}:{lineno}; the container may fail to bind."
                        ),
                        evidence=(
                            Evidence(
                                source="runtime",
                                location=f"127.0.0.1:{host_port}",
                                kind="port-probe",
                            ),
                        ),
                    )
                )
    return findings


def applies_container(ctx: ScanContext) -> bool:
    return bool(ctx.files.compose_files or ctx.files.dockerfiles)


class ContainerCheck:
    id = CHECK_ID

    @staticmethod
    def applies(ctx: ScanContext) -> bool:
        return applies_container(ctx)

    @staticmethod
    def run(ctx: ScanContext) -> Iterable[Finding]:
        return run_container_check(ctx)
