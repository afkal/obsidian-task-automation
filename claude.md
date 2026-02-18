Instructions for Claude Code when working on this project.

## Project overview

Python CLI tool (`obs-tasks`) that reads task definitions from Obsidian Markdown files, executes them manually via CLI or Obsidian Shell Commands plugin, and writes results back to Markdown. All task state lives in the vault — no databases, no external state files. License: MIT.

**Current status:** MVP complete. Manual execution works. Automatic scheduling (cron daemon / background service) is planned for post-MVP.

## Key documents

- `docs/step-by-step.md` — Step-by-step implementation plan with checkboxes (follow this)
- `docs/mvp-specification.md` — MVP specification (background context, detailed examples)

When the two documents conflict, `step-by-step.md` wins — it reflects the latest decisions. Consult the spec for detailed format examples and field definitions. Ask the human if unclear.

## Development workflow

### Step-by-step implementation process

This project is built incrementally. Follow this cycle for every implementation step:

1. **Read** `docs/step-by-step.md`, find the next unchecked step
2. **Implement** that one step only — never skip ahead or combine steps
3. **Run tests** (`.venv/bin/pytest tests/`) and show results to the human
4. **Ask the human for approval** — do not assume approval, wait for explicit confirmation
5. **Propose a git commit** with a descriptive message — do not commit without approval
6. **Commit** after human approves, then mark the step `[x]` in step-by-step.md
7. **Move to the next step** only after the commit is done

### Git discipline

- Commit after every approved step, before starting the next one
- Commit message format: `feat: short description (step N)` or `fix:`, `refactor:`, `test:`, `docs:`
- Never commit automatically — always propose first and wait for approval
- Never amend a commit unless the human explicitly asks
- Never force push

### When something is unclear

- If the step has ambiguity, **ask before implementing**
- If you discover a problem mid-implementation, **report it before continuing**
- If tests fail after implementation, **fix and re-run before asking for approval**
- If a dependency doesn't install, report the error with context

## Architecture principles

### All data in Markdown

The core principle: task definitions, execution state, statistics, run history and reports are all Markdown files inside the Obsidian vault. The only exception is the app config file (default `~/.obs-tasks/config.json`, but in this project stored at project root via `config.py`).

### Separation of concerns

- `src/obs_tasks/models.py` — dataclasses only, no I/O
- `src/obs_tasks/parser.py` — reads Markdown → Task objects, no writing
- `src/obs_tasks/executor.py` — runs shell commands, no Markdown awareness
- `src/obs_tasks/writer.py` — updates Markdown files (Current State, Statistics, Run History), creates reports
- `src/obs_tasks/state.py` — system-level state in `.task-runner.md`
- `src/obs_tasks/config.py` — Config dataclass, load/save config.json
- `src/obs_tasks/cli.py` — Click CLI, wires components together
- `src/obs_tasks/scheduler.py` — [post-MVP] scheduling math (croniter), no I/O
- `src/obs_tasks/main.py` — [post-MVP] TaskRunner service loop, orchestration only

### Key design rules

- **Atomic file writes** — always write to temp file then rename
- **Parser flexibility** — detect tasks by `- Command:` + `- Schedule:` lines, not heading level
- **Never modify user content** — writer touches only `#### Current State`, `#### Statistics`, and `#### Run History`
- **Never raise from executor** — `execute_task()` always returns an `ExecutionResult`
- **Recovery over precision** — catch-up on startup for missed tasks matters more than exact cron timing

### Error handling

- Executor catches all exceptions and wraps them in `ExecutionResult`
- Parser skips malformed tasks with a warning log, never crashes
- Main loop isolates tick errors — one bad tick must not crash the service
- CLI shows human-readable errors, never raw stack traces

## Virtual environment

This project uses a Python 3.13 virtual environment at `.venv/`.

**Always use `.venv/bin/` prefix when running project commands:**

```bash
.venv/bin/pytest tests/
.venv/bin/obs-tasks --help
.venv/bin/pip install -e ".[dev]"
```

## Running tests

```bash
.venv/bin/pytest tests/
.venv/bin/pytest tests/ -v              # verbose
.venv/bin/pytest tests/test_parser.py   # single file
.venv/bin/pytest tests/ --cov=obs_tasks # with coverage
```

Current state: 200 tests, 98% coverage.

## GitHub repository

https://github.com/afkal/obsidian-task-automation (SSH: `git@github.com:afkal/obsidian-task-automation.git`)

## Real vault location

`/Users/tilai/Library/CloudStorage/OneDrive-VaisalaOyj/Obsidian/Vaisala/07_Task-automation/`

## MVP implementation status

Steps 1–9 are complete (see `docs/step-by-step.md`). Post-MVP features (scheduler, main loop) are documented there.

Additional features beyond the step-by-step plan:
- **Run History** — `#### Run History` table in task files with report wiki-links (max 20 rows)
- **Obsidian integration docs** — Shell Commands + Commander plugin setup in README
