"""Tests for obs_tasks.writer — Markdown state updates and report creation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from obs_tasks.models import ExecutionResult, Task, TaskStatus
from obs_tasks.writer import (
    _atomic_write,
    _find_section_range,
    _find_task_block_range,
    build_current_state_lines,
    build_statistics_lines,
    create_report,
    update_task_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_task(
    title: str = "Backup Docs",
    command: str = "echo backup",
    schedule: str = "0 2 * * *",
    file_path: Path | None = None,
    heading_line: int = 0,
    **kwargs,
) -> Task:
    from obs_tasks.models import slugify

    return Task(
        id=slugify(title),
        title=title,
        command=command,
        schedule=schedule,
        file_path=file_path,
        heading_line=heading_line,
        **kwargs,
    )


def _make_result(
    task_id: str = "backup-docs",
    success: bool = True,
    stdout: str = "Done",
    stderr: str = "",
    exit_code: int = 0,
    duration: float = 2.5,
    error_message: str | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        task_id=task_id,
        success=success,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        started_at=datetime(2025, 1, 15, 10, 30, 0),
        finished_at=datetime(2025, 1, 15, 10, 30, 2),
        duration=duration,
        error_message=error_message,
    )


# ---------------------------------------------------------------------------
# build_current_state_lines
# ---------------------------------------------------------------------------


class TestBuildCurrentStateLines:
    def test_success_state(self) -> None:
        lines = build_current_state_lines(
            status=TaskStatus.SUCCESS,
            last_run=datetime(2025, 1, 15, 10, 30, 0),
            next_run=datetime(2025, 1, 16, 2, 0, 0),
            duration=45.2,
            result_summary="Backed up 245 pages",
        )
        assert lines[0] == "#### Current State"
        assert "✅ Success" in lines[1]
        assert "2025-01-15 10:30:00" in lines[2]
        assert "2025-01-16 02:00:00" in lines[3]
        assert "45.2s" in lines[4]
        assert "Backed up 245 pages" in lines[5]

    def test_failed_state(self) -> None:
        lines = build_current_state_lines(
            status=TaskStatus.FAILED,
            last_run=datetime(2025, 1, 15, 10, 30, 0),
            next_run=None,
            duration=1.0,
            result_summary="Connection refused",
        )
        assert "❌ Failed" in lines[1]
        assert "Connection refused" in lines[5]

    def test_never_run_state(self) -> None:
        lines = build_current_state_lines(
            status=TaskStatus.NEVER_RUN,
            last_run=None,
            next_run=None,
            duration=None,
            result_summary=None,
        )
        assert "Never run" in lines[1]
        assert "- " in lines[2]  # "-" placeholder for Last Run
        assert "- " in lines[4]  # "-" placeholder for Duration


# ---------------------------------------------------------------------------
# build_statistics_lines
# ---------------------------------------------------------------------------


class TestBuildStatisticsLines:
    def test_with_failures(self) -> None:
        lines = build_statistics_lines(
            total_runs=47,
            successful_runs=46,
            failed_runs=1,
            last_failure=datetime(2024, 11, 15, 2, 0, 0),
        )
        assert lines[0] == "#### Statistics"
        assert "47" in lines[1]
        assert "46" in lines[2]
        assert "1" in lines[3]
        assert "2024-11-15 02:00:00" in lines[4]

    def test_no_failures(self) -> None:
        lines = build_statistics_lines(
            total_runs=10,
            successful_runs=10,
            failed_runs=0,
            last_failure=None,
        )
        assert "0" in lines[3]
        assert "- Last Failure: -" == lines[4]


# ---------------------------------------------------------------------------
# _find_section_range
# ---------------------------------------------------------------------------


class TestFindSectionRange:
    def test_finds_existing_section(self) -> None:
        lines = [
            "### My Task",
            "- Command: `echo hi`",
            "",
            "#### Current State",
            "- Status: Success",
            "- Last Run: 2025-01-01 00:00:00",
            "",
            "#### Statistics",
            "- Total Runs: 5",
        ]
        r = _find_section_range(lines, "Current State")
        assert r == (3, 7)

    def test_section_to_end_of_file(self) -> None:
        lines = [
            "#### Statistics",
            "- Total Runs: 5",
            "- Successful: 5",
        ]
        r = _find_section_range(lines, "Statistics")
        assert r == (0, 3)

    def test_section_not_found(self) -> None:
        lines = [
            "### My Task",
            "- Command: `echo hi`",
        ]
        r = _find_section_range(lines, "Current State")
        assert r is None

    def test_stops_at_hr(self) -> None:
        lines = [
            "#### Current State",
            "- Status: Success",
            "---",
            "## Next Section",
        ]
        r = _find_section_range(lines, "Current State")
        assert r == (0, 2)

    def test_stops_at_detailed_output_link(self) -> None:
        lines = [
            "#### Statistics",
            "- Total Runs: 5",
            "",
            "**Detailed Output:** [[Reports/2025-01-15-task]]",
        ]
        r = _find_section_range(lines, "Statistics")
        assert r == (0, 3)

    def test_respects_search_bounds(self) -> None:
        lines = [
            "#### Current State",
            "- Status: Success of other task",
            "",
            "## My Task",
            "#### Current State",
            "- Status: Failed",
        ]
        r = _find_section_range(lines, "Current State", search_start=3, search_end=6)
        assert r == (4, 6)


# ---------------------------------------------------------------------------
# _find_task_block_range
# ---------------------------------------------------------------------------


class TestFindTaskBlockRange:
    def test_fast_path_heading_line(self) -> None:
        lines = [
            "# File Header",
            "",
            "## Backup Docs",
            "- Command: `echo backup`",
            "",
            "## Other Task",
        ]
        task = _make_task(title="Backup Docs", heading_line=2)
        r = _find_task_block_range(lines, task)
        assert r == (2, 5)

    def test_fallback_title_search(self) -> None:
        lines = [
            "# File Header",
            "",
            "## Backup Docs",
            "- Command: `echo backup`",
            "",
            "## Other Task",
        ]
        task = _make_task(title="Backup Docs", heading_line=99)  # Wrong line
        r = _find_task_block_range(lines, task)
        assert r == (2, 5)

    def test_block_to_eof(self) -> None:
        lines = [
            "## Only Task",
            "- Command: `echo`",
            "- Schedule: * * * * *",
        ]
        task = _make_task(title="Only Task", heading_line=0)
        r = _find_task_block_range(lines, task)
        assert r == (0, 3)

    def test_not_found(self) -> None:
        lines = [
            "## Something Else",
            "Some text",
        ]
        task = _make_task(title="Missing Task", heading_line=0)
        r = _find_task_block_range(lines, task)
        assert r is None


# ---------------------------------------------------------------------------
# _atomic_write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_creates_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        _atomic_write(f, "hello\n")
        assert f.read_text() == "hello\n"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        f = tmp_path / "sub" / "dir" / "file.md"
        _atomic_write(f, "content\n")
        assert f.exists()
        assert f.read_text() == "content\n"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("old\n")
        _atomic_write(f, "new\n")
        assert f.read_text() == "new\n"

    def test_no_temp_files_left(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        _atomic_write(f, "content\n")
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "test.md"


# ---------------------------------------------------------------------------
# update_task_state — success scenario
# ---------------------------------------------------------------------------


class TestUpdateTaskStateSuccess:
    def test_updates_existing_sections(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text(
            """\
