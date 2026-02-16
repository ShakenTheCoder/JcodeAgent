# JCode v0.2.0 — Feature Summary

## Core Architecture

### 4-Role AI System
Each role uses the same local model weights but with specialised system prompts for task isolation:

| Role | Model | What It Does |
|------|-------|-------------|
| 🧠 Planner | deepseek-r1:14b | Architecture design, task DAG creation, dependency mapping |
| 💻 Coder | qwen2.5-coder:14b | File generation from structured context, targeted patches |
| 🔍 Reviewer | qwen2.5-coder:14b | Pre-execution code review (logic, security, completeness) |
| 🔬 Analyzer | deepseek-r1:14b | Error root cause analysis, fix strategy generation |

### DAG Task Tree
- Tasks have explicit `depends_on` fields
- Execution follows topological order — a file isn't generated until its dependencies are verified
- Deadlock detection with automatic skip for blocked tasks
- Status state machine: `PENDING → IN_PROGRESS → GENERATED → REVIEWING → NEEDS_FIX → VERIFIED/FAILED/SKIPPED`

### Structured Memory Engine
Instead of dumping raw conversation history, each role gets only the context it needs:

- **Coder** sees: architecture summary + file index + task description (not the full plan)
- **Reviewer** sees: the file content + architecture context (not generation history)
- **Analyzer** sees: error output + failure log of previous fixes (avoids repeating mistakes)
- **Planner** sees: failure log + architecture when refining plans

### Verification Pipeline
Multi-check quality gate per file:

| Check | Languages | Tool |
|-------|-----------|------|
| Syntax | Python, JS, JSON | `py_compile`, `node --check`, `json.loads` |
| Lint | Python | `ruff` or `flake8` |
| Type Check | Python | (extensible) |

### Self-Correction Loop
```
Generate → Review → Verify → [fail?] → Analyze → Patch → Re-verify
                                                    ↑         │
                                                    └─────────┘ (up to 3×)
```

- Analyzer produces structured JSON: `root_cause`, `fix_strategy`, `is_dependency_issue`
- Failure log prevents the same fix from being attempted twice
- After 3 failures, task is marked FAILED and execution continues

### Patch Mode
- Fixes use `patch_file()` instead of `generate_file()` — sends current file content + error + fix strategy
- Results in minimal targeted changes rather than full regeneration
- Preserves working code that passed review

## CLI Features

### Commands
| Command | Description |
|---------|-------------|
| `build <prompt>` | Full pipeline: plan → generate → review → verify → fix |
| `plan` | Show current plan with task statuses |
| `files` | List generated files with sizes |
| `tree` | Show project directory tree |
| `projects` | List all saved projects |
| `resume` | Resume the last project |
| `save` | Manually save current session |
| `load <path>` | Load a session file |
| `settings` | View/edit settings |
| `clear` | Clear screen |
| `help` | Show help |
| `quit` | Exit JCode |

### First-Run Setup Wizard
- Interactive setup on first launch
- Choose default output directory
- Settings persist in `~/.jcode/settings.json`

### Project Management
- Auto-save after each task completion
- Session files in `.jcode_session.json` per project
- Resume any project from where you left off
- Project metadata tracked in `~/.jcode/projects/`

### Adaptive Context Windows
- Complexity auto-detected from prompt analysis
- Context window scales: 16k (simple) → 24k → 32k → 40k (large)
- Based on file count, database usage, API complexity, auth, testing

## File Structure

```
jcode/
├── __init__.py          # v0.2.0
├── __main__.py          # python -m jcode
├── cli.py               # Rich interactive CLI + setup wizard
├── config.py            # TaskStatus, TaskNode, ProjectState, models
├── prompts.py           # All 4 role prompts with JSON schemas
├── ollama_client.py     # Unified call_model(role, ...) dispatcher
├── context.py           # Structured memory + DAG + session persistence
├── planner.py           # Plan creation with think-tag stripping
├── coder.py             # generate_file() + patch_file()
├── reviewer.py          # Pre-execution review → JSON verdict
├── analyzer.py          # Error diagnosis → structured fix plan
├── executor.py          # Verification pipeline + dependency install
├── iteration.py         # DAG-based orchestration engine
├── file_manager.py      # File I/O + Rich tree display
└── settings.py          # Persistent user settings
```
