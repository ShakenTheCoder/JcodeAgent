# Changelog

## v0.9.9 — Reliability: Files Actually Get Written

Critical reliability fixes discovered during real-world testing. The agent was generating correct code but never writing it to disk because models don't follow the exact output format. This release makes JCode bulletproof regardless of how the model formats its output.

### Robust File Parser (THE critical fix)
- **Multi-strategy parser**: `_apply_file_changes()` now handles 4 output formats:
  - **Format 1**: `===FILE: path=== ... ===END===` (ideal, standard)
  - **Format 2**: `===FILE: path===` followed by ` ```lang ... ``` ` (common model behavior — no ===END===)
  - **Format 3**: Markdown headings (`### main.py`) or bold (`**main.py**`) followed by code blocks
  - **Format 4**: `===FILE: path===` followed by raw content split at next marker (ultimate fallback)
- **Confirmation message**: Shows `✓ N file(s) written to disk` after successful writes
- **Build pipeline coder**: `_strip_fences()` in coder.py now handles models that add explanations around code blocks

### Model Registry Fix
- **Removed `qwen3-coder:8b`** — this model does not exist on Ollama (caused silent pull failures)
- **Changed `qwen3-coder:32b` → `qwen3-coder:30b`** — the actual available model (19GB)
- Only `qwen3-coder:30b` and `qwen3-coder:480b` exist as of June 2025

### Crash Protection (KeyboardInterrupt)
- **Ctrl+C during model streaming** no longer crashes the app — returns partial output gracefully
- **Ctrl+C in REPL routing** caught — returns to prompt instead of stack trace
- **General exception handling** in REPL mode dispatch — errors are displayed cleanly
- `_stream()` in ollama_client.py: wrapped in try/except KeyboardInterrupt, shows partial output length

### Strengthened System Prompts
- **AGENTIC_SYSTEM**: Complete rewrite with explicit format rules, correct/incorrect examples, visual section separators
- **Mode 1 (ACTION) prompt**: Stronger ===END=== requirement, explicit "no markdown fences" rule
- Models now see concrete examples of correct vs incorrect file block formatting
- Triple-reinforced: "Remember: ===FILE:=== then raw code then ===END===. No markdown fences inside file blocks. Ever."

### Display Text Cleanup
- Response display now strips all file block formats (not just ===END=== ones) before showing summary panel

## v0.9.8 — Simplified Two-Mode Architecture

Major refactor: JCode now has a clean two-mode architecture. No more intent classification — every message goes straight to the active mode handler.

### Two Modes
- **⚡ Agentic (default)**: Every message triggers autonomous action — classify, generate, auto-run, auto-fix. No ambiguity.
- **💬 Chat**: Conversational mode with reasoning, web search, explanations — but NO file modifications. Fully read-only.
- Switch with `/agentic` or `/chat`

### Slash Commands
- All utility commands now use `/` prefix: `/run`, `/commit`, `/push`, `/pull`, `/status`, `/log`, `/diff`, `/remote`, `/files`, `/tree`, `/plan`, `/models`, `/help`, `/version`, `/update`, `/clear`, `/quit`
- Slash commands work identically in both modes

### Agentic Intelligence
- **Task classification on every request**: `classify_task()` runs before every agentic action — selects optimal models based on complexity × size
- **Model routing**: Shows classification label and routed models for transparency
- **Build detection**: Prompts like "build a tinder for linkedin" auto-route to the full build pipeline (classify → research → plan → generate → review → verify → fix → run)
- **Auto-run after code generation**: After writing files, JCode auto-detects and runs the project
- **Auto-fix loop**: If run fails, JCode feeds the error back to the model and retries (up to 3 attempts)

### Run Detection Improvements
- Node.js entry files (`app.js`, `index.js`, `server.js`) now detected in subdirectories (`server/`, `backend/`, `src/`, `api/`)
- `package.json` `main` field used as fallback when no scripts are defined
- More subdirectories searched for `package.json` (`app/` added)

### Architecture Cleanup
- Removed intent classification system from REPL (no more `classify_intent()` calls)
- Removed `_handle_navigate()` and `_handle_git()` — logic inlined into slash command handler
- Added `_run_fix_prompt()` helper — shared by `/run` auto-fix, build post-fix, and agentic auto-fix
- Chat mode (`_cmd_chat`) is now strictly read-only — strips any ===FILE:=== or ===RUN:=== blocks

