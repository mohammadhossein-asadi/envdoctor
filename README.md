<div align="center">

# 🩺 EnvDoctor

**Diagnose why any repository won't run on your machine — then step into a clean, disposable environment where it just works.**

[![CI](https://github.com/mohammadhossein-asadi/envdoctor/actions/workflows/ci.yml/badge.svg)](https://github.com/mohammadhossein-asadi/envdoctor/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#platform-support)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![type checked: mypy strict](https://img.shields.io/badge/types-mypy--strict-blue)](https://mypy-lang.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

*No more "works on my machine."*

</div>

---

## Table of contents

- [The problem](#the-problem)
- [What it does](#what-it-does)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [CLI reference](#cli-reference)
- [How it works](#how-it-works)
- [Platform support](#platform-support)
- [Safety, secrets & privacy](#safety-secrets--privacy)
- [Exit codes](#exit-codes)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security policy](#security-policy)
- [License](#license)

---

## The problem

> *"It works on my machine."*

Every developer has lost hours to it. A freshly cloned repository fails with a cryptic error, and the real cause is buried somewhere across five markdown files, a drifted `.env.example`, a Docker service nobody mentioned, and a Node version pinned in a file you didn't know existed.

The usual failure modes:

| You hit… | Because… |
|---|---|
| `KeyError: 'DATABASE_URL'` | The var is documented in `README.md` line 42 — or not at all |
| `Unsupported Python version` | `pyproject.toml` requires `>=3.11`, you have 3.10 |
| `Cannot find module` / `engine not compatible` | `.nvmrc` says 20, you're on 18 |
| `Cannot connect to the Docker daemon` | Docker Desktop isn't running (again) |
| `port is already allocated` | Something else owns 5432 |

EnvDoctor reads what the repository *declares*, probes what your machine *has*, and shows you the gap — with evidence, file/line references, and the exact fix command for **your OS and shell**. And when you just want a clean room, it drops you into an ephemeral container that vanishes the moment you exit.

## What it does

**EnvDoctor mode — diagnosis**

- 🔍 Scans `README.md`, `CONTRIBUTING.md`, `docs/`, `scripts/`, `.env.example`, `docker-compose.yml`, `Dockerfile`, `package.json`, `pyproject.toml`, `requirements.txt`, `Makefile`, GitHub Actions, and more
- 📋 Cross-references every environment variable the repo mentions against your actual shell environment and local `.env`
- 🐍 Checks Python/Node toolchain requirements from `pyproject.toml`, `.python-version`, `.nvmrc`, `package.json`, `runtime.txt`, `.tool-versions` — including Windows `py`-launcher discovery
- 🐳 Sanity-checks container setup: is a daemon reachable, is the compose plugin installed, are images pinned, are ports free
- 📝 Grades onboarding docs: which required variables are documented, where, and what's missing entirely
- 💡 Every finding carries file:line evidence and an OS-correct fix command (`$env:` on PowerShell, `export` on POSIX)

**TempEnv mode — ephemeral environments**

- 🧊 `envdoctor shell .` → a clean container with the *diagnosed* requirements pre-applied (image inferred from the repo, env vars injected, your code mounted)
- 🧪 `envdoctor temp python:3.12` → a pure clean room from any image, no diagnosis needed
- 🧹 Zero leftover state: containers are `--rm`, owned by a label, and reaped automatically — even if your terminal dies mid-session, the next `sweep` cleans up orphans

## Installation

Requires **Python 3.10+**. No cloud services, no daemon of its own.

```bash
# pipx (recommended)
pipx install envdoctor

# uv
uv tool install envdoctor

# pip
pip install envdoctor
```

You get **two commands**:

- `envdoctor` — the full doctor + clean-room CLI
- `tempenv` — just the ephemeral-environment surface, for people who only want disposable environments

<details>
<summary>Install from source (for development)</summary>

```bash
git clone https://github.com/mohammadhossein-asadi/envdoctor.git
cd envdoctor
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

</details>

## Quickstart

```bash
# 1. Why doesn't this repo run?
envdoctor check .
```

```text
 Environment variables
  ✗ MISSING      DATABASE_URL       .env.example:1, README.md:42
  ✗ MISSING      REDIS_URL          docker-compose.yml:15
  ! DOCUMENTED-ONLY  API_KEY        set in shell, but not in your .env
  ✓ PRESENT      DEBUG              .env:3

 Toolchain
  ✗ python 3.10.11 does not satisfy pyproject.toml requires-python >=3.11

 Container
  ! Docker daemon not reachable — start Docker Desktop to use `shell`/`temp`
  ! Image python:3.12 in Dockerfile is not pinned by digest

 Fix suggestions
  → PowerShell:  $env:DATABASE_URL = "postgresql://…"
  → Write missing vars to .env:   envdoctor fix . --write
```

```bash
# 2. Safe, dry-run fix: generate .env from .env.example without clobbering
envdoctor fix .          # shows a unified diff only
envdoctor fix . --write  # writes values that don't already exist

# 3. Or skip your machine entirely
envdoctor shell .                 # diagnosed requirements pre-applied
envdoctor temp python:3.12        # pure clean room, any image
envdoctor temp node:20 --mount .  # clean room with your code mounted

# The container is removed automatically when you exit. No leftovers. Ever.

# 4. The same engine as a standalone tool
tempenv python:3.12 --mount .
tempenv ps
tempenv sweep
```

## CLI reference

### `envdoctor check [PATH]`

Diagnose a repository. Default target is the current directory.

| Flag | Effect |
|---|---|
| `--json` | Machine-readable report on stdout (stable schema; nothing else printed) |
| `--strict` | Exit `1` on *any* finding, even info-level — useful as a CI gate |
| `--only env,toolchain,container,docs` | Run a subset of the four checks |

### `envdoctor fix [PATH]`

Generate `.env` from `.env.example` / `.env.sample`.

- Dry-run unified diff by default; `--write` applies it
- **Never overwrites** values that already exist in your `.env`
- Placeholder-only values (e.g. `changeme`) are copied with a comment

### `envdoctor shell [PATH]`

Diagnose, pick a sensible base image, inject required env vars, mount your code, and drop you into an interactive shell. On exit the container is destroyed automatically.

### `envdoctor temp IMAGE`

A clean room from any image. Combine with `--mount PATH` to bring your code along.

### `envdoctor ps` · `envdoctor kill NAME` · `envdoctor sweep`

List live EnvDoctor environments, stop one by name, or reap all orphaned environments (containers whose owner process is gone).

### `tempenv …`

`tempenv` exposes the identical session engine (`tempenv IMAGE [--mount PATH]`, `ps`, `kill`, `sweep`) without the diagnosis layer.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | No problems found |
| `1` | Findings at/above the severity threshold (`--strict` lowers the bar to any finding) |
| `2` | Usage error (bad flags, missing path, …) |
| `3` | No container runtime available for a command that needs one |
| `4` | Partial results — some checks failed mid-run (always treat as unreliable) |

## How it works

1. **Inventory** — a bounded walk of the repo (respects `.gitignore`, skips heavy directories) classifies files into dotenv, compose, docs, scripts, and language manifests.
2. **Parsers** — a tolerant dotenv parser (with lints), a small YAML subset parser for compose `environment:`/`env_file:` blocks (no PyYAML dependency), and a doc scanner that extracts `VAR_NAME` mentions with file:line evidence.
3. **Checks** — four pure functions over a `ScanContext` (repo path + env map), so they're trivially testable and composable:
   - `envvars` — required vs. present vs. documented-only, severity by evidence strength
   - `toolchain` — Python/Node version constraints vs. your actual interpreters
   - `container` — daemon reachability, compose plugin, unpinned images, port conflicts
   - `docscoverage` — where required vars *should* be documented but aren't
4. **Report** — findings aggregated with severities, evidence, and OS/shell-aware fix commands; rendered by Rich or emitted as JSON.
5. **Runtime** — a thin backend abstraction (Docker SDK first, Podman best-effort) creates labeled, auto-removing containers. Secrets are passed via the container API — never command lines, never logs.

See [DESIGN.md](DESIGN.md) for the full architecture.

## Platform support

| OS | Status | Notes |
|---|---|---|
| **Windows** | ✅ First-class | PowerShell-aware fix commands, `py` launcher discovery, works with Docker Desktop; console encoding handled (cp1252-safe output) |
| **macOS** | ✅ First-class | Docker Desktop, colima, or OrbStack all work |
| **Linux** | ✅ First-class | Docker or rootless Podman |

If no runtime is found, EnvDoctor **never crashes or assumes**: it tells you exactly how to install one for your OS (exit code `3`).

Podman on Windows runs through a WSL2 VM; volume mounts of Windows paths have known limitations — EnvDoctor warns rather than silently mis-mounting.

## Safety, secrets & privacy

- **Local-first**: all analysis runs on your machine. No telemetry, no phoning home. The only network traffic is image pulls you explicitly trigger.
- **Secrets are never logged** — not in reports, not in JSON output, not in container argv. Env vars are injected through the container API.
- **Sensitive mounts are refused by default**: `~/.ssh`, `~/.aws`, `~/.gnupg`, and friends require an explicit `--allow-sensitive-mount` flag.
- **`.env` is never clobbered**: `fix` merges additively and never touches values that already exist.
- **Orphan reaping**: every environment is stamped with an owner PID; `sweep` destroys containers whose owner is gone, so a crashed terminal can't leak containers.

## Exit-code-first automation

`check --json --strict` is designed as a CI gate that enforces your repository's environment contract:

```yaml
# .github/workflows/env.yml
- run: pipx install envdoctor
- run: envdoctor check . --json --strict
```

## Troubleshooting

<details>
<summary><code>Cannot connect to the Docker daemon</code></summary>

- **Windows/macOS**: start Docker Desktop and wait for the whale icon.
- **Linux**: `sudo systemctl start docker` (or use rootless Podman — EnvDoctor detects it).
- Check with `docker ps`; if that fails, EnvDoctor's `container` check will print the exact next step for your OS.
</details>

<details>
<summary>Weird characters in the terminal output (Windows)</summary>

EnvDoctor auto-falls back to ASCII-safe glyphs on consoles that can't render Unicode (e.g. cp1252 `cmd.exe`). If your font still misrenders, a UTF-8-capable terminal (Windows Terminal) is recommended.
</details>

<details>
<summary><code>check</code> reports a variable I don't recognize</summary>

Every finding cites its evidence (`file:line`). If the mention is a false positive (e.g. an all-caps identifier in prose), it's a scanner tuning issue — please [open an issue](https://github.com/mohammadhossein-asadi/envdoctor/issues) with the file and line.
</details>

## Development

```bash
git clone https://github.com/mohammadhossein-asadi/envdoctor.git
cd envdoctor
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest                      # unit + CLI tests (Docker integration tests auto-skip without a daemon)
ruff check src tests        # lint
ruff format --check .       # formatting
mypy src                    # strict typing
```

The CI matrix runs **Windows, macOS, and Linux × Python 3.10 and 3.12**, so cross-platform regressions are caught before merge.

## Roadmap

- [ ] **V1** — `pause`/`resume` for environments, plugin API for language ecosystems (Go, Rust, …), `pyproject.toml`-driven configuration
- [ ] **V2** — IDE extensions, remote runtime targets, doc-generation (`envdoctor docs` writes the env-var table into your README)

Have a use case? [Open an issue](https://github.com/mohammadhossein-asadi/envdoctor/issues) — the scope stays deliberately small: diagnosis + disposable environments, nothing else.

## Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup and the ground rules (cross-platform correctness is non-negotiable: every change must be plausibly correct on Windows, macOS, and Linux).

## Security policy

See [SECURITY.md](SECURITY.md). In short: please report vulnerabilities privately via GitHub Security Advisories rather than public issues.

## License

[MIT](LICENSE) © Mohammadhossein Asadi and contributors.

> **Note:** EnvDoctor is not affiliated with the unrelated [`env-doctor`](https://pypi.org/project/env-doctor/) PyPI package (GPU/AI library diagnosis).
