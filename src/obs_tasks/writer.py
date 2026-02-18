"""Markdown writer — updates task state/statistics and creates report files.

Design rules:
- Never modify user content (Command, Schedule, notes).
- Only touch ``#### Current State``, ``#### Statistics``, and
  ``#### Run History`` sections.
- Atomic file writes: write to temp file then rename.
- Create report files with full output, metadata and Obsidian backlinks.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from obs_tasks.models import ExecutionResult, Task, TaskStatus, slugify

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_STATUS_EMOJI = {
    TaskStatus.SUCCESS: "✅ Success",
    TaskStatus.FAILED: "❌ Failed",
    TaskStatus.RUNNING: "🔄 Running",
    TaskStatus.NEVER_RUN: "Never run",
}


def _format_status(status: TaskStatus) -> str:
    return _STATUS_EMOJI.get(status, status.value)


def _format_datetime(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return f"{seconds:.1f}s"


def _format_result(summary: str | None) -> str:
    if not summary:
        return "-"
    # Keep it single-line for the inline field.
    return summary.replace("\n", " ").strip()[:200]


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def build_current_state_lines(
    status: TaskStatus,
    last_run: datetime | None,
    next_run: datetime | None,
    duration: float | None,
    result_summary: str | None,
) -> list[str]:
    """Build the lines for a ``#### Current State`` section."""
    return [
        "#### Current State",
        f"- Status: {_format_status(status)}",
        f"- Last Run: {_format_datetime(last_run)}",
        f"- Next Run: {_format_datetime(next_run)}",
        f"- Duration: {_format_duration(duration)}",
        f"- Result: {_format_result(result_summary)}",
    ]


def build_statistics_lines(
    total_runs: int,
    successful_runs: int,
    failed_runs: int,
    last_failure: datetime | None,
) -> list[str]:
    """Build the lines for a ``#### Statistics`` section."""
    return [
        "#### Statistics",
        f"- Total Runs: {total_runs}",
        f"- Successful: {successful_runs}",
        f"- Failed: {failed_runs}",
        f"- Last Failure: {_format_datetime(last_failure)}",
    ]


# ---------------------------------------------------------------------------
# Run History
# ---------------------------------------------------------------------------

MAX_HISTORY_ROWS = 20
"""Maximum number of rows kept in the Run History table."""

_HISTORY_HEADER = [
    "#### Run History",
    "| Time | Status | Duration | Report |",
    "|------|--------|----------|--------|",
]


def _parse_history_rows(
    lines: list[str],
    section_range: tuple[int, int],
) -> list[str]:
    """Extract data rows from an existing Run History table.

    Returns a list of ``| … |`` data lines (excludes the heading, header
    row and separator row).
    """
    start, end = section_range
    rows: list[str] = []
    for i in range(start, end):
        line = lines[i].strip()
        # Skip heading, header row, separator row, and blanks
        if not line or line.startswith("#") or line.startswith("|---"):
            continue
        if line.startswith("| Time"):
            continue
        if line.startswith("|"):
            rows.append(line)
    return rows


def build_run_history_lines(
    existing_rows: list[str],
    result: ExecutionResult,
    report_name: str | None = None,
) -> list[str]:
    """Build the full ``#### Run History`` section lines.

    Prepends a new row for *result*, keeps at most
    :data:`MAX_HISTORY_ROWS` rows.
    """
    status_emoji = "✅" if result.success else "❌"
    time_str = result.started_at.strftime("%Y-%m-%d %H:%M:%S")
    duration_str = _format_duration(result.duration)

    if report_name:
        # Obsidian wiki-link without .md extension
        report_link = f"[[{report_name}]]"
    else:
        report_link = "-"

    new_row = f"| {time_str} | {status_emoji} | {duration_str} | {report_link} |"

    all_rows = [new_row] + existing_rows
    # Truncate to max rows
    all_rows = all_rows[:MAX_HISTORY_ROWS]

    return _HISTORY_HEADER + all_rows


# ---------------------------------------------------------------------------
# Section replacement in file content
# ---------------------------------------------------------------------------

# Matches a heading line like "#### Current State" or "#### Statistics"
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def _find_section_range(
    lines: list[str],
    section_title: str,
    search_start: int = 0,
    search_end: int | None = None,
) -> tuple[int, int] | None:
    """Find the line range [start, end) of a ``####``-level section.

    Returns the range of lines from the heading itself up to (but not
    including) the next heading at the same or higher level, a ``---``
    separator, a ``**Detailed`` link line, or EOF.
    """
    end = search_end if search_end is not None else len(lines)
    start_idx = None
    section_level = None

    for i in range(search_start, end):
        m = _HEADING_RE.match(lines[i])
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if title.lower() == section_title.lower() and start_idx is None:
                start_idx = i
                section_level = level
                continue
            # If we already found the section, stop at next heading
            # at same or higher level.
            if start_idx is not None and level <= section_level:
                return (start_idx, i)

        # Also stop at horizontal rules or detailed-output links
        if start_idx is not None:
            stripped = lines[i].strip()
            if stripped == "---":
                return (start_idx, i)
            if stripped.startswith("**Detailed"):
                return (start_idx, i)

    if start_idx is not None:
        return (start_idx, end)
    return None


def _find_task_block_range(
    lines: list[str], task: Task
) -> tuple[int, int]:
    """Return the line range [start, end) for the task's block.

    With one-file-per-task, the entire file is the task block.
    """
    return (0, len(lines))


