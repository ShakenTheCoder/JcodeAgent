# Changelog

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
