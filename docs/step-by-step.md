# Obsidian Task Automation — MVP Implementation Plan

> This document is the implementation guide for AI coding agents (Claude Code).
> Read `docs/mvp-specification.md` first for full context.
> Human reviewer: use the checkboxes to track progress.

## Project Summary

Python CLI tool that reads task definitions from Obsidian Markdown files, executes them on cron schedules, and writes results back to Markdown. All state lives in the vault — no databases.

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
    ├─ scheduler.py   → decides when to run (croniter + catch-up)
    ├─ executor.py    → runs shell commands (subprocess)
    ├─ writer.py      → updates .md with results + creates reports
    ├─ state.py       → system state in .task-runner.md
    ├─ models.py      → dataclasses (Task, ExecutionResult, etc.)
    ├─ config.py      → Config dataclass, JSON persistence
    ├─ cli.py         → Click CLI (obs-tasks command)
    └─ main.py        → TaskRunner service loop
```

Package layout: `src/obs_tasks/`, entry point: `obs-tasks = "obs_tasks.cli:cli"`

## Key Design Rules

1. **All data in Markdown** — no JSON state files, no databases. Config is the only exception (`~/.obs-tasks/config.json`).
2. **Atomic file writes** — always write to temp file then rename. Never leave a half-written .md file.
3. **Parser flexibility** — detect tasks by finding `- Command:` + `- Schedule:` lines, not by heading level. The task title is the nearest heading above those lines.
4. **Never modify user content** — writer updates only `#### Current State` and `#### Statistics` sections. Command, Schedule, and any user notes are preserved exactly.
5. **Recovery over precision** — on startup, compare `last_startup` from state file against each task's `next_run`. Any missed tasks get executed. Tasks that have never run execute immediately.
6. **Re-parse every tick** — the main loop re-reads all task files each cycle (every 60s). This picks up user edits without needing file watchers.
7. **Never raise from executor** — `execute_task()` always returns an `ExecutionResult`, even on timeout or crash.

---

## Implementation Steps

Work through these steps in order. Each step builds on the previous. Write tests alongside the code (TDD). Run `pytest` after each step to verify nothing is broken.

---

### Step 1: Project Scaffolding

- [ ] Create `pyproject.toml` with dependencies: click, pyyaml, python-dateutil, croniter. Dev deps: pytest, pytest-cov.
- [ ] Create `.gitignore` (standard Python)
- [ ] Create `src/obs_tasks/__init__.py` with `__version__ = "0.1.0"`
- [ ] Create `src/obs_tasks/cli.py` with a placeholder Click group
- [ ] Create `tests/__init__.py` and `tests/conftest.py` (empty)
- [ ] Verify: `pip install -e ".[dev]"` succeeds, `pytest` runs, `obs-tasks --help` prints output

---

### Step 2: Data Models

- [ ] `src/obs_tasks/models.py` — `TaskStatus` enum, `Task` dataclass, `ExecutionResult` dataclass, `SystemState` dataclass, `slugify()` helper
- [ ] `src/obs_tasks/config.py` — `Config` dataclass with `load()`/`save()` for `~/.obs-tasks/config.json`
- [ ] `tests/test_models.py` — test defaults, enum values, slugify edge cases, ExecutionResult.summary truncation, Config round-trip
- [ ] Verify: all tests pass

Refer to `mvp-specification.md` lines 139–162 for the Task data model and lines 588–600 for Config fields.

---

### Step 3: Markdown Parser

This is the most complex component. Read `mvp-specification.md` lines 108–163 for the task markdown format, and lines 460–516 for realistic examples.

- [ ] `src/obs_tasks/parser.py` — find task files, parse single file, parse all tasks
- [ ] Support both format variants from the spec (direct `### Title` with fields, and `#### Task Definition` sub-headed)
- [ ] Parse all fields: Command (from backticks), Schedule, Status (with emoji handling), Last Run, Next Run, Duration, Result, statistics counters
- [ ] Handle missing/optional fields gracefully — set defaults, never crash
- [ ] Track source file path and heading line number on each Task (needed by writer)
- [ ] `tests/test_parser.py` — test simple task, sub-headed format, multiple tasks per file, minimal task (only Command+Schedule), malformed task (skip gracefully), emoji status, datetime parsing, duration parsing, file discovery
- [ ] Verify: all tests pass

---

### Step 4: Command Executor

- [ ] `src/obs_tasks/executor.py` — `execute_task()` that runs a shell command and returns `ExecutionResult`
- [ ] Use `subprocess.run(shell=True, capture_output=True, text=True, timeout=...)`
- [ ] Handle: successful commands, non-zero exit codes, timeouts, exceptions — never raise
- [ ] `tests/test_executor.py` — test echo, stderr capture, exit codes, timeout, invalid commands, duration tracking, working directory
- [ ] Verify: all tests pass

---

### Step 5: Markdown Writer

Second most complex component. The writer must surgically update specific sections without touching anything else.

- [ ] `src/obs_tasks/writer.py` — update task state/statistics in source file, create report files
- [ ] Find the task's section by heading line (fast path) with fallback to title search
- [ ] Find and replace `#### Current State` and `#### Statistics` subsections; create them if missing
- [ ] Create report files at `Reports/YYYY-MM-DD-task-slug.md` with full output, metadata, and Obsidian backlinks
- [ ] Use atomic writes (temp file + rename) for all file operations
- [ ] `tests/test_writer.py` — test state updates (success/failure), statistics increments, timestamp/duration formatting, Command/Schedule preservation, section creation when missing, report file creation, atomic write behavior, multi-task file safety
- [ ] Verify: all tests pass

