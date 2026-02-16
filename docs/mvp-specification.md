# Obsidian Task Automation - MVP Specification

## Project Overview

A Python-based task automation system that integrates with Obsidian vaults to execute scheduled and on-demand tasks defined in Markdown files. The system reads task definitions from Markdown, executes commands, and writes results back to the vault.

### Target User
- Technical users (DevOps, developers, power users)
- Obsidian users for knowledge management
- Users who want to automate recurring tasks and track results in Markdown

### Success Criteria
- Read task definitions from Obsidian Markdown files
- Execute tasks based on schedule (cron-style)
- Write execution results back to Markdown
- Survive restarts (persistent state)
- Simple, reliable, maintainable

---

## Core Concept

**Single Source of Truth:** All task definitions, state, and results live in Obsidian Markdown files.

**Why Everything in Markdown:**
- ✅ **Consistency** - Same format for all data (no JSON/database)
- ✅ **Transparency** - State is human-readable, inspectable in Obsidian
- ✅ **Searchability** - Full-text search works on all data
- ✅ **Git-friendly** - Version control for all state changes
- ✅ **Backup-simple** - Vault backup = complete backup (no external files)
- ✅ **Obsidian-native** - Dataview queries, backlinks, graph view all work
- ✅ **Portable** - Pure markdown, no proprietary formats
- ✅ **No sync issues** - Everything in vault, syncs together

**Architecture:**
```
Obsidian Vault (Markdown files)
    ↕ (read/write)
Python Task Runner
    ├─ Task Parser (read .md)
    ├─ Scheduler (time-based execution)
    ├─ Executor (run commands)
    └─ Result Writer (write back to .md)
```

---

## MVP Scope (Priority 1)

### IN SCOPE - What we WILL build:

#### 1. Task Definition Format (Markdown)
- Tasks defined in Markdown with specific syntax
- Key fields: Title, Command, Schedule
- Support for basic metadata (status, last run, result)

#### 2. Task Parser
- Read Markdown files from Obsidian vault
- Parse task definitions into Python objects
- Extract: command, schedule, current status

#### 3. Scheduler
- Execute tasks based on cron-style schedules
- Support common patterns: daily, hourly, weekly
- Persistent state (remember what has been run)
- Catch-up logic (run missed tasks after restart)

#### 4. Task Executor
- Execute shell commands
- Capture stdout/stderr
- Track execution time
- Basic error handling (timeout, non-zero exit)

#### 5. Result Writer
- Update Markdown files with execution results
- Write: status, timestamp, duration, output summary
- Create separate report files for detailed output
- Maintain execution history

#### 6. Background Service
- Run continuously in background
- Check schedule every minute
- Load tasks on startup
- Reload tasks when Markdown files change (optional in MVP)

### OUT OF SCOPE - What we will NOT build in MVP:

#### Deferred to Post-MVP:
- **Manual triggers** (watchdog for file changes, run=true triggers)
- **VPN detection** and dependency checking
- **Retry logic** for failed tasks
- **Network checks** before execution
- **Web UI** or dashboard
- **Multiple vault support**
- **Task dependencies** (run task B after task A)
- **Parallel execution** (run multiple tasks simultaneously)
- **Interactive tasks** (tasks requiring user input)
- **Advanced scheduling** (calendar-based, business day rules)
- **Notifications** (email, Slack, etc.)
- **Task templates** and presets
- **Cloud sync** or collaboration features
- **Plugin system** for Obsidian

---

## Data Model

### Task Definition (in Markdown)

**Location:** Any `.md` file in vault (commonly in `Tasks/` folder)

```markdown
### Task Title
- Command: `shell command to execute`
- Schedule: cron expression

#### Current State
- Status: Current status (never_run/success/failed/running)
- Last Run: 2024-12-16 02:00:15
- Next Run: 2024-12-17 02:00:00
- Duration: 45.2s
- Result: Brief output summary (first ~200 chars)

#### Statistics
- Total Runs: 47
- Successful: 46
- Failed: 1
- Last Failure: 2024-11-15 02:00:00

**Detailed Report:** [[Reports/2024-12-16-task-title]]
```

