"""Integration tests — end-to-end pipeline for manual task execution.

Tests the full flow: parse → execute → write → re-parse, plus CLI
commands working together. These tests verify that all components
integrate correctly for the absolute MVP (manual triggering).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from obs_tasks.cli import cli
from obs_tasks.config import Config
from obs_tasks.executor import execute_task
from obs_tasks.models import TaskStatus
from obs_tasks.parser import parse_all_tasks, parse_file
from obs_tasks.writer import create_report, update_task_state


# ---------------------------------------------------------------------------
# Full pipeline: parse → execute → write → re-parse
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """Verify the core parse → execute → write → re-parse cycle."""

    def test_success_pipeline(self, sample_vault: Path) -> None:
        """Successful command updates state and statistics correctly."""
        task_file = sample_vault / "Tasks" / "Echo Hello.md"

        # 1. Parse
        tasks = parse_file(task_file)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.title == "Echo Hello"
        assert task.status == TaskStatus.NEVER_RUN
        assert task.total_runs == 0

        # 2. Execute
        result = execute_task(task.id, task.command, timeout=10)
        assert result.success
        assert "hello world" in result.stdout

        # 3. Write (create report first, then update state with report link)
        report = create_report(task, result, sample_vault / "Reports")
        update_task_state(task, result, report_path=report)
        assert report.exists()

        # 4. Re-parse and verify state
        tasks2 = parse_file(task_file)
        updated = tasks2[0]
        assert updated.status == TaskStatus.SUCCESS
        assert updated.total_runs == 1
        assert updated.successful_runs == 1
        assert updated.failed_runs == 0
        assert updated.last_run is not None
        assert updated.duration is not None
        assert updated.duration >= 0

        # 5. Verify Run History section with report link
        content = task_file.read_text(encoding="utf-8")
        assert "#### Run History" in content
        assert f"[[{report.stem}]]" in content

    def test_failure_pipeline(self, sample_vault: Path) -> None:
        """Failed command updates state with failure info."""
        task_file = sample_vault / "Tasks" / "Failing Task.md"

        # Parse
        tasks = parse_file(task_file)
        task = tasks[0]

        # Execute
        result = execute_task(task.id, task.command, timeout=10)
        assert not result.success

        # Write
        update_task_state(task, result)

        # Re-parse
        tasks2 = parse_file(task_file)
        updated = tasks2[0]
        assert updated.status == TaskStatus.FAILED
        assert updated.total_runs == 1
        assert updated.successful_runs == 0
        assert updated.failed_runs == 1
        assert updated.last_failure is not None

    def test_statistics_accumulate(self, sample_vault: Path) -> None:
        """Running multiple times increments statistics correctly."""
        task_file = sample_vault / "Tasks" / "Echo Hello.md"

        for i in range(3):
            tasks = parse_file(task_file)
            task = tasks[0]
            result = execute_task(task.id, task.command, timeout=10)
            update_task_state(task, result)

        # After 3 runs
        tasks = parse_file(task_file)
        final = tasks[0]
        assert final.total_runs == 3
        assert final.successful_runs == 3
        assert final.failed_runs == 0

        # Verify Run History has 3 rows
        content = task_file.read_text(encoding="utf-8")
        assert "#### Run History" in content
        # Count data rows (lines starting with "| 20")
        data_rows = [
            l for l in content.splitlines()
            if l.strip().startswith("| 20")
        ]
        assert len(data_rows) == 3

    def test_mixed_success_and_failure_stats(self, tmp_path: Path) -> None:
        """Statistics track both successes and failures correctly."""
        vault = tmp_path / "vault"
        tasks_dir = vault / "Tasks"
        reports_dir = vault / "Reports"
        tasks_dir.mkdir(parents=True)
        reports_dir.mkdir(parents=True)

        # A task with a conditional command: first run succeeds, then we change it
        task_file = tasks_dir / "Mixed Task.md"
        task_file.write_text(
            """\
