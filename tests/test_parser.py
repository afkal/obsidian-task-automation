"""Tests for obs_tasks.parser — Markdown parser for task definitions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from obs_tasks.models import Task, TaskStatus
from obs_tasks.parser import (
    _find_task_blocks,
    _parse_datetime,
    _parse_duration,
    _parse_int,
    _parse_status,
    find_task_files,
    parse_all_tasks,
    parse_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Create a minimal vault with a Tasks/ directory."""
    tasks_dir = tmp_path / "Tasks"
    tasks_dir.mkdir()
    return tmp_path


def _write_task_file(vault: Path, name: str, content: str) -> Path:
    """Helper: write a .md file inside Tasks/."""
    f = vault / "Tasks" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# find_task_files
# ---------------------------------------------------------------------------


class TestFindTaskFiles:
    def test_finds_md_files(self, vault: Path) -> None:
        _write_task_file(vault, "work.md", "# Work\n")
        _write_task_file(vault, "personal.md", "# Personal\n")
        files = find_task_files(vault, "Tasks")
        assert len(files) == 2
        names = [f.name for f in files]
        assert "work.md" in names
        assert "personal.md" in names

    def test_recursive_discovery(self, vault: Path) -> None:
        _write_task_file(vault, "sub/deep.md", "# Deep\n")
        files = find_task_files(vault, "Tasks")
        assert len(files) == 1
        assert files[0].name == "deep.md"

    def test_skips_hidden_files(self, vault: Path) -> None:
        _write_task_file(vault, ".hidden.md", "# Hidden\n")
        _write_task_file(vault, ".hidden_dir/task.md", "# Task\n")
        _write_task_file(vault, "visible.md", "# Visible\n")
        files = find_task_files(vault, "Tasks")
        assert len(files) == 1
        assert files[0].name == "visible.md"

    def test_returns_sorted(self, vault: Path) -> None:
        _write_task_file(vault, "zebra.md", "# Z\n")
        _write_task_file(vault, "alpha.md", "# A\n")
        files = find_task_files(vault, "Tasks")
        assert files[0].name == "alpha.md"
        assert files[1].name == "zebra.md"

    def test_missing_folder_returns_empty(self, vault: Path) -> None:
        files = find_task_files(vault, "NonExistent")
        assert files == []

    def test_ignores_non_md_files(self, vault: Path) -> None:
        _write_task_file(vault, "notes.txt", "not markdown")
        _write_task_file(vault, "task.md", "# Task\n")
        files = find_task_files(vault, "Tasks")
        assert len(files) == 1
        assert files[0].name == "task.md"


# ---------------------------------------------------------------------------
# parse_file — simple format (direct heading + fields)
# ---------------------------------------------------------------------------