**Key principles:**
- Definition (Command, Schedule) = user-editable, rarely changes
- State (Status, Last Run, etc.) = system-managed, updates frequently
- Statistics = cumulative, system-managed
- Clear sections for easy parsing and updating

### Task Object (Python)

```python
@dataclass
class Task:
    id: str              # Unique identifier
    title: str           # Display name
    command: str         # Shell command
    schedule: str        # Cron expression
    
    # State (read from and written to markdown)
    status: str          # "never_run", "success", "failed", "running"
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    duration: Optional[float]  # seconds
    result_summary: Optional[str]  # First 200 chars of output
    total_runs: int
    successful_runs: int
    failed_runs: int
    
    # Metadata
    file_path: Path      # Source markdown file
    line_number: int     # Location in file
```

### State Storage Strategy

**All state is stored in Markdown files - no separate JSON files.**

**Task-level state** (in task definition file):
- Current status, last run, next run
- Execution statistics
- Latest result summary

**System-level state** (in `.task-runner.md` or `System/Task Runner.md`):
- Last startup time
- Vault configuration
- Global statistics

**Why Markdown for state:**
- Single source of truth (Obsidian vault)
- Human-readable and editable
- Git-friendly (version control)
- Searchable in Obsidian
- No sync/backup issues
- Dataview compatible

---

## File Structure

```
obsidian-task-automation/
├── src/obs_tasks/
│   ├── __init__.py
│   ├── main.py                 # TaskRunner service loop
│   ├── cli.py                  # Click CLI (obs-tasks command)
│   ├── parser.py               # Markdown parser
│   ├── scheduler.py            # Schedule management (croniter)
│   ├── executor.py             # Command execution
│   ├── writer.py               # Result writing
│   ├── models.py               # Data classes
│   ├── config.py               # Config dataclass, JSON persistence
│   └── state.py                # State persistence
├── tests/
│   ├── conftest.py             # Shared fixtures
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
│   └── step-by-step.md         # Implementation plan for AI agent
├── pyproject.toml
├── claude.md                   # Instructions for Claude Code
├── README.md
└── .gitignore
```

---

## Component Specifications

### 1. Task Parser (`parser.py`)

**Purpose:** Read and parse task definitions from Markdown files.

**Key Functions:**
- `find_task_files(vault_path: Path) -> List[Path]` - Find all .md files
- `parse_file(file_path: Path) -> List[Task]` - Extract tasks from one file
- `parse_task_block(lines: List[str]) -> Task` - Parse one task definition

**Input:** Markdown files in Obsidian vault
**Output:** List of Task objects with all state included

**Key Logic:**
- Identify task blocks by finding `- Command:` + `- Schedule:` lines (heading-level agnostic)
- The task title is the nearest heading above those lines (any level: `#`, `##`, `###`, etc.)
- Parse definition fields: Command (from backticks), Schedule (cron expression)
- Parse state fields: Status (with emoji handling), Last Run, Next Run, Duration, Result
- Parse statistics: Total Runs, Successful, Failed
- Handle missing/optional fields gracefully (set defaults)
- Track file location (path, line number) for updates

**Parsing Strategy:**
- Scan for `- Command:` lines to locate task definitions
- For each, find the nearest heading above it (the task title)
- Determine block boundaries (from heading to next same-or-higher-level heading or EOF)
- Extract all fields within the block (definition, state, statistics)
- Create Task object with all fields populated

### 2. Scheduler (`scheduler.py`)

**Purpose:** Determine when tasks should run and trigger execution.

**Key Functions:**
- `load_tasks() -> List[Task]` - Load all tasks from vault
- `should_run(task: Task) -> bool` - Check if task is due
- `schedule_loop()` - Main loop (runs every minute)
- `calculate_next_run(task: Task) -> datetime` - Next execution time

**State Management:**
- Load state on startup
- Check for missed executions (catch-up)
- Save state after each execution
- Handle edge cases (DST, timezone changes)

**Schedule Parsing (via croniter):**
- Full cron syntax support: `0 2 * * *`, `*/30 * * * *`, `0 9 * * MON-FRI`
- `croniter` handles parsing and next-run calculation
- `is_valid()` for schedule validation

