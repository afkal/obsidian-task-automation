# Obsidian Task Automation — MVP Implementation Plan

> This document is the implementation guide for AI coding agents (Claude Code).
> Read `docs/mvp-specification.md` first for full context.
> Human reviewer: use the checkboxes to track progress.

## Current Status

**MVP is complete.** All steps 1–9 are done. 232 tests, 98% coverage.

Additional features implemented beyond the original plan:
- **Run History** — `#### Run History` markdown table in task files with Obsidian `[[wiki-links]]` to reports (max 20 rows). Implemented in `writer.py`, tested in `test_writer.py`.
- **Parameters** — `#### Parameters` section in task files with `- Key: Value` pairs, passed as JSON via `{{params}}` placeholder. Parameters saved in reports for audit trail. Implemented in `parser.py`, `executor.py`, `writer.py`, `cli.py`.
- **Obsidian integration** — Shell Commands + Commander plugin setup documented in README.

**Next steps** are in the Post-MVP section below (scheduler, main loop). These are optional — the MVP is fully functional for manual execution.

## Project Summary

Python CLI tool that reads task definitions from Obsidian Markdown files, executes them manually via CLI or Obsidian Shell Commands plugin, and writes results back to Markdown. All state lives in the vault — no databases.

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| CLI framework | **Click** | Cleaner than argparse, good subcommand support |
| Packaging | **pyproject.toml** (PEP 621) | Modern Python standard |
| Cron parsing | **croniter** | Lightweight, handles full cron syntax |
| State storage | **Markdown + YAML frontmatter** | Consistent with "everything in vault" principle |
| Testing | **pytest, TDD-style** | Tests written alongside each component |
| Python | **3.13+** | Latest stable, modern type hints |

## Architecture Overview

```
Obsidian Vault (.md files)
    ↕ read/write
Python Task Runner
    ├─ parser.py      → reads .md → Task objects
    ├─ executor.py    → runs shell commands (subprocess)
    ├─ writer.py      → updates .md with results + creates reports
    ├─ state.py       → system state in .task-runner.md
    ├─ models.py      → dataclasses (Task, ExecutionResult, etc.)
    ├─ config.py      → Config dataclass, JSON persistence
    ├─ cli.py         → Click CLI (obs-tasks command)
    ├─ scheduler.py   → decides when to run (croniter + catch-up)  [post-MVP]
    └─ main.py        → TaskRunner service loop                    [post-MVP]
```

Package layout: `src/obs_tasks/`, entry point: `obs-tasks = "obs_tasks.cli:cli"`

## Key Design Rules

1. **All data in Markdown** — no JSON state files, no databases. Config is the only exception (`config.json` in project root).
2. **Atomic file writes** — always write to temp file then rename. Never leave a half-written .md file.
3. **One file per task** — each .md file in Tasks/ is one task. The task title comes from the filename (without .md). Headings inside the file are optional and ignored by the parser.
4. **Never modify user content** — writer updates only `#### Current State`, `#### Statistics`, and `#### Run History` sections. Task Definition and any user notes are preserved exactly.
5. **Recovery over precision** — on startup, compare `last_startup` from state file against each task's `next_run`. Any missed tasks get executed. Tasks that have never run execute immediately.
6. **Re-parse every tick** — the main loop re-reads all task files each cycle (every 60s). This picks up user edits without needing file watchers.
7. **Never raise from executor** — `execute_task()` always returns an `ExecutionResult`, even on timeout or crash.

---

## Implementation Steps

Work through these steps in order. Each step builds on the previous. Write tests alongside the code (TDD). Run `pytest` after each step to verify nothing is broken.

### MVP Scope

**Absolute MVP (Steps 1–9):** Manual task execution via CLI and Obsidian Shell Commands plugin. Parse → execute → write → report. No scheduling, no background service.

**Post-MVP:** Scheduled background execution (scheduler.py, main.py service loop, catch-up recovery).

---

### Step 1: Project Scaffolding

- [x] Create `pyproject.toml` with dependencies: click, pyyaml, python-dateutil, croniter. Dev deps: pytest, pytest-cov.
- [x] Create `.gitignore` (standard Python)
- [x] Create `src/obs_tasks/__init__.py` with `__version__ = "0.1.0"`
- [x] Create `src/obs_tasks/cli.py` with a placeholder Click group
- [x] Create `tests/__init__.py` and `tests/conftest.py` (empty)
- [x] Verify: `pip install -e ".[dev]"` succeeds, `pytest` runs, `obs-tasks --help` prints output

---

### Step 2: Data Models

