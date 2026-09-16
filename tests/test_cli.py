"""CLI integration tests via Typer's CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from envdoctor.cli.main import app, tempenv_app

runner = CliRunner()


def test_check_json_reports_missing_envvar(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("MISSING_THING=\nPRESENT_THING=ok\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["check", str(tmp_path), "--only", "env", "--json"],
        env={"PRESENT_THING": "1"},
    )
    assert result.exit_code in (0, 1)
    payload = json.loads(result.output)
    ids = [f["id"] for f in payload["findings"]]
    assert "env/MISSING_THING/missing" in ids
    assert "env/PRESENT_THING/present" in ids


def test_check_unknown_only_flag_is_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path), "--only", "nope"])
    assert result.exit_code == 2


def test_check_missing_path_usage_error() -> None:
    result = runner.invoke(app, ["check", "does-not-exist-xyz"])
    assert result.exit_code == 2


def test_fix_dry_run_then_write(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("A=1\n", encoding="utf-8")
    dry = runner.invoke(app, ["fix", str(tmp_path)])
    assert dry.exit_code == 0
    assert "Dry run only" in dry.output
    assert not (tmp_path / ".env").exists()

    write = runner.invoke(app, ["fix", str(tmp_path), "--write"])
    assert write.exit_code == 0
    assert (tmp_path / ".env").exists()


def test_fix_without_example(tmp_path: Path) -> None:
    result = runner.invoke(app, ["fix", str(tmp_path)])
    assert result.exit_code == 0
    assert "No .env.example" in result.output


def test_tempenv_help_lists_run_ps_kill_sweep() -> None:
    result = runner.invoke(tempenv_app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "ps", "kill", "sweep"):
        assert command in result.output


def test_envdoctor_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("check", "fix", "shell", "temp", "ps", "kill", "sweep"):
        assert command in result.output
