# EnvDoctor (with TempEnv core) — Design Specification

> **Status:** Approved spec · **Package:** `envdoctor` (PyPI name verified available) · **License:** MIT
>
> **Disambiguation:** Not affiliated with the unrelated `env-doctor` PyPI project (GPU/AI library diagnosis).

**Pitch:** *Diagnose why any repository won't run on your machine — then step into a clean, disposable environment where it just works.*

---

## 0. Locked decisions

- **Two entrypoints**: `envdoctor` (full CLI) and `tempenv` (alias binary routing to the ephemeral-env commands). One package, two commands.
- **MVP diagnosis = all four pillars**: env-var gap analysis, toolchain checks, container sanity checks, doc-coverage analysis.
- Research findings baked in: PyPI name `envdoctor` is **available** (verified); `env-doctor` on PyPI is an unrelated GPU-diagnosis tool → we take `envdoctor` and add a README disambiguation note. The `docker` SDK is production-stable and current (verified) → primary runtime driver.

## 1. Product name & pitch

**envdoctor** — *"Diagnose why any repository won't run on your machine — then step into a clean, disposable environment where it just works."*

- `envdoctor check/fix/shell/temp/...` — the full experience.
- `tempenv <image|path>`, `tempenv ps|pause|resume|kill|sweep` — top-level mirror of the ephemeral-environment surface for users who only ever want clean rooms. Implemented by mounting the same Typer TempEnv sub-app at top level; zero code duplication.

## 2. Feature prioritization

### MVP (v0.1–v0.3)

**Diagnosis — all four pillars:**

1. **Env-var gap analysis**: parse `.env.example` / `.env.sample` / `.env.template`, compose `environment:` / `env_file:`, and regex-scan docs + scripts for `ALL_CAPS_VAR` mentions → diff against the real process environment → classified as MISSING / SET-BUT-DOCUMENTED-ONLY (should live in `.env`) / PRESENT. Every finding carries evidence (`file:line`).
2. **Toolchain checks**: required Python (`pyproject.toml` `requires-python`, `.python-version`, `runtime.txt`) and Node (`package.json` `engines`, `.nvmrc`) compared against installed interpreters (found via `shutil.which`, `py -0p` on Windows); per-OS install suggestions.
3. **Container sanity**: Docker/compose presence; is Docker reachable (SDK → context → pipe/socket probe)? compose plugin present? unpinned `:latest` images flagged; obvious port-collision warnings.
4. **Doc-coverage analysis**: scan `README`/`CONTRIBUTING`/`docs/**/*.md` for setup sections and platform keywords (`brew`/`apt`/`choco`/`winget`, PowerShell vs bash); flag platform-specific steps and missing docs for the detected stack.

**Commands**: `check` (`--json`, `--strict`, `--only env,toolchain,container,docs`), `fix` (dry-run diff by default; generates `.env` from `.env.example` without touching existing values; `--write` to apply), `shell` / `temp`, `ps`, `kill`, `sweep`.

**Runtime**: Docker via SDK (primary), Podman via docker-compatible socket (best-effort, Windows limitation noted); graceful "no runtime" message with OS-specific install pointers — never assumes Docker exists.

**Teardown**: `AutoRemove` + `finally`/`atexit`/SIGBREAK handling on Windows + label-based orphan sweeper on every CLI start → zero leftover containers by default.

**Output**: Rich panels with severity colors, evidence column, "suggested next steps" with copy-paste commands for the *detected* OS and shell; `--json` and CI-quiet modes.

### V1 (v0.4–v0.9)

- `tempenv pause/resume` (commit + named volume, TTL reaper), `envdoctor watch`, deep `doctor --strict`
- Language-ecosystem plugins via entry points; lockfile drift detection; secret-hygiene scan (real-looking secrets committed + `.gitignore` check)
- `.envdoctor.toml` project contract + user profiles; SARIF output for CI
- `shell` pre-flight auto-applies diagnosed env vars into the ephemeral env (the combined magic, fully polished)