## Backup Docs
- Command: `echo backup`
- Schedule: 0 2 * * *

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
            encoding="utf-8",
        )

        task = _make_task(file_path=f, heading_line=0)
        result = _make_result()
        update_task_state(task, result)

        content = f.read_text(encoding="utf-8")
        assert "✅ Success" in content
        assert "2025-01-15 10:30:00" in content
        assert "2.5s" in content
        assert "Done" in content  # result summary
        assert "Total Runs: 1" in content
        assert "Successful: 1" in content
        assert "Failed: 0" in content

    def test_preserves_command_and_schedule(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text(
            """\
## Backup Docs
- Command: `echo backup`
- Schedule: 0 2 * * *

#### Current State
- Status: Never run
""",
            encoding="utf-8",
        )
        task = _make_task(file_path=f, heading_line=0)
        result = _make_result()
        update_task_state(task, result)

        content = f.read_text(encoding="utf-8")
        assert "- Command: `echo backup`" in content
        assert "- Schedule: 0 2 * * *" in content

    def test_creates_sections_when_missing(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text(
            """\
## Backup Docs
- Command: `echo backup`
- Schedule: 0 2 * * *
""",
            encoding="utf-8",
        )
        task = _make_task(file_path=f, heading_line=0)
        result = _make_result()
        update_task_state(task, result)

        content = f.read_text(encoding="utf-8")
        assert "#### Current State" in content
        assert "#### Statistics" in content
        assert "✅ Success" in content
        assert "Total Runs: 1" in content


# ---------------------------------------------------------------------------
# update_task_state — failure scenario
# ---------------------------------------------------------------------------


class TestUpdateTaskStateFailure:
    def test_failure_updates_state(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text(
            """\
## Backup Docs
- Command: `echo backup`
- Schedule: 0 2 * * *

#### Current State
- Status: ✅ Success
- Last Run: 2025-01-14 10:00:00
- Next Run: 2025-01-15 02:00:00
- Duration: 1.0s
- Result: OK

#### Statistics
- Total Runs: 5
- Successful: 5
- Failed: 0
- Last Failure: -
""",
            encoding="utf-8",
        )
        task = _make_task(
            file_path=f,
            heading_line=0,
            total_runs=5,
            successful_runs=5,
            failed_runs=0,
        )
        result = _make_result(
            success=False,
            exit_code=1,
            stdout="",
            stderr="Connection refused",
            error_message="Connection refused",
        )
        update_task_state(task, result)

        content = f.read_text(encoding="utf-8")
        assert "❌ Failed" in content
        assert "Total Runs: 6" in content
        assert "Successful: 5" in content
        assert "Failed: 1" in content
        assert "Last Failure: 2025-01-15" in content

    def test_increments_statistics(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text(
            """\
## Backup Docs
- Command: `echo backup`
- Schedule: 0 2 * * *

#### Statistics
- Total Runs: 10
- Successful: 8
- Failed: 2
- Last Failure: 2024-12-01 00:00:00
""",
            encoding="utf-8",
        )
        task = _make_task(
            file_path=f,
            heading_line=0,
            total_runs=10,
            successful_runs=8,
            failed_runs=2,
            last_failure=datetime(2024, 12, 1),
        )
        result = _make_result(success=True)
        update_task_state(task, result)

        content = f.read_text(encoding="utf-8")
        assert "Total Runs: 11" in content
        assert "Successful: 9" in content
        assert "Failed: 2" in content


# ---------------------------------------------------------------------------
# update_task_state — multi-task file safety
# ---------------------------------------------------------------------------


class TestMultiTaskFileSafety:
    def test_only_target_task_is_modified(self, tmp_path: Path) -> None:
        f = tmp_path / "multi.md"
        f.write_text(
            """\
# Work Tasks

## Task Alpha
- Command: `echo alpha`
- Schedule: 0 1 * * *

#### Current State
- Status: Never run
- Last Run: -
- Next Run: -
- Duration: -
- Result: -

## Task Beta
- Command: `echo beta`
- Schedule: 0 2 * * *

#### Current State
- Status: ✅ Success
- Last Run: 2025-01-14 00:00:00
- Next Run: 2025-01-15 00:00:00
- Duration: 1.0s
- Result: Beta OK
""",
            encoding="utf-8",
        )
        # Update only Task Alpha
        task_a = _make_task(
            title="Task Alpha",
            command="echo alpha",
            file_path=f,
            heading_line=2,
        )
        result = _make_result(task_id="task-alpha", stdout="Alpha done")
        update_task_state(task_a, result)

        content = f.read_text(encoding="utf-8")
        # Alpha should be updated
        assert "Alpha done" in content
        # Beta should be unchanged
        assert "Beta OK" in content
        assert "- Command: `echo beta`" in content


# ---------------------------------------------------------------------------
# update_task_state — edge cases
# ---------------------------------------------------------------------------


class TestUpdateTaskStateEdgeCases:
    def test_missing_file_path(self) -> None:
        task = _make_task(file_path=None)
        result = _make_result()
        # Should not raise
        update_task_state(task, result)

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        task = _make_task(file_path=tmp_path / "gone.md")
        result = _make_result()
        # Should not raise
        update_task_state(task, result)

    def test_next_run_is_written(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text(
            """\
## Backup Docs
- Command: `echo backup`
- Schedule: 0 2 * * *
""",
            encoding="utf-8",
        )
        task = _make_task(file_path=f, heading_line=0)
        result = _make_result()
        next_run = datetime(2025, 1, 16, 2, 0, 0)
        update_task_state(task, result, next_run=next_run)

        content = f.read_text(encoding="utf-8")
        assert "2025-01-16 02:00:00" in content


# ---------------------------------------------------------------------------
# create_report
# ---------------------------------------------------------------------------


class TestCreateReport:
    def test_creates_report_file(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "Reports"
        task = _make_task(
            title="Backup Docs",
            command="echo backup",
            file_path=tmp_path / "Tasks" / "work.md",
        )
        result = _make_result(stdout="Backup complete\n245 files processed")

        path = create_report(task, result, reports_dir)

        assert path.exists()
        assert path.name == "2025-01-15-backup-docs.md"
        assert path.parent == reports_dir

    def test_report_contains_metadata(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "Reports"
        task = _make_task(
            file_path=tmp_path / "work.md",
        )
        result = _make_result()
        path = create_report(task, result, reports_dir)
        content = path.read_text(encoding="utf-8")

        assert "# Backup Docs - Execution Report" in content
        assert "**Executed:** 2025-01-15 10:30:00" in content
        assert "**Duration:** 2.5 seconds" in content
        assert "**Command:** `echo backup`" in content
        assert "**Exit Code:** 0" in content
        assert "✅ Success" in content

    def test_report_contains_output(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "Reports"
        task = _make_task(file_path=tmp_path / "work.md")
        result = _make_result(stdout="Line 1\nLine 2\nLine 3")
        path = create_report(task, result, reports_dir)
        content = path.read_text(encoding="utf-8")

        assert "Line 1\nLine 2\nLine 3" in content

    def test_report_contains_backlink(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "Reports"
        task = _make_task(file_path=tmp_path / "Tasks" / "work.md")
        result = _make_result()
        path = create_report(task, result, reports_dir)
        content = path.read_text(encoding="utf-8")

        assert "[[work]]" in content

    def test_failed_report(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "Reports"
        task = _make_task(file_path=tmp_path / "work.md")
        result = _make_result(
            success=False,
            exit_code=1,
            stdout="",
            stderr="Permission denied",
            error_message="Permission denied",
        )
        path = create_report(task, result, reports_dir)
        content = path.read_text(encoding="utf-8")

        assert "❌ Failed" in content
        assert "**Exit Code:** 1" in content
        assert "## Errors" in content
        assert "Permission denied" in content

    def test_no_stderr_section_when_empty(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "Reports"
        task = _make_task(file_path=tmp_path / "work.md")
        result = _make_result(stderr="")
        path = create_report(task, result, reports_dir)
        content = path.read_text(encoding="utf-8")

        assert "## Errors" not in content

    def test_report_ends_with_footer(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "Reports"
        task = _make_task(file_path=tmp_path / "work.md")
        result = _make_result()
        path = create_report(task, result, reports_dir)
        content = path.read_text(encoding="utf-8")

        assert "*Generated by Obsidian Task Automation*" in content

    def test_no_output_placeholder(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "Reports"
        task = _make_task(file_path=tmp_path / "work.md")
        result = _make_result(stdout="")
        path = create_report(task, result, reports_dir)
        content = path.read_text(encoding="utf-8")

        assert "(no output)" in content
