# Obsidian Task Automation

Python CLI tool that reads task definitions from Obsidian Markdown files, executes them, and writes results back to Markdown. All task state lives in the vault — no databases, no external state files.

![Task view in Obsidian](docs/images/task-view.png)

## Features

- **All state in Markdown** — task definitions, execution results, statistics and run history live in your vault
- **Run History** — each task file includes a table of recent executions with status, duration and links to detailed reports
- **Obsidian integration** — report links use `[[wiki-links]]` so you can click through from the history table directly to full execution reports
- **Shell Commands plugin support** — trigger tasks from Obsidian's UI with a single click
- **No external dependencies** — no databases, no cloud services, just Markdown files

## Installation

Requires Python 3.13+.

```bash
git clone https://github.com/afkal/obsidian-task-automation.git
cd obsidian-task-automation
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Quick Start

```bash
# 1. Point obs-tasks at your Obsidian vault
obs-tasks init /path/to/your/vault

# 2. Create a task file in Tasks/
#    e.g. Tasks/Backup Docs.md (see format below)

# 3. List tasks
obs-tasks list
obs-tasks list -v    # verbose

# 4. Run a task
obs-tasks run "Backup Docs"
obs-tasks run --file "/path/to/Tasks/Backup Docs.md"
```

## Task File Format

Each `.md` file in `Tasks/` is one task. The filename (without `.md`) is the task title.

```markdown
#### Task Definition
- Command: `rsync -av ~/Documents /backup/docs`
- Schedule: 0 2 * * *

#### Current State
- Status: ✅ Success
- Last Run: 2024-12-16 02:00:15
- Next Run: -
- Duration: 45.2s
- Result: Sent 3 files

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

**You write:** `#### Task Definition` with `- Command:` and `- Schedule:` lines.

**The tool writes:** `#### Current State`, `#### Statistics` and `#### Run History` sections after each run. The history table shows the 20 most recent executions with clickable `[[wiki-links]]` to detailed report files.

You can add any other headings or notes (e.g. `#### Notes`) — they won't be touched.

## CLI Commands

| Command | Description |
|---------|-------------|
| `obs-tasks init <vault_path>` | Initialise config, create Tasks/ and Reports/ |
| `obs-tasks list [-v]` | Show all tasks and their status |
| `obs-tasks run <name>` | Run a task by name (partial match, case-insensitive) |
| `obs-tasks run --file <path>` | Run the task in a specific file |
| `obs-tasks --version` | Show version |

## Obsidian Shell Commands Setup

Use the [Shell Commands](https://github.com/Taitava/obsidian-shellcommands) plugin to trigger tasks directly from Obsidian:

1. Install and enable the Shell Commands plugin
2. Add a new shell command:
   ```
   /path/to/.venv/bin/obs-tasks run --file "{{file_path:absolute}}"
   ```
3. Assign a hotkey or add it to the command palette
4. Open a task file in Obsidian and trigger the command

The `{{file_path:absolute}}` variable is replaced by the plugin with the current file's path.

## Reports

Each execution creates a report in `Reports/` with:

- Timestamp, duration, command, exit code
- Full stdout and stderr output
- Obsidian backlink to the task file (`[[Task Name]]`)

Report filenames: `YYYY-MM-DD-HHMMSS-task-slug.md`

Reports are automatically linked in the task file's **Run History** table — click any `[[report]]` link in Obsidian to jump to the full execution details.

## Development

```bash
# Run tests
.venv/bin/pytest tests/
.venv/bin/pytest tests/ -v                 # verbose
.venv/bin/pytest tests/ --cov=obs_tasks    # with coverage

# Install in development mode
.venv/bin/pip install -e ".[dev]"
```

## License

MIT
