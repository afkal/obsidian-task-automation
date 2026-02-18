"""Markdown parser for Obsidian task definitions.

Each .md file in the Tasks/ folder represents one task.
The task title is the filename (without .md extension).
The parser looks for ``- Command:`` and ``- Schedule:`` lines
anywhere in the file.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from dateutil.parser import parse as dateutil_parse

from .models import Task, TaskStatus, slugify

logger = logging.getLogger(__name__)

# Regex patterns
COMMAND_RE = re.compile(r"^-\s*Command:\s*`(.+?)`\s*$")
COMMAND_NO_BACKTICK_RE = re.compile(r"^-\s*Command:\s*(.+?)\s*$")
SCHEDULE_RE = re.compile(r"^-\s*Schedule:\s*(.+?)\s*$")
STATUS_RE = re.compile(r"^-\s*Status:\s*(.+?)\s*$")
LAST_RUN_RE = re.compile(r"^-\s*Last Run:\s*(.+?)\s*$")
NEXT_RUN_RE = re.compile(r"^-\s*Next Run:\s*(.+?)\s*$")
DURATION_RE = re.compile(r"^-\s*Duration:\s*(.+?)\s*$")
RESULT_RE = re.compile(r"^-\s*Result:\s*(.+?)\s*$")
TOTAL_RUNS_RE = re.compile(r"^-\s*Total Runs:\s*(.+?)\s*$")
SUCCESSFUL_RE = re.compile(r"^-\s*Successful:\s*(.+?)\s*$")
FAILED_RE = re.compile(r"^-\s*Failed:\s*(.+?)\s*$")
LAST_FAILURE_RE = re.compile(r"^-\s*Last Failure:\s*(.+?)\s*$")


def find_task_files(vault_path: Path, task_folder: str = "Tasks") -> list[Path]:
    """Find all .md files in the task folder, recursively.

    Skips hidden files and directories (starting with '.').
    Returns files sorted by path for deterministic ordering.
    """
    tasks_dir = vault_path / task_folder
    if not tasks_dir.is_dir():
        logger.warning("Task folder not found: %s", tasks_dir)
        return []

    files = []
    for path in tasks_dir.rglob("*.md"):
        # Skip hidden files/dirs
        if any(part.startswith(".") for part in path.relative_to(tasks_dir).parts):
            continue
        files.append(path)

    return sorted(files)


def parse_file(file_path: Path) -> list[Task]:
    """Parse a task definition from a single markdown file.

    One file = one task. The task title is the filename (without .md).
    Returns a list with one Task, or empty list if no valid task found.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Cannot read file %s: %s", file_path, e)
        return []

    lines = content.splitlines()
    fields = _extract_fields(lines)

    if not fields.get("command") or not fields.get("schedule"):
        if fields.get("command") and not fields.get("schedule"):
            logger.warning(
                "File '%s' has Command but no Schedule, skipping", file_path.name
            )
        return []

    title = file_path.stem  # filename without .md

    task = Task(
        id=slugify(title),
        title=title,
        command=fields["command"],
        schedule=fields["schedule"],
        status=_parse_status(fields.get("status")),
        last_run=_parse_datetime(fields.get("last_run")),
        next_run=_parse_datetime(fields.get("next_run")),
        duration=_parse_duration(fields.get("duration")),
        result_summary=(
            fields["result"]
            if fields.get("result") and fields["result"] != "-"
            else None
        ),
        total_runs=_parse_int(fields.get("total_runs")),
        successful_runs=_parse_int(fields.get("successful")),
        failed_runs=_parse_int(fields.get("failed")),
        last_failure=_parse_datetime(fields.get("last_failure")),
        file_path=file_path,
        heading_line=0,
    )
    return [task]


def parse_all_tasks(vault_path: Path, task_folder: str = "Tasks") -> list[Task]:
    """Find all task files and parse all tasks from them."""
    files = find_task_files(vault_path, task_folder)
    tasks = []
    for f in files:
        tasks.extend(parse_file(f))
    return tasks