### 3. Task Executor (`executor.py`)

**Purpose:** Execute shell commands and capture results.

**Key Functions:**
- `execute(task: Task) -> ExecutionResult` - Run command
- `_run_command(command: str) -> subprocess.Result` - Execute shell command
- `_format_output(result) -> str` - Format output for markdown

**Execution Details:**
- Run command in shell
- Set working directory to vault root
- Timeout: 5 minutes (configurable)
- Capture stdout and stderr separately
- Return exit code, output, duration

**Error Handling:**
- Timeout → mark as failed
- Non-zero exit → mark as failed
- Exception → mark as failed, log error
- Always write result (even if failed)

### 4. Result Writer (`writer.py`)

**Purpose:** Write execution results back to Markdown files.

**Key Functions:**
- `update_task_state(task: Task, result: ExecutionResult)` - Update Current State section
- `update_task_statistics(task: Task)` - Update Statistics section
- `create_report_file(task: Task, result: ExecutionResult)` - Create detailed report
- `_update_section(content: str, section: str, new_lines: List[str]) -> str` - Edit specific section

**Update Strategy:**
- Find task block in file (by title or unique identifier)
- Update ONLY the "#### Current State" section
- Update ONLY the "#### Statistics" section
- Preserve definition (Command, Schedule) - never modify
- Preserve user notes and custom content
- Atomic file writes (write temp file, then rename)

**Sections Updated:**

**Current State (after every execution):**
```markdown
#### Current State
- Status: ✅ Success
- Last Run: 2024-12-16 02:00:15
- Next Run: 2024-12-17 02:00:00
- Duration: 45.2s
- Result: Backed up 1,234 files (5.2 GB)
```

**Statistics (after every execution):**
```markdown
#### Statistics
- Total Runs: 47
- Successful: 46
- Failed: 1
- Average Duration: 43.5s
- Last Failure: 2024-11-15 02:00:00
```

**Report Files:**
- Location: `Reports/YYYY-MM-DD-task-name.md`
- Content: Full command output, timestamp, metadata
- Linked from task definition
- Named with date for easy chronological sorting

**Markdown Update Algorithm:**
1. Read entire file
2. Find task section (starts with `### Task Title`)
3. Locate `#### Current State` subsection
4. Replace lines until next `####` heading
5. Locate `#### Statistics` subsection
6. Replace lines until next `####` heading or `---`
7. Write back atomically (temp file + rename)

### 5. State Manager (`state.py`)

**Purpose:** Manage system-level state in Markdown format.

**Key Functions:**
- `load_system_state() -> dict` - Load from markdown file
- `save_system_state(state: dict)` - Write to markdown file
- `get_last_startup() -> Optional[datetime]` - When runner last started
- `set_last_startup(timestamp: datetime)` - Record startup time

**State File Location:** `<vault>/.task-runner.md` (hidden file in vault root)

**State File Format:**
```markdown
---
last_startup: 2024-12-16T10:00:00
vault_version: 1
---

# Task Runner System State

**Last Startup:** 2024-12-16 10:00:00
**Vault Path:** /Users/timo/Obsidian/Main

This file contains task runner system metadata.
Used for catch-up logic after restarts.

⚠️ This file is managed automatically. Manual edits may be overwritten.

## Global Statistics

- Total Tasks: 12
- Active Scheduled Tasks: 8
- Total Executions (all time): 1,247
- Successful: 1,198
- Failed: 49
- Last 24h Executions: 15
```

**Why Markdown:**
- Consistent with "all data in Obsidian" philosophy
- Human-readable for debugging
- Can be viewed/searched in Obsidian
- YAML frontmatter for structured data
- Markdown body for human context
- Git-friendly

### 6. Main Application (`main.py`)

**Purpose:** Orchestrate all components, main entry point.

**Key Functions:**
- `main()` - Entry point
- `startup()` - Initialize components
- `run_scheduler_loop()` - Main execution loop
- `shutdown()` - Clean exit

**Startup Sequence:**
1. Load configuration (vault path)
2. Initialize state manager
3. Parse all tasks from vault
4. Check for catch-up (missed runs)
5. Start scheduler loop

