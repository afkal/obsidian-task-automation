"""Core data models for Obsidian Task Automation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class TaskStatus(str, Enum):
    """Possible states for a task."""

    NEVER_RUN = "never_run"
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"


def slugify(title: str) -> str:
    """Convert a task title to a filesystem-safe identifier.

    >>> slugify("Backup Vaisala Documentation")
    'backup-vaisala-documentation'
    >>> slugify("  Hello, World! (test)  ")
    'hello-world-test'
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug.strip("-")


@dataclass
class Task:
    """A task parsed from an Obsidian markdown file."""

    # Identity
    id: str
    title: str

    # Definition (user-editable)
    command: str
    schedule: str

    # State (system-managed)
    status: TaskStatus = TaskStatus.NEVER_RUN
    last_run: datetime | None = None
    next_run: datetime | None = None
    duration: float | None = None
    result_summary: str | None = None

    # Statistics (system-managed)
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    last_failure: datetime | None = None

    # Source location (for writer)
    file_path: Path | None = None
    heading_line: int = 0


@dataclass
class ExecutionResult:
    """Result of executing a single task."""

    task_id: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime
    duration: float
    error_message: str | None = None
    timed_out: bool = False

    @property
    def summary(self) -> str:
        """First ~200 chars of output, or error message if failed."""
        if not self.success and self.error_message:
            text = self.error_message
        elif self.stdout:
            text = self.stdout
        elif self.stderr:
            text = self.stderr
        else:
            return ""
        return text[:200].strip()


@dataclass
class SystemState:
    """System-level state stored in .task-runner.md."""

    last_startup: datetime | None = None
    vault_path: Path | None = None
    vault_version: int = 1
    total_tasks: int = 0
    active_scheduled_tasks: int = 0
    total_executions: int = 0
    total_successful: int = 0
    total_failed: int = 0
