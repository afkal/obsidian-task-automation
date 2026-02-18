"""Tests for obs_tasks.writer — Markdown state updates and report creation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from obs_tasks.models import ExecutionResult, Task, TaskStatus
from obs_tasks.writer import (
    MAX_HISTORY_ROWS,
    _atomic_write,
    _find_section_range,
    _find_task_block_range,
    _parse_history_rows,
    build_current_state_lines,
    build_run_history_lines,
    build_statistics_lines,
    create_report,
    update_task_state,
)

# Note: With one-file-per-task design, _find_task_block_range always
# returns (0, len(lines)) — the entire file is the task block.


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
    """With one-file-per-task, the block is always the entire file."""

    def test_whole_file_is_block(self) -> None:
        lines = [
            "## Backup Docs",
            "- Command: `echo backup`",
            "- Schedule: 0 2 * * *",
            "",
            "#### Current State",
            "- Status: Never run",
        ]
        task = _make_task(title="Backup Docs", heading_line=0)
        r = _find_task_block_range(lines, task)
        assert r == (0, 6)

    def test_empty_file(self) -> None:
        lines: list[str] = []
        task = _make_task(title="Empty", heading_line=0)
        r = _find_task_block_range(lines, task)
        assert r == (0, 0)

    def test_single_line(self) -> None:
        lines = ["- Command: `echo hi`"]
        task = _make_task(heading_line=0)
        r = _find_task_block_range(lines, task)
        assert r == (0, 1)


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
#### Task Definition
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
#### Task Definition
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
#### Task Definition
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
#### Task Definition
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
#### Task Definition
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


class TestUpdatePreservesUserContent:
    """With one-file-per-task, updates should not clobber user content."""

    def test_preserves_notes_and_purpose(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text(
            """\
#### Task Definition
- Command: `echo backup`
- Schedule: 0 2 * * *

#### Current State
- Status: Never run
- Last Run: -
- Next Run: -
- Duration: -
- Result: -