### Files Changed
- `jcode/cli.py` — Major refactor: new REPL with slash commands, `_cmd_agentic()` with classification + auto-run, `_agentic_auto_run()`, `_run_fix_prompt()`, read-only `_cmd_chat()`, improved `_detect_run_command()`
- `jcode/__init__.py` — Version bump to 0.9.8
- `pyproject.toml` — Version bump to 0.9.8

---

## v0.9.7 — Model Pull UX Improvements

Bugfix & UX: Model pulling now shows real progress (bytes downloaded, transfer speed), handles Ctrl+C gracefully, and gives better size estimates.

### Model Pull Improvements
- **Real progress tracking**: Shows bytes downloaded and transfer speed (was stuck at 0%)
- **Graceful cancellation**: Press Ctrl+C during download to skip a model and continue with fallback
- **Accurate size estimates**: 70B models → 40GB, 32B → 20GB, 14B → 9GB, 7B → 5GB (was flat 12GB estimate)
- **Better feedback**: "Skipped — will use fallback" when cancelled, "may take 10-30min per model" warning
- **Tip shown**: User is informed they can press Ctrl+C to skip slow downloads

### Technical Changes
- `pull_model()` now uses `Live` progress with `DownloadColumn` and `TransferSpeedColumn`
- Catches `KeyboardInterrupt` at two levels (inner loop + outer function) for clean exit
- Returns `False` on cancellation instead of crashing
- `ensure_models_for_complexity()` handles partial success (some models pulled, some skipped)

### Files Changed
- `jcode/config.py` — Rewritten `pull_model()` with better progress tracking and KeyboardInterrupt handling
- `jcode/ollama_client.py` — Improved size estimates and user feedback in `ensure_models_for_complexity()`

---

## v0.9.6 — Interactive Model Pulling

Feature: JCode now detects missing ideal models and offers to pull them before starting a build. Users can choose to download recommended models or continue with fallback models.

### Interactive Model Management
- Before starting a build, JCode checks if all ideal models for the task classification are installed
- If missing models are detected, shows a table comparing ideal vs. fallback models for each role
- Prompts user: "Pull missing models now?" with Yes/No choice
- If Yes: pulls each missing model with progress bar, then continues with ideal models
- If No: continues immediately with fallback models (no delay, no errors)
- Example: `heavy/large` task recommends `deepseek-r1:70b` (not installed) → offers to pull or falls back to `deepseek-r1:14b`

### New Functions
- `get_ideal_and_actual_models()` — returns role → (ideal_model, actual_model, is_fallback) mapping
- `get_missing_ideal_models()` — returns list of missing ideal models grouped by roles
- `pull_model()` — pulls a model from Ollama registry with progress bar
- Enhanced `ensure_models_for_complexity()` — interactive pre-check with pull option (was a stub)

### User Experience
```
⚠ Some ideal models are not installed:

  Role        Ideal Model           Will Use              Status
  planner     deepseek-r1:70b       deepseek-r1:14b       fallback
  coder       qwen3-coder:32b       qwen2.5-coder:32b     fallback
  reviewer    qwen2.5-coder:14b     qwen2.5-coder:14b     ✓
  analyzer    deepseek-r1:14b       deepseek-r1:14b       ✓

  Missing models: deepseek-r1:70b, qwen3-coder:32b
  Estimated download: ~24GB

Pull missing models now? (if no, will use fallback models) [y/N]:
```

### Files Changed
- `jcode/config.py` — `get_ideal_and_actual_models()`, `get_missing_ideal_models()`, `pull_model()` with progress bar
- `jcode/ollama_client.py` — Enhanced `ensure_models_for_complexity()` with interactive pull workflow

---

## v0.9.5 — Model Fallback Fix

Critical bugfix: `_is_model_local()` incorrectly matched different quantizations of the same base model. When requesting `deepseek-r1:70b` (not installed), it returned True because `deepseek-r1:14b` was installed, causing `model 'deepseek-r1:70b' not found (status code: 404)` errors.

