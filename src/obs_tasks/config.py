"""Configuration management for obs-tasks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".obs-tasks"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "obs-tasks.log"
PID_FILE = CONFIG_DIR / "obs-tasks.pid"


@dataclass
class Config:
    """Application configuration."""

    vault_path: Path
    task_folder: str = "Tasks"
    reports_folder: str = "Reports"
    state_file: str = ".task-runner.md"
    check_interval: int = 60
    command_timeout: int = 300
    log_level: str = "INFO"

    @classmethod
    def load(cls, config_file: Path = CONFIG_FILE) -> Config:
        """Load config from JSON file.

        Raises FileNotFoundError if file doesn't exist.
        Raises ValueError if file contains invalid JSON or missing fields.
        """
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        text = config_file.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid config JSON: {e}") from e

        if "vault_path" not in data:
            raise ValueError("Config missing required field: vault_path")

        data["vault_path"] = Path(data["vault_path"])
        return cls(**data)

    def save(self, config_file: Path = CONFIG_FILE) -> None:
        """Persist config to JSON file. Creates parent directories if needed."""
        config_file.parent.mkdir(parents=True, exist_ok=True)
        data = {k: str(v) if isinstance(v, Path) else v for k, v in asdict(self).items()}
        config_file.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )

    @property
    def tasks_path(self) -> Path:
        return self.vault_path / self.task_folder

    @property
    def reports_path(self) -> Path:
        return self.vault_path / self.reports_folder

    @property
    def state_path(self) -> Path:
        return self.vault_path / self.state_file