Refer to `mvp-specification.md` lines 306–341 for the exact section formats the writer should produce.

---

### Step 6: State Manager

- [ ] `src/obs_tasks/state.py` — `StateManager` class that reads/writes `.task-runner.md` with YAML frontmatter
- [ ] `load()` returns defaults if file doesn't exist; `save()` uses atomic write
- [ ] `record_startup()` and `update_after_execution()` for lifecycle tracking
- [ ] `tests/test_state.py` — test load/save round-trip, missing file defaults, startup recording, execution counter updates, frontmatter format
- [ ] Verify: all tests pass

Refer to `mvp-specification.md` lines 354–387 for the state file format.

---

### Step 7: Scheduler

- [ ] `src/obs_tasks/scheduler.py` — scheduling logic using croniter
- [ ] `calculate_next_run()` — croniter-based next execution time
- [ ] `should_run()` — returns true if: never_run, or next_run <= now (but not if status is running)
- [ ] `check_for_catchup()` — **the recovery mechanism**: find tasks whose `next_run` falls between `last_startup` and now. These missed their window during downtime and need to be executed.
- [ ] `validate_all_schedules()` — separate valid from invalid cron expressions
- [ ] `tests/test_scheduler.py` — test next_run calculations (daily/hourly/weekly), should_run logic for all states, catch-up after downtime, first-ever startup, schedule validation
- [ ] Verify: all tests pass

---

### Step 8: CLI

- [ ] `src/obs_tasks/cli.py` — full Click CLI replacing the placeholder
- [ ] `init <vault_path>` — create config file, Tasks/ and Reports/ directories, initial state file
- [ ] `list [--verbose]` — parse and display all tasks with status
- [ ] `run <task_name>` — find task by name (case-insensitive partial match), execute, write results
- [ ] `start [--foreground]` — launch the TaskRunner service (PID file for background mode)
- [ ] `stop` — send SIGTERM to PID from file
- [ ] `status` — show service state and task summary
- [ ] `history [--limit N]` — list recent executions from report files
- [ ] `tests/test_cli.py` — use Click's CliRunner to test each command
- [ ] Verify: all tests pass
- [ ] Manual smoke test: `obs-tasks init /tmp/test-vault && obs-tasks list`

---

### Step 9: Main Service Loop

- [ ] `src/obs_tasks/main.py` — `TaskRunner` class that orchestrates everything
- [ ] `startup()` — load state, parse tasks, validate schedules, run catch-up for missed tasks
- [ ] `run_loop()` — poll every `check_interval` seconds
- [ ] `_tick()` — re-parse all tasks, find due tasks, execute each sequentially
- [ ] `_execute_and_record()` — execute task, update markdown, create report, update system state, calculate next_run
- [ ] `shutdown()` — graceful exit with signal handlers (SIGTERM, SIGINT)
- [ ] Error isolation: one failed tick must not crash the loop
- [ ] Verify: tested via integration tests in next step

---

### Step 10: Integration Tests

- [ ] Update `tests/conftest.py` with shared fixtures: `sample_vault` (tmp_path with realistic task files), `sample_config`
- [ ] `tests/test_integration.py` — end-to-end tests:
  - Full pipeline: parse → execute → write → re-parse → verify state updated
  - Failed task: verify failure status and statistics
  - Catch-up after simulated restart
  - State persistence across StateManager instances
  - Multiple tasks execute sequentially without interference
  - Command/Schedule lines survive multiple execution cycles
  - Report files are created correctly
  - Statistics accumulate over repeated executions
  - CLI init + list + run work end-to-end
- [ ] Verify: all tests pass (unit + integration)

---

### Step 11: Polish

- [ ] Set up logging: file handler to `~/.obs-tasks/obs-tasks.log`, 7-day rotation, configurable level
- [ ] Improve error messages: clear guidance when vault not initialized, no tasks found, invalid cron expressions
- [ ] Write `README.md`: installation, quick start, task format reference, CLI commands, troubleshooting
- [ ] Final pass: remove dead code, ensure consistent style
- [ ] Final verify: `pytest --cov=obs_tasks` — all green, reasonable coverage

---

## Markdown Format Reference

The parser must handle this task format (from the spec). The writer produces the `Current State` and `Statistics` sections:

```markdown
### Task Title Here

Description text (optional, preserved by writer).

#### Task Definition
- Command: `shell command to execute`
- Schedule: 0 2 * * *

#### Current State
- Status: Success
- Last Run: 2024-12-16 02:00:15
- Next Run: 2024-12-17 02:00:00
- Duration: 45.2s
- Result: Brief output summary

#### Statistics
- Total Runs: 47
- Successful: 46
- Failed: 1
- Last Failure: 2024-11-15 02:00:00

**Detailed Output:** [[Reports/2024-12-16-task-title]]
```

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
│   ├── scheduler.py
│   ├── cli.py
│   └── main.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_parser.py
│   ├── test_executor.py
│   ├── test_writer.py
│   ├── test_state.py
│   ├── test_scheduler.py
│   ├── test_cli.py
│   └── test_integration.py
├── docs/
│   ├── mvp-specification.md
│   └── step-by-step.md
├── pyproject.toml
├── .gitignore
└── README.md
```
