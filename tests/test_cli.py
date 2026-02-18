"""Tests for obs_tasks.cli — Click CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from obs_tasks.cli import cli
from obs_tasks.config import CONFIG_FILE


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Create a vault with a Tasks/ dir and a sample task.

    With one-file-per-task, the title is the filename stem: "Echo Task".
    """
    tasks_dir = tmp_path / "Tasks"
    tasks_dir.mkdir()
    reports_dir = tmp_path / "Reports"
    reports_dir.mkdir()
    task_file = tasks_dir / "Echo Task.md"
    task_file.write_text(
        """\
#### Task Definition
- Command: `echo hello from task`
- Schedule: 0 * * * *
""",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def config_file(tmp_path: Path, vault: Path, monkeypatch) -> Path:
    """Create a config file pointing to the vault and patch CONFIG_FILE."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg = cfg_dir / "config.json"
    cfg.write_text(
        json.dumps({"vault_path": str(vault)}),
        encoding="utf-8",
    )
    monkeypatch.setattr("obs_tasks.cli.CONFIG_FILE", cfg)
    monkeypatch.setattr("obs_tasks.config.CONFIG_FILE", cfg)
    return cfg


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "obs-tasks" in result.output


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_creates_dirs_and_config(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        vault = tmp_path / "my-vault"
        vault.mkdir()
        cfg = tmp_path / "cfg" / "config.json"
        monkeypatch.setattr("obs_tasks.cli.CONFIG_FILE", cfg)
        monkeypatch.setattr("obs_tasks.config.CONFIG_FILE", cfg)

        result = runner.invoke(cli, ["init", str(vault)])

        assert result.exit_code == 0
        assert "Initialised" in result.output
        assert (vault / "Tasks").is_dir()
        assert (vault / "Reports").is_dir()
        assert cfg.exists()

        # Config should contain vault_path
        data = json.loads(cfg.read_text())
        assert data["vault_path"] == str(vault)

    def test_init_nonexistent_path(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["init", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_init_idempotent(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        cfg = tmp_path / "cfg" / "config.json"
        monkeypatch.setattr("obs_tasks.cli.CONFIG_FILE", cfg)
        monkeypatch.setattr("obs_tasks.config.CONFIG_FILE", cfg)

        runner.invoke(cli, ["init", str(vault)])
        result = runner.invoke(cli, ["init", str(vault)])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestList:
    def test_list_shows_tasks(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "Echo Task" in result.output
        assert "1 task(s)" in result.output

    def test_list_verbose(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        result = runner.invoke(cli, ["list", "-v"])
        assert result.exit_code == 0
        assert "echo hello from task" in result.output
        assert "0 * * * *" in result.output

    def test_list_empty_vault(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        empty_vault = tmp_path / "empty"
        empty_vault.mkdir()
        (empty_vault / "Tasks").mkdir()

        cfg = tmp_path / "cfg" / "config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"vault_path": str(empty_vault)}))
        monkeypatch.setattr("obs_tasks.cli.CONFIG_FILE", cfg)
        monkeypatch.setattr("obs_tasks.config.CONFIG_FILE", cfg)

        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No tasks found" in result.output

    def test_list_without_init(
        self, runner: CliRunner, tmp_path: Path, monkeypatch
    ) -> None:
        cfg = tmp_path / "no-config" / "config.json"
        monkeypatch.setattr("obs_tasks.cli.CONFIG_FILE", cfg)
        monkeypatch.setattr("obs_tasks.config.CONFIG_FILE", cfg)

        result = runner.invoke(cli, ["list"])
        assert result.exit_code != 0
        assert "init" in result.output.lower() or "init" in (result.output + (result.output or "")).lower()


# ---------------------------------------------------------------------------
# run — by name
# ---------------------------------------------------------------------------


class TestRunByName:
    def test_run_by_exact_name(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        result = runner.invoke(cli, ["run", "Echo Task"])
        assert result.exit_code == 0
        assert "Running: Echo Task" in result.output
        assert "hello from task" in result.output
        assert "Success" in result.output

    def test_run_by_partial_name(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        result = runner.invoke(cli, ["run", "echo"])
        assert result.exit_code == 0
        assert "hello from task" in result.output

    def test_run_case_insensitive(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        result = runner.invoke(cli, ["run", "ECHO TASK"])
        assert result.exit_code == 0
        assert "Success" in result.output

    def test_run_no_match(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        result = runner.invoke(cli, ["run", "nonexistent"])
        assert result.exit_code != 0
        assert "No task matching" in result.output

    def test_run_updates_markdown(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        runner.invoke(cli, ["run", "Echo Task"])

        task_file = vault / "Tasks" / "Echo Task.md"
        content = task_file.read_text(encoding="utf-8")
        assert "#### Current State" in content
        assert "Success" in content
        assert "Total Runs: 1" in content

    def test_run_creates_report(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        runner.invoke(cli, ["run", "Echo Task"])

        reports = list((vault / "Reports").glob("*.md"))
        assert len(reports) == 1
        assert "echo-task" in reports[0].name


# ---------------------------------------------------------------------------
# run — by file (Shell Commands plugin mode)
# ---------------------------------------------------------------------------


class TestRunByFile:
    def test_run_by_file_path(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        task_file = vault / "Tasks" / "Echo Task.md"
        result = runner.invoke(cli, ["run", "--file", str(task_file)])
        assert result.exit_code == 0
        assert "hello from task" in result.output

    def test_run_by_file_short_flag(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        task_file = vault / "Tasks" / "Echo Task.md"
        result = runner.invoke(cli, ["run", "-f", str(task_file)])
        assert result.exit_code == 0

    def test_run_failed_command(
        self, runner: CliRunner, vault: Path, config_file: Path
    ) -> None:
        fail_file = vault / "Tasks" / "Failing Task.md"
        fail_file.write_text(
            """\
#### Task Definition
- Command: `exit 1`
- Schedule: 0 * * * *
""",
            encoding="utf-8",
        )
        result = runner.invoke(cli, ["run", "-f", str(fail_file)])
        assert result.exit_code == 0  # CLI exits 0, task itself failed
        assert "Failed" in result.output

    def test_run_no_args(
        self, runner: CliRunner, config_file: Path
    ) -> None:
        result = runner.invoke(cli, ["run"])
        assert result.exit_code != 0
        assert "Provide a task name or --file" in result.output
