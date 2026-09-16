"""Unit tests for language/toolchain requirement extraction."""

from __future__ import annotations

from pathlib import Path

from envdoctor.core.scan.language import extract_language_reqs

def test_node_engines_and_nvmrc(tmp_path: Path) -> None:
    pkg = tmp_path / "package.json"
    pkg.write_text('{"engines": {"node": ">=20"}}', encoding="utf-8")
    nvmrc = tmp_path / ".nvmrc"
    nvmrc.write_text("v20.11.0\n", encoding="utf-8")  # exact pin -> ==, not >=

    reqs = extract_language_reqs(
        package_json=pkg, pyproject=None, nvmrc=nvmrc, python_version_files=[]
    )
    assert [r.specifier for r in reqs.node] == [">=20", "==20.11.0"]

def test_pyproject_requires_python(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    reqs = extract_language_reqs(
        package_json=None, pyproject=pyproject, nvmrc=None, python_version_files=[]
    )
    assert reqs.python[0].specifier == ">=3.11"
    assert "pyproject.toml" in reqs.python[0].source

def test_python_version_file(tmp_path: Path) -> None:
    marker = tmp_path / ".python-version"
    marker.write_text("3.12.4\n", encoding="utf-8")
    reqs = extract_language_reqs(
        package_json=None, pyproject=None, nvmrc=None, python_version_files=[marker]
    )
    assert reqs.python[0].specifier == ">=3.12.4"