- [x] `src/obs_tasks/models.py` — `TaskStatus` enum, `Task` dataclass, `ExecutionResult` dataclass, `SystemState` dataclass, `slugify()` helper
- [x] `src/obs_tasks/config.py` — `Config` dataclass with `load()`/`save()` for `~/.obs-tasks/config.json`
- [x] `tests/test_models.py` — test defaults, enum values, slugify edge cases, ExecutionResult.summary truncation, Config round-trip
- [x] Verify: all tests pass

Refer to `mvp-specification.md` lines 139–162 for the Task data model and lines 588–600 for Config fields.

---

### Step 3: Markdown Parser

This is the most complex component. Read `mvp-specification.md` lines 108–163 for the task markdown format, and lines 460–516 for realistic examples.

- [x] `src/obs_tasks/parser.py` — find task files, parse single file, parse all tasks
- [x] Support both format variants from the spec (direct `### Title` with fields, and `#### Task Definition` sub-headed)
- [x] Parse all fields: Command (from backticks), Schedule, Status (with emoji handling), Last Run, Next Run, Duration, Result, statistics counters
- [x] Handle missing/optional fields gracefully — set defaults, never crash
- [x] Track source file path and heading line number on each Task (needed by writer)
- [x] `tests/test_parser.py` — test simple task, sub-headed format, multiple tasks per file, minimal task (only Command+Schedule), malformed task (skip gracefully), emoji status, datetime parsing, duration parsing, file discovery
- [x] Verify: all tests pass

---

### Step 4: Command Executor

- [x] `src/obs_tasks/executor.py` — `execute_task()` that runs a shell command and returns `ExecutionResult`
- [x] Use `subprocess.run(shell=True, capture_output=True, text=True, timeout=...)`
- [x] Handle: successful commands, non-zero exit codes, timeouts, exceptions — never raise
- [x] `tests/test_executor.py` — test echo, stderr capture, exit codes, timeout, invalid commands, duration tracking, working directory
- [x] Verify: all tests pass

---

### Step 5: Markdown Writer

Second most complex component. The writer must surgically update specific sections without touching anything else.

- [x] `src/obs_tasks/writer.py` — update task state/statistics in source file, create report files
- [x] Find the task's section by heading line (fast path) with fallback to title search
- [x] Find and replace `#### Current State` and `#### Statistics` subsections; create them if missing
- [x] Create report files at `Reports/YYYY-MM-DD-task-slug.md` with full output, metadata, and Obsidian backlinks
- [x] Use atomic writes (temp file + rename) for all file operations
- [x] `tests/test_writer.py` — test state updates (success/failure), statistics increments, timestamp/duration formatting, Command/Schedule preservation, section creation when missing, report file creation, atomic write behavior, multi-task file safety
- [x] Verify: all tests pass

Refer to `mvp-specification.md` lines 306–341 for the exact section formats the writer should produce.

---

### Step 6: State Manager

- [x] `src/obs_tasks/state.py` — minimalist: `save_last_startup()` / `load_last_startup()` with `Task Runner.md` in vault root (YAML frontmatter)
- [x] `load()` returns None if file doesn't exist; `save()` uses atomic write
- [x] `tests/test_state.py` — test load/save round-trip, missing file, empty file, invalid YAML, missing field, invalid datetime, multiple cycles
- [x] Verify: all tests pass

Refer to `mvp-specification.md` lines 354–387 for the state file format.

---

### Step 7: CLI + Refactoring

CLI was prioritised before scheduler since manual triggering is the primary use case. Several architectural changes were made alongside:

- [x] `src/obs_tasks/cli.py` — full Click CLI: `init`, `list [--verbose]`, `run <name>` / `run --file <path>`
- [x] `run --file` mode for Obsidian Shell Commands plugin (`obs-tasks run --file "{{file_path:absolute}}"`)
- [x] Refactor parser: one file = one task, filename is task title (removed heading-based multi-task support)
- [x] Simplify writer: `_find_task_block_range()` returns entire file (no heading search needed)
- [x] Move config from `~/.obs-tasks/config.json` to project root (next to pyproject.toml), gitignored
- [x] Add timestamps to report filenames (`YYYY-MM-DD-HHMMSS-slug.md`) to prevent overwrites
- [x] Adopt `#### Task Definition` heading convention for Command/Schedule fields
- [x] `tests/test_cli.py` — 18 tests using Click's CliRunner
- [x] Verify: 166 tests pass

---

### Step 8: Integration Tests

- [x] Update `tests/conftest.py` with shared fixtures: `sample_vault` (tmp_path with realistic task files), `sample_config`
- [x] `tests/test_integration.py` — 14 end-to-end tests for the manual execution pipeline:
  - Full pipeline: parse → execute → write → re-parse → verify state updated
  - Failed task: verify failure status and statistics
  - Multiple tasks execute sequentially without interference
  - Command/Schedule lines survive multiple execution cycles
  - Report files are created correctly
  - Statistics accumulate over repeated executions
  - CLI init + list + run work end-to-end
