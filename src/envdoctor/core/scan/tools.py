"""Host tool discovery: interpreters, docker CLI, compose plugin.

All probes are timeout-bounded subprocess calls with fixed arguments; a probe
that fails or times out simply reports "not found" so checks degrade gracefully.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

@dataclass(frozen=True)
class InstalledTool:
    name: str
    version: str  # "" when undetermined
    path: str  # "" when not found

def _run_version(cmd: tuple[str, ...], timeout: float = 5.0) -> str:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.strip().splitlines()[0].strip() if out.strip() else ""

def probe_tool(name: str, args: tuple[str, ...] = ("--version",)) -> InstalledTool:
    """Locate a tool on PATH and ask its version. Never raises."""
    exe = shutil.which(name)
    if exe is None:
        return InstalledTool(name=name, version="", path="")
    return InstalledTool(name=name, version=_run_version((exe, *args)), path=exe)

def probe_python() -> InstalledTool:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return InstalledTool(name="python", version=version, path=sys.executable)

def probe_python_launcher() -> list[InstalledTool]:
    """Windows `py -0p` listing; empty elsewhere (POSIX has versioned binaries)."""
    if sys.platform != "win32":
        return []
    exe = shutil.which("py")
    if exe is None:
        return []
    out = _run_version((exe, "-0p"), timeout=10.0)
    interpreters: list[InstalledTool] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("installed", " -v")):
            continue
        if " * " in line or line.startswith(" -"):
            parts = [p.strip() for p in line.split(" ") if p.strip()]
            if parts and parts[0].lstrip("-").startswith("V"):
                tag = parts[0].lstrip("-V")
                path = parts[-1] if parts[-1].lower().endswith(".exe") else ""
                interpreters.append(
                    InstalledTool(name=f"python{tag}", version=tag.lstrip("V"), path=path)
                )
    return interpreters

def probe_node() -> InstalledTool:
    return probe_tool("node")

def probe_docker_cli() -> InstalledTool:
    return probe_tool("docker")

def probe_compose() -> InstalledTool:
    """Compose plugin availability via `docker compose version`."""
    exe = shutil.which("docker")
    if exe is None:
        return InstalledTool(name="docker-compose", version="", path="")
    return InstalledTool(
        name="docker-compose", version=_run_version((exe, "compose", "version")), path=exe
    )

def probe_podman() -> InstalledTool:
    return probe_tool("podman")

def port_in_use(host: str, port: int) -> bool:
    """Cross-platform port check used by container sanity warnings."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0
