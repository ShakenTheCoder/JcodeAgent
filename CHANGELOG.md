# Changelog

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
