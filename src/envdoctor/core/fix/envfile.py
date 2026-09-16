"""Safe `.env` generation (the `fix` command's core).

Rules (per DESIGN.md section 7):
- Dry-run by default: nothing is written unless `write=True`.
- NEVER overwrites existing values in `.env`.
- New lines are appended with empty values so the user can fill them in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


@dataclass
class FixPlan:
    """What `fix` wants to do, fully inspectable before anything is written."""

    env_path: Path
    example_path: Path
    to_add: list[str] = field(default_factory=list)  # vars missing from .env
    preserved: list[str] = field(default_factory=list)  # vars kept as-is
    already_complete: bool = False

    def as_diff_text(self) -> str:
        if self.already_complete:
            return "(no changes — .env already covers every variable in .env.example)"
        lines = [f"# would write {self.env_path.name} (from {self.example_path.name})"]
        for name in self.to_add:
            lines.append(f"+ {name}=")
        for name in self.preserved:
            lines.append(f"  {name}=<existing value kept>")
        return "\n".join(lines)


def build_fix_plan(root: Path) -> FixPlan | None:
    """Plan .env creation from the first .env.example-like file found."""
    from envdoctor.core.scan.inventory import DOTENV_ACTUAL_NAMES, DOTENV_EXAMPLE_NAMES

    example: Path | None = None
    actual: Path | None = None
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if path.name in DOTENV_EXAMPLE_NAMES and example is None:
            example = path
        if path.name in DOTENV_ACTUAL_NAMES and actual is None:
            actual = path
    if example is None:
        return None

    example_names = [k for k in (dotenv_values(example) or {}) if k]
    actual_values = dotenv_values(actual) if actual is not None and actual.exists() else {}
    actual_names = {k for k in (actual_values or {}) if k}

    plan = FixPlan(
        env_path=root / ".env",
        example_path=example,
        to_add=[n for n in example_names if n not in actual_names],
        preserved=sorted(actual_names & set(example_names)),
    )
    plan.already_complete = not plan.to_add
    return plan


def apply_fix(plan: FixPlan, write: bool = False) -> str:
    """Return the rendered .env content; write only when `write=True`.

    Merge policy: keep every existing .env line verbatim, then append
    missing example variables with empty values and a pointer comment.
    """
    existing_text = ""
    if plan.env_path.exists():
        existing_text = plan.env_path.read_text(encoding="utf-8", errors="replace")

    example_names = [k for k in (dotenv_values(plan.example_path) or {}) if k]
    rendered = render_merged_env(existing_text, example_names)

    if write and not plan.already_complete:
        plan.env_path.write_text(rendered, encoding="utf-8")
    return rendered


def render_merged_env(existing_text: str, example_names: list[str]) -> str:
    """Pure merge function: existing lines preserved, missing vars appended."""

    existing_names: set[str] = set()
    kept_lines: list[str] = []
    for raw in existing_text.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name = stripped.split("=", 1)[0].strip()
            if name.startswith("export "):
                name = name[len("export ") :].strip()
            existing_names.add(name)
        kept_lines.append(raw)

    additions = [name for name in example_names if name not in existing_names]
    out = existing_text.rstrip("\n")
    if additions:
        if out:
            out += "\n\n"
        out += "# Added by envdoctor fix — fill in the values:\n"
        out += "\n".join(f"{name}=" for name in additions)
        out += "\n"
    return out
