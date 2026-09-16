# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `envdoctor check` — env-var gap analysis, toolchain (Python/Node) checks, container sanity, doc-coverage analysis; `--json`, `--strict`, `--only`.
- `envdoctor fix` — safe `.env` generation from `.env.example` (dry-run diff by default, `--write` to apply).
- `envdoctor shell` / `envdoctor temp` — ephemeral Docker environments with automatic teardown and orphan sweeping.
- `envdoctor ps` / `kill` / `sweep` — session management.
- `tempenv` — top-level entrypoint exposing the same ephemeral-environment engine.
- Cross-platform runtime detection (Docker SDK, Podman socket) with OS-specific install guidance when no runtime is found.