### Model Resolution Fix
- `_is_model_local()` now requires EXACT name match (including quantization tag)
- Previously: `"deepseek-r1:70b"` matched `"deepseek-r1:14b"` via `startswith()` check on base name
- Now: Only matches if full name is in local models (handles `:latest` normalization correctly)
- Fallback now works correctly: `heavy/large` planner requests `reasoning/large` → no exact match → falls back to `deepseek-r1:14b` (reasoning/medium)

### Files Changed
- `jcode/config.py` — Fixed `_is_model_local()` to match full model names, not base prefixes

---

## v0.9.4 — Smart Classification (LLM + Semantic Signals)

Critical fix: "build a tinder for linkedin" was classified as `simple/small` → now correctly classified as `heavy/large`. Short prompts describing complex apps no longer fall through to the default.

### LLM-Based Pre-Classification
- New `_llm_classify()` calls the fastest available model to reason about task complexity before keyword matching
- Uses a structured classification prompt that understands what "build a tinder for X" actually implies (auth, database, matching, profiles, etc.)
- Adds ~1-3s but prevents catastrophic misclassification of short prompts
- Falls back gracefully to keyword-only scoring if no model is available
- LLM result is fused with keyword scoring — the HIGHER classification always wins (err on the side of giving more resources)

### App-Type Complexity Signals
- Added "clone" signals to `_HEAVY_SIGNALS`: "like tinder", "uber for", "a spotify", "an airbnb", etc. — covers 19 major platforms
- Added domain signals to `_HEAVY_SIGNALS`: "social network", "marketplace", "dating app", "matching system", "recommendation engine", "booking system", "fintech", "saas", etc.
- Added domain signals to `_MEDIUM_SIGNALS`: "web app", "mobile app", "game", "analytics", "profile", "search", "forum", etc.
- "build a tinder for linkedin" now matches 2 heavy signals → `heavy/medium` from keywords alone (LLM pushes to `heavy/large`)

### Default Classification Bias Fix
- When no keyword signals match AND no LLM available, default is now `medium/medium` instead of `simple/small`
- Only classify as `simple` when explicit simple signals are present ("simple", "basic", "calculator", "todo", "landing page")
- Short prompts with no signals (e.g., "build a weather app") now get `medium/medium` instead of being penalized

### Classification Examples (Before → After)
| Prompt | Before | After |
|--------|--------|-------|
| "build a tinder for linkedin" | simple/small | heavy/large |
| "build a weather app" | simple/small | medium/medium |
| "build me an uber for dogs" | simple/small | heavy/large |
| "create a social network" | simple/small | medium/medium |
| "build a dating app with matching" | simple/small | heavy/medium |
| "build a simple calculator" | simple/small | simple/small ✓ |
| "make a landing page" | simple/small | simple/small ✓ |

### Files Changed
- `jcode/config.py` — `_llm_classify()`, `_CLASSIFY_PROMPT`, expanded `_HEAVY_SIGNALS` (19 app-type + 12 domain signals), expanded `_MEDIUM_SIGNALS` (12 domain signals), `_classify_from_prompt()` rewritten with 2-phase LLM+keyword fusion, default bias fix

---

## v0.9.3 — Fence Stripping & Execution Safety

Bugfix: models wrap `===FILE:===` content in markdown fences (` ```json ``` `), corrupting files like `package.json`. Commands now stop on failure instead of blindly continuing.

