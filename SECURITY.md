# Security policy

## Supported versions

| Version | Supported |
|---|---|
| latest `main` | ✅ |

## Reporting a vulnerability

Please report vulnerabilities **privately** via [GitHub Security Advisories](https://github.com/mohammadhossein-asadi/envdoctor/security/advisories/new) rather than public issues. Include a description, reproduction steps, and affected components. You can expect an initial response within a few days.

## Scope and design posture

EnvDoctor is a local developer tool. Areas we treat as security-sensitive:

- **Secret handling** — environment variables are injected through the container API, never on command lines, and are never written to logs or JSON reports.
- **Sensitive mounts** — well-known credential directories (`~/.ssh`, `~/.aws`, `~/.gnupg`, …) are refused unless the user passes an explicit opt-in flag.
- **File writes** — `envdoctor fix` never overwrites existing `.env` values.
- **Container lifecycle** — sessions are labeled and reaped; nothing runs privileged and no host paths are mounted implicitly.

## What is out of scope

- Vulnerabilities in Docker/Podman themselves — report upstream.
- Report content that leaks secrets the user explicitly placed in scanned files (we aim to minimize, but the source of truth is the user's repository).
