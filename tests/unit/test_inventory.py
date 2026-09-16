"""Unit tests for the repository file inventory."""

from __future__ import annotations

from pathlib import Path

from envdoctor.core.scan.inventory import build_inventory

def test_root_files_classified(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env").write_text("A=2\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM alpine\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("all:\n\techo hi\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    (tmp_path / ".nvmrc").write_text("20\n", encoding="utf-8")
    (tmp_path / ".python-version").write_text("3.12\n", encoding="utf-8")

    inv = build_inventory(tmp_path)
    assert inv.dotenv_examples and inv.dotenv_actual
    assert inv.compose_files and inv.dockerfiles
    assert inv.package_json is not None and inv.pyproject is not None
    assert inv.makefile is not None and inv.nvmrc is not None
    assert inv.markdown_docs and inv.python_version_files

def test_skips_node_modules_and_git(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / "left-pad").mkdir(parents=True)
    (tmp_path / "node_modules" / "left-pad" / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".git" / "objects").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "abc").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")

    inv = build_inventory(tmp_path)
    assert inv.package_json is None
    assert inv.markdown_docs and inv.markdown_docs[0].name == "README.md"

def test_docs_and_scripts_within_depth(tmp_path: Path) -> None:
    docs = tmp_path / "docs" / "setup"
    docs.mkdir(parents=True)
    (docs / "install.md").write_text("install steps\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "bootstrap.sh").write_text("export NEEDED_VAR=1\n", encoding="utf-8")

    inv = build_inventory(tmp_path)
    assert any(p.name == "install.md" for p in inv.markdown_docs)
    assert any(p.name == "bootstrap.sh" for p in inv.shell_scripts)