class TestParseFileSimple:
    """Tasks with heading followed directly by field lines."""

    def test_simple_task(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "simple.md",
            """\
### Backup Docs
- Command: `python backup.py`
- Schedule: 0 2 * * *
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.title == "Backup Docs"
        assert t.command == "python backup.py"
        assert t.schedule == "0 2 * * *"
        assert t.id == "backup-docs"
        assert t.status == TaskStatus.NEVER_RUN

    def test_command_without_backticks(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "nobacktick.md",
            """\
### My Task
- Command: echo hello
- Schedule: 0 * * * *
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 1
        assert tasks[0].command == "echo hello"

    def test_minimal_task_only_command_and_schedule(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "minimal.md",
            """\
## Run Tests
- Command: `pytest tests/`
- Schedule: */30 * * * *
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.command == "pytest tests/"
        assert t.schedule == "*/30 * * * *"
        assert t.status == TaskStatus.NEVER_RUN
        assert t.last_run is None
        assert t.next_run is None
        assert t.duration is None
        assert t.total_runs == 0


# ---------------------------------------------------------------------------
# parse_file — sub-headed format (#### Task Definition)
# ---------------------------------------------------------------------------


class TestParseFileSubHeaded:
    """Tasks using the #### Task Definition sub-section variant from the spec."""

    def test_sub_headed_with_all_sections(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "full.md",
            """\
## Backup Vaisala Documentation

### Purpose
Daily backup of internal documentation to local storage.

### Task Definition
- Command: `python ~/scripts/backup_docs.py --target /backups/vaisala`
- Schedule: 0 2 * * *

#### Current State
- Status: ✅ Success
- Last Run: 2024-12-16 02:00:15
- Next Run: 2024-12-17 02:00:00
- Duration: 45.2s
- Result: Backed up 245 pages (12.5 MB)

#### Statistics
- Total Runs: 47
- Successful: 46
- Failed: 1
- Last Failure: 2024-11-15 02:00:00
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.title == "Backup Vaisala Documentation"
        assert t.command == "python ~/scripts/backup_docs.py --target /backups/vaisala"
        assert t.schedule == "0 2 * * *"
        assert t.status == TaskStatus.SUCCESS
        assert t.last_run == datetime(2024, 12, 16, 2, 0, 15)
        assert t.next_run == datetime(2024, 12, 17, 2, 0, 0)
        assert t.duration == 45.2
        assert t.result_summary == "Backed up 245 pages (12.5 MB)"
        assert t.total_runs == 47
        assert t.successful_runs == 46
        assert t.failed_runs == 1
        assert t.last_failure == datetime(2024, 11, 15, 2, 0, 0)


# ---------------------------------------------------------------------------
# parse_file — multiple tasks in one file
# ---------------------------------------------------------------------------


class TestParseFileMultipleTasks:
    def test_two_tasks_in_one_file(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "multi.md",
            """\
# Work Automation Tasks

## Backup Docs
- Command: `python backup.py`
- Schedule: 0 2 * * *

## Update Stats
- Command: `python stats.py`
- Schedule: 0 9 * * MON
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 2
        titles = {t.title for t in tasks}
        assert titles == {"Backup Docs", "Update Stats"}

    def test_tasks_at_different_heading_levels(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "levels.md",
            """\
# Top Level

## Task A
- Command: `echo a`
- Schedule: 0 1 * * *

### Task B
- Command: `echo b`
- Schedule: 0 2 * * *
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 2

    def test_full_spec_example_two_tasks(self, vault: Path) -> None:
        """Realistic example from the spec: two tasks in work.md."""
        f = _write_task_file(
            vault,
            "work.md",
            """\
# Work Automation Tasks

## Backup Vaisala Documentation

### Purpose
Daily backup of internal documentation to local storage.

### Task Definition
- Command: `python ~/scripts/backup_docs.py --target /backups/vaisala`
- Schedule: 0 2 * * *

#### Current State
- Status: ✅ Success
- Last Run: 2024-12-16 02:00:15
- Next Run: 2024-12-17 02:00:00
- Duration: 45.2s
- Result: Backed up 245 pages (12.5 MB)

#### Statistics
- Total Runs: 47
- Successful: 46
- Failed: 1
- Last Failure: 2024-11-15 02:00:00

**Detailed Output:** [[Reports/2024-12-16-backup-vaisala-documentation]]

### Notes
- Requires VPN connection
- Backs up to external drive mounted at /backups

---

## Update GitHub Statistics

### Task Definition
- Command: `python ~/scripts/github_stats.py`
- Schedule: 0 9 * * MON

#### Current State
- Status: ✅ Success
- Last Run: 2024-12-15 09:00:00
- Next Run: 2024-12-22 09:00:00
- Duration: 3.2s
- Result: Analyzed 142 commits, 23 PRs

#### Statistics
- Total Runs: 8
- Successful: 8
- Failed: 0
- Last Failure: Never

**Detailed Output:** [[Reports/2024-12-15-update-github-statistics]]
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 2

        backup = next(t for t in tasks if "Backup" in t.title)
        assert backup.title == "Backup Vaisala Documentation"
        assert backup.total_runs == 47
        assert backup.successful_runs == 46

        stats = next(t for t in tasks if "GitHub" in t.title)
        assert stats.title == "Update GitHub Statistics"
        assert stats.schedule == "0 9 * * MON"
        assert stats.total_runs == 8
        assert stats.failed_runs == 0


# ---------------------------------------------------------------------------
# parse_file — malformed / edge cases
# ---------------------------------------------------------------------------


class TestParseFileMalformed:
    def test_command_without_schedule_skipped(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "nosched.md",
            """\
### Missing Schedule
- Command: `echo hello`
""",
        )
        tasks = parse_file(f)
        assert tasks == []

    def test_schedule_without_command_skipped(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "nocmd.md",
            """\
### Missing Command
- Schedule: 0 * * * *
""",
        )
        tasks = parse_file(f)
        assert tasks == []

    def test_command_without_heading_skipped(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "noheading.md",
            """\
- Command: `echo hello`
- Schedule: 0 * * * *
""",
        )
        tasks = parse_file(f)
        assert tasks == []

    def test_empty_file(self, vault: Path) -> None:
        f = _write_task_file(vault, "empty.md", "")
        tasks = parse_file(f)
        assert tasks == []

    def test_no_tasks_just_headings(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "notasks.md",
            """\
# Notes
## Some heading
Just text, no task fields.
""",
        )
        tasks = parse_file(f)
        assert tasks == []

    def test_unreadable_file(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.md"
        tasks = parse_file(f)
        assert tasks == []


# ---------------------------------------------------------------------------
# parse_file — field tracking (source location)
# ---------------------------------------------------------------------------


class TestParseFileMetadata:
    def test_file_path_tracked(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "tracked.md",
            """\
### My Task
- Command: `echo test`
- Schedule: 0 * * * *
""",
        )
        tasks = parse_file(f)
        assert tasks[0].file_path == f

    def test_heading_line_tracked(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "lines.md",
            """\
# Header

Some intro text.

### My Task
- Command: `echo test`
- Schedule: 0 * * * *
""",
        )
        tasks = parse_file(f)
        # "### My Task" is on line index 4 (0-based)
        assert tasks[0].heading_line == 4


# ---------------------------------------------------------------------------
# parse_all_tasks
# ---------------------------------------------------------------------------


class TestParseAllTasks:
    def test_parses_across_files(self, vault: Path) -> None:
        _write_task_file(
            vault,
            "a.md",
            """\
### Task A
- Command: `echo a`
- Schedule: 0 1 * * *
""",
        )
        _write_task_file(
            vault,
            "b.md",
            """\
### Task B
- Command: `echo b`
- Schedule: 0 2 * * *
""",
        )
        tasks = parse_all_tasks(vault, "Tasks")
        assert len(tasks) == 2
        titles = {t.title for t in tasks}
        assert titles == {"Task A", "Task B"}

    def test_empty_vault(self, vault: Path) -> None:
        tasks = parse_all_tasks(vault, "Tasks")
        assert tasks == []


# ---------------------------------------------------------------------------
# _find_task_blocks internals
# ---------------------------------------------------------------------------


class TestFindTaskBlocks:
    def test_block_boundaries_stop_at_same_level_heading(self) -> None:
        lines = [
            "## Task One",
            "- Command: `echo one`",
            "- Schedule: 0 1 * * *",
            "## Task Two",
            "- Command: `echo two`",
            "- Schedule: 0 2 * * *",
        ]
        blocks = _find_task_blocks(lines)
        assert len(blocks) == 2
        assert blocks[0].title == "Task One"
        assert blocks[1].title == "Task Two"

    def test_block_boundaries_stop_at_higher_level_heading(self) -> None:
        lines = [
            "### Deep Task",
            "- Command: `echo deep`",
            "- Schedule: 0 1 * * *",
            "## Higher Level",
            "Some other content",
        ]
        blocks = _find_task_blocks(lines)
        assert len(blocks) == 1
        assert blocks[0].title == "Deep Task"

    def test_no_command_lines_returns_empty(self) -> None:
        lines = [
            "## Just a heading",
            "Some paragraph text.",
        ]
        blocks = _find_task_blocks(lines)
        assert blocks == []


# ---------------------------------------------------------------------------
# _parse_status
# ---------------------------------------------------------------------------


class TestParseStatus:
    def test_none_returns_never_run(self) -> None:
        assert _parse_status(None) == TaskStatus.NEVER_RUN

    def test_success_variants(self) -> None:
        assert _parse_status("Success") == TaskStatus.SUCCESS
        assert _parse_status("✅ Success") == TaskStatus.SUCCESS
        assert _parse_status("succeeded") == TaskStatus.SUCCESS
        assert _parse_status("ok") == TaskStatus.SUCCESS

    def test_failed_variants(self) -> None:
        assert _parse_status("Failed") == TaskStatus.FAILED
        assert _parse_status("❌ Failed") == TaskStatus.FAILED
        assert _parse_status("failure") == TaskStatus.FAILED
        assert _parse_status("error") == TaskStatus.FAILED

    def test_running_variants(self) -> None:
        assert _parse_status("Running") == TaskStatus.RUNNING
        assert _parse_status("🔄 Running") == TaskStatus.RUNNING
        assert _parse_status("in progress") == TaskStatus.RUNNING

    def test_never_run_variants(self) -> None:
        assert _parse_status("Never run") == TaskStatus.NEVER_RUN
        assert _parse_status("pending") == TaskStatus.NEVER_RUN
        assert _parse_status("-") == TaskStatus.NEVER_RUN

    def test_unknown_defaults_to_never_run(self) -> None:
        assert _parse_status("something_weird") == TaskStatus.NEVER_RUN


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    def test_none_returns_none(self) -> None:
        assert _parse_datetime(None) is None

    def test_placeholder_values(self) -> None:
        assert _parse_datetime("-") is None
        assert _parse_datetime("") is None
        assert _parse_datetime("Never") is None
        assert _parse_datetime("never") is None
        assert _parse_datetime("N/A") is None
        assert _parse_datetime("n/a") is None

    def test_iso_format(self) -> None:
        dt = _parse_datetime("2024-12-16 02:00:15")
        assert dt == datetime(2024, 12, 16, 2, 0, 15)

    def test_date_only(self) -> None:
        dt = _parse_datetime("2024-12-16")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 12
        assert dt.day == 16

    def test_invalid_returns_none(self) -> None:
        assert _parse_datetime("not-a-date") is None


# ---------------------------------------------------------------------------
# _parse_duration
# ---------------------------------------------------------------------------


class TestParseDuration:
    def test_none_returns_none(self) -> None:
        assert _parse_duration(None) is None

    def test_placeholder_values(self) -> None:
        assert _parse_duration("-") is None
        assert _parse_duration("") is None
        assert _parse_duration("N/A") is None

    def test_seconds_with_suffix(self) -> None:
        assert _parse_duration("45.2s") == 45.2
        assert _parse_duration("3.2s") == 3.2
        assert _parse_duration("100s") == 100.0

    def test_seconds_without_suffix(self) -> None:
        assert _parse_duration("45.2") == 45.2

    def test_invalid_returns_none(self) -> None:
        assert _parse_duration("fast") is None


# ---------------------------------------------------------------------------
# _parse_int
# ---------------------------------------------------------------------------


class TestParseInt:
    def test_none_returns_zero(self) -> None:
        assert _parse_int(None) == 0

    def test_placeholder_values(self) -> None:
        assert _parse_int("-") == 0
        assert _parse_int("") == 0
        assert _parse_int("N/A") == 0

    def test_normal_integers(self) -> None:
        assert _parse_int("47") == 47
        assert _parse_int("0") == 0

    def test_comma_separated(self) -> None:
        assert _parse_int("1,247") == 1247

    def test_invalid_returns_zero(self) -> None:
        assert _parse_int("many") == 0


# ---------------------------------------------------------------------------
# Integration: parse realistic spec example
# ---------------------------------------------------------------------------


class TestParseRealisticExample:
    """End-to-end parsing of realistic markdown from the spec."""

    def test_failed_task_state(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "failed.md",
            """\
### Database Cleanup
- Command: `python ~/scripts/db_cleanup.py`
- Schedule: 0 3 * * SUN

#### Current State
- Status: ❌ Failed
- Last Run: 2024-12-15 03:00:01
- Next Run: 2024-12-22 03:00:00
- Duration: 12.5s
- Result: Connection refused: localhost:5432

#### Statistics
- Total Runs: 10
- Successful: 8
- Failed: 2
- Last Failure: 2024-12-15 03:00:01
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.status == TaskStatus.FAILED
        assert t.result_summary == "Connection refused: localhost:5432"
        assert t.total_runs == 10
        assert t.successful_runs == 8
        assert t.failed_runs == 2

    def test_never_run_task(self, vault: Path) -> None:
        f = _write_task_file(
            vault,
            "new.md",
            """\
### Brand New Task
- Command: `echo hello`
- Schedule: 0 * * * *

#### Current State
- Status: Never run
- Last Run: -
- Next Run: -
- Duration: -
- Result: -

#### Statistics
- Total Runs: 0
- Successful: 0
- Failed: 0
- Last Failure: -
""",
        )
        tasks = parse_file(f)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.status == TaskStatus.NEVER_RUN
        assert t.last_run is None
        assert t.next_run is None
        assert t.duration is None
        assert t.result_summary is None
        assert t.total_runs == 0
        assert t.successful_runs == 0
        assert t.failed_runs == 0
        assert t.last_failure is None

    def test_result_dash_becomes_none(self, vault: Path) -> None:
        """Result field set to '-' should be treated as None."""
        f = _write_task_file(
            vault,
            "dash.md",
            """\
### Dash Result
- Command: `echo test`
- Schedule: 0 * * * *
- Result: -
""",
        )
        tasks = parse_file(f)
        assert tasks[0].result_summary is None
