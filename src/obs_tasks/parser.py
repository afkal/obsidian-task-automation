"""Markdown parser for Obsidian task definitions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dateutil.parser import parse as dateutil_parse

from .models import Task, TaskStatus, slugify

logger = logging.getLogger(__name__)

# Generic sub-heading titles that should not be used as task titles.
# When the nearest heading above a Command line has one of these titles,
# we look further up for the real task title.
_GENERIC_HEADINGS = frozenset({
    "task definition",
    "definition",
    "configuration",
    "config",
    "setup",
    "task config",
    "task configuration",
})

# Regex patterns
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
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


@dataclass
class _RawBlock:
    """Intermediate representation of a parsed task block."""

    title: str
    heading_level: int
    heading_line: int
    command: str | None = None
    schedule: str | None = None
    status: str | None = None
    last_run: str | None = None
    next_run: str | None = None
    duration: str | None = None
    result: str | None = None
    total_runs: str | None = None
    successful: str | None = None
    failed: str | None = None
    last_failure: str | None = None


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
    """Parse all task definitions from a single markdown file.

    Returns an empty list if no tasks found or file cannot be read.
    Logs warnings for malformed tasks.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Cannot read file %s: %s", file_path, e)
        return []

    lines = content.splitlines()
    blocks = _find_task_blocks(lines)

    tasks = []
    for block in blocks:
        task = _block_to_task(block, file_path)
        if task is not None:
            tasks.append(task)

    return tasks


def parse_all_tasks(vault_path: Path, task_folder: str = "Tasks") -> list[Task]:
    """Find all task files and parse all tasks from them."""
    files = find_task_files(vault_path, task_folder)
    tasks = []
    for f in files:
        tasks.extend(parse_file(f))
    return tasks


def _find_task_blocks(lines: list[str]) -> list[_RawBlock]:
    """Identify task blocks by scanning for Command + Schedule lines.

    Strategy:
    1. Find all lines that match '- Command: ...'
    2. For each, find the nearest heading above it
    3. Determine the block boundaries
    4. Extract all fields within the block
    """
    # First pass: find all headings and command lines
    headings: list[tuple[int, int, str]] = []  # (line_idx, level, title)
    command_lines: list[int] = []

    for i, line in enumerate(lines):
        hm = HEADING_RE.match(line)
        if hm:
            headings.append((i, len(hm.group(1)), hm.group(2).strip()))

        if COMMAND_RE.match(line) or COMMAND_NO_BACKTICK_RE.match(line):
            command_lines.append(i)

    if not command_lines:
        return []

    blocks = []
    for cmd_line in command_lines:
        # Find nearest heading above the command line
        nearest_heading = None
        for h_line, h_level, h_title in reversed(headings):
            if h_line < cmd_line:
                nearest_heading = (h_line, h_level, h_title)
                break

        if nearest_heading is None:
            logger.warning(
                "Found Command at line %d but no heading above it, skipping", cmd_line + 1
            )
            continue

        h_line, h_level, h_title = nearest_heading

        # If the nearest heading is a generic sub-heading like "Task Definition",
        # look further up for the real task title (parent heading at a higher level).
        if h_title.strip().lower() in _GENERIC_HEADINGS:
            parent_heading = None
            for ph_line, ph_level, ph_title in reversed(headings):
                if ph_line < h_line and ph_level < h_level:
                    parent_heading = (ph_line, ph_level, ph_title)
                    break
            if parent_heading is not None:
                h_line, h_level, h_title = parent_heading

        # Determine block end: next heading at same or higher level, or EOF
        block_end = len(lines)
        for next_h_line, next_h_level, _ in headings:
            if next_h_line > h_line and next_h_level <= h_level:
                block_end = next_h_line
                break

        # Extract fields from the block
        block_lines = lines[h_line:block_end]
        raw = _RawBlock(
            title=h_title,
            heading_level=h_level,
            heading_line=h_line,
        )
        _extract_fields(block_lines, raw)

        if raw.command and raw.schedule:
            blocks.append(raw)
        elif raw.command and not raw.schedule:
            logger.warning(
                "Task '%s' at line %d has Command but no Schedule, skipping",
                h_title,
                h_line + 1,
            )
        # If no command found in block, it was a false positive from
        # a nested heading — skip silently

    return blocks


def _extract_fields(block_lines: list[str], raw: _RawBlock) -> None:
    """Extract all task fields from a block of lines."""
    for line in block_lines:
        # Command (prefer backtick version)
        m = COMMAND_RE.match(line)
        if m:
            raw.command = m.group(1)
            continue
        if raw.command is None:
            m = COMMAND_NO_BACKTICK_RE.match(line)
            if m:
                raw.command = m.group(1)
                continue

        m = SCHEDULE_RE.match(line)
        if m:
            raw.schedule = m.group(1)
            continue

        m = STATUS_RE.match(line)
        if m:
            raw.status = m.group(1)
            continue

        m = LAST_RUN_RE.match(line)
        if m:
            raw.last_run = m.group(1)
            continue

        m = NEXT_RUN_RE.match(line)
        if m:
            raw.next_run = m.group(1)
            continue

        m = DURATION_RE.match(line)
        if m:
            raw.duration = m.group(1)
            continue

        m = RESULT_RE.match(line)
        if m:
            raw.result = m.group(1)
            continue

        m = TOTAL_RUNS_RE.match(line)
        if m:
            raw.total_runs = m.group(1)
            continue

        m = SUCCESSFUL_RE.match(line)
        if m:
            raw.successful = m.group(1)
            continue

        m = FAILED_RE.match(line)
        if m:
            raw.failed = m.group(1)
            continue

        m = LAST_FAILURE_RE.match(line)
        if m:
            raw.last_failure = m.group(1)
            continue


def _block_to_task(block: _RawBlock, file_path: Path) -> Task | None:
    """Convert a raw block into a Task object."""
    if not block.command or not block.schedule:
        return None

    return Task(
        id=slugify(block.title),
        title=block.title,
        command=block.command,
        schedule=block.schedule,
        status=_parse_status(block.status),
        last_run=_parse_datetime(block.last_run),
        next_run=_parse_datetime(block.next_run),
        duration=_parse_duration(block.duration),
        result_summary=block.result if block.result and block.result != "-" else None,
        total_runs=_parse_int(block.total_runs),
        successful_runs=_parse_int(block.successful),
        failed_runs=_parse_int(block.failed),
        last_failure=_parse_datetime(block.last_failure),
        file_path=file_path,
        heading_line=block.heading_line,
    )


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
