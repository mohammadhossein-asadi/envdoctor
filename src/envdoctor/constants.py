"""Project-wide constants: labels, sensitive-variable hints, command ids."""

from __future__ import annotations

NAME = "envdoctor"
VERSION = "0.1.0"

# --- Container labels (org.reverse-dns style, per DESIGN.md section 6) ---
LABEL_PREFIX = "org.envdoctor"
LABEL_SESSION = f"{LABEL_PREFIX}/session"
LABEL_OWNER = f"{LABEL_PREFIX}/owner"
LABEL_NAME = f"{LABEL_PREFIX}/name"
LABEL_BASE_IMAGE = f"{LABEL_PREFIX}/image"
LABEL_MANAGED = f"{LABEL_PREFIX}/managed"

# --- Exit codes (DESIGN.md section 5) ---
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
EXIT_NO_RUNTIME = 3
EXIT_PARTIAL = 4

# --- Env var classification (per pillar 1 of the spec) ---
ENV_MISSING = "missing"
ENV_DOCUMENTED_ONLY = "documented-only"
ENV_PRESENT = "present"

# --- Heuristics: variables that look secret-ish (values are never shown anyway) ---
SECRET_HINTS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "PASS",
    "CREDENTIAL",
    "PRIVATE",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
)

# Vars that are almost always host-side config, not repo requirements.
IGNORED_ENV_VARS = frozenset(
    {
        "PATH",
        "HOME",
        "PWD",
        "SHELL",
        "USER",
        "LOGNAME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "TERM",
        "EDITOR",
        "VISUAL",
        "PAGER",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "SSH_AUTH_SOCK",
        "SSH_AGENT_PID",
        "DISPLAY",
        "XDG_*",
        "COMPUTERNAME",
        "USERNAME",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "WINDIR",
        "PROCESSOR_ARCHITECTURE",
        "NUMBER_OF_PROCESSORS",
        "OS",
    }
)
