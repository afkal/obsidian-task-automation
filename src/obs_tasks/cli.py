"""CLI entry point for obs-tasks.

Commands:
    init   — initialise config and vault directories
    list   — show all tasks and their status
    run    — execute a task (by name or by file path)
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__
from .config import CONFIG_FILE, Config
from .executor import execute_task
from .models import TaskStatus
from .parser import parse_all_tasks, parse_file
from .writer import create_report, update_task_state


def _load_config() -> Config:
    """Load config or exit with a friendly message."""
    try:
        return Config.load(CONFIG_FILE)
    except FileNotFoundError:
        click.echo(
            "Error: Not initialised. Run 'obs-tasks init <vault_path>' first.",
            err=True,
        )
        sys.exit(1)
    except ValueError as exc:
        click.echo(f"Error: Invalid config — {exc}", err=True)
        sys.exit(1)


@click.group()
@click.version_option(version=__version__, prog_name="obs-tasks")
def cli():
    """Obsidian Task Automation — schedule and run tasks from your vault."""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("vault_path", type=click.Path(exists=True, file_okay=False))
def init(vault_path: str) -> None:
    """Initialise config and create Tasks/ and Reports/ directories."""
    vault = Path(vault_path).resolve()
    config = Config(vault_path=vault)

    # Create directories
    config.tasks_path.mkdir(parents=True, exist_ok=True)
    config.reports_path.mkdir(parents=True, exist_ok=True)

    # Save config
    config.save(CONFIG_FILE)

    click.echo(f"✅ Initialised vault: {vault}")
    click.echo(f"   Config:  {CONFIG_FILE}")
    click.echo(f"   Tasks:   {config.tasks_path}")
    click.echo(f"   Reports: {config.reports_path}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

_STATUS_ICONS = {
    TaskStatus.SUCCESS: "✅",
    TaskStatus.FAILED: "❌",
    TaskStatus.RUNNING: "🔄",
    TaskStatus.NEVER_RUN: "⏸️ ",
}


@cli.command("list")
@click.option("--verbose", "-v", is_flag=True, help="Show extra detail.")
def list_tasks(verbose: bool) -> None:
    """Show all tasks and their current status."""
    config = _load_config()
    tasks = parse_all_tasks(config.vault_path, config.task_folder)

    if not tasks:
        click.echo("No tasks found.")
        return

    click.echo(f"Found {len(tasks)} task(s):\n")

    for t in tasks:
        icon = _STATUS_ICONS.get(t.status, "?")
        click.echo(f"  {icon} {t.title}")
        if verbose:
            click.echo(f"      Command:  {t.command}")
            click.echo(f"      Schedule: {t.schedule}")
            click.echo(f"      File:     {t.file_path}")
            if t.last_run:
                click.echo(f"      Last Run: {t.last_run.strftime('%Y-%m-%d %H:%M:%S')}")
            if t.total_runs > 0:
                click.echo(
                    f"      Runs:     {t.total_runs} "
                    f"({t.successful_runs} ok, {t.failed_runs} failed)"
                )
            click.echo()


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("task_name", required=False)
@click.option(
    "--file", "-f", "file_path",
    type=click.Path(exists=True, dir_okay=False),
    help="Run the task defined in this file (for Shell Commands plugin).",
)
def run(task_name: str | None, file_path: str | None) -> None:
    """Execute a task by name or by file path.

    \b
    Examples:
        obs-tasks run "Backup Docs"
        obs-tasks run --file /path/to/Tasks/work.md
    """
    if not task_name and not file_path:
        click.echo("Error: Provide a task name or --file path.", err=True)
        sys.exit(1)

    config = _load_config()

    if file_path:
        tasks = parse_file(Path(file_path))
    else:
        tasks = parse_all_tasks(config.vault_path, config.task_folder)

    if not tasks:
        if file_path:
            click.echo(
                f"Error: No valid task in '{Path(file_path).name}'. "
                "A task needs at least '- Command:' and '- Schedule:' lines.",
                err=True,
            )
        else:
            click.echo(
                "Error: No tasks found in vault. "
                "Create .md files with '- Command:' and '- Schedule:' in Tasks/.",
                err=True,
            )
        sys.exit(1)

    # Find the target task
    if task_name:
        # Case-insensitive partial match
        name_lower = task_name.lower()
        matches = [t for t in tasks if name_lower in t.title.lower()]
        if not matches:
            click.echo(f"Error: No task matching '{task_name}'.", err=True)
            sys.exit(1)
        if len(matches) > 1:
            click.echo(f"Error: Multiple tasks match '{task_name}':", err=True)
            for m in matches:
                click.echo(f"  - {m.title}", err=True)
            sys.exit(1)
        task = matches[0]
    else:
        # --file mode: one file = one task
        task = tasks[0]

    # Execute
    click.echo(f"▶ Running: {task.title}")
    click.echo(f"  Command: {task.command}")
    click.echo()

    result = execute_task(
        task.id, task.command, timeout=config.command_timeout
    )

    # Write results back (create report first so we can link it in history)
    report_path = create_report(task, result, config.reports_path)
    update_task_state(task, result, report_path=report_path)

    # Show result
    if result.success:
        click.echo(f"✅ Success ({result.duration:.1f}s)")
    else:
        click.echo(f"❌ Failed (exit {result.exit_code}, {result.duration:.1f}s)")

    if result.stdout.strip():
        click.echo(f"\n--- Output ---\n{result.stdout.rstrip()}")
    if result.stderr.strip():
        click.echo(f"\n--- Errors ---\n{result.stderr.rstrip()}")

    click.echo(f"\n📄 Report: {report_path}")
