"""OS, shell, and host utilities.

Detection is deliberately conservative: on anything uncertain we fall back to
POSIX defaults, and every helper is unit-testable without touching a real host.
"""

from __future__ import annotations

import os
import platform
import sys
from collections.abc import Mapping
from pathlib import Path

from platformdirs import user_config_path

# Known names per family, used to normalize `shells`
_BASH_LIKE = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
_WINDOWS_SHELLS = {"powershell", "pwsh", "cmd", "pwsh.exe", "powershell.exe", "cmd.exe"}

def detect_system() -> str:
    """Return platform.system(): 'Windows', 'Darwin', or 'Linux'."""
    return platform.system()

def detect_shell(env: Mapping[str, str] | None = None) -> str:
    """Best-effort shell name: powershell | cmd | zsh | bash | fish | sh."""
    env = dict(env) if env is not None else dict(os.environ)

    if sys.platform == "win32":
        # `SHELL` is set by Git Bash/MSYS2 environments on Windows. Report the
        # actual shell when we recognize it; map exotic POSIX variants to bash.
        shell_var = env.get("SHELL", "").lower()
        if shell_var:
            base = Path(shell_var).stem
            if base in ("zsh", "fish"):
                return base
            if base in _BASH_LIKE:
                return "bash"
        # CI shells and scripts commonly set these.
        if env.get("PSModulePath"):
            return "powershell"
        if env.get("ComSpec"):
            base = Path(env["ComSpec"]).stem.lower()
            if "pwsh" in base:
                return "powershell"
            if "powershell" in base:
                return "powershell"
            if "cmd" in base:
                return "cmd"
        return "powershell"  # Windows default: Windows PowerShell ships with the OS

    # POSIX: prefer SHELL, then process tree hints.
    shell_var = Path(env.get("SHELL", "")).stem.lower()
    if shell_var in _BASH_LIKE:
        return shell_var
    if env.get("ZSH_VERSION"):
        return "zsh"
    if env.get("BASH_VERSION"):
        return "bash"
    if env.get("FISH_VERSION"):
        return "fish"

    # Fall back to the login shell's basename for the invoking user.
    passwd_shell = ""
    if sys.platform == "darwin" or hasattr(os, "getuid"):
        try:
            pwd_mod = __import__("pwd")
            passwd_shell = Path(pwd_mod.getpwuid(os.getuid()).pw_shell).stem.lower()
        except (ImportError, KeyError):
            passwd_shell = ""
    if passwd_shell in _BASH_LIKE:
        return passwd_shell
    return "sh"

def detect_config_dir(create: bool = False) -> Path:
    """XDG-compliant on Linux/macOS, %APPDATA% on Windows (via platformdirs)."""
    path = user_config_path("envdoctor")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path

def pid_alive(pid: int) -> bool:
    """Cross-platform liveness probe with zero external dependencies."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        # Windows: process-existence via OpenProcess (no external deps).
        try:
            import ctypes

            SYNCHRONIZE = 0x00100000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return False
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    # POSIX: signal 0 checks existence + permission.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except OSError:
        return False
    return True

def docker_install_hint(system: str) -> str:
    """OS-specific install guidance for when no container runtime is found."""
    if system == "Windows":
        return (
            "Install Docker Desktop for Windows: "
            "https://docs.docker.com/desktop/setup/install-windows-installation/ (requires WSL2)."
        )
    if system == "Darwin":
        return (
            "Install Docker Desktop for Mac: "
            "https://docs.docker.com/desktop/setup/install-mac-install/ "
            "or run `brew install colima docker` and `colima start`."
        )
    return (
        "Install Docker Engine: https://docs.docker.com/engine/install/ "
        "or rootless Podman: https://podman.io/docs/installation."
    )

def copy_mode_hint() -> str:
    """Explain copy-mode fallback (Windows bind-mount failures)."""
    return (
        "Falling back to COPY mode: your repository is copied into the container "
        "instead of bind-mounted. Changes are not written back to the host; "
        "copy the results out before exiting."
    )

def sensitive_dir_warning(dir_name: str) -> str:
    return (
        f"Refusing to mount sensitive directory {dir_name!r} by default. "
        "Re-run with --allow-sensitive-mount to override."
    )