### V2 (1.0+)

- Runtimes via plugin API: devcontainer.json support, Podman native, Nix shells, LXC (Linux)
- VS Code / JetBrains extensions; remote diagnosis over SSH; `tempenv serve` demo URLs
- Opt-in AI-assisted explanations (user-supplied key or local model; still local-first)

## 3. Technical architecture & key libraries

Layered, pure-Python, stdlib-first, all I/O behind protocols:

```
src/envdoctor/
  cli/        # Typer app, Rich rendering, exit codes; envdoctor + tempenv mains
  core/scan/  # FileInventory + parsers: dotenv, toml/tomllib, json, yaml-lite, regex doc scanner
  core/checks/# Check protocol + registry: EnvVarCheck, ToolchainCheck, ContainerCheck, DocsCheck
  core/report/# Finding, Severity, Evidence, Report; redaction utilities
  core/fix/   # SafeFix protocol (dry-run default)
  runtime/    # RuntimeBackend protocol; DockerBackend (docker SDK), PodmanBackend (socket probe), NullBackend
  tempenv/    # Session lifecycle: create/exec/teardown/pause/kill; labels + sweeper
  platform/   # platformdirs paths, OS/shell detection, env introspection, Windows path helpers
  plugins/    # importlib.metadata entry-point registry (`envdoctor.plugins` group)
```

**Libraries**: `typer` + `rich` (CLI/UX), `platformdirs` (XDG + Windows config/cache), `python-dotenv` (dotenv parsing incl. interpolation), `docker` (SDK — production/stable), `packaging` (version specifiers), `tomllib` (3.11+) with `tomli` marker for 3.10. Optional `pyyaml` only if compose parsing demands it; regex fallback keeps the tool light.

Design rules: checks are pure functions over `ScanContext` (fast, trivially testable); container access only through `RuntimeBackend`; no network calls except user-triggered image pulls.

## 4. Cross-platform strategy & known pitfalls → mitigations

| Area | Windows | macOS | Linux |
|---|---|---|---|
| Docker discovery | named pipe `//./pipe/docker_engine`, `docker context` | `~/.docker/run/docker.sock`, colima fallback | `/var/run/docker.sock`, rootless |
| Podman | WSL2 only → detect & message clearly | native | native |
| Mounts | bind-mount probe with tiny container; auto-fallback to **copy mode** on failure | POSIX | POSIX |
| Shells | PowerShell/cmd/Git Bash detection → OS+shell-correct fix syntax | zsh/bash | bash/zsh/fish |
| Config | `%APPDATA%` via platformdirs | `~/Library/Application Support` (XDG-respecting) | XDG |
| Teardown | `finally` + `atexit` + `signal.SIGBREAK` + label sweeper | `atexit` | `atexit` |