#### Notes
- Requires VPN connection
- Runs on the server
""",
            encoding="utf-8",
        )
        task = _make_task(file_path=f, heading_line=0)
        result = _make_result()
        update_task_state(task, result)

        content = f.read_text(encoding="utf-8")
        # User content preserved
        assert "#### Notes" in content
        assert "Requires VPN connection" in content
        # Task definition preserved
        assert "- Command: `echo backup`" in content
        assert "- Schedule: 0 2 * * *" in content
        # State updated
        assert "✅ Success" in content


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
#### Task Definition
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
        assert path.name == "2025-01-15-103000-backup-docs.md"
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


# ---------------------------------------------------------------------------
# _parse_history_rows
# ---------------------------------------------------------------------------


class TestParseHistoryRows:
    def test_extracts_data_rows(self) -> None:
        lines = [
            "#### Run History",
            "| Time | Status | Duration | Report |",
            "|------|--------|----------|--------|",
            "| 2025-01-15 10:30:00 | ✅ | 2.5s | [[report-1]] |",
            "| 2025-01-14 10:00:00 | ❌ | 1.0s | [[report-2]] |",
        ]
        rows = _parse_history_rows(lines, (0, 5))
        assert len(rows) == 2
        assert "2025-01-15" in rows[0]
        assert "2025-01-14" in rows[1]

    def test_empty_section(self) -> None:
        lines = [
            "#### Run History",
            "| Time | Status | Duration | Report |",
            "|------|--------|----------|--------|",
        ]
        rows = _parse_history_rows(lines, (0, 3))
        assert rows == []

    def test_skips_blank_lines(self) -> None:
        lines = [
            "#### Run History",
            "| Time | Status | Duration | Report |",
            "|------|--------|----------|--------|",
            "| 2025-01-15 10:30:00 | ✅ | 2.5s | [[r1]] |",
            "",
            "| 2025-01-14 10:00:00 | ❌ | 1.0s | [[r2]] |",
        ]
        rows = _parse_history_rows(lines, (0, 6))
        assert len(rows) == 2

    def test_handles_partial_range(self) -> None:
        """Only reads rows within the given range."""
        lines = [
            "some other content",
            "#### Run History",
            "| Time | Status | Duration | Report |",
            "|------|--------|----------|--------|",
            "| 2025-01-15 10:30:00 | ✅ | 2.5s | [[r1]] |",
            "#### Next Section",
        ]
        rows = _parse_history_rows(lines, (1, 5))
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# build_run_history_lines
# ---------------------------------------------------------------------------


class TestBuildRunHistoryLines:
    def test_first_run(self) -> None:
        """First execution creates a table with one data row."""
        result = _make_result()
        lines = build_run_history_lines([], result, "2025-01-15-103000-backup-docs")
        assert lines[0] == "#### Run History"
        assert "| Time |" in lines[1]
        assert lines[2].startswith("|---")
        assert len(lines) == 4  # header(3) + 1 data row
        assert "2025-01-15 10:30:00" in lines[3]
        assert "✅" in lines[3]
        assert "2.5s" in lines[3]
        assert "[[2025-01-15-103000-backup-docs]]" in lines[3]

    def test_prepends_new_row(self) -> None:
        """New row appears before existing rows."""
        existing = ["| 2025-01-14 10:00:00 | ✅ | 1.0s | [[old-report]] |"]
        result = _make_result()
        lines = build_run_history_lines(
            existing, result, "2025-01-15-103000-backup-docs"
        )
        # 3 header lines + 2 data rows
        assert len(lines) == 5
        # New row first (after header)
        assert "2025-01-15 10:30:00" in lines[3]
        # Old row second
        assert "2025-01-14 10:00:00" in lines[4]

    def test_truncates_to_max_rows(self) -> None:
        """Table never exceeds MAX_HISTORY_ROWS data rows."""
        existing = [
            f"| 2025-01-{i:02d} 00:00:00 | ✅ | 1.0s | [[r{i}]] |"
            for i in range(1, MAX_HISTORY_ROWS + 5)  # 24 rows
        ]
        result = _make_result()
        lines = build_run_history_lines(existing, result, "new-report")
        data_rows = [l for l in lines if l.startswith("|") and not l.startswith("|---") and "Time" not in l]
        assert len(data_rows) == MAX_HISTORY_ROWS

    def test_failure_emoji(self) -> None:
        """Failed execution shows ❌ emoji."""
        result = _make_result(success=False, exit_code=1)
        lines = build_run_history_lines([], result, "report")
        assert "❌" in lines[3]

    def test_without_report_name(self) -> None:
        """When no report is provided, shows '-' instead of link."""
        result = _make_result()
        lines = build_run_history_lines([], result, None)
        # Last column should be "-"
        assert "| - |" in lines[3]

    def test_duration_formatting(self) -> None:
        """Duration uses the same format as Current State."""
        result = _make_result(duration=123.456)
        lines = build_run_history_lines([], result, None)
        assert "123.5s" in lines[3]


# ---------------------------------------------------------------------------
# update_task_state — Run History integration
# ---------------------------------------------------------------------------


class TestUpdateTaskStateRunHistory:
    def test_creates_run_history_section(self, tmp_path: Path) -> None:
        """Run History section is created on first execution."""
        f = tmp_path / "task.md"
        f.write_text(
            """\
#### Task Definition
- Command: `echo backup`
- Schedule: 0 2 * * *
""",
            encoding="utf-8",
        )
        task = _make_task(file_path=f)
        result = _make_result()
        report = tmp_path / "Reports" / "2025-01-15-103000-backup-docs.md"
        update_task_state(task, result, report_path=report)

        content = f.read_text(encoding="utf-8")
        assert "#### Run History" in content
        assert "| Time |" in content
        assert "2025-01-15 10:30:00" in content
        assert "[[2025-01-15-103000-backup-docs]]" in content

    def test_accumulates_history_rows(self, tmp_path: Path) -> None:
        """Multiple executions add rows to the table."""
        f = tmp_path / "task.md"
        f.write_text(
            """\
