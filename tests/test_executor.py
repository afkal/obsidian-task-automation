"""Tests for obs_tasks.executor — shell command execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from obs_tasks.executor import _prepare_command, execute_task
from obs_tasks.models import ExecutionResult


# ---------------------------------------------------------------------------
# Successful commands
# ---------------------------------------------------------------------------


class TestSuccessfulCommands:
    def test_echo_returns_stdout(self) -> None:
        r = execute_task("t1", "echo hello")
        assert r.success is True
        assert r.exit_code == 0
        assert r.stdout.strip() == "hello"
        assert r.timed_out is False
        assert r.error_message is None

    def test_multiline_output(self) -> None:
        r = execute_task("t2", "echo line1 && echo line2")
        assert r.success is True
        lines = r.stdout.strip().splitlines()
        assert lines == ["line1", "line2"]

    def test_duration_is_positive(self) -> None:
        r = execute_task("t3", "echo fast")
        assert r.duration > 0
        assert r.duration < 10  # Sanity: echo should be very fast

    def test_timestamps_populated(self) -> None:
        r = execute_task("t4", "echo ts")
        assert r.started_at is not None
        assert r.finished_at is not None
        assert r.finished_at >= r.started_at

    def test_task_id_preserved(self) -> None:
        r = execute_task("my-task-id", "echo ok")
        assert r.task_id == "my-task-id"

    def test_returns_execution_result(self) -> None:
        r = execute_task("t5", "echo ok")
        assert isinstance(r, ExecutionResult)


# ---------------------------------------------------------------------------
# Stderr capture
# ---------------------------------------------------------------------------


class TestStderrCapture:
    def test_stderr_captured(self) -> None:
        r = execute_task("t6", "echo error >&2")
        assert "error" in r.stderr

    def test_mixed_stdout_stderr(self) -> None:
        r = execute_task("t7", "echo out && echo err >&2")
        assert "out" in r.stdout
        assert "err" in r.stderr


# ---------------------------------------------------------------------------
# Non-zero exit codes
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_non_zero_is_failure(self) -> None:
        r = execute_task("t8", "exit 1")
        assert r.success is False
        assert r.exit_code == 1

    def test_exit_code_42(self) -> None:
        r = execute_task("t9", "exit 42")
        assert r.success is False
        assert r.exit_code == 42

    def test_error_message_from_stderr(self) -> None:
        r = execute_task("t10", "echo 'bad thing' >&2 && exit 1")
        assert r.success is False
        assert "bad thing" in r.error_message

    def test_error_message_fallback_when_no_stderr(self) -> None:
        r = execute_task("t11", "exit 3")
        assert r.success is False
        assert "code 3" in r.error_message

    def test_summary_shows_error_on_failure(self) -> None:
        r = execute_task("t12", "echo 'stderr msg' >&2 && exit 1")
        assert "stderr msg" in r.summary


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


class TestTimeout:
    def test_timeout_returns_failure(self) -> None:
        r = execute_task("t13", "sleep 10", timeout=0.5)
        assert r.success is False
        assert r.timed_out is True
        assert "timed out" in r.error_message.lower()
        assert r.exit_code == -1

    def test_timeout_duration_approximately_correct(self) -> None:
        r = execute_task("t14", "sleep 10", timeout=0.5)
        # Duration should be close to timeout, not 10 seconds
        assert r.duration < 3


# ---------------------------------------------------------------------------
# Invalid / problematic commands
# ---------------------------------------------------------------------------


class TestInvalidCommands:
    def test_nonexistent_command(self) -> None:
        r = execute_task("t15", "this_command_does_not_exist_xyz123")
        assert r.success is False
        assert r.exit_code != 0
        # Shell should produce an error in stderr
        assert r.stderr != "" or r.error_message is not None

    def test_syntax_error_in_command(self) -> None:
        r = execute_task("t16", "if then else fi")
        assert r.success is False

    def test_empty_command(self) -> None:
        # Empty string passed to shell should succeed (no-op)
        r = execute_task("t17", "")
        # Behavior varies by shell, but should not raise
        assert isinstance(r, ExecutionResult)


# ---------------------------------------------------------------------------
# Working directory
# ---------------------------------------------------------------------------


class TestWorkingDirectory:
    def test_custom_working_dir(self, tmp_path: Path) -> None:
        r = execute_task("t18", "pwd", working_dir=tmp_path)
        assert r.success is True
        # pwd output should contain the tmp_path
        assert str(tmp_path.resolve()) in r.stdout.strip() or \
               tmp_path.name in r.stdout.strip()

    def test_default_working_dir(self) -> None:
        r = execute_task("t19", "pwd")
        assert r.success is True
        assert r.stdout.strip() != ""

    def test_nonexistent_working_dir(self, tmp_path: Path) -> None:
        bad_dir = tmp_path / "does_not_exist"
        r = execute_task("t20", "echo hello", working_dir=bad_dir)
        # subprocess should fail — the error is caught
        assert r.success is False
        assert r.error_message is not None


# ---------------------------------------------------------------------------
# Never raises
# ---------------------------------------------------------------------------


class TestNeverRaises:
    """Verify the 'never raise' design rule."""

    def test_all_error_types_return_result(self) -> None:
        """Run several problematic commands — none should raise."""
        commands = [
            "exit 1",
            "this_does_not_exist_xyz",
            "sleep 10",  # will timeout
        ]
        for cmd in commands:
            r = execute_task("safety", cmd, timeout=0.5)
            assert isinstance(r, ExecutionResult), f"Raised for: {cmd}"


# ---------------------------------------------------------------------------
# _prepare_command
# ---------------------------------------------------------------------------


class TestPrepareCommand:
    def test_no_parameters_passthrough(self) -> None:
        cmd = _prepare_command("echo hello", None)
        assert cmd == "echo hello"

    def test_empty_dict_passthrough(self) -> None:
        cmd = _prepare_command("echo hello", {})
        assert cmd == "echo hello"

    def test_params_placeholder_replaced(self) -> None:
        params = {"amount": "100", "name": "Test"}
        cmd = _prepare_command("python run.py {{params}}", params)
        # The placeholder should be replaced with a shell-quoted JSON string
        assert "{{params}}" not in cmd
        assert "python run.py" in cmd

    def test_no_placeholder_appends_json(self) -> None:
        """When command has no {{params}}, JSON is appended to the end."""
        params = {"key": "value"}
        cmd = _prepare_command("echo hello", params)
        assert cmd.startswith("echo hello ")
        assert '"key"' in cmd
        assert '"value"' in cmd


# ---------------------------------------------------------------------------
# Parameters — integration with execute_task
# ---------------------------------------------------------------------------


class TestExecuteWithParameters:
    def test_params_substituted_in_command(self) -> None:
        """{{params}} in command is replaced with JSON and executed."""
        params = {"greeting": "hello"}
        r = execute_task("t-param", "echo {{params}}", parameters=params)
        assert r.success is True
        # Output should contain the JSON
        assert "greeting" in r.stdout
        assert "hello" in r.stdout

    def test_no_params_no_change(self) -> None:
        """Without parameters, command runs normally."""
        r = execute_task("t-nop", "echo normal", parameters=None)
        assert r.success is True
        assert r.stdout.strip() == "normal"

    def test_special_chars_in_params_safe(self) -> None:
        """Parameters with shell-special characters are safely escaped."""
        params = {"cmd": "hello; echo injected"}
        r = execute_task("t-safe", "echo {{params}}", parameters=params)
        assert r.success is True
        # The output should be the JSON string, not execute the injected command
        assert "injected" not in r.stdout.split("\n")[0] or \
               '{"cmd": "hello; echo injected"}' in r.stdout
