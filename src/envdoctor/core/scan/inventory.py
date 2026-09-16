"""Repository inventory: discover the files EnvDoctor cares about, quickly.

The walk is bounded (depth-limited, ignore-listed) so large repositories are
scanned in milliseconds. Pure `pathlib`; works identically on all OSes.
"""

from __future__ import annotations

import os
from pathlib import Path

from envdoctor.core.models import FileInventory

# Directories that are never interesting and often enormous.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
        ".tox",
        ".nox",
        ".idea",
        ".vscode",
        "coverage",
        ".next",
        ".nuxt",
        "vendor",
    }
)

DOTENV_EXAMPLE_NAMES = {".env.example", ".env.sample", ".env.template"}
DOTENV_ACTUAL_NAMES = {".env", ".env.local", ".env.development", ".env.test", ".env.production"}
PYTHON_VERSION_FILE_NAMES = {".python-version", "runtime.txt", ".tool-versions"}

MAX_DOCS_DEPTH = 3  # root/docs/ up to three levels deep
MAX_SCRIPTS_DEPTH = 2

def _is_compose(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(("docker-compose", "compose")) and lowered.endswith((".yml", ".yaml"))

def _is_dockerfile(name: str) -> bool:
    return name == "Dockerfile" or name.startswith("Dockerfile.")

def _is_requirements(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("requirements") and lowered.endswith(".txt")

def _is_ci_workflow(path: Path) -> bool:
    return (
        ".github" in path.parts and "workflows" in path.parts and path.suffix in (".yml", ".yaml")
    )

def _is_markdown(name: str) -> bool:
    return name.lower().endswith((".md", ".markdown"))

def _is_shell_script(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith((".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"))

def _walk(root: Path, max_depth: int) -> list[Path]:
    """Depth-bounded os.walk that skips junk directories. Deterministic order."""
    found: list[Path] = []
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        depth = len(current.parts) - root_depth
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".docker")
        )
        for fname in sorted(filenames):
            found.append(current / fname)
    return found

def build_inventory(root: Path) -> FileInventory:
    """Classify a repository's files into the inventory the checks consume."""
    inv = FileInventory(root=root)

    for path in _walk(root, max_depth=4):
        name = path.name
        rel_parts = path.relative_to(root).parts

        if len(rel_parts) == 1:  # repository root only
            if name in DOTENV_EXAMPLE_NAMES:
                inv.dotenv_examples.append(path)
                continue
            if name in DOTENV_ACTUAL_NAMES:
                inv.dotenv_actual.append(path)
                continue
            if _is_compose(name):
                inv.compose_files.append(path)
                continue
            if _is_dockerfile(name):
                inv.dockerfiles.append(path)
                continue
            if name == "package.json":
                inv.package_json = path
                continue
            if name == "pyproject.toml":
                inv.pyproject = path
                continue
            if _is_requirements(name):
                inv.requirements.append(path)
                continue
            if name.lower() == "makefile":
                inv.makefile = path
                continue
            if name == ".nvmrc":
                inv.nvmrc = path
                continue
            if name in PYTHON_VERSION_FILE_NAMES:
                inv.python_version_files.append(path)
                continue
            if _is_markdown(name):
                inv.markdown_docs.append(path)
                continue
            if _is_shell_script(name):
                inv.shell_scripts.append(path)
                continue
            if name == ".devcontainer.json":
                inv.devcontainer = path
                continue

        if rel_parts[:1] == (".devcontainer",) and name == "devcontainer.json":
            inv.devcontainer = path
            continue

        if _is_ci_workflow(path):
            inv.ci_workflows.append(path)
            continue

        if "docs" in rel_parts[:2] and _is_markdown(name) and len(rel_parts) <= MAX_DOCS_DEPTH + 1:
            inv.markdown_docs.append(path)
            continue

        if (
            "scripts" in rel_parts[:2]
            and _is_shell_script(name)
            and len(rel_parts) <= MAX_SCRIPTS_DEPTH + 1
        ):
            inv.shell_scripts.append(path)
            continue

    return inv