**Main Loop (every minute):**
1. Check all tasks
2. Execute tasks that are due
3. Update state
4. Sleep 60 seconds

**Shutdown:**
- Save state
- Log summary
- Exit cleanly

---

## MVP User Workflow

### Setup (One-time)

1. **Install tool:**
   ```bash
   pip install obsidian-task-automation
   ```

2. **Configure vault path:**
   ```bash
   obs-tasks init ~/Obsidian/Main
   ```

3. **Start service:**
   ```bash
   obs-tasks start
   # Or: Set up auto-start (systemd/launchd/Task Scheduler)
   ```

### Daily Usage

1. **Define tasks in Obsidian:**
   - Create/edit task in `Tasks/work.md`
   - Set command and schedule
   - Save file

2. **Tasks run automatically:**
   - Scheduler executes at defined times
   - Results appear in Markdown
   - Reports generated automatically

3. **Review results:**
   - Check task status in Obsidian
   - Click report links for details
   - View execution history

### Example Task Definition

**File:** `Tasks/work.md`

```markdown
# Work Automation Tasks

## Backup Vaisala Documentation

### Purpose
Daily backup of internal documentation to local storage.

### Task Definition
- Command: `python ~/scripts/backup_docs.py --target /backups/vaisala`
- Schedule: 0 2 * * *

#### Current State
- Status: ✅ Success
- Last Run: 2024-12-16 02:00:15
- Next Run: 2024-12-17 02:00:00
- Duration: 45.2s
- Result: Backed up 245 pages (12.5 MB)

#### Statistics
- Total Runs: 47
- Successful: 46
- Failed: 1
- Average Duration: 44.1s
- Last Failure: 2024-11-15 02:00:00

**Detailed Output:** [[Reports/2024-12-16-backup-vaisala-documentation]]

### Notes
- Requires VPN connection (post-MVP feature)
- Backs up to external drive mounted at /backups
- Retention: Keep last 30 days

---

## Update GitHub Statistics

### Task Definition
- Command: `python ~/scripts/github_stats.py`
- Schedule: 0 9 * * MON

#### Current State
- Status: ✅ Success
- Last Run: 2024-12-15 09:00:00
- Next Run: 2024-12-22 09:00:00
- Duration: 3.2s
- Result: Analyzed 142 commits, 23 PRs

#### Statistics
- Total Runs: 8
- Successful: 8
- Failed: 0
- Average Duration: 3.5s
- Last Failure: Never

**Detailed Output:** [[Reports/2024-12-15-update-github-statistics]]
```

**Report File:** `Reports/2024-12-16-backup-vaisala-documentation.md`

```markdown
# Backup Vaisala Documentation - Execution Report

**Executed:** 2024-12-16 02:00:15
**Duration:** 45.2 seconds
**Command:** `python ~/scripts/backup_docs.py --target /backups/vaisala`
**Exit Code:** 0
**Status:** ✅ Success

## Output

```
Starting backup process...
Connecting to Confluence API...
Found 245 pages to backup
Downloading: Project Alpha Documentation (1/245)
Downloading: DevSecOps Guidelines (2/245)
...
Backup completed successfully
Total size: 12.5 MB
Saved to: /backups/vaisala/2024-12-16/
```

## Links
- Back to [[Tasks/work]]
- Previous report: [[Reports/2024-12-15-backup-vaisala-documentation]]

---
*Generated by Obsidian Task Automation*
```

---

## Technical Requirements

### Dependencies

```txt
# Core
click>=8.0              # CLI framework
croniter>=1.3           # Cron expression parsing and next-run calculation
pyyaml>=6.0             # YAML frontmatter parsing
python-dateutil>=2.8    # Better datetime parsing

# Dev
pytest>=7.0
pytest-cov>=4.0
```

**Why croniter over schedule:** The spec defines tasks with cron expressions (`0 2 * * *`). `croniter` parses these natively and calculates next run times. The `schedule` library uses a different API (`every().day.at()`) and doesn't support cron syntax — we would need a separate cron parser anyway.

**Why Click:** Cleaner subcommand support than argparse, automatic help text generation, good testing support via `CliRunner`.