Additional mitigations: pure `pathlib` everywhere; long-path (`\\?\`) handling for deep repos; no `shell=True` except with explicitly selected shell; runtime capability probed at command start with actionable fallback messages.

## 5. CLI command design (examples)

```
envdoctor check .                     # report; --json / --strict (CI exit 1 on CRITICAL) / --only env,docs
envdoctor fix .                       # dry-run diff by default; --write to apply
envdoctor shell .                     # ephemeral env, diagnosed requirements pre-applied
  --image python:3.12 --node 20
  --mount BIND|COPY                   # default: bind on unix; auto-copy fallback on Windows
  --env-file .env --env K=V --no-env-inherit
  --shell pwsh --keep                 # --keep disables auto-removal (explicit opt-out)
envdoctor temp python:3.12 --mount .  # pure clean room
envdoctor ps | pause NAME | resume NAME | kill NAME | sweep

tempenv python:3.12                   # same engine, top-level entry
tempenv ps / pause / resume / kill / sweep
```

Exit codes: 0 ok · 1 findings ≥ threshold · 2 usage · 3 no runtime · 4 partial results.

## 6. Data model / internal abstractions

```python
@dataclass(frozen=True)
class Evidence: source: str; location: str; snippet: str; kind: str  # file|env|runtime|doc

@dataclass(frozen=True)
class Finding:
    id: str; severity: Severity; title: str; detail: str
    evidence: list[Evidence]; fix: FixSuggestion | None   # command + safety class

class Check(Protocol):
    id: str
    def applies(self, ctx: ScanContext) -> bool: ...
    def run(self, ctx: ScanContext) -> Iterable[Finding]: ...

@dataclass
class ScanContext:
    root: Path; files: FileInventory; os: OSInfo; shell: ShellInfo
    env: Mapping[str, str]; config: Config

class RuntimeBackend(Protocol):
    name: str
    def available(self) -> RuntimeStatus: ...
    def run_session(self, spec: SessionSpec) -> SessionResult: ...  # owns lifecycle
```

Session labeling: `org.envdoctor/session=<uuid>`, `org.envdoctor/owner=<pid>`, optional `ttl`. The sweeper reaps labeled containers whose owner PID is dead → orphan-proof without any daemon.

## 7. Security & privacy

- Secrets: compare **names**, never print values; length-presence only; redaction enforced in `--json` output; injection via container `Environment` API (not argv → no `ps` leakage); `--no-env-inherit` for fully clean rooms.
- Local-first: zero telemetry; no network except user-triggered pulls; stated plainly in docs.
- `fix` is dry-run-by-default, never overwrites without `--write`.
- Mount safety: sensitive host dirs (`~/.ssh`, `~/.aws`) blocked unless `--allow-sensitive-mount`; `--pull=missing` default; image names validated.
- Supply chain: pinned lower-bound deps, SBOM in releases, signed PyPI publish via trusted publishing.

## 8. Testing strategy across OSes

- **Unit**: parsers (dotenv variants, TOML, engines, doc scanner), finding aggregation, redaction — pure functions, high coverage.
- **CI matrix** (GitHub Actions): {ubuntu, macos, windows} × {3.10, 3.12}; docker-in-docker job for real runtime smoke tests; separate Podman job; a Windows job *without* Docker asserting graceful degradation messages.
- **Integration**: fake `RuntimeBackend` for lifecycle logic; `@pytest.mark.docker` real-container tests (create → exec → assert autoremove by label query).
- **Fixture repos**: `tests/fixtures/` gallery (env-example-only, compose app, node engines, docs-only) reused by unit + `CliRunner` CLI tests.
- **Windows-specific**: path conversion, teardown via SIGBREAK simulation, long paths.

## 9. Open-source release plan & documentation

- PyPI `envdoctor` (verified available); GitHub topics `developer-tools, docker, environment, cli`; README disambiguation: "not affiliated with `env-doctor` (GPU diagnosis)".
- Structure: `README.md` (with vhs/asciinema GIFs per-OS), `DESIGN.md` (this spec), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, MIT `LICENSE`, `CHANGELOG.md` (Keep a Changelog), `docs/` (mkdocs-material: install, quickstart, commands, runtimes, plugins, privacy), `examples/` (the fixture repos), `.envdoctor.toml.example`.
- Process: `main` protected, conventional commits, release-please, v0.1 publish via GitHub Actions trusted publishing; install docs for `pipx install envdoctor` / `uv tool install envdoctor`.
- Community: Discussions Q&A; parser plugins as `good first issue`.

## 10. Future expansion

IDE extensions · language-ecosystem analyzer plugins (go/cargo/maven/composer) · devcontainer.json runtime · Nix shells · LXC/Firecracker (Linux) · `tempenv serve` demo URLs · team "environment contract" mode (`.envdoctor.toml` committed → `check --from-contract` as a CI PR check) · opt-in AI explanations.
