"""Tests for models and config."""

from datetime import datetime
from pathlib import Path

import pytest

from obs_tasks.config import Config
from obs_tasks.models import (
    ExecutionResult,
    SystemState,
    Task,
    TaskStatus,
    slugify,
)


# --- TaskStatus ---


class TestTaskStatus:
    def test_values(self):
        assert TaskStatus.NEVER_RUN == "never_run"
        assert TaskStatus.SUCCESS == "success"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.RUNNING == "running"

    def test_is_string(self):
        assert isinstance(TaskStatus.SUCCESS, str)


# --- slugify ---


class TestSlugify:
    def test_basic(self):
        assert slugify("Backup Photos") == "backup-photos"

    def test_special_chars(self):
        assert slugify("Hello, World! (test)") == "hello-world-test"

    def test_multiple_spaces(self):
        assert slugify("lots   of   spaces") == "lots-of-spaces"

    def test_leading_trailing_spaces(self):
        assert slugify("  trimmed  ") == "trimmed"

    def test_hyphens_preserved(self):
        assert slugify("already-hyphenated") == "already-hyphenated"

    def test_empty_string(self):
        assert slugify("") == ""

    def test_only_special_chars(self):
        assert slugify("!!!") == ""

    def test_numbers(self):
        assert slugify("Task 42 v2") == "task-42-v2"


# --- Task ---


class TestTask:
    def test_required_fields(self):
        task = Task(id="test", title="Test", command="echo hi", schedule="0 * * * *")
        assert task.id == "test"
        assert task.command == "echo hi"

    def test_defaults(self):
        task = Task(id="t", title="T", command="cmd", schedule="* * * * *")
        assert task.status == TaskStatus.NEVER_RUN
        assert task.last_run is None
        assert task.next_run is None
        assert task.duration is None
        assert task.result_summary is None
        assert task.total_runs == 0
        assert task.successful_runs == 0
        assert task.failed_runs == 0
        assert task.last_failure is None
        assert task.file_path is None
        assert task.heading_line == 0


# --- ExecutionResult ---


class TestExecutionResult:
    def _make_result(self, **kwargs):
        defaults = dict(
            task_id="test",
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
            started_at=datetime(2024, 1, 1, 0, 0, 0),
            finished_at=datetime(2024, 1, 1, 0, 0, 1),
            duration=1.0,
        )
        defaults.update(kwargs)
        return ExecutionResult(**defaults)

    def test_summary_from_stdout(self):
        result = self._make_result(stdout="hello world")
        assert result.summary == "hello world"

    def test_summary_truncates(self):
        result = self._make_result(stdout="x" * 300)
        assert len(result.summary) == 200

    def test_summary_from_error_on_failure(self):
        result = self._make_result(
            success=False, stdout="", error_message="Timed out"
        )
        assert result.summary == "Timed out"

    def test_summary_from_stderr_when_no_stdout(self):
        result = self._make_result(stdout="", stderr="error output")
        assert result.summary == "error output"

    def test_summary_empty(self):
        result = self._make_result(stdout="", stderr="")
        assert result.summary == ""

    def test_summary_prefers_error_on_failure(self):
        result = self._make_result(
            success=False,
            stdout="some output",
            error_message="Command timed out",
        )
        assert result.summary == "Command timed out"


# --- SystemState ---


class TestSystemState:
    def test_defaults(self):
        state = SystemState()
        assert state.last_startup is None
        assert state.vault_path is None
        assert state.vault_version == 1
        assert state.total_executions == 0
        assert state.total_successful == 0
        assert state.total_failed == 0


# --- Config ---


class TestConfig:
    def test_paths(self, tmp_path):
        config = Config(vault_path=tmp_path / "vault")
        assert config.tasks_path == tmp_path / "vault" / "Tasks"
        assert config.reports_path == tmp_path / "vault" / "Reports"
        assert config.state_path == tmp_path / "vault" / "Task Runner.md"

    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "config.json"
        original = Config(vault_path=tmp_path / "vault", log_level="DEBUG")
        original.save(config_file)

        loaded = Config.load(config_file)
        assert loaded.vault_path == original.vault_path
        assert loaded.log_level == "DEBUG"
        assert loaded.check_interval == 60
        assert loaded.command_timeout == 300

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Config.load(tmp_path / "nope.json")

    def test_load_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json")
        with pytest.raises(ValueError, match="Invalid config JSON"):
            Config.load(bad_file)

    def test_load_missing_vault_path(self, tmp_path):
        incomplete = tmp_path / "incomplete.json"
        incomplete.write_text('{"log_level": "INFO"}')
        with pytest.raises(ValueError, match="vault_path"):
            Config.load(incomplete)

    def test_defaults(self):
        config = Config(vault_path=Path("/vault"))
        assert config.task_folder == "Tasks"
        assert config.reports_folder == "Reports"
        assert config.state_file == "Task Runner.md"
        assert config.check_interval == 60
        assert config.command_timeout == 300
        assert config.log_level == "INFO"
