# Changelog

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