- [x] Verify: 185 tests pass (unit + integration), 97% coverage

---

### Step 9: Polish

- [x] Improve error messages: clear guidance when vault not initialized, no tasks found, command failures
- [x] Write `README.md`: installation, quick start, task format reference, CLI commands, Obsidian Shell Commands setup, troubleshooting
- [x] Final pass: remove dead code, ensure consistent style
- [x] Final verify: `pytest --cov=obs_tasks` — 185 tests, 98% coverage

---

## Post-MVP: Scheduled Background Execution

> These steps add automatic scheduled execution. The absolute MVP works without them — manual triggering via CLI and Obsidian Shell Commands is fully functional.

### Post-MVP Step A: Scheduler

- [ ] `src/obs_tasks/scheduler.py` — scheduling logic using croniter
- [ ] `calculate_next_run()` — croniter-based next execution time
- [ ] `should_run()` — returns true if: never_run, or next_run <= now (but not if status is running)
- [ ] `check_for_catchup()` — **the recovery mechanism**: find tasks whose `next_run` falls between `last_startup` and now. These missed their window during downtime and need to be executed.
- [ ] `validate_all_schedules()` — separate valid from invalid cron expressions
- [ ] `tests/test_scheduler.py` — test next_run calculations (daily/hourly/weekly), should_run logic for all states, catch-up after downtime, first-ever startup, schedule validation
- [ ] Verify: all tests pass

---

### Post-MVP Step B: Main Service Loop

- [ ] `src/obs_tasks/main.py` — `TaskRunner` class that orchestrates everything
- [ ] `startup()` — load state, parse tasks, validate schedules, run catch-up for missed tasks
- [ ] `run_loop()` — poll every `check_interval` seconds
- [ ] `_tick()` — re-parse all tasks, find due tasks, execute each sequentially
- [ ] `_execute_and_record()` — execute task, update markdown, create report, update system state, calculate next_run
- [ ] `shutdown()` — graceful exit with signal handlers (SIGTERM, SIGINT)
- [ ] Error isolation: one failed tick must not crash the loop
- [ ] CLI `start` / `stop` / `status` commands
- [ ] Verify: tested via integration tests

---

## Markdown Format Reference

One file per task. Filename = task title (e.g. `Backup Docs.md` → title "Backup Docs"). The writer produces the `Current State`, `Statistics`, and `Run History` sections:

```markdown
#### Task Definition
- Command: `shell command to execute`
- Schedule: 0 2 * * *

#### Parameters
- Amount: 1234.56
- Customer: Acme Corp

#### Current State
- Status: ✅ Success
- Last Run: 2024-12-16 02:00:15
- Next Run: 2024-12-17 02:00:00
- Duration: 45.2s
- Result: Brief output summary

#### Statistics
- Total Runs: 47
- Successful: 46
- Failed: 1
- Last Failure: 2024-11-15 02:00:00

#### Run History
| Time | Status | Duration | Report |
|------|--------|----------|--------|
| 2024-12-16 02:00:15 | ✅ | 45.2s | [[2024-12-16-020015-backup-docs]] |
| 2024-12-15 02:00:12 | ✅ | 44.8s | [[2024-12-15-020012-backup-docs]] |
| 2024-12-14 02:00:09 | ❌ | 1.2s | [[2024-12-14-020009-backup-docs]] |
```

Headings inside the file are optional — the parser only looks for `- Command:` and `- Schedule:` lines. The `#### Parameters` section is optional — if present, keys are normalised (lowercase, spaces → underscores) and the JSON is automatically appended to the command. Use `{{params}}` placeholder to control the position explicitly. Parameters are also saved in execution reports. The Run History table is limited to the 20 most recent rows.

## File Structure (Target)

```
obsidian-task-automation/
├── src/obs_tasks/
│   ├── __init__.py
│   ├── models.py
│   ├── config.py
│   ├── parser.py
│   ├── executor.py
│   ├── writer.py
│   ├── state.py
│   ├── cli.py
│   ├── scheduler.py          [post-MVP]
│   └── main.py               [post-MVP]
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_parser.py
│   ├── test_executor.py
│   ├── test_writer.py
│   ├── test_state.py
│   ├── test_cli.py
│   ├── test_integration.py
│   └── test_scheduler.py     [post-MVP]
├── docs/
│   ├── mvp-specification.md
│   └── step-by-step.md
├── pyproject.toml
├── .gitignore
└── README.md
```
