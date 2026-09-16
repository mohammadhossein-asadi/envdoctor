"""The EnvDoctor CLI: `envdoctor` and `tempenv` entrypoints.

Progressive disclosure: bare commands do the right thing; flags unlock power.
Exit codes: 0 ok · 1 findings · 2 usage · 3 no runtime · 4 partial (constants.py).
"""

from __future__ import annotations

import contextlib
import platform
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from envdoctor import constants
from envdoctor.core.checks.container import ContainerCheck
from envdoctor.core.checks.docscoverage import DocsCheck
from envdoctor.core.checks.envvars import EnvVarCheck
from envdoctor.core.checks.toolchain import ToolchainCheck
from envdoctor.core.context import build_context
from envdoctor.core.fix import apply_fix, build_fix_plan
from envdoctor.core.report import Report
from envdoctor.runtime.registry import best_backend, no_runtime_message
from envdoctor.tempenv.session import (
    SensitiveMountError,
    build_spec,
    load_env_file,
    run_session,
    sweep_orphans,
)

app = typer.Typer(
    name="envdoctor",
    help="Diagnose why a repository won't run, then step into a clean temporary environment.",
    no_args_is_help=True,
    add_completion=False,
)

tempenv_app = typer.Typer(
    name="tempenv",
    help="Ephemeral, isolated, self-cleaning environments.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

# --- check/fix selection ------------------------------------------------------

CHECK_IDS = {
    "env": EnvVarCheck,
    "toolchain": ToolchainCheck,
    "container": ContainerCheck,
    "docs": DocsCheck,
}

_ENV_ARGS_OPTION = typer.Option(
    None, "--env", "-e", help="Inject KEY=V (repeatable), injected via API not argv"
)
_ENV_FILE_OPTION = typer.Option(None, "--env-file", help="Inject variables from a dotenv file")

def _selected_checks(only: str | None) -> list[tuple[str, type]]:
    if not only:
        return list(CHECK_IDS.items())
    wanted = [token.strip() for token in only.split(",") if token.strip()]
    unknown = [w for w in wanted if w not in CHECK_IDS]
    if unknown:
        console.print(f"[red]Unknown check id(s): {', '.join(unknown)}[/red]")
        raise typer.Exit(constants.EXIT_USAGE)
    return [(w, CHECK_IDS[w]) for w in wanted]

# --- check -------------------------------------------------------------------

@app.command()
def check(
    path: Path = typer.Argument(Path("."), help="Repository to diagnose"),
    only: str | None = typer.Option(
        None, "--only", help="Comma-separated subset: env,toolchain,container,docs"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Machine-readable output (secret values are never included)"
    ),
    strict: bool = typer.Option(False, "--strict", help="Exit 1 on any finding above INFO"),
) -> None:
    """Diagnose env vars, toolchain, containers, and docs for a repository."""
    if not path.exists():
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(constants.EXIT_USAGE)

    selected = _selected_checks(only)
    backend = best_backend()
    docker_status = ""
    status = backend.status()
    docker_status = status.detail if status.available else "not available"

    report = Report(scanned_path=str(path))
    ctx = build_context(root=path, docker_status=docker_status or None)

    ran_any = False
    for check_id, cls in selected:
        instance = cls()
        try:
            if not instance.applies(ctx):
                continue
            report.extend(list(instance.run(ctx)))
            report.checks_run.append(check_id)
            ran_any = True
        except Exception as exc:  # noqa: BLE001 - a broken check must not kill the report
            console.print(f"[yellow]Check {check_id} failed: {exc}[/yellow]")
            report.partial = True

    if not ran_any:
        report.partial = True

    if strict:
        # Strict mode: any finding above INFO fails.
        blocking = [f for f in report.findings if f.severity.value not in ("ok", "info")]
        if blocking:
            report.partial = False
            if json_output:
                console.print_json(report.as_json())
            else:
                from envdoctor.cli.render import render_report

                render_report(report, ctx, console)
            raise typer.Exit(constants.EXIT_FINDINGS)

    if json_output:
        console.print_json(report.as_json())
    else:
        from envdoctor.cli.render import render_next_steps, render_report

        render_report(report, ctx, console)
        render_next_steps(report, ctx, console)

    raise typer.Exit(report.exit_code())

# --- fix ---------------------------------------------------------------------

@app.command()
def fix(
    path: Path = typer.Argument(Path("."), help="Repository to fix"),
    write: bool = typer.Option(
        False, "--write", help="Actually write .env (default: dry-run diff)"
    ),
) -> None:
    """Generate .env from .env.example without clobbering existing values."""
    plan = build_fix_plan(path.expanduser().resolve())
    if plan is None:
        console.print("[yellow]No .env.example found - nothing to generate from.[/yellow]")
        raise typer.Exit(constants.EXIT_OK)
    apply_fix(plan, write=write)
    if write:
        if plan.already_complete:
            console.print("[green].env already complete - left untouched.[/green]")
        else:
            console.print(
                f"[green]Wrote {plan.env_path} ({len(plan.to_add)} variables added).[/green]"
            )
    else:
        console.print(plan.as_diff_text())
        console.print("[dim]Dry run only - re-run with --write to apply.[/dim]")

# --- ephemeral environments ----------------------------------------------------

def _mount_option(path: Path | None) -> Path | None:
    return path.expanduser().resolve() if path is not None else None

def _parse_env_args(env_args: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in env_args or []:
        if "=" not in item:
            console.print(f"[red]--env expects KEY=value, got: {item}[/red]")
            raise typer.Exit(constants.EXIT_USAGE)
        key, _, value = item.partition("=")
        out[key.strip()] = value
    return out

def _common_session_options(  # noqa: ANN001 - backend is a RuntimeBackend
    image: str | None,
    mount: Path | None,
    mount_mode: str,
    env_args: list[str] | None,
    env_file: Path | None,
    no_env_inherit: bool,
    shell: str,
    ports: list[str] | None,
    keep: bool,
    allow_sensitive: bool,
    backend: Any,
) -> Any:
    if backend.status().kind.value == "none" or not backend.status().available:
        console.print(f"[red]{no_runtime_message(backend, platform.system())}[/red]")
        raise typer.Exit(constants.EXIT_NO_RUNTIME)
    from envdoctor.platform.system import copy_mode_hint

    effective_mode = mount_mode
    if mount is not None and mount_mode == "bind" and platform.system() == "Windows":
        console.print(f"[yellow]{copy_mode_hint()}[/yellow]")
        effective_mode = "copy"
    try:
        return build_spec(
            image=image or "alpine:3.20",
            mount=_mount_option(mount),
            mount_mode=effective_mode,
            env_vars=_parse_env_args(env_args),
            env_file_vars=load_env_file(env_file) if env_file else {},
            inherit_env=not no_env_inherit,
            shell=shell,
            ports=tuple(_parse_ports(ports or [])),
            keep=keep,
            allow_sensitive=allow_sensitive,
        )
    except SensitiveMountError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(constants.EXIT_USAGE) from exc

def _parse_ports(port_args: list[str]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for item in port_args:
        try:
            host_s, _, container_s = item.partition(":")
            out.append((int(host_s), int(container_s or host_s)))
        except ValueError as exc:
            console.print(f"[red]--publish expects HOST:CONTAINER, got: {item}[/red]")
            raise typer.Exit(constants.EXIT_USAGE) from exc
    return out

def _run_with_teardown(spec: Any, backend: Any) -> None:
    import atexit

    def _cleanup() -> None:
        with contextlib.suppress(Exception):  # atexit must never raise
            backend.kill_session(spec.session_id)

    atexit.register(_cleanup)
    try:
        result = run_session(backend, spec)
    finally:
        atexit.unregister(_cleanup)
    console.print(f"[dim]{result.detail or ''}[/dim]")
    raise typer.Exit(result.exit_code)

@app.command()
def shell(
    path: Path = typer.Argument(Path("."), help="Repository to open in a clean environment"),
    image: str | None = typer.Option(None, "--image", help="Override the auto-detected base image"),
    mount: Path | None = typer.Option(
        None, "--mount", help="Path to mount (defaults to PATH itself)"
    ),
    mount_mode: str = typer.Option("bind", "--mount-mode", help="bind | copy"),
    env_args: list[str] | None = _ENV_ARGS_OPTION,
    env_file: Path | None = _ENV_FILE_OPTION,
    no_env_inherit: bool = typer.Option(
        False, "--no-env-inherit", help="Start from a truly empty environment"
    ),
    shell_name: str = typer.Option("bash", "--shell", help="Shell inside the container"),
    ports: list[str] | None = typer.Option(
        None, "--publish", "-p", help="HOST:CONTAINER (repeatable)"
    ),
    keep: bool = typer.Option(
        False, "--keep", help="Do NOT auto-remove the container on exit (explicit opt-out)"
    ),
    allow_sensitive: bool = typer.Option(
        False, "--allow-sensitive-mount", help="Allow mounting ~/.ssh etc."
    ),
) -> None:
    """Open a clean ephemeral environment with this repo's requirements pre-applied."""
    backend = best_backend()
    target = path.expanduser().resolve()
    spec = _common_session_options(
        image or _detect_image(target),
        mount if mount is not None else target,
        mount_mode,
        env_args,
        env_file,
        no_env_inherit,
        shell_name,
        ports,
        keep,
        allow_sensitive,
        backend,
    )
    sweep_orphans(backend)
    _run_with_teardown(spec, backend)

@app.command()
def temp(
    image: str = typer.Argument(..., help="Base image for the clean room"),
    mount: Path | None = typer.Option(None, "--mount", help="Optional path to mount or copy in"),
    mount_mode: str = typer.Option("bind", "--mount-mode", help="bind | copy"),
    env_args: list[str] | None = _ENV_ARGS_OPTION,
    env_file: Path | None = _ENV_FILE_OPTION,
    no_env_inherit: bool = typer.Option(
        False, "--no-env-inherit", help="Start from a truly empty environment"
    ),
    shell_name: str = typer.Option("bash", "--shell", help="Shell inside the container"),
    ports: list[str] | None = typer.Option(
        None, "--publish", "-p", help="HOST:CONTAINER (repeatable)"
    ),
    keep: bool = typer.Option(
        False, "--keep", help="Do NOT auto-remove the container on exit (explicit opt-out)"
    ),
    allow_sensitive: bool = typer.Option(
        False, "--allow-sensitive-mount", help="Allow mounting ~/.ssh etc."
    ),
) -> None:
    """Spin up a pure temporary environment from any image."""
    backend = best_backend()
    spec = _common_session_options(
        image,
        mount,
        mount_mode,
        env_args,
        env_file,
        no_env_inherit,
        shell_name,
        ports,
        keep,
        allow_sensitive,
        backend,
    )
    sweep_orphans(backend)
    _run_with_teardown(spec, backend)

def _detect_image(path: Path) -> str:
    from envdoctor.tempenv.session import image_for_repo

    return image_for_repo(path)

# --- session management ---------------------------------------------------------

@app.command("ps")
def ps() -> None:
    """List EnvDoctor-managed environments (and sweep orphans first)."""
    backend = best_backend()
    if not backend.status().available:
        console.print(f"[red]{no_runtime_message(backend, platform.system())}[/red]")
        raise typer.Exit(constants.EXIT_NO_RUNTIME)
    reaped = sweep_orphans(backend)
    rows = backend.list_sessions()
    from envdoctor.cli.render import render_env_table

    if reaped:
        console.print(f"[dim]swept {reaped} orphaned environment(s)[/dim]")
    render_env_table(rows, console)

@app.command()
def kill(session: str = typer.Argument(..., help="Session id (see envdoctor ps)")) -> None:
    """Stop and remove an environment by session id."""
    backend = best_backend()
    if backend.kill_session(session):
        console.print("[green]Environment removed.[/green]")
    else:
        console.print("[yellow]No matching environment found.[/yellow]")
        raise typer.Exit(constants.EXIT_OK)

@app.command()
def sweep() -> None:
    """Remove all orphaned environments (owner process no longer alive)."""
    backend = best_backend()
    reaped = sweep_orphans(backend)
    console.print(f"[green]Swept {reaped} orphaned environment(s).[/green]")

# --- tempenv top-level app -------------------------------------------------------

tempenv_app.command("ps")(ps)
tempenv_app.command("kill")(kill)
tempenv_app.command("sweep")(sweep)

@tempenv_app.command(
    "run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def tempenv_run(
    ctx: typer.Context,
    image: str | None = typer.Argument(
        None, help="Base image; omit to auto-detect from the current repo"
    ),
) -> None:
    """`tempenv [IMAGE] [-- any temp flags]` — auto-detects the image for '.' when omitted."""
    temp(
        image=image if image is not None else _detect_image(Path(".")),
        mount=Path(".") if image is None else None,
        mount_mode="bind",
        env_args=None,
        env_file=None,
        no_env_inherit=False,
        shell_name="bash",
        ports=None,
        keep=False,
        allow_sensitive=False,
    )

def run() -> None:
    app()

def run_tempenv() -> None:
    tempenv_app()

if __name__ == "__main__":  # pragma: no cover
    app()