**Why PyYAML:** For parsing YAML frontmatter in state markdown file (standard Obsidian feature).

### Packaging
- `pyproject.toml` (PEP 621) — modern Python standard, all config in one place
- Package layout: `src/obs_tasks/` (src layout)
- CLI entry point: `obs-tasks = "obs_tasks.cli:cli"`

### Python Version
- Python 3.13+ (latest stable)

### Platform Support
- macOS (primary)
- Linux (should work)
- Windows (best-effort, may have path issues)

### Performance Requirements
- Parse 100 tasks in <1 second
- Scheduler check cycle: 60 seconds
- Support vaults up to 10,000 files
- Memory usage: <50 MB

---

## Configuration

### Config File: `~/.obs-tasks/config.json`

```json
{
  "vault_path": "/home/timo/Obsidian/Main",
  "task_folder": "Tasks",
  "reports_folder": "Reports",
  "state_file": ".task-runner.md",
  "check_interval": 60,
  "command_timeout": 300,
  "log_level": "INFO"
}
```

**Note:** `state_file` now points to a Markdown file, not JSON.

### Environment Variables (optional overrides)

```bash
OBS_TASKS_VAULT=/path/to/vault
OBS_TASKS_LOG_LEVEL=DEBUG
```

---

## Testing Strategy

### Unit Tests
- `test_parser.py` - Markdown parsing edge cases
- `test_scheduler.py` - Schedule calculation logic
- `test_executor.py` - Command execution (mocked)
- `test_writer.py` - Markdown writing/updating

### Integration Tests
- End-to-end: Define task → execute → verify result in Markdown
- State persistence: Restart → verify catch-up works
- Error handling: Failed commands → verify status update

### Manual Testing Scenarios
1. Define simple daily task → verify it runs at correct time
2. Restart service → verify tasks don't re-run immediately
3. Define task in past → verify catch-up execution
4. Long-running task → verify timeout works
5. Failed command → verify error captured in Markdown

---

## Development Phases

### Phase 1: Core Parsing (Week 1)
**Deliverable:** Can read tasks from Markdown

- Implement Task model
- Implement Markdown parser
- Unit tests for parser
- CLI to list parsed tasks

**Acceptance:** `obs-tasks list` shows all tasks from vault

### Phase 2: Execution Engine (Week 1-2)
**Deliverable:** Can execute commands and capture results

- Implement executor
- Implement result writer
- Unit tests for execution
- CLI to manually run one task

**Acceptance:** `obs-tasks run "task-name"` executes and updates Markdown

### Phase 3: Scheduling (Week 2)
**Deliverable:** Tasks run automatically on schedule

- Implement scheduler
- Implement state persistence
- Implement catch-up logic
- Background service mode

**Acceptance:** Service runs in background, executes tasks at scheduled times

### Phase 4: Polish & Docs (Week 3)
**Deliverable:** Production-ready MVP

- Error handling improvements
- Logging
- Documentation (README, examples)
- Installation instructions
- Basic CLI help

**Acceptance:** Can be installed and used by external user following README

---

## CLI Interface (MVP)

```bash
# Initialize configuration
obs-tasks init /path/to/vault

# List all tasks
obs-tasks list

# Run specific task manually
obs-tasks run "Backup Photos"

# Start background scheduler
obs-tasks start

# Stop background scheduler
obs-tasks stop

# Check status
obs-tasks status

# Show recent executions
obs-tasks history --limit 10
```

---

## Error Handling (MVP Level)

### What we WILL handle:
- Command timeout (5 minutes)
- Non-zero exit codes
- Missing vault path
- Invalid Markdown syntax (skip task, log warning)
- File write failures (log error, continue)

### What we will NOT handle (defer to post-MVP):
- Network failures → just fail the task
- VPN dependency → user must ensure VPN is up
- Concurrent execution → single-threaded only
- Task conflicts → last-write-wins on Markdown
- Circular dependencies → not supported

### Error Logging
- Log to file: `~/.obs-tasks/obs-tasks.log`
- Log level: INFO (configurable to DEBUG)
- Rotate logs: Keep last 7 days
- Include: timestamp, level, task name, error message

---

## Deployment

