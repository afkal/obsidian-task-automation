"""Command executor — runs shell commands and returns ExecutionResult.

Design rule: execute_task() NEVER raises. All errors are captured and
wrapped in an ExecutionResult with success=False.
"""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from obs_tasks.models import ExecutionResult

logger = logging.getLogger(__name__)


def execute_task(
    task_id: str,
    command: str,
    timeout: float = 300,
    working_dir: Path | None = None,
) -> ExecutionResult:
    """Run a shell command and return the result.

    Args:
        task_id: Identifier for the task (for logging and the result).
        command: Shell command to execute (passed to ``shell=True``).
        timeout: Maximum seconds before the command is killed.
        working_dir: Working directory for the subprocess. Defaults to
            the current directory if *None*.

    Returns:
        An :class:`ExecutionResult` — always, even on timeout or crash.
    """
    started_at = datetime.now()
    start_time = time.monotonic()

    cwd = str(working_dir) if working_dir else None

    try:
        logger.info("Executing task '%s': %s", task_id, command)
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        elapsed = time.monotonic() - start_time
        finished_at = datetime.now()

        success = proc.returncode == 0
        error_msg = None
        if not success:
            # Use stderr as error message for non-zero exit codes.
            error_msg = (
                proc.stderr.strip()
                if proc.stderr.strip()
                else f"Command exited with code {proc.returncode}"
            )

        result = ExecutionResult(
            task_id=task_id,
            success=success,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            started_at=started_at,
            finished_at=finished_at,
            duration=round(elapsed, 3),
            error_message=error_msg,
            timed_out=False,
        )

        if success:
            logger.info("Task '%s' succeeded in %.1fs", task_id, elapsed)
        else:
            logger.warning(
                "Task '%s' failed (exit %d) in %.1fs",
                task_id,
                proc.returncode,
                elapsed,
            )
        return result

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start_time
        finished_at = datetime.now()
        logger.error("Task '%s' timed out after %.1fs", task_id, elapsed)

        return ExecutionResult(
            task_id=task_id,
            success=False,
            exit_code=-1,
            stdout="",
            stderr="",
            started_at=started_at,
            finished_at=finished_at,
            duration=round(elapsed, 3),
            error_message=f"Command timed out after {timeout}s",
            timed_out=True,
        )

    except Exception as exc:
        elapsed = time.monotonic() - start_time
        finished_at = datetime.now()
        logger.error("Task '%s' raised an exception: %s", task_id, exc)

        return ExecutionResult(
            task_id=task_id,
            success=False,
            exit_code=-1,
            stdout="",
            stderr="",
            started_at=started_at,
            finished_at=finished_at,
            duration=round(elapsed, 3),
            error_message=str(exc),
            timed_out=False,
        )