#### Task Definition
- Command: `echo backup`
- Schedule: 0 2 * * *
""",
            encoding="utf-8",
        )
        # Run 1
        task = _make_task(file_path=f)
        result1 = _make_result(
            duration=1.0,
            stdout="run1",
        )
        result1 = ExecutionResult(
            task_id="backup-docs",
            success=True,
            exit_code=0,
            stdout="run1",
            stderr="",
            started_at=datetime(2025, 1, 14, 10, 0, 0),
            finished_at=datetime(2025, 1, 14, 10, 0, 1),
            duration=1.0,
        )
        report1 = tmp_path / "Reports" / "2025-01-14-100000-backup-docs.md"
        update_task_state(task, result1, report_path=report1)

        # Run 2
        from obs_tasks.parser import parse_file

        tasks = parse_file(f)
        task2 = tasks[0]
        result2 = ExecutionResult(
            task_id="backup-docs",
            success=True,
            exit_code=0,
            stdout="run2",
            stderr="",
            started_at=datetime(2025, 1, 15, 10, 0, 0),
            finished_at=datetime(2025, 1, 15, 10, 0, 2),
            duration=2.0,
        )
        report2 = tmp_path / "Reports" / "2025-01-15-100000-backup-docs.md"
        update_task_state(task2, result2, report_path=report2)

        content = f.read_text(encoding="utf-8")
        # Both runs should appear
        assert "2025-01-15 10:00:00" in content
        assert "2025-01-14 10:00:00" in content
        # Newer run should be first (closer to header)
        idx_new = content.index("2025-01-15 10:00:00")
        idx_old = content.index("2025-01-14 10:00:00")
        assert idx_new < idx_old

    def test_without_report_path(self, tmp_path: Path) -> None:
        """Run History works without a report_path (shows '-')."""
        f = tmp_path / "task.md"
        f.write_text(
            """\
#### Task Definition
- Command: `echo test`
- Schedule: 0 * * * *
""",
            encoding="utf-8",
        )
        task = _make_task(file_path=f)
        result = _make_result()
        update_task_state(task, result)  # no report_path

        content = f.read_text(encoding="utf-8")
        assert "#### Run History" in content
        assert "| - |" in content  # no report link

    def test_max_rows_enforced(self, tmp_path: Path) -> None:
        """Run History table doesn't grow beyond MAX_HISTORY_ROWS."""
        f = tmp_path / "task.md"
        # Build a file with an existing Run History at max capacity
        history_rows = []
        for i in range(MAX_HISTORY_ROWS):
            history_rows.append(
                f"| 2025-01-{i+1:02d} 00:00:00 | ✅ | 1.0s | [[r{i}]] |"
            )

        content = """\
#### Task Definition
- Command: `echo test`
- Schedule: 0 * * * *

#### Run History
| Time | Status | Duration | Report |
|------|--------|----------|--------|
"""
        content += "\n".join(history_rows) + "\n"
        f.write_text(content, encoding="utf-8")

        task = _make_task(file_path=f)
        result = _make_result()
        update_task_state(task, result, report_path=tmp_path / "Reports" / "new.md")

        updated = f.read_text(encoding="utf-8")
        # Count data rows (lines starting with "| 20")
        data_rows = [
            l for l in updated.splitlines()
            if l.strip().startswith("| 20")
        ]
        assert len(data_rows) == MAX_HISTORY_ROWS

    def test_preserves_all_other_sections(self, tmp_path: Path) -> None:
        """Run History addition doesn't disturb other sections."""
        f = tmp_path / "task.md"
        f.write_text(
            """\
#### Task Definition
- Command: `echo backup`
- Schedule: 0 2 * * *

#### Notes
Important user notes here.
""",
            encoding="utf-8",
        )
        task = _make_task(file_path=f)
        result = _make_result()
        update_task_state(task, result)

        content = f.read_text(encoding="utf-8")
        assert "#### Notes" in content
        assert "Important user notes here." in content
        assert "#### Current State" in content
        assert "#### Statistics" in content
        assert "#### Run History" in content
