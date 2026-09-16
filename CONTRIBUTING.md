# Contributing to EnvDoctor

Thanks for helping make "it doesn't work on your machine" a thing of the past! 🩺

## Dev setup

```bash
git clone <your-fork> && cd envdoctor
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Ground rules

- **Python 3.10+**, cross-platform first: every change must be plausibly correct on Windows, macOS, and Linux. Watch out for path separators, shell syntax, and process semantics.
- **Checks are pure functions** over `ScanContext` — no I/O inside checks; read files in the scan layer, act in the fix layer.
- **All container access goes through `RuntimeBackend`** — never import `docker` outside `envdoctor/runtime/`.
- **Never log or print secret values.** Compare names, show presence/length only. Redaction helpers live in `core/report/redact.py` — use them.
- **Dry-run by default.** Anything that writes to the user's repo needs an explicit `--write`-style flag.
- Windows CI runs without Docker: failure modes must degrade to clear messages, never tracebacks.

## Testing

- Unit tests for parsers and checks go in `tests/unit/`; CLI tests in `tests/test_cli.py`; real-container tests are marked `@pytest.mark.docker` and skipped when no runtime is present.
- Fixture repos live in `tests/fixtures/` — add one when you teach the scanner something new.
- Run the full gate before pushing: `ruff check . && ruff format --check . && mypy src && pytest`.

## Commit style

Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`). Releases are cut by maintainers via release-please.

## Areas that especially need help

- New ecosystem parsers (Go, Cargo, Maven, Composer) — see `core/scan/` and the plugin entry-point group `envdoctor.plugins`.
- Podman and rootless-Docker edge cases.
- Docs: per-OS setup guides and translation of fix suggestions.
