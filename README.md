# JCode 🤖

> **A local AI coding agent powered by Ollama** — plans, generates, reviews, and iterates on full projects using 4 specialized AI roles.

![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue)
![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-green)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow)

## How It Works

```
Prompt → 🧠 Planner → 💻 Coder → 🔍 Reviewer → ✅ Verify → 🔬 Analyzer → 🔄 Fix → ✅ Done
```

JCode uses **4 AI roles** (same local models, different specialised prompts) to build software the way an engineering team would:

1. **🧠 Plan** — DeepSeek-R1 creates architecture, dependency graph, and a DAG of tasks
2. **💻 Code** — Qwen2.5-Coder generates each file using structured memory (not raw plan dumps)
3. **🔍 Review** — Pre-execution code review catches bugs *before* they run
4. **✅ Verify** — Static analysis: syntax check, linting (ruff/flake8), type checks
5. **🔬 Analyze** — If verification fails, the Analyzer diagnoses the root cause
6. **🔄 Patch** — Targeted minimal fix applied; re-verify; repeat up to 3×
7. **✅ Done** — Verified project output with full DAG completion

### Key Innovations

- **DAG Task Tree** — tasks have dependencies; a file isn't generated until its deps are verified
- **Structured Memory** — architecture summary + file index + failure log (not context dumps)
- **Patch Mode** — fixes are minimal targeted patches, not full regeneration
- **Self-Correction** — Analyzer→Coder feedback loop avoids repeating the same mistake

## Prerequisites

- **Python 3.10+**
- **Ollama** installed and running (`ollama serve`)
- ~20 GB disk space for both models

## Quick Start

### One-Command Install (Recommended)

**Mac / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
iwr -useb https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.ps1 | iex
```

Installs Python, Ollama, AI models, and JCode — only what's missing. Then just run `jcode`.

### Manual Install

```bash
# 1. Clone / navigate to the project
cd JcodeAgent

# 2. Install
pip install -e .

# 3. Start Ollama (in another terminal)
ollama serve

# 4. Pull models (first time only)
ollama pull deepseek-r1:14b
ollama pull qwen2.5-coder:14b

# 5. Launch JCode
jcode
```

## Usage

```
jcode> build a REST API with FastAPI that manages a todo list with SQLite
```

JCode will:
1. Plan the architecture and create a dependency-ordered task DAG
2. Generate each file with full architectural context
3. Review each file for bugs before execution
4. Run static analysis (syntax + lint)
5. Auto-diagnose and patch any failures
6. Output the complete verified project

### Commands

| Command | Description |
|---------|-------------|
| `build <prompt>` | Full pipeline: plan → generate → review → verify → fix |
| `plan` | Show current plan and task statuses |
| `files` | List generated files with sizes |
| `tree` | Show project directory tree |
| `projects` | List all saved projects |
| `resume` | Resume last project |
| `save` | Manually save session |
| `load <path>` | Load session from file |
| `settings` | View/edit settings |
| `clear` | Clear screen |
| `help` | Show help |
| `quit` | Exit JCode |

## Architecture

```
jcode/
├── __init__.py          # Package metadata (v0.2.0)
├── __main__.py          # python -m jcode entry
├── cli.py               # Rich interactive CLI
├── config.py            # Models, TaskStatus, TaskNode, ProjectState
├── prompts.py           # All 4 role prompt templates
├── ollama_client.py     # Unified model caller with role dispatch
├── context.py           # Structured memory engine + DAG
├── planner.py           # Plan creation (DeepSeek-R1)
├── coder.py             # File generation + patch mode
├── reviewer.py          # Pre-execution code review
├── analyzer.py          # Error diagnosis + fix strategy
├── executor.py          # Verification pipeline (syntax/lint/type)
├── iteration.py         # DAG-based orchestration engine
├── file_manager.py      # File I/O + Rich directory tree
└── settings.py          # Persistent user settings
```

## 4-Role System

| Role | Model | Prompt Style | Purpose |
|------|-------|-------------|---------|
| 🧠 Planner | `deepseek-r1:14b` | Architecture-focused | Task DAG, tech stack, dependency graph |
| 💻 Coder | `qwen2.5-coder:14b` | Implementation-focused | File generation, targeted patches |
| 🔍 Reviewer | `qwen2.5-coder:14b` | Audit-focused | Pre-execution bug/security review |
| 🔬 Analyzer | `deepseek-r1:14b` | Diagnostic-focused | Root cause analysis, fix strategy |

Same model weights, different system prompts = role specialisation without extra downloads.

## Task Pipeline

```
For each task in DAG order:

  ┌─────────┐     ┌──────────┐     ┌──────────┐
  │ GENERATE ├────►│  REVIEW  ├────►│  VERIFY  │
  └─────────┘     └────┬─────┘     └────┬─────┘
                       │                 │
                  issues?            passed?
                       │                 │
                  ┌────▼─────┐      ┌───▼────┐
                  │  PATCH   │      │VERIFIED│
                  └──────────┘      └────────┘
                       │
                       │ still fails?
                       │
                  ┌────▼─────┐     ┌──────────┐
                  │ ANALYZE  ├────►│  PATCH   ├──► re-verify (up to 3×)
                  └──────────┘     └──────────┘
```

## Configuration

Settings are stored in `~/.jcode/settings.json`:
- Default output directory
- Auto-save preference
- Project metadata in `~/.jcode/projects/`

Sessions are auto-saved to `.jcode_session.json` in each project directory and can be resumed with `resume`.

## License

MIT
