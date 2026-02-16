Instructions for Claude Code when working on this project.

## Project overview

Python CLI tool (`obs-tasks`) that reads task definitions from Obsidian Markdown files, executes them on cron schedules, and writes results back to Markdown. All task state lives in the vault — no databases, no external state files. License: MIT.

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

The core principle: task definitions, execution state, statistics, and reports are all Markdown files inside the Obsidian vault. The only exception is the app config file (`~/.obs-tasks/config.json`).

### Separation of concerns

- `src/obs_tasks/models.py` — dataclasses only, no I/O
- `src/obs_tasks/parser.py` — reads Markdown → Task objects, no writing
- `src/obs_tasks/executor.py` — runs shell commands, no Markdown awareness
- `src/obs_tasks/writer.py` — updates Markdown files, no execution logic
- `src/obs_tasks/scheduler.py` — scheduling math (croniter), no I/O
- `src/obs_tasks/state.py` — system-level state in `.task-runner.md`
- `src/obs_tasks/cli.py` — Click CLI, wires components together
- `src/obs_tasks/main.py` — TaskRunner service loop, orchestration only

### Key design rules

- **Atomic file writes** — always write to temp file then rename
- **Parser flexibility** — detect tasks by `- Command:` + `- Schedule:` lines, not heading level
- **Never modify user content** — writer touches only `#### Current State` and `#### Statistics`
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
