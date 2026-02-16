"""Tests for obs_tasks.state — minimalist state manager."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from obs_tasks.state import (
    STATE_FILENAME,
    _build_content,
    load_last_startup,
    save_last_startup,
)


# ---------------------------------------------------------------------------
# _build_content
# ---------------------------------------------------------------------------


class TestBuildContent:
    def test_contains_frontmatter(self) -> None:
        content = _build_content(datetime(2025, 1, 15, 10, 0, 0))
        assert content.startswith("---\n")
        assert "last_startup:" in content
        assert "2025-01-15T10:00:00" in content

    def test_contains_markdown_body(self) -> None:
        content = _build_content(datetime(2025, 1, 15, 10, 0, 0))
        assert "# Task Runner State" in content
        assert "**Last Startup:** 2025-01-15 10:00:00" in content
        assert "⚠️" in content


# ---------------------------------------------------------------------------
# save_last_startup
# ---------------------------------------------------------------------------


class TestSaveLastStartup:
    def test_creates_file(self, tmp_path: Path) -> None:
        ts = datetime(2025, 1, 15, 10, 30, 0)
        save_last_startup(tmp_path, ts)

        state_file = tmp_path / STATE_FILENAME
        assert state_file.exists()

    def test_file_content_is_valid(self, tmp_path: Path) -> None:
        ts = datetime(2025, 1, 15, 10, 30, 0)
        save_last_startup(tmp_path, ts)

        content = (tmp_path / STATE_FILENAME).read_text(encoding="utf-8")
        assert "---" in content
        assert "2025-01-15T10:30:00" in content

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        save_last_startup(tmp_path, datetime(2025, 1, 1, 0, 0, 0))
        save_last_startup(tmp_path, datetime(2025, 6, 15, 12, 0, 0))

        content = (tmp_path / STATE_FILENAME).read_text(encoding="utf-8")
        assert "2025-06-15T12:00:00" in content
        assert "2025-01-01" not in content


# ---------------------------------------------------------------------------
# load_last_startup
# ---------------------------------------------------------------------------


class TestLoadLastStartup:
    def test_round_trip(self, tmp_path: Path) -> None:
        ts = datetime(2025, 1, 15, 10, 30, 0)
        save_last_startup(tmp_path, ts)
        loaded = load_last_startup(tmp_path)
        assert loaded == ts

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert load_last_startup(tmp_path) is None

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / STATE_FILENAME).write_text("", encoding="utf-8")
        assert load_last_startup(tmp_path) is None

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / STATE_FILENAME).write_text(
            "# Just markdown\nNo frontmatter here.\n",
            encoding="utf-8",
        )
        assert load_last_startup(tmp_path) is None

    def test_invalid_yaml_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / STATE_FILENAME).write_text(
            "---\n[invalid yaml\n---\n",
            encoding="utf-8",
        )
        assert load_last_startup(tmp_path) is None

    def test_missing_field_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / STATE_FILENAME).write_text(
            "---\nsome_other_key: 42\n---\n",
            encoding="utf-8",
        )
        assert load_last_startup(tmp_path) is None

    def test_invalid_datetime_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / STATE_FILENAME).write_text(
            "---\nlast_startup: not-a-date\n---\n",
            encoding="utf-8",
        )
        assert load_last_startup(tmp_path) is None

    def test_multiple_save_load_cycles(self, tmp_path: Path) -> None:
        for day in [1, 5, 10, 20]:
            ts = datetime(2025, 3, day, 8, 0, 0)
            save_last_startup(tmp_path, ts)
            assert load_last_startup(tmp_path) == ts