def _replace_or_insert_section(
    lines: list[str],
    section_title: str,
    new_section_lines: list[str],
    block_start: int,
    block_end: int,
) -> list[str]:
    """Replace a section within a task block, or insert it if missing.

    The section is searched within ``lines[block_start:block_end]``.
    If not found, the new section is appended at the end of the block.
    """
    section_range = _find_section_range(
        lines, section_title, search_start=block_start, search_end=block_end
    )

    if section_range is not None:
        s_start, s_end = section_range
        return lines[:s_start] + new_section_lines + [""] + lines[s_end:]
    else:
        # Insert before block_end (before the next heading / EOF).
        # Add a blank line before the section if the preceding line isn't blank.
        insert_at = block_end
        prefix = []
        if insert_at > 0 and lines[insert_at - 1].strip() != "":
            prefix = [""]
        return (
            lines[:insert_at]
            + prefix
            + new_section_lines
            + [""]
            + lines[insert_at:]
        )


# ---------------------------------------------------------------------------
# Atomic file write
# ---------------------------------------------------------------------------


def _atomic_write(file_path: Path, content: str) -> None:
    """Write *content* to *file_path* atomically (temp file + rename)."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=file_path.parent, suffix=".tmp", prefix=".obs-tasks-"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, file_path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_task_state(
    task: Task,
    result: ExecutionResult,
    next_run: datetime | None = None,
    report_path: Path | None = None,
) -> None:
    """Update the ``#### Current State`` section in the task's source file.

    Also updates ``#### Statistics`` and ``#### Run History`` in the same
    write.  Pass *report_path* to include an Obsidian wiki-link in the
    history table.
    """
    if task.file_path is None:
        logger.error("Cannot update task '%s': no file_path", task.title)
        return

    file_path = Path(task.file_path)
    if not file_path.exists():
        logger.error("Task file does not exist: %s", file_path)
        return

    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    block_start, block_end = _find_task_block_range(lines, task)

    # Compute new state values
    status = TaskStatus.SUCCESS if result.success else TaskStatus.FAILED
    last_run = result.started_at
    duration = result.duration
    summary = result.summary

    # Compute new statistics
    total_runs = task.total_runs + 1
    successful_runs = task.successful_runs + (1 if result.success else 0)
    failed_runs = task.failed_runs + (0 if result.success else 1)
    last_failure = (
        result.started_at if not result.success else task.last_failure
    )

    # Build new section lines
    state_lines = build_current_state_lines(
        status, last_run, next_run, duration, summary
    )
    stats_lines = build_statistics_lines(
        total_runs, successful_runs, failed_runs, last_failure
    )

    # Replace/insert Current State first, then Statistics.
    # After replacing Current State, block_end may shift, so we
    # re-find the block range for Statistics.
    lines = _replace_or_insert_section(
        lines, "Current State", state_lines, block_start, block_end
    )

    # Re-find block range (it may have shifted after insertion)
    block_start, block_end = _find_task_block_range(lines, task)

    lines = _replace_or_insert_section(
        lines, "Statistics", stats_lines, block_start, block_end
    )

    # --- Run History ---
    # Re-find block range again (may have shifted after Statistics)
    block_start, block_end = _find_task_block_range(lines, task)

    # Read existing history rows (if any)
    history_range = _find_section_range(
        lines, "Run History", search_start=block_start, search_end=block_end
    )
    existing_rows = (
        _parse_history_rows(lines, history_range) if history_range else []
    )

    # Build report name for wiki-link (stem without .md)
    report_name = report_path.stem if report_path else None

    history_lines = build_run_history_lines(
        existing_rows, result, report_name
    )

    lines = _replace_or_insert_section(
        lines, "Run History", history_lines, block_start, block_end
    )

    new_content = "\n".join(lines)
    # Ensure file ends with newline
    if not new_content.endswith("\n"):
        new_content += "\n"

    _atomic_write(file_path, new_content)
    logger.info("Updated state for task '%s' in %s", task.title, file_path)


def create_report(
    task: Task,
    result: ExecutionResult,
    reports_dir: Path,
) -> Path:
    """Create a detailed report file for an execution.

    Returns the path to the created report file.
    """
    date_str = result.started_at.strftime("%Y-%m-%d-%H%M%S")
    slug = slugify(task.title)
    filename = f"{date_str}-{slug}.md"
    report_path = reports_dir / filename

    status_text = "✅ Success" if result.success else "❌ Failed"

    # Build the source file backlink (Obsidian wiki-link style)
    source_link = ""
    if task.file_path is not None:
        # Use relative name without .md extension for Obsidian link
        source_name = Path(task.file_path).stem
        source_link = f"- Back to [[{source_name}]]"

    # Build report content
    report_lines = [
        f"# {task.title} - Execution Report",
        "",
        f"**Executed:** {_format_datetime(result.started_at)}",
        f"**Duration:** {result.duration:.1f} seconds",
        f"**Command:** `{task.command}`",
        f"**Exit Code:** {result.exit_code}",
        f"**Status:** {status_text}",
        "",
        "## Output",
        "",
        "```",
        result.stdout.rstrip() if result.stdout else "(no output)",
        "```",
    ]

    # Add stderr section if present
    if result.stderr and result.stderr.strip():
        report_lines += [
            "",
            "## Errors",
            "",
            "```",
            result.stderr.rstrip(),
            "```",
        ]

    # Add links section
    report_lines += [
        "",
        "## Links",
    ]
    if source_link:
        report_lines.append(source_link)

    report_lines += [
        "",
        "---",
        "*Generated by Obsidian Task Automation*",
    ]

    content = "\n".join(report_lines) + "\n"
    _atomic_write(report_path, content)
    logger.info("Created report: %s", report_path)
    return report_path
