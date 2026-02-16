# JCode Technical Guide

> Architecture deep-dive for developers who want to understand, extend, or contribute to JCode.

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [4-Role System](#4-role-system)
3. [DAG Task Engine](#dag-task-engine)
4. [Structured Memory](#structured-memory)
5. [Prompt Engineering](#prompt-engineering)
6. [Verification Pipeline](#verification-pipeline)
7. [Self-Correction & Failure Escalation](#self-correction--failure-escalation)
8. [CLI Architecture](#cli-architecture)
9. [Module Reference](#module-reference)
10. [Extending JCode](#extending-jcode)
11. [Development Setup](#development-setup)

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        CLI (cli.py)                          │
│   Interactive launcher → project selection → build command   │
├──────────────────────────────────────────────────────────────┤
│                   Iteration Engine (iteration.py)            │
│   DAG traversal → per-task pipeline → failure escalation     │
├────────┬────────┬────────────┬───────────┬──────────────────┤
│Planner │ Coder  │  Reviewer  │ Analyzer  │    Executor      │
│ (R1)   │ (Qwen) │  (Qwen)    │  (R1)     │  (subprocess)   │
├────────┴────────┴────────────┴───────────┴──────────────────┤
│               Context Manager (context.py)                   │
│   Structured memory: arch summary, file index, failure log   │
├──────────────────────────────────────────────────────────────┤
│                   Ollama Client (ollama_client.py)            │
│   Unified call_model(role, messages) → streaming output      │
├──────────────────────────────────────────────────────────────┤
│                   Ollama Server (localhost:11434)             │
│   deepseek-r1:14b  ·  qwen2.5-coder:14b                     │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User prompt
    │
    ▼
Planner (deepseek-r1:14b) ─── outputs JSON ──►  Plan
    │                                            ├── architecture_summary
    │                                            ├── tech_stack
    │                                            ├── file_index
    │                                            └── tasks[] (DAG)
    ▼
Iteration Engine ─── for each task in topological order:
    │
    ├── 1. Coder.generate_file(task, structured_context)
    ├── 2. Reviewer.review_file(file, architecture)
    ├── 3. Executor.verify_file(file_path)
    │       ├── syntax check
    │       ├── lint (ruff/flake8)
    │       └── type check (extensible)
    │
    ├── if verify fails (up to 3×):
    │   ├── Analyzer.analyze_error(file, error, failure_log)
    │   ├── Coder.patch_file(file, fix_strategy)
    │   └── re-verify
    │
    ├── if 3× fails → escalation:
    │   ├── option: re-plan with Planner
    │   ├── option: simplify task
    │   ├── option: skip and continue
    │   └── option: pause for user input
    │
    └── mark task: VERIFIED | FAILED | SKIPPED
```

---

## 4-Role System

The core insight: **same model weights, different system prompts = role specialisation**.

We use only 2 model downloads but create 4 distinct behaviours:

### Role Assignments

| Role | Model | Temperature | Purpose |
|------|-------|------------|---------|
| 🧠 Planner | `deepseek-r1:14b` | 0.6 | Architecture, task DAG, dependency mapping |
| 💻 Coder | `qwen2.5-coder:14b` | 0.15 | Deterministic code generation, patches |
| 🔍 Reviewer | `qwen2.5-coder:14b` | 0.3 | Pre-execution bug/security review |
| 🔬 Analyzer | `deepseek-r1:14b` | 0.2 | Root cause analysis, fix strategies |

### Why This Works

- **DeepSeek-R1** is a reasoning model — it uses `<think>` tags internally for chain-of-thought. Perfect for planning and diagnosis.
- **Qwen2.5-Coder** is a code-specialised model — it produces cleaner, more syntactically correct code. Perfect for generation and review.
- Low temperature on Coder (0.15) = deterministic, consistent output.
- Higher temperature on Planner (0.6) = creative architecture exploration.

### Role Isolation

Each role has:
- Its own system prompt (defined in `prompts.py`)
- Its own conversation history (stored in `context.py`)
- Its own context slice (only receives relevant information)

This prevents "role confusion" where the model might mix planning with coding.

---

## DAG Task Engine

Tasks are **not** executed linearly. They form a Directed Acyclic Graph (DAG).

### TaskNode

```python
@dataclass
class TaskNode:
    id: int
    file: str              # e.g., "src/models.py"
    description: str       # e.g., "Define SQLAlchemy models"
    depends_on: list[int]  # e.g., [1, 2] — must be VERIFIED first
    status: TaskStatus     # State machine
    failure_count: int     # Per-task failure counter
    error_summary: str     # Last error for this task
    review_feedback: str   # Last reviewer feedback
```

### State Machine

```
PENDING → IN_PROGRESS → GENERATED → REVIEWING → VERIFIED
                                         │
                                    NEEDS_FIX ← ─ ─ ─ ┐
                                         │              │
                                    [fix attempt]       │
                                         │              │
                                    re-VERIFY ──── still fails?
                                         │
                                    FAILED (after 3×) or SKIPPED
```

### Execution Order

`get_ready_tasks()` returns only tasks where **all dependencies are VERIFIED**:

```python
def get_ready_tasks(self) -> list[TaskNode]:
    verified_ids = {t.id for t in self._task_dag if t.status == TaskStatus.VERIFIED}
    return [
        t for t in self._task_dag
        if t.status == TaskStatus.PENDING
        and all(dep in verified_ids for dep in t.depends_on)
    ]
```

### Deadlock Detection

If no tasks are ready but some are pending (circular dependency or failed dependency), the engine detects the deadlock and skips blocked tasks.

---

## Structured Memory

**The key innovation.** Instead of dumping the entire conversation into context (which wastes tokens on a 14B model), we slice information by role:

### What Each Role Sees

| Role | Receives | Does NOT receive |
|------|----------|-----------------|
| Coder | Architecture summary, file index, task description | Raw plan JSON, failure log, review history |
| Reviewer | File content, architecture summary | Generation history, other files |
| Analyzer | Error output, failure log (previous attempts) | Plan, other files |
| Planner | Failure log, architecture summary | Individual file contents |

### Memory Layers

1. **architecture_summary** — one-paragraph description of the system
2. **file_index** — every file and its one-line purpose
3. **dependency_graph** — who imports whom
4. **failure_log** — what broke, what was tried, what worked
5. **task_nodes** — current DAG state with statuses

### Why This Matters

A 14B model with 16k context and **curated 2k of structured memory** outperforms a 70B model with 128k context and raw dumps. Signal-to-noise ratio is everything.

---

## Prompt Engineering

### DeepSeek-R1 Think Tags

DeepSeek-R1 outputs `<think>...</think>` blocks for chain-of-thought reasoning. We strip these before parsing JSON:

```python
def _extract_json(text: str) -> dict:
    # Remove <think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Find JSON in remaining text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group()) if match else {}
```

### JSON-Only Output

All roles that need structured output are prompted with explicit JSON schemas:

```
You MUST respond with a JSON object:
{
  "approved": true/false,
  "issues": [{"severity": "critical|warning|info", "description": "..."}],
  "summary": "..."
}
```

### Prompt Structure

Each prompt follows this pattern:
1. **Role identity** — "You are a senior code reviewer..."
2. **Constraints** — "Respond ONLY with JSON. No explanation."
3. **Context injection** — Architecture summary, file index (sliced)
4. **Task** — Specific instruction for this file/error
5. **Output schema** — Exact JSON structure expected

---

## Verification Pipeline

Multi-check quality gate per file (`executor.py`):

### Checks by Language

| Language | Syntax | Lint | Type Check |
|----------|--------|------|-----------|
| Python | `py_compile` | `ruff` → `flake8` fallback | extensible |
| JavaScript | `node --check` | — | — |
| JSON | `json.loads()` | — | — |

### VerificationResult

```python
@dataclass
class VerificationResult:
    passed: bool
    checks: dict[str, tuple[bool, str]]  # check_name → (passed, detail)
    
    @property
    def summary(self) -> str:
        return "\n".join(f"{'✅' if ok else '❌'} {name}: {msg}"
                        for name, (ok, msg) in self.checks.items())
    
    @property
    def failed_checks(self) -> list[str]:
        return [name for name, (ok, _) in self.checks.items() if not ok]
```

---

## Self-Correction & Failure Escalation

### Fix Loop (Per Task)

```
Attempt 1: Analyzer diagnoses → Coder patches → Verify
Attempt 2: Analyzer diagnoses (with attempt 1 in failure_log) → Coder patches → Verify
Attempt 3: Analyzer diagnoses (with attempts 1-2 in failure_log) → Coder patches → Verify
```

The failure_log prevents the Analyzer from suggesting the same fix twice.

### Escalation (After 3 Failures)

When a task exhausts all fix attempts, the engine offers 4 strategies:

1. **Re-plan** — Send failure context back to Planner for an alternative approach
2. **Simplify** — Regenerate with a simplified task description
3. **Skip** — Mark as SKIPPED, continue with remaining tasks
4. **Pause** — Ask the user what to do

The engine picks automatically based on context, or asks the user in interactive mode.

---

## CLI Architecture

### Launch Flow

```
jcode
  ├── First run? → Setup wizard (choose output dir)
  ├── Check Ollama → fail fast if not running
  └── Interactive launcher:
      ├── 🆕 Create new project
      │   ├── Enter prompt
      │   ├── (Optional) clone GitHub repo as base
      │   └── → Plan → Build pipeline
      ├── 📂 Continue a project (select from list)
      │   └── → Resume from last state
      ├── 📥 Import a project
      │   ├── Local path
      │   └── GitHub URL → clone
      └── After build → REPL with commands
```

### Available Commands

| Command | Module | Description |
|---------|--------|-------------|
| `build` | `cli.py` | Full pipeline |
| `plan` | `cli.py` | Show current plan |
| `files` | `cli.py` | List generated files |
| `tree` | `file_manager.py` | Directory tree |
| `projects` | `settings.py` | List saved projects |
| `resume` | `cli.py` | Resume last project |
| `update` | `cli.py` | Self-update JCode |
| `save/load` | `context.py` | Session management |
| `settings` | `settings.py` | Edit preferences |

---

## Module Reference

| Module | Lines | Purpose |
|--------|-------|---------|
| `config.py` | ~190 | Models, TaskStatus, TaskNode, ProjectState, complexity detection |
| `prompts.py` | ~200 | All 4 role system/task prompts with JSON schemas |
| `ollama_client.py` | ~120 | Unified `call_model(role, msgs)`, streaming, model verification |
| `context.py` | ~300 | Structured memory engine, DAG, session serialization |
| `planner.py` | ~80 | `create_plan()`, `refine_plan()`, think-tag stripping |
| `coder.py` | ~100 | `generate_file()`, `patch_file()`, fence stripping |
| `reviewer.py` | ~60 | `review_file()` → JSON verdict |
| `analyzer.py` | ~70 | `analyze_error()` → structured diagnosis |
| `executor.py` | ~150 | `verify_file()`, multi-language checks |
| `iteration.py` | ~240 | DAG orchestrator, fix loop, escalation |
| `cli.py` | ~450 | Interactive CLI, launcher, all commands |
| `settings.py` | ~120 | Persistent settings in `~/.jcode/` |
| `file_manager.py` | ~90 | File I/O, Rich directory tree |

---

## Extending JCode

### Adding a New Role

1. Add model config in `config.py` (or reuse existing model)
2. Create system + task prompts in `prompts.py`
3. Create the role module (e.g., `tester.py`)
4. Wire it into `iteration.py`'s pipeline
5. Add conversation history in `context.py`

### Adding a New Language Verifier

In `executor.py`, add a new case to `verify_file()`:

```python
elif suffix == ".rs":
    result = _verify_rust(file_path)
```

Then implement `_verify_rust()` following the pattern of `_verify_python()`.

### Adding a New CLI Command

1. Add the command handler as `_cmd_yourcommand()` in `cli.py`
2. Add it to the dispatch block in `main()`
3. Update `HELP_TEXT`

### Custom Specialisation Templates

Create prompt templates for specific tech stacks:

```python
FASTAPI_TEMPLATE = {
    "tech_stack": ["python", "fastapi", "sqlalchemy", "pydantic"],
    "files_hint": ["main.py", "models.py", "schemas.py", "database.py", "routers/"],
    "conventions": "Use async endpoints. Use Pydantic v2 model_validator."
}
```

---

## Development Setup

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/JcodeAgent.git
cd JcodeAgent

# Create venv
python3 -m venv .venv
source .venv/bin/activate

# Install in dev mode
pip install -e .

# Run
jcode

# Run module directly
python -m jcode
```

### Project Structure

```
JcodeAgent/
├── jcode/                 # Source package
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── context.py
│   ├── prompts.py
│   ├── ollama_client.py
│   ├── planner.py
│   ├── coder.py
│   ├── reviewer.py
│   ├── analyzer.py
│   ├── executor.py
│   ├── iteration.py
│   ├── file_manager.py
│   └── settings.py
├── docs/                  # Landing page
│   └── index.html
├── install.sh             # Mac/Linux installer
├── install.ps1            # Windows installer
├── pyproject.toml
├── requirements.txt
├── README.md
├── CHANGELOG.md
├── FEATURES.md
├── BEGINNER_GUIDE.md
└── TECHNICAL_GUIDE.md
```
