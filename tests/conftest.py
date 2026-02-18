"""Shared test fixtures for obs-tasks tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obs_tasks.config import Config


@pytest.fixture
def sample_vault(tmp_path: Path) -> Path:
    """Create a realistic vault with Tasks/ and Reports/ directories.

    Contains two task files with different commands:
    - "Echo Hello.md" — always succeeds
    - "Failing Task.md" — always fails (exit 1)
    """
    vault = tmp_path / "vault"
    tasks = vault / "Tasks"
    reports = vault / "Reports"
    tasks.mkdir(parents=True)
    reports.mkdir(parents=True)

    (tasks / "Echo Hello.md").write_text(
        """\
#### Task Definition
- Command: `echo hello world`
- Schedule: 0 * * * *
""",
        encoding="utf-8",
    )

    (tasks / "Failing Task.md").write_text(
        """\
#### Task Definition
- Command: `exit 1`
- Schedule: 0 2 * * *
""",
        encoding="utf-8",
    )

    return vault


@pytest.fixture
def sample_config(sample_vault: Path, tmp_path: Path, monkeypatch) -> Config:
    """Create a Config pointing to sample_vault and patch CONFIG_FILE."""
    config = Config(vault_path=sample_vault)

    cfg_file = tmp_path / "cfg" / "config.json"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    config.save(cfg_file)

    monkeypatch.setattr("obs_tasks.cli.CONFIG_FILE", cfg_file)
    monkeypatch.setattr("obs_tasks.config.CONFIG_FILE", cfg_file)

    return config