### Installation

**Via pip (when published):**
```bash
pip install obsidian-task-automation
```

**From source:**
```bash
git clone https://github.com/user/obsidian-task-automation
cd obsidian-task-automation
pip install -e .
```

### Auto-start Setup

**Linux (systemd):**
```bash
obs-tasks install-service
systemctl --user enable obs-tasks
systemctl --user start obs-tasks
```

**macOS (launchd):**
```bash
obs-tasks install-service
launchctl load ~/Library/LaunchAgents/com.obs-tasks.plist
```

**Windows (Task Scheduler):**
```powershell
obs-tasks install-service
# Creates scheduled task to run on login
```

---

## Non-Functional Requirements

### Reliability
- Service should run for days/weeks without restart
- State must survive crashes (save after each execution)
- Failed tasks should not block other tasks

### Maintainability
- Clear separation of concerns (parser, executor, writer)
- Type hints on all functions
- Docstrings on public APIs
- Simple, readable code

### Observability
- Log all executions (start, end, result)
- Log all errors with context
- State file shows system health
- Easy to debug via logs

### Security
- Execute commands in shell (user is trusted)
- No network access from tool itself
- Read/write only to configured vault
- No elevation of privileges

---

## Future Enhancements (Post-MVP)

### Priority 2 (Next iteration):
- Manual triggers (watchdog for file changes)
- VPN detection and automatic retry
- Retry logic with exponential backoff
- Web dashboard for monitoring
- **Manual/semi-automated task workflows** (see below)

### Priority 3 (Later):
- Task dependencies (DAG execution)
- Parallel execution
- Advanced scheduling (calendar-based)
- Notifications (email, Slack)

### Priority 4 (Nice to have):
- Obsidian plugin (UI integration)
- Cloud sync support
- Multi-vault support
- Task templates and wizards

### Manual & Semi-Automated Workflows (Post-MVP Concept)

Extend the platform beyond automated shell commands to support **manual and semi-automated repeatable processes**. Same Markdown-based definition, same reporting, but the "executor" is a human following step-by-step instructions.

**Use cases:**
- Purchase Order creation (triggered on demand, guided step-by-step, human fills forms)
- Monthly compliance checklist (scheduled reminder, human completes and confirms)
- Semi-automated deploy (script runs pre-checks, human approves, script continues)

**Proposed task format:**
```markdown
### Create Purchase Order

#### Task Definition
- Type: manual
- Trigger: on-demand

#### Steps
1. Open SAP → navigate to ME21N
2. Fill header: vendor, company code 1000
3. Add line items from the attached request
4. Get approval from cost center owner
5. Submit PO and record PO number

#### Current State
- Status: ✅ Completed
- Started: 2025-02-16 09:15:00
- Completed: 2025-02-16 09:42:00
- Duration: 27min
- Result: PO #4500012345 created
```

**Key differences from automated tasks:**
- `Type: manual` or `semi-auto` instead of implicit `auto`
- `Trigger: on-demand` instead of cron schedule (scheduled reminders also possible)
- `Steps` section with checkable items (human marks each done)
- Duration measured from first step start to last step completion
- Result entered by human (or captured from final automated step)

**Implementation considerations:**
- Requires interactive UI — likely an Obsidian plugin or CLI interactive mode
- Parser needs to handle `Type` and `Steps` fields
- Writer needs to track per-step completion timestamps
- Same report generation and statistics tracking as automated tasks
- Fits the "single source of truth in Markdown" philosophy perfectly

---

## Success Metrics

### MVP is successful if:
1. Can parse tasks from 5+ different Markdown files
2. Executes scheduled tasks within 1 minute of scheduled time
3. Correctly updates Markdown with results
4. Survives restart and catches up on missed tasks
5. Runs for 7 days without manual intervention
6. User (Timo) uses it daily for real work tasks