#### Task Definition
- Command: `echo success`
- Schedule: 0 * * * *
""",
            encoding="utf-8",
        )

        # Run 1: success
        tasks = parse_file(task_file)
        task = tasks[0]
        result = execute_task(task.id, task.command, timeout=10)
        update_task_state(task, result)

        # Now change the command to a failing one
        content = task_file.read_text(encoding="utf-8")
        content = content.replace("`echo success`", "`exit 1`")
        task_file.write_text(content, encoding="utf-8")

        # Run 2: failure
        tasks = parse_file(task_file)
        task = tasks[0]
        result = execute_task(task.id, task.command, timeout=10)
        update_task_state(task, result)

        # Verify mixed stats
        tasks = parse_file(task_file)
        final = tasks[0]
        assert final.total_runs == 2
        assert final.successful_runs == 1
        assert final.failed_runs == 1
        assert final.last_failure is not None


# ---------------------------------------------------------------------------
# Command/Schedule preservation
# ---------------------------------------------------------------------------


class TestUserContentPreservation:
    """Writer must never modify Command, Schedule, or user notes."""

    def test_command_and_schedule_survive_multiple_cycles(
        self, sample_vault: Path
    ) -> None:
        """Command and Schedule lines are identical after multiple runs."""
        task_file = sample_vault / "Tasks" / "Echo Hello.md"
        original_cmd = "echo hello world"
        original_schedule = "0 * * * *"

        for _ in range(3):
            tasks = parse_file(task_file)
            task = tasks[0]
            assert task.command == original_cmd
            assert task.schedule == original_schedule

            result = execute_task(task.id, task.command, timeout=10)
            update_task_state(task, result)

        # Final check
        tasks = parse_file(task_file)
        assert tasks[0].command == original_cmd
        assert tasks[0].schedule == original_schedule

    def test_user_notes_preserved(self, tmp_path: Path) -> None:
        """Custom user notes outside managed sections survive writes."""
        vault = tmp_path / "vault"
        tasks_dir = vault / "Tasks"
        reports_dir = vault / "Reports"
        tasks_dir.mkdir(parents=True)
        reports_dir.mkdir(parents=True)

        task_file = tasks_dir / "Noted Task.md"
        task_file.write_text(
            """\
#### Task Definition
- Command: `echo test`
- Schedule: 0 * * * *

#### Notes
This is my personal note about this task.
It should not be touched by the writer.
""",
            encoding="utf-8",
        )

        # Execute and write
        tasks = parse_file(task_file)
        task = tasks[0]
        result = execute_task(task.id, task.command, timeout=10)
        update_task_state(task, result)

        # Check notes are preserved
        content = task_file.read_text(encoding="utf-8")
        assert "#### Notes" in content
        assert "personal note about this task" in content
        assert "should not be touched" in content


# ---------------------------------------------------------------------------
# Multiple tasks in vault
# ---------------------------------------------------------------------------


class TestMultipleTasks:
    """Multiple tasks don't interfere with each other."""

    def test_sequential_execution_no_interference(
        self, sample_vault: Path
    ) -> None:
        """Running two different tasks doesn't corrupt either file."""
        echo_file = sample_vault / "Tasks" / "Echo Hello.md"
        fail_file = sample_vault / "Tasks" / "Failing Task.md"

        # Run echo task
        tasks = parse_file(echo_file)
        echo_task = tasks[0]
        result1 = execute_task(echo_task.id, echo_task.command, timeout=10)
        update_task_state(echo_task, result1)

        # Run failing task
        tasks = parse_file(fail_file)
        fail_task = tasks[0]
        result2 = execute_task(fail_task.id, fail_task.command, timeout=10)
        update_task_state(fail_task, result2)

        # Verify echo task is still correct
        tasks = parse_file(echo_file)
        assert tasks[0].status == TaskStatus.SUCCESS
        assert tasks[0].total_runs == 1

        # Verify failing task is correct
        tasks = parse_file(fail_file)
        assert tasks[0].status == TaskStatus.FAILED
        assert tasks[0].total_runs == 1

    def test_parse_all_finds_both(self, sample_vault: Path) -> None:
        """parse_all_tasks discovers all task files in the vault."""
        tasks = parse_all_tasks(sample_vault, "Tasks")
        titles = {t.title for t in tasks}
        assert "Echo Hello" in titles
        assert "Failing Task" in titles


# ---------------------------------------------------------------------------
# Report files
# ---------------------------------------------------------------------------


