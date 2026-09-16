"""Fix layer: safe, inspectable, dry-run-by-default remediation."""

from envdoctor.core.fix.envfile import FixPlan, apply_fix, build_fix_plan, render_merged_env

__all__ = ["FixPlan", "apply_fix", "build_fix_plan", "render_merged_env"]
