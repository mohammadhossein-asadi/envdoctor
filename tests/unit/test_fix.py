"""Unit tests for the fix module's safe .env generation."""

from __future__ import annotations

from pathlib import Path

from envdoctor.core.fix import apply_fix, build_fix_plan, render_merged_env


def test_render_preserves_existing_and_appends_missing() -> None:
    existing = "# my config\nDATABASE_URL=postgres://real\n"
    merged = render_merged_env(existing, ["DATABASE_URL", "API_KEY", "DEBUG"])
    assert "DATABASE_URL=postgres://real" in merged
    assert "API_KEY=" in merged and "DEBUG=" in merged
    assert merged.index("DATABASE_URL=postgres://real") < merged.index("API_KEY=")


def test_build_and_apply_dry_run(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("A=1\nB=2\n", encoding="utf-8")
    plan = build_fix_plan(tmp_path)
    assert plan is not None and plan.to_add == ["A", "B"]

    apply_fix(plan, write=False)
    assert not (tmp_path / ".env").exists()

    apply_fix(plan, write=True)
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "A=" in env_text and "B=" in env_text


def test_never_clobbers_existing_values(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("A=1\nB=2\n", encoding="utf-8")
    (tmp_path / ".env").write_text("A=REAL_SECRET\n", encoding="utf-8")
    plan = build_fix_plan(tmp_path)
    assert plan is not None
    assert plan.to_add == ["B"]
    apply_fix(plan, write=True)
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "A=REAL_SECRET" in text
    assert "B=" in text


def test_complete_env_is_noop(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("A=set\n", encoding="utf-8")
    plan = build_fix_plan(tmp_path)
    assert plan is not None and plan.already_complete


def test_no_example_returns_none(tmp_path: Path) -> None:
    assert build_fix_plan(tmp_path) is None