### Markdown Fence Stripping
- New `_strip_content_fences()` strips ` ```lang ``` ` from file content inside `===FILE:===` blocks
- Handles `json`, `javascript`, `python`, `typescript`, and bare ` ``` ` fences
- Applied automatically in `_apply_file_changes()` before writing to disk
- Fixes: `package.json` written with backtick fences → `npm install EJSONPARSE`

### Command Execution: Stop on Failure
- `_apply_run_commands()` now stops executing remaining `===RUN:===` commands when one fails
- Prevents cascading failures (e.g., `npm start` running after `npm install` fails)
- Shows "Stopping — fix the error before continuing" message
- `===BACKGROUND:===` commands are not affected (they don't block)

### Run Command Detection Improvements
- Added Node.js entry file fallback: `app.js`, `index.js`, `server.js`, `main.js` detected even without `package.json`
- `_detect_run_command` now logs a warning when `package.json` has invalid JSON instead of silently failing
- Detection order: Python entry → `package.json` scripts → HTML → Node.js entry → any `.py` file

### Files Changed
- `jcode/cli.py` — `_strip_content_fences()`, stop-on-failure in `_apply_run_commands()`, Node.js fallback in `_detect_run_command()`, JSON parse error logging

---

## v0.9.2 — Autonomous Execution

Critical fix: agent mode now actually executes commands and builds projects end-to-end instead of just printing instructions.

### Intent Classification Fix
- Added `_BUILD_PATTERNS` — "i want you to build an app", "create a website", "make me a dashboard" now correctly classify as BUILD (previously fell through to CHAT)
- BUILD patterns score 1.5× and always win over CHAT in tie-breaking
- Added RUN patterns: "get the project running", "auto run", "run the commands", "install and run"
- "i want you to build an app that shows weather info" now triggers the full build pipeline instead of a chat response

### Agent Mode Routes All Input to Agentic Handler
- In agent mode, CHAT-classified input now routes to `_cmd_agentic()` instead of `_cmd_chat()`
- This means ANY request in agent mode gets autonomous file creation + command execution
- Chat mode still uses `_cmd_chat()` for conversational responses

### Command Execution (`===RUN:===` / `===BACKGROUND:===`)
- New `_apply_run_commands()` function parses and executes shell commands from model output
- `===RUN: command===` — synchronous execution with output display (120s timeout)
- `===BACKGROUND: command===` — background processes for servers/watchers
- Safety filter blocks dangerous commands (rm -rf /, sudo rm, mkfs, dd, fork bombs)
- Output capped at 20 lines per command for clean display
- Wired into both `_cmd_agentic()` and `_cmd_chat()` — files applied before commands run

### Updated Prompts
- `AGENTIC_SYSTEM`: now instructs model to emit `===RUN:===` blocks for package installation, project setup, and server startup — never tell user to run manually
- `AGENTIC_TASK`: changed "Modification Request" to "Request", added autonomous mode instructions
- `CHAT_SYSTEM` MODE 3: updated to emit `===RUN:===` blocks instead of showing commands to copy-paste

### Files Changed
- `jcode/intent.py` — Added `_BUILD_PATTERNS`, expanded `_RUN_PATTERNS`, BUILD always wins over CHAT
- `jcode/cli.py` — CHAT→agentic routing in agent mode, `_apply_run_commands()`, command block stripping in display
- `jcode/prompts.py` — `===RUN:===`/`===BACKGROUND:===` format in AGENTIC_SYSTEM, CHAT_SYSTEM, AGENTIC_TASK

---

## v0.9.1 — Spec Contracts, RAG Memory & Structured Errors

Implements the frontier-grade coding agent blueprint: planner outputs formal specs, coder enforces them as contracts, embedding-based RAG memory provides cross-file context, and structured error parsing enables smarter fix loops.

### Spec-as-Contract Pipeline
- **Planner** now outputs formal spec fields: `database_schema`, `api_surface`, `auth_flow`, `deployment`
- **Coder** enforces spec compliance: "NO STACK DRIFT — if the spec says React, don't use Vue"
- `get_spec_details()` extracts spec from plan and injects into every CODER_TASK prompt
- Simple projects gracefully skip formal spec fields

### Embedding-Based RAG Memory (`memory.py`)
- New `ProjectMemory` class with `FileEmbedding` dataclass
- `index_files()`: embeds file summaries with MD5 change detection (skips unchanged files)
- `retrieve()`: cosine similarity search over embeddings
- `get_relevant_context()`: formatted RAG context for prompt injection
- Lazy initialization — only activates when an embedding model is installed
- Full serialization via `to_dict()` / `from_dict()` for session persistence
- Graceful fallback: all methods return empty results if no embedding model available

### RAG Integration
- Memory indexed before first wave and re-indexed after each generation wave
- Coder receives "Semantically Related" context from RAG alongside dependency context
- Session save/load preserves vector memory embeddings
- `ctx.index_memory()` and `ctx.get_relevant_files()` convenience methods on ContextManager

### Expanded Model Registry
- **Coding**: Added `qwen3-coder:32b/8b` (priority 5 — highest), `deepseek-coder:33b/6.7b`
- **Reasoning**: Added `deepseek-r1:70b` (priority 5 for large reasoning tasks)
- **Summarizer**: Added `phi4:14b`, `phi3.5:latest`, `gemma3:4b` — new category
- **Embedding**: Added `all-minilm:latest`, `nomic-embed-text:latest` — new category
- **General**: Added `llama3.3:latest`, `llama3.1:latest`
- `ModelSpec` extended with `is_embedding: bool` field
- New helpers: `get_embedding_model()`, `get_summarizer_model()`

### Structured Error Parsing
- `VerificationResult.structured_errors` property parses raw error output
- Extracts Python errors (`File "path", line N`), JS/ruff errors (`path:line:col: message`)
- Returns `{file, line, category, message}` dicts for targeted fix routing

### Size Threading
- `size` parameter now threaded through entire pipeline: planner → coder → reviewer → analyzer → iteration
- All `get_model_for_role()` calls include both complexity and size
- Display shows `Classification: complexity/size` throughout

### Files Changed
- `jcode/memory.py` — **New**: Full RAG memory module (230+ lines)
- `jcode/config.py` — Expanded MODEL_REGISTRY, added embedding/summarizer categories and helpers
- `jcode/prompts.py` — Planner spec schema, coder spec enforcement, CODER_TASK `{spec_details}`
- `jcode/context.py` — ProjectMemory integration, spec extraction, session persistence
- `jcode/coder.py` — RAG context injection, size threading, spec_details in prompts
- `jcode/executor.py` — structured_errors property on VerificationResult
- `jcode/iteration.py` — Memory indexing per wave, size threading
- `jcode/planner.py` — Size threading, display update
- `jcode/reviewer.py` — Size threading
- `jcode/analyzer.py` — Size threading

---

## v0.9.0 — Multi-Model Orchestrator

Major architecture redesign — JCode becomes an intelligent orchestrator that classifies tasks by complexity and size, then routes to the best available model for each role.

### Task Classification System
- **Complexity levels**: Heavy, Medium, Simple — detected from prompt keywords and project context
- **Size levels**: Large, Medium, Small — based on file count and scope
- **Matrix routing**: Each (complexity × size) combination maps to optimal models per role (planner, coder, reviewer, analyzer)
- Fast path for simple tasks, deep research pipeline for heavy tasks

### Multi-Model Registry
- `ModelSpec` dataclass: name, category, tier, supports_thinking, supports_tools, context_default, priority
- `MODEL_REGISTRY`: extensible dict of all known models with capabilities
- `MODEL_CATEGORIES`: coding, reasoning, agentic — each listing available models
- Automatic fallback chains when preferred models aren't installed
- `get_model_for_role()`: resolves best available model with graceful degradation

### Simplified Modes
- Two modes: **agent** and **chat** — switch by typing `agent` or `chat`
- Removed legacy mode complexity (plan/agentic/etc.)
- Agent mode: full build pipeline with classification-based routing
- Chat mode: conversational coding assistance

### Research Pipeline (Heavy Tasks)
- `research_pipeline()`: parallel web search + documentation fetching
- Uses `ThreadPoolExecutor` for concurrent research
- `RESEARCH_SYNTHESIS_SYSTEM` prompt synthesizes findings into actionable context
- Automatically triggered when task is classified as heavy

### Enhanced Prompts
- All role prompts (Planner, Coder, Reviewer, Analyzer) rewritten with stronger guidelines
- Chat prompt enhanced with runtime error handling instructions
- Agentic prompt enhanced for orchestrator behavior

### New Commands
- `models` — Shows available models, categories, and routing table
- `agent` / `chat` — Direct mode switching

### Rewritten Files
- `jcode/config.py` — Complete rewrite: enums, ModelSpec, MODEL_REGISTRY, classify_task(), ROLE_ROUTING, get_model_for_role(), describe_model_plan()
- `jcode/ollama_client.py` — Complete rewrite: _is_reasoning_model(), _get_options_for_model(), model-category-aware option tuning
- `jcode/prompts.py` — Complete rewrite: enhanced all role prompts, added RESEARCH_SYNTHESIS_SYSTEM

### Updated Files
- `jcode/cli.py` — Build pipeline uses classification, mode switching, models command
- `jcode/intent.py` — Added Intent.MODE, agent/chat as exact commands
- `jcode/web.py` — Added research_pipeline() for heavy task research
- `jcode/context.py` — Added get_size() method
- `install.sh` / `install.ps1` — Updated model lists (+ deepseek-r1:14b)

### Backward Compatibility
- Legacy `detect_complexity()` wrapper preserved
- Legacy model constants (PLANNER_MODEL, etc.) preserved as aliases
- Default `size="medium"` parameter ensures existing callers work unchanged
- Unchanged modules: planner.py, iteration.py, coder.py, reviewer.py, analyzer.py, file_manager.py, settings.py, executor.py

---

## v0.8.1 — Speed Fix

### Fixed
- Replaced deepseek-r1 with qwen2.5-coder for all roles — eliminates 2+ minute thinking pauses
- Added `<think>` tag filtering for reasoning model output cleanup

---

## v0.8.0 — Performance Overhaul

### Fixed
- Fixed 5+ minute builds caused by model pulling on every request
- Implemented never-pull policy — uses only locally available models
- Optimized model selection to prefer already-loaded models

---

## v0.7.0 — CWD-Aware Agent

### Added
- CWD-aware operation — builds in current working directory
- Git integration with auto-commit on successful builds
- Project scanning — detects existing project structure
- Dual modes: plan (structured) and agentic (free-form)

---

## v0.6.0 — Smart Model Tiering

### Added
- Smart model tiering — selects model size based on task complexity
- Parallel file generation for independent tasks
- Task Graph Engine for dependency-aware execution

---

## v0.2.0 — Architecture Overhaul

Complete rewrite implementing a 4-role multi-model system with structured memory.

### New Architecture
- **4-Role System**: Planner, Coder, Reviewer, Analyzer — each with isolated system prompts
- **DAG Task Tree**: Tasks have dependencies; topological execution order
- **Structured Memory**: Architecture summary + file index + failure log (replaces raw context dumps)
- **Verification Pipeline**: Syntax → lint → type check per file
- **Self-Correction Loop**: Analyze error → patch → re-verify (up to 3 attempts)
- **Patch Mode**: Targeted minimal fixes instead of full file regeneration

### New Files
- `jcode/prompts.py` — All 4 role prompt templates with JSON schemas
- `jcode/reviewer.py` — Pre-execution code review (catches bugs before running)
- `jcode/analyzer.py` — Error diagnosis producing structured fix instructions
- `jcode/executor.py` — Multi-language verification pipeline

### Rewritten Files
- `jcode/config.py` — TaskStatus enum, TaskNode dataclass, 4 model configs
- `jcode/ollama_client.py` — Unified `call_model(role)` dispatcher
- `jcode/context.py` — Full structured memory engine with DAG support
- `jcode/planner.py` — DeepSeek-R1 think-tag stripping, architecture output
- `jcode/coder.py` — `generate_file()` + `patch_file()` with structured context
- `jcode/iteration.py` — DAG-based orchestration (generate→review→verify→fix)
- `jcode/cli.py` — All commands rebuilt, `build` replaces free-text prompt

### Preserved Files
- `jcode/settings.py` — User settings (unchanged from v0.1)
- `jcode/file_manager.py` — File I/O (unchanged)

---

## v0.1.1 — Bug Fixes & Enhancements

### Fixed
- `OSError: [Errno 30] Read-only file system` when entering `/first_project`
- Path expansion now handles `~`, relative paths, and validates writability

### Added
- First-run setup wizard for default output directory
- Project tracking and resume capability (`projects`, `resume` commands)
- Adaptive context windows based on project complexity
- Auto-save sessions on file generation and exit
- `settings` command for viewing/editing configuration

---

## v0.1.0 — Initial Release

- Dual-model architecture: DeepSeek-R1 (planning) + Qwen2.5-Coder (generation)
- Rich CLI with interactive prompt
- Linear iteration loop with error feedback
- File system manager with Rich tree display
- Basic session save/load
