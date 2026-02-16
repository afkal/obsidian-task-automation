"""State manager — reads/writes Task Runner.md in the vault root.

Minimalist MVP version: stores only ``last_startup`` in YAML frontmatter.
The Markdown body is a short human-readable note visible in Obsidian.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import yaml

from obs_tasks.writer import _atomic_write

logger = logging.getLogger(__name__)

STATE_FILENAME = "Task Runner.md"


def _build_content(last_startup: datetime) -> str:
    """Build the full .task-runner.md content."""
    frontmatter = yaml.dump(
        {"last_startup": last_startup.isoformat()},
        default_flow_style=False,
    ).strip()

    return (
        f"---\n"
        f"{frontmatter}\n"
        f"---\n"
        f"\n"
        f"# Task Runner State\n"
        f"\n"
        f"**Last Startup:** {last_startup.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"\n"
        f"⚠️ This file is managed automatically. Manual edits may be overwritten.\n"
    )


def load_last_startup(vault_path: Path) -> datetime | None:
    """Read ``last_startup`` from the state file.

    Returns *None* if the file doesn't exist or can't be parsed.
    """
    state_file = vault_path / STATE_FILENAME
    if not state_file.exists():
        logger.debug("State file not found: %s", state_file)
        return None

    try:
        content = state_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read state file: %s", exc)
        return None

    # Extract YAML frontmatter between --- delimiters
    parts = content.split("---", 2)
    if len(parts) < 3:
        logger.warning("State file has no valid frontmatter")
        return None

    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML in state file: %s", exc)
        return None

    if not isinstance(data, dict) or "last_startup" not in data:
        logger.warning("State file missing last_startup field")
        return None

    raw = data["last_startup"]

    # yaml.safe_load may return a datetime directly for ISO strings
    if isinstance(raw, datetime):
        return raw

    try:
        return datetime.fromisoformat(str(raw))
    except (ValueError, TypeError) as exc:
        logger.warning("Invalid last_startup value: %s", exc)
        return None


def save_last_startup(vault_path: Path, timestamp: datetime) -> None:
    """Write ``last_startup`` to the state file (atomic write)."""
    state_file = vault_path / STATE_FILENAME
    content = _build_content(timestamp)
    _atomic_write(state_file, content)
    logger.info("Saved last_startup=%s to %s", timestamp, state_file)