def _extract_fields(lines: list[str]) -> dict[str, str]:
    """Extract all task fields from file lines."""
    fields: dict[str, str] = {}

    for line in lines:
        # Command (prefer backtick version, first occurrence wins)
        if "command" not in fields:
            m = COMMAND_RE.match(line)
            if m:
                fields["command"] = m.group(1)
                continue
            m = COMMAND_NO_BACKTICK_RE.match(line)
            if m:
                fields["command"] = m.group(1)
                continue

        # Schedule (first occurrence wins)
        if "schedule" not in fields:
            m = SCHEDULE_RE.match(line)
            if m:
                fields["schedule"] = m.group(1)
                continue

        m = STATUS_RE.match(line)
        if m:
            fields["status"] = m.group(1)
            continue

        m = LAST_RUN_RE.match(line)
        if m:
            fields["last_run"] = m.group(1)
            continue

        m = NEXT_RUN_RE.match(line)
        if m:
            fields["next_run"] = m.group(1)
            continue

        m = DURATION_RE.match(line)
        if m:
            fields["duration"] = m.group(1)
            continue

        m = RESULT_RE.match(line)
        if m:
            fields["result"] = m.group(1)
            continue

        m = TOTAL_RUNS_RE.match(line)
        if m:
            fields["total_runs"] = m.group(1)
            continue

        m = SUCCESSFUL_RE.match(line)
        if m:
            fields["successful"] = m.group(1)
            continue

        m = FAILED_RE.match(line)
        if m:
            fields["failed"] = m.group(1)
            continue

        m = LAST_FAILURE_RE.match(line)
        if m:
            fields["last_failure"] = m.group(1)
            continue

    return fields


def _parse_status(value: str | None) -> TaskStatus:
    """Parse status string, handling emoji prefixes.

    '✅ Success' -> SUCCESS
    '❌ Failed' -> FAILED
    'Never run' -> NEVER_RUN
    'Running' -> RUNNING
    None -> NEVER_RUN
    """
    if value is None:
        return TaskStatus.NEVER_RUN

    # Strip common emoji prefixes
    cleaned = value.strip()
    for prefix in ("✅", "❌", "🔄", "⏳"):
        cleaned = cleaned.removeprefix(prefix).strip()

    lower = cleaned.lower()

    if lower in ("success", "succeeded", "ok"):
        return TaskStatus.SUCCESS
    if lower in ("failed", "failure", "error"):
        return TaskStatus.FAILED
    if lower in ("running", "in progress", "in_progress"):
        return TaskStatus.RUNNING
    if lower in ("never run", "never_run", "pending", "-"):
        return TaskStatus.NEVER_RUN

    logger.warning("Unknown task status '%s', defaulting to NEVER_RUN", value)
    return TaskStatus.NEVER_RUN


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse datetime string, returning None for empty/placeholder values."""
    if value is None:
        return None

    cleaned = value.strip()
    if cleaned in ("-", "", "Never", "never", "N/A", "n/a"):
        return None

    try:
        return dateutil_parse(cleaned)
    except (ValueError, OverflowError):
        logger.warning("Cannot parse datetime: '%s'", value)
        return None


def _parse_duration(value: str | None) -> float | None:
    """Parse duration string like '45.2s' into float seconds."""
    if value is None:
        return None

    cleaned = value.strip()
    if cleaned in ("-", "", "N/A"):
        return None

    # Remove trailing 's' suffix
    cleaned = cleaned.rstrip("s").strip()

    try:
        return float(cleaned)
    except ValueError:
        logger.warning("Cannot parse duration: '%s'", value)
        return None


def _parse_int(value: str | None) -> int:
    """Parse integer, returning 0 for empty/placeholder values."""
    if value is None:
        return 0

    cleaned = value.strip()
    if cleaned in ("-", "", "N/A"):
        return 0

    # Handle comma-separated numbers like "1,247"
    cleaned = cleaned.replace(",", "")

    try:
        return int(cleaned)
    except ValueError:
        logger.warning("Cannot parse integer: '%s'", value)
        return 0
