"""Unit tests for the four diagnosis checks."""

from __future__ import annotations

from envdoctor.core.checks.container import run_container_check
from envdoctor.core.checks.docscoverage import run_docs_check
from envdoctor.core.checks.envvars import run_envvar_check
from envdoctor.core.checks.toolchain import _compare, run_toolchain_check

def test_envvar_missing_and_present(context_factory) -> None:  # type: ignore[no-untyped-def]
    ctx = context_factory(
        {
            ".env.example": "DATABASE_URL=postgres://localhost/db\nAPI_KEY=\nDEBUG=true\n",
            "README.md": "Set DATABASE_URL before running.\n",
        },
        env={"DEBUG": "true"},
    )
    findings = run_envvar_check(ctx)
    by_id = {f.id: f for f in findings}
    assert "env/DATABASE_URL/missing" in by_id
    assert "env/API_KEY/missing" in by_id
    assert "env/DEBUG/present" in by_id
    missing = by_id["env/DATABASE_URL/missing"]
    assert any("README.md" in e.location for e in missing.evidence)

def test_envvar_documented_only(context_factory) -> None:  # type: ignore[no-untyped-def]
    ctx = context_factory(
        {"README.md": "Set MYSTERY_TOKEN in your environment.\n"},
        env={},
    )
    findings = run_envvar_check(ctx)
    assert any(f.id == "env/MYSTERY_TOKEN/documented-only" for f in findings)

def test_envvar_ignores_host_vars(context_factory) -> None:  # type: ignore[no-untyped-def]
    ctx = context_factory(
        {"README.md": "Run `export PATH=$PATH:./bin` first.\n"},
        env={},
    )
    findings = run_envvar_check(ctx)
    assert not any("PATH" in f.id for f in findings)

def test_envvar_shell_correct_fix(context_factory) -> None:  # type: ignore[no-untyped-def]
    unix_ctx = context_factory({".env.example": "FOO=bar\n"}, env={})
    win_ctx_shell = context_factory({".env.example": "FOO=bar\n"}, env={}, system="Windows")
    win_ctx_shell.shell = "powershell"
    unix_fix = list(run_envvar_check(unix_ctx))[0].fix
    win_fix = [f for f in run_envvar_check(win_ctx_shell) if f.fix is not None][0].fix
    assert unix_fix is not None and unix_fix.command.startswith("export ")
    assert win_fix is not None and win_fix.command.startswith("$env:")

def test_toolchain_pyproject_version_gate(context_factory) -> None:  # type: ignore[no-untyped-def]
    ctx = context_factory({"pyproject.toml": '[project]\nrequires-python = ">=4.0"\n'})
    findings = run_toolchain_check(ctx)
    assert any(f.id == "toolchain/python/missing" for f in findings)

def test_toolchain_satisfied(context_factory) -> None:  # type: ignore[no-untyped-def]
    ctx = context_factory({"pyproject.toml": '[project]\nrequires-python = ">=3.8"\n'})
    findings = run_toolchain_check(ctx)
    assert any(f.id == "toolchain/python/ok" for f in findings)

def test_compare_operators() -> None:
    assert _compare("3.12.1", ">=", "3.10")
    assert _compare("3.9.7", "<", "3.10")
    assert _compare("20.11.0", "==", "20")
    assert not _compare("3.10.0", ">=", "3.11")

def test_docs_platform_missing(context_factory) -> None:  # type: ignore[no-untyped-def]
    ctx = context_factory(
        {"README.md": "# Setup\n\nRun `brew install postgres` then `apt-get install libpq`.\n"},
        system="Windows",
    )
    findings = run_docs_check(ctx)
    assert any(f.id == "docs/platform-missing-current" for f in findings)

def test_docs_none_present(context_factory) -> None:  # type: ignore[no-untyped-def]
    ctx = context_factory({})
    findings = run_docs_check(ctx)
    assert any(f.id == "docs/none" for f in findings)

def test_container_check_skips_when_no_docker_files(context_factory) -> None:  # type: ignore[no-untyped-def]
    ctx = context_factory({"README.md": "# hi\n"})
    findings = run_container_check(ctx)
    assert findings == []