class TestReportFiles:
    """Report creation and content verification."""

    def test_report_has_correct_content(self, sample_vault: Path) -> None:
        """Report file contains command, output, and backlink."""
        task_file = sample_vault / "Tasks" / "Echo Hello.md"
        reports_dir = sample_vault / "Reports"

        tasks = parse_file(task_file)
        task = tasks[0]
        result = execute_task(task.id, task.command, timeout=10)
        report_path = create_report(task, result, reports_dir)

        content = report_path.read_text(encoding="utf-8")
        assert "Echo Hello" in content
        assert "echo hello world" in content
        assert "hello world" in content
        assert "[[Echo Hello]]" in content
        assert "**Exit Code:** 0" in content

    def test_report_filename_format(self, sample_vault: Path) -> None:
        """Report filename has timestamp and slug."""
        task_file = sample_vault / "Tasks" / "Echo Hello.md"
        reports_dir = sample_vault / "Reports"

        tasks = parse_file(task_file)
        task = tasks[0]
        result = execute_task(task.id, task.command, timeout=10)
        report_path = create_report(task, result, reports_dir)

        # Format: YYYY-MM-DD-HHMMSS-slug.md
        name = report_path.name
        assert name.endswith("-echo-hello.md")
        # Date prefix like 2025-01-15-143022
        assert len(name.split("-")) >= 5

    def test_multiple_reports_no_overwrite(
        self, sample_vault: Path
    ) -> None:
        """Two runs at different seconds create two separate report files."""
        import time

        task_file = sample_vault / "Tasks" / "Echo Hello.md"
        reports_dir = sample_vault / "Reports"

        tasks = parse_file(task_file)
        task = tasks[0]
        result1 = execute_task(task.id, task.command, timeout=10)
        create_report(task, result1, reports_dir)

        # Wait 1 second so the timestamp differs
        time.sleep(1)

        tasks = parse_file(task_file)
        task = tasks[0]
        result2 = execute_task(task.id, task.command, timeout=10)
        create_report(task, result2, reports_dir)

        reports = list(reports_dir.glob("*.md"))
        assert len(reports) == 2


# ---------------------------------------------------------------------------
# CLI end-to-end
# ---------------------------------------------------------------------------


class TestCLIEndToEnd:
    """Full CLI workflow: init → list → run → list again."""

    def test_init_list_run_cycle(self, tmp_path: Path, monkeypatch) -> None:
        """Complete CLI workflow from scratch."""
        runner = CliRunner()
        vault = tmp_path / "my-vault"
        vault.mkdir()

        cfg_file = tmp_path / "cfg" / "config.json"
        monkeypatch.setattr("obs_tasks.cli.CONFIG_FILE", cfg_file)
        monkeypatch.setattr("obs_tasks.config.CONFIG_FILE", cfg_file)

        # 1. Init
        result = runner.invoke(cli, ["init", str(vault)])
        assert result.exit_code == 0
        assert (vault / "Tasks").is_dir()
        assert (vault / "Reports").is_dir()

        # 2. Create a task file manually (as user would in Obsidian)
        task_file = vault / "Tasks" / "Greet.md"
        task_file.write_text(
            """\
#### Task Definition
- Command: `echo hello from CLI test`
- Schedule: 0 9 * * *
""",
            encoding="utf-8",
        )

        # 3. List — should show the task as never run
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "Greet" in result.output
        assert "1 task(s)" in result.output

        # 4. Run the task
        result = runner.invoke(cli, ["run", "Greet"])
        assert result.exit_code == 0
        assert "hello from CLI test" in result.output
        assert "Success" in result.output

        # 5. List again — should show updated status
        result = runner.invoke(cli, ["list", "-v"])
        assert result.exit_code == 0
        assert "Greet" in result.output
        assert "Last Run:" in result.output

        # 6. Report should exist
        reports = list((vault / "Reports").glob("*.md"))
        assert len(reports) == 1

    def test_run_by_file_end_to_end(
        self, sample_vault: Path, sample_config: Config
    ) -> None:
        """Run via --file flag (Shell Commands plugin mode)."""
        runner = CliRunner()
        task_file = sample_vault / "Tasks" / "Echo Hello.md"

        result = runner.invoke(cli, ["run", "--file", str(task_file)])
        assert result.exit_code == 0
        assert "hello world" in result.output

        # Verify file was updated
        content = task_file.read_text(encoding="utf-8")
        assert "#### Current State" in content
        assert "Success" in content

        # Verify report created
        reports = list((sample_vault / "Reports").glob("*.md"))
        assert len(reports) == 1

    def test_run_then_run_again(
        self, sample_vault: Path, sample_config: Config
    ) -> None:
        """Two consecutive runs update statistics correctly."""
        runner = CliRunner()

        result1 = runner.invoke(cli, ["run", "Echo Hello"])
        assert result1.exit_code == 0

        result2 = runner.invoke(cli, ["run", "Echo Hello"])
        assert result2.exit_code == 0

        # Parse and verify
        task_file = sample_vault / "Tasks" / "Echo Hello.md"
        tasks = parse_file(task_file)
        assert tasks[0].total_runs == 2
        assert tasks[0].successful_runs == 2