### User Satisfaction:
- Saves time compared to manual execution
- Reduces cognitive load (don't forget to run tasks)
- Results are easy to find and review in Obsidian
- Rare failures are acceptable if clearly reported

---

## Documentation Requirements

### README.md
- Installation instructions
- Quick start guide
- Example task definitions
- Troubleshooting

### User Guide
- Task definition syntax reference
- Schedule format (cron expressions)
- CLI command reference
- Configuration options

### Developer Guide (minimal)
- Architecture overview
- How to run tests
- How to contribute
- Code style guide

---

## Known Limitations (MVP)

### By Design:
- Single vault only
- No GUI (Obsidian IS the GUI)
- Single-threaded execution
- No task prioritization
- No resource limits (CPU, memory)

### Technical:
- Markdown parsing is fragile (strict format required)
- Schedule checks every 60 seconds (not real-time)
- Tasks must complete within 5 minutes
- No support for interactive commands
- File locking may cause issues on network drives

### Platform-specific:
- Windows path handling may differ
- macOS may require security permissions (Full Disk Access)
- Linux cron may conflict (use one or the other)

---

## Risks and Mitigations

### Risk: Markdown format changes break parser
**Mitigation:** 
- Keep format simple and well-documented
- Add validation and helpful error messages
- Version the format (add format version field)

### Risk: Vault conflicts (Obsidian writes, tool writes)
**Mitigation:**
- Tool only appends/updates specific sections
- Use atomic file operations
- Accept last-write-wins (acceptable for MVP)

### Risk: Long-running tasks block other tasks
**Mitigation:**
- Implement timeout (5 minutes)
- Document that tasks should be quick
- Defer parallel execution to post-MVP

### Risk: User forgets service is running
**Mitigation:**
- Clear logging
- Status command shows if running
- Write heartbeat to state file

### Risk: Schedule misconfiguration (runs too often)
**Mitigation:**
- Validate schedule on parse
- Log every execution (user can audit)
- Add dry-run mode to test schedules

---

## Appendix A: Cron Expression Quick Reference

```
# Format: minute hour day month weekday

# Every day at 2 AM
0 2 * * *

# Every Monday at 9 AM
0 9 * * MON

# Every hour
0 * * * *

# Every 30 minutes (not standard cron, use external library)
*/30 * * * *

# First day of month
0 0 1 * *

# Weekdays at 8 AM
0 8 * * MON-FRI
```

**Note:** Full cron syntax is supported via the `croniter` library.

---

## Appendix B: Example Vault Structure

```
Obsidian-Vault/
├── Tasks/
│   ├── work.md              # Work-related automation
│   ├── personal.md          # Personal tasks
│   └── maintenance.md       # System maintenance
├── Reports/
│   ├── 2024-12-16-backup-photos.md
│   ├── 2024-12-16-github-sync.md
│   └── 2024-12-15-weekly-report.md
├── Scripts/                 # Optional: Store scripts here
│   ├── backup_photos.py
│   └── github_sync.py
├── .task-runner.md          # System state (markdown)
└── .obsidian/              # Obsidian config (ignore)
```

---

## Appendix C: Task Definition Template

Copy this template to create new tasks:

```markdown
### Task Name Here

Brief description of what this task does.

#### Task Definition
- Command: `command to execute`
- Schedule: 0 2 * * *

#### Current State
- Status: Never run
- Last Run: -
- Next Run: -
- Duration: -
- Result: -

#### Statistics
- Total Runs: 0
- Successful: 0
- Failed: 0
- Average Duration: -
- Last Failure: -

**Detailed Output:** -

#### Notes
- Any special considerations
- Dependencies or requirements
- Troubleshooting tips

---
```

---

## Version History

**v0.1.0 - MVP Specification**
- Initial specification document
- Core features defined
- MVP scope established
- Development phases planned

**v0.1.1 - Technology decisions updated**
- Python 3.13+ (was 3.9+)
- croniter for cron parsing (was schedule)
- Click for CLI (was implicit argparse)
- pyproject.toml packaging (was requirements.txt)
- src/obs_tasks/ package layout (was flat src/)
- macOS as primary platform (was Linux)
- Parser strategy: heading-agnostic, detects tasks by Command+Schedule lines

---

## Contact & Feedback

**Project:** Obsidian Task Automation
**Maintainer:** Timo (Vaisala DevSecOps)
**Status:** Implementation in progress
**Implementation guide:** `docs/step-by-step.md`

---

END OF SPECIFICATION