"""Unit tests for platform utilities and TempEnv session safety."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from envdoctor.platform.system import detect_shell, pid_alive
from envdoctor.tempenv.session import (
    SensitiveMountError,
    build_spec,
    guard_sensitive_mount,
    image_for_repo,
)

def test_pid_alive_self_and_bogus() -> None:
    assert pid_alive(os.getpid())
    assert not pid_alive(999999999)

def test_detect_shell_env_priority() -> None:
    assert detect_shell({"SHELL": "/bin/zsh"}) == "zsh"
    assert detect_shell({"SHELL": "/usr/bin/fish"}) == "fish"
    # Git Bash on Windows reports as bash; POSIX shells map correctly everywhere.
    assert detect_shell({"SHELL": "C:/Program Files/Git/usr/bin/bash.exe"}) == "bash"

def test_guard_rejects_ssh_mount(tmp_path: Path) -> None:
    ssh_dir = Path.home() / ".ssh"
    if ssh_dir.exists():  # only assertable when the directory exists
        with pytest.raises(SensitiveMountError):
            guard_sensitive_mount(ssh_dir)
    with pytest.raises(SensitiveMountError):
        guard_sensitive_mount(Path.home() / ".aws" / "config")
    guard_sensitive_mount(tmp_path, allow=True)

def test_image_detection(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert "node" in image_for_repo(tmp_path)

    (tmp_path / "package.json").unlink()  # switch ecosystem: node file gone, python file added
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert "python" in image_for_repo(tmp_path)
    assert image_for_repo(None) == "alpine:3.20"

def test_build_spec_injection_and_labels(tmp_path: Path) -> None:
    spec = build_spec(
        image="python:3.12",
        mount=tmp_path,
        mount_mode="bind",
        env_vars={"TOKEN": "super-secret"},
        env_file_vars={"EXTRA": "1"},
        inherit_env=False,
        shell="bash",
        ports=(),
        keep=False,
    )
    assert spec.env["TOKEN"] == "super-secret"
    assert spec.env["EXTRA"] == "1"
    assert spec.labels["org.envdoctor/managed"] == "1"
    assert spec.name.startswith("envdoctor-")
    assert spec.auto_remove is True

def test_build_spec_no_inherit_when_requested(tmp_path: Path) -> None:
    os.environ["ENVDOCTOR_TEST_MARKER"] = "1"
    spec = build_spec(
        image="alpine",
        mount=None,
        mount_mode="bind",
        env_vars={},
        env_file_vars={},
        inherit_env=True,
        shell="sh",
        ports=(),
        keep=False,
    )
    assert spec.env.get("ENVDOCTOR_TEST_MARKER") == "1"
    spec_clean = build_spec(
        image="alpine",
        mount=None,
        mount_mode="bind",
        env_vars={},
        env_file_vars={},
        inherit_env=False,
        shell="sh",
        ports=(),
        keep=False,
    )
    assert "ENVDOCTOR_TEST_MARKER" not in spec_clean.env
    del os.environ["ENVDOCTOR_TEST_MARKER"]
