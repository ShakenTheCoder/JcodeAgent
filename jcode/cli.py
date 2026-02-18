"""
JCode CLI v0.9.8 — Intelligent multi-model orchestrator.

JCode lives inside your project directory. Two modes:
  AGENTIC (default) — every message triggers autonomous action:
    classify → research → plan → generate → auto-run → auto-fix → commit
  CHAT — conversational: reasoning, websearch, explanations — no file changes

Switch modes with /agentic or /chat.
Slash commands (/help, /run, /commit, etc.) work in both modes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.history import InMemoryHistory

from jcode import __version__
from jcode.config import (
    ProjectState, classify_task, get_model_for_role, get_all_required_models,
    describe_model_plan, detect_complexity,
)
from jcode.context import ContextManager
from jcode.planner import create_plan
from jcode.iteration import execute_plan
from jcode.file_manager import print_tree
from jcode.ollama_client import check_ollama_running, call_model, ensure_models_for_complexity, list_available_models
from jcode.settings import SettingsManager
from jcode.executor import set_autonomous
from jcode.web import set_internet_access, web_search, fetch_page, search_and_summarize, research_task, is_internet_allowed
from jcode.prompts import (
    CHAT_SYSTEM, CHAT_CONTEXT, AGENTIC_SYSTEM, AGENTIC_TASK,
    RESEARCH_SYSTEM, RESEARCH_TASK, PLANNER_RESEARCH_CONTEXT,
)
from jcode.intent import _BUILD_PATTERNS
from jcode.scanner import scan_project, detect_project_type, scan_files
from jcode import git_manager

console = Console()

# ═══════════════════════════════════════════════════════════════════
# ASCII Art
# ═══════════════════════════════════════════════════════════════════

BANNER = r"""
     ██╗ ██████╗ ██████╗ ██████╗ ███████╗
     ██║██╔════╝██╔═══██╗██╔══██╗██╔════╝
     ██║██║     ██║   ██║██║  ██║█████╗
██   ██║██║     ██║   ██║██║  ██║██╔══╝
╚█████╔╝╚██████╗╚██████╔╝██████╔╝███████╗
 ╚════╝  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝"""

HELP_TEXT = """
[bold white]JCode — Two Modes[/bold white]

  [bold cyan]⚡ Agentic[/bold cyan] (default)  Every message triggers autonomous action.
                       JCode classifies, plans, generates code, runs it,
                       and auto-fixes errors — fully autonomous.

  [bold cyan]💬 Chat[/bold cyan]               Conversational mode. JCode reasons, searches
                       the web, explains — but does NOT modify files.

[bold white]Slash Commands[/bold white]  (work in both modes)

  [bold cyan]Modes[/bold cyan]
  [cyan]/agentic[/cyan]           Switch to agentic mode
  [cyan]/chat[/cyan]              Switch to chat mode

  [bold cyan]Project[/bold cyan]
  [cyan]/run[/cyan]               Detect and run the project
  [cyan]/test[/cyan]              Run project tests
  [cyan]/files[/cyan]             List all project files
  [cyan]/tree[/cyan]              Show directory tree
  [cyan]/plan[/cyan]              Show current build plan
  [cyan]/models[/cyan]            Show available models and routing

  [bold cyan]Git[/bold cyan]
  [cyan]/commit[/cyan] [message]  Stage all changes and commit
  [cyan]/push[/cyan]              Push to remote
  [cyan]/pull[/cyan]              Pull from remote
  [cyan]/status[/cyan]            Show git status
  [cyan]/log[/cyan]               Show recent commits
  [cyan]/diff[/cyan]              Show uncommitted changes
  [cyan]/remote[/cyan] <url>      Set up GitHub remote

  [bold cyan]Utility[/bold cyan]
  [cyan]/version[/cyan]           Show JCode version
  [cyan]/update[/cyan]            Update JCode to latest version
  [cyan]/clear[/cyan]             Clear the terminal
  [cyan]/help[/cyan]              Show this help
  [cyan]/quit[/cyan]              Exit
"""


# ═══════════════════════════════════════════════════════════════════
# Interactive selectors
# ═══════════════════════════════════════════════════════════════════

def _select_one(title: str, options: list[str]) -> int | None:
    """Arrow keys to move, enter to confirm. Returns 0-based index or None."""
    try:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
    except Exception:
        return _select_one_fallback(title, options)

    selected = 0

    def _render():
        for _ in range(len(options) + 1):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.write(f"  {title}\n")
        for i, opt in enumerate(options):
            marker = "[cyan]>[/cyan] " if i == selected else "  "
            style = "bold white" if i == selected else "dim"
            console.print(f"    {marker}[{style}]{opt}[/{style}]", highlight=False)
        sys.stdout.flush()

    console.print(f"  {title}")
    for i, opt in enumerate(options):
        marker = "[cyan]>[/cyan] " if i == selected else "  "
        style = "bold white" if i == selected else "dim"
        console.print(f"    {marker}[{style}]{opt}[/{style}]", highlight=False)

    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\r" or ch == "\n":
                break
            if ch == "\x03":
                selected = None
                break
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    selected = (selected - 1) % len(options)
                elif seq == "[B":
                    selected = (selected + 1) % len(options)
            _render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    console.print()
    return selected


def _select_one_fallback(title: str, options: list[str]) -> int | None:
    """Simple numbered fallback for non-TTY."""
    console.print(f"\n  {title}\n")
    for i, opt in enumerate(options, 1):
        console.print(f"    [cyan]{i}[/cyan]  {opt}")
    console.print()
    pick = pt_prompt("  > ").strip()
    try:
        idx = int(pick) - 1
        if 0 <= idx < len(options):
            return idx
    except ValueError:
        pass
    return 0


# ═══════════════════════════════════════════════════════════════════
# Logging helper
# ═══════════════════════════════════════════════════════════════════

def _log(tag: str, message: str) -> None:
    """Structured log line: [HH:MM:SS] TAG  message"""
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"  [dim]{ts}[/dim]  [cyan]{tag:<10}[/cyan]  {message}")


# ═══════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════

def main():
    """Entry point for the JCode CLI — CWD-aware, single REPL."""
    settings_mgr = SettingsManager()
    history = InMemoryHistory()

    # -- First-run: create config dir
    if settings_mgr.is_first_run():
        settings_mgr.config_dir.mkdir(parents=True, exist_ok=True)
        settings_mgr.save_settings()

    # -- Banner
    console.print(BANNER, style="bold cyan", highlight=False)
    console.print(
        f"  v{__version__}  |  your local, unlimited & private software engineer",
        style="dim white",
    )
    console.print()

    # -- Check Ollama
    if not check_ollama_running():
        console.print("  [dim]Ollama is not running.[/dim]")
        console.print("  [dim]Start it with:[/dim]  [cyan]ollama serve[/cyan]")
        console.print(
            "  [dim]Then pull models:[/dim]  [cyan]ollama pull qwen2.5-coder:14b && ollama pull qwen2.5-coder:7b[/cyan]",
        )
        sys.exit(1)
    console.print("  [cyan]Ollama connected[/cyan]")

    # Show available models
    available = list_available_models()
    model_count = len([m for m in available if m])
    console.print(f"  [dim]Multi-model routing enabled — {model_count} model(s) available[/dim]")

    # -- Detect project directory (CWD)
    project_dir = Path.cwd().resolve()
    console.print(f"  [cyan]Project directory:[/cyan] {project_dir}")

    # -- Git check
    if git_manager.git_available():
        if git_manager.is_git_repo(project_dir):
            branch = git_manager.get_current_branch(project_dir)
            remote = git_manager.get_remote_url(project_dir)
            console.print(f"  [cyan]Git:[/cyan] {branch}" + (f" → {remote}" if remote else ""))
        else:
            console.print(f"  [dim]Git: not initialized (use 'commit' to auto-init)[/dim]")
    else:
        console.print(f"  [dim]Git: not installed[/dim]")

    # -- Permissions (only ask if never asked before)
    console.print()
    _check_permissions(settings_mgr)

    # -- Scan project
    has_files = any(True for p in project_dir.iterdir() if not p.name.startswith("."))
    if has_files:
        ctx = scan_project(project_dir)
        # Try to load existing session
        session_file = project_dir / ".jcode_session.json"
        if session_file.exists():
            try:
                ctx = ContextManager.load_session(session_file)
                ctx.state.output_dir = project_dir
                _scan_project_files(ctx, project_dir)
                console.print(f"  [dim]Resumed previous session[/dim]")
            except Exception:
                pass
    else:
        state = ProjectState(
            name=project_dir.name,
            description="New project",
            output_dir=project_dir,
        )
        ctx = ContextManager(state)
        console.print(f"  [dim]Empty directory — ready to build[/dim]")

    # -- Mode
    mode = settings_mgr.settings.default_mode
    # Normalize legacy "agentic" to "agent"
    if mode == "agentic":
        mode = "agent"
    console.print(f"  [cyan]Mode:[/cyan] {mode}  [dim](/agentic or /chat to switch)[/dim]")

    # -- Hint
    console.print()
    console.print(
        "  Type naturally or use [cyan]/help[/cyan] for commands.\n"
    )

    # -- Main REPL
    _repl(ctx, project_dir, settings_mgr, mode, history)


# ═══════════════════════════════════════════════════════════════════
# Permissions (persisted — asked once, remembered forever)
# ═══════════════════════════════════════════════════════════════════

def _check_permissions(settings_mgr: SettingsManager) -> None:
    """Ask for autonomy + internet permissions if not already granted."""

    # -- Autonomy
    if settings_mgr.settings.autonomous_access is None:
        console.print(
            "  [bold white]JCode needs permission to install packages and run[/bold white]"
        )
        console.print(
            "  [bold white]terminal commands on your behalf for full autonomy.[/bold white]"
        )
        console.print()

        choice = _select_one("Grant autonomous access?", [
            "Yes — install packages and run commands automatically",
            "No  — ask me before each action",
        ])
        settings_mgr.settings.autonomous_access = (choice == 0)
        settings_mgr.save_settings()

    set_autonomous(settings_mgr.settings.autonomous_access)

    if settings_mgr.settings.autonomous_access:
        console.print("  [cyan]Autonomous mode: on[/cyan]")
    else:
        console.print("  [dim]Autonomous mode: off (will ask before actions)[/dim]")

    # -- Internet
    if settings_mgr.settings.internet_access is None:
        console.print()
        console.print(
            "  [bold white]JCode can search the web and read documentation[/bold white]"
        )
        console.print(
            "  [bold white]to build better projects using real-world knowledge.[/bold white]"
        )
        console.print()

        choice = _select_one("Grant internet access?", [
            "Yes — search the web and read documentation",
            "No  — work offline only",
        ])
        settings_mgr.settings.internet_access = (choice == 0)
        settings_mgr.save_settings()

    set_internet_access(settings_mgr.settings.internet_access)

    if settings_mgr.settings.internet_access:
        console.print("  [cyan]Internet access: on[/cyan]")
    else:
        console.print("  [dim]Internet access: off[/dim]")
    console.print()


# ═══════════════════════════════════════════════════════════════════
# Build-detection heuristic for agentic mode
# ═══════════════════════════════════════════════════════════════════

def _looks_like_build(user_input: str) -> bool:
    """Detect if user wants to build a full project from scratch.

    When True, agentic mode routes to the full build pipeline
    (classify → research → plan → generate → review → verify → fix → run).
    """
    lower = user_input.lower().strip()

    # Standard build patterns from intent module
    for pattern in _BUILD_PATTERNS:
        if re.search(pattern, lower):
            return True

    # App-type names strongly imply building from scratch
    _APP_SIGNALS = [
        r"\b(?:tinder|uber|airbnb|instagram|twitter|whatsapp|spotify|netflix|"
        r"amazon|slack|discord|reddit|youtube|facebook|linkedin|trello|notion|"
        r"shopify|etsy|doordash|grubhub|venmo|paypal)\b.*\b(?:for|like|clone)\b",
        r"\b(?:for|like|clone)\b.*\b(?:tinder|uber|airbnb|instagram|twitter|"
        r"whatsapp|spotify|netflix|amazon|slack|discord|reddit|youtube|facebook|"
        r"linkedin|trello|notion|shopify|etsy|doordash|grubhub|venmo|paypal)\b",
        r"\b(?:dating|ride.?sharing|food.?delivery|social.?media|e.?commerce|"
        r"marketplace|messaging|streaming)\s+(?:app|platform|site|website|service)\b",
    ]
    for pattern in _APP_SIGNALS:
        if re.search(pattern, lower):
            return True

    return False


# ═══════════════════════════════════════════════════════════════════
# Main REPL — two modes, slash commands
# ═══════════════════════════════════════════════════════════════════

def _repl(
    ctx: ContextManager,
    project_dir: Path,
    settings_mgr: SettingsManager,
    mode: str,
    history: InMemoryHistory,
) -> None:
    """Two-mode REPL: agentic (default) acts on every message, chat reasons without changes.

    Slash commands (/help, /run, /commit, etc.) work identically in both modes.
    Everything else is routed to the active mode handler.
    """
    proj_name = ctx.state.name or project_dir.name

    while True:
        try:
            mode_indicator = "⚡" if mode == "agent" else "💬"
            user_input = pt_prompt(
                f"{mode_indicator} {proj_name}> ", history=history,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            _auto_save(ctx, project_dir)
            break

        if not user_input:
            continue

        # ── Slash commands (work in both modes) ──────────────────
        if user_input.startswith("/"):
            cmd = user_input[1:].strip()
            lower_cmd = cmd.lower()

            # Mode switching
            if lower_cmd in ("agentic", "agent"):
                mode = "agent"
                settings_mgr.settings.default_mode = mode
                settings_mgr.save_settings()
                console.print("  ⚡ [cyan]Switched to agentic mode[/cyan]")
                continue
            elif lower_cmd == "chat":
                mode = "chat"
                settings_mgr.settings.default_mode = mode
                settings_mgr.save_settings()
                console.print("  💬 [cyan]Switched to chat mode[/cyan]")
                continue

            # Quit
            elif lower_cmd in ("quit", "exit", "q"):
                _auto_save(ctx, project_dir)
                console.print("  [dim]Goodbye.[/dim]\n")
                break

            # Project commands
            elif lower_cmd == "run":
                _cmd_run(ctx, project_dir, settings_mgr)
                continue
            elif lower_cmd in ("test", "tests"):
                _cmd_test(project_dir, ctx)
                continue
            elif lower_cmd == "rebuild":
                _log("REBUILD", "Re-running build pipeline")
                execute_plan(ctx, project_dir)
                _auto_save(ctx, project_dir)
                _git_auto_commit(project_dir, settings_mgr, "rebuild project")
                continue
            elif lower_cmd == "files":
                _cmd_files(project_dir)
                continue
            elif lower_cmd == "tree":
                _cmd_tree(ctx, project_dir)
                continue
            elif lower_cmd == "plan":
                _cmd_plan(ctx)
                continue
            elif lower_cmd == "models":
                _cmd_models()
                continue

            # Git commands
            elif lower_cmd in ("commit", "save"):
                _ensure_git_repo(project_dir)
                ok, result = git_manager.auto_commit(project_dir)
                if ok:
                    _log("GIT", f"Committed: {result}")
                else:
                    console.print(f"  [dim]{result}[/dim]")
                continue
            elif lower_cmd.startswith("commit "):
                _ensure_git_repo(project_dir)
                message = cmd.split(None, 1)[1].strip() if " " in cmd else "update"
                ok, result = git_manager.commit(project_dir, message)
                if ok:
                    _log("GIT", f"Committed ({result}): {message}")
                else:
                    console.print(f"  [dim]{result}[/dim]")
                continue
            elif lower_cmd == "push":
                _ensure_git_repo(project_dir)
                ok, result = git_manager.push(project_dir)
                if ok:
                    _log("GIT", result)
                else:
                    console.print(f"  [yellow]{result}[/yellow]")
                    if "No configured push destination" in result or "no upstream" in result.lower():
                        console.print("  [dim]Set a remote: /remote <github-url>[/dim]")
                continue
            elif lower_cmd == "pull":
                _ensure_git_repo(project_dir)
                ok, result = git_manager.pull(project_dir)
                if ok:
                    _log("GIT", f"Pulled: {result}")
                    _scan_project_files(ctx, project_dir)
                else:
                    console.print(f"  [yellow]{result}[/yellow]")
                continue
            elif lower_cmd == "status":
                git_manager.print_status(project_dir)
                continue
            elif lower_cmd == "log":
                _ensure_git_repo(project_dir)
                git_manager.print_log(project_dir)
                continue
            elif lower_cmd == "diff":
                _ensure_git_repo(project_dir)
                diff_output = git_manager.diff(project_dir)
                if diff_output:
                    console.print(Panel(diff_output, title="Git Diff", border_style="dim"))
                else:
                    console.print("  [dim]No uncommitted changes[/dim]")
                continue
            elif lower_cmd.startswith("remote "):
                _ensure_git_repo(project_dir)
                url = cmd.split(None, 1)[1].strip()
                if git_manager.setup_github_remote(project_dir, url):
                    _log("GIT", f"Remote set to: {url}")
                continue

            # Utility
            elif lower_cmd == "help":
                console.print(HELP_TEXT, highlight=False)
                continue
            elif lower_cmd == "clear":
                console.clear()
                continue
            elif lower_cmd == "version":
                console.print(f"\n  [bold cyan]JCode[/bold cyan] [white]v{__version__}[/white]")
                console.print(f"  [dim]https://github.com/ShakenTheCoder/JcodeAgent[/dim]\n")
                continue
            elif lower_cmd == "update":
                _cmd_update()
                continue
            elif lower_cmd == "uninstall":
                _cmd_uninstall(settings_mgr)
                continue
            else:
                console.print(f"  [dim]Unknown command: /{lower_cmd}[/dim]")
                console.print(f"  [dim]Type /help for available commands[/dim]")
                continue

        # ── Mode-based routing (non-slash input) ─────────────────
        try:
            if mode == "agent":
                # Agentic mode: every message triggers action
                if _looks_like_build(user_input):
                    # Full build pipeline for new-project requests
                    ctx, project_dir = _cmd_build(user_input, ctx, project_dir, settings_mgr)
                    proj_name = ctx.state.name or project_dir.name
                else:
                    # Autonomous modify/create/fix/run
                    _cmd_agentic(ctx, project_dir, user_input, settings_mgr)
            else:
                # Chat mode: reason, explain, search — no file changes
                _cmd_chat(ctx, project_dir, user_input)
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠ Interrupted[/yellow]")
            continue
        except Exception as exc:
            console.print(f"\n[red]✗ Error: {exc}[/red]")
            console.print("[dim]  You can try again or use /help for commands.[/dim]")
            continue


def _ensure_git_repo(project_dir: Path) -> None:
    """Ensure git is available and the project has a repo."""
    if not git_manager.ensure_git():
        return
    if not git_manager.is_git_repo(project_dir):
        _log("GIT", "Initializing git repository")
        git_manager.init_repo(project_dir, initial_commit=True)


def _git_auto_commit(
    project_dir: Path,
    settings_mgr: SettingsManager,
    description: str = "",
) -> None:
    """Auto-commit if enabled in settings."""
    if not settings_mgr.settings.git_auto_commit:
        return
    if not git_manager.git_available():
        return

    # Initialize repo if needed
    if not git_manager.is_git_repo(project_dir):
        git_manager.init_repo(project_dir, initial_commit=False)

    ok, result = git_manager.auto_commit(project_dir, description)
    if ok and result != "nothing to commit":
        _log("GIT", f"Auto-committed: {result}")

    # Auto-push if enabled
    if settings_mgr.settings.git_auto_push and ok:
        remote = git_manager.get_remote_url(project_dir)
        if remote:
            push_ok, push_result = git_manager.push(project_dir)
            if push_ok:
                _log("GIT", f"Auto-pushed")


# ═══════════════════════════════════════════════════════════════════
# Build command — full autonomous pipeline
# ═══════════════════════════════════════════════════════════════════

def _cmd_build(
    prompt: str,
    ctx: ContextManager,
    project_dir: Path,
    settings_mgr: SettingsManager,
) -> tuple[ContextManager, Path]:
    """Full autonomous pipeline: classify → research → plan → generate → review → verify → fix.
    Operates inside the current project directory (CWD)."""

    console.print(f"\n  [dim]Building in:[/dim] [cyan]{project_dir}[/cyan]")

    # Classify the task (complexity × size)
    classification = classify_task(prompt=prompt)
    console.print(f"  [dim]Classification:[/dim] [bold]{classification.label}[/bold]"
                  f"  [dim](complexity={classification.complexity.value}, size={classification.size.value})[/dim]")

    # Show model routing for this classification
    model_plan = describe_model_plan(classification.complexity.value, classification.size.value)
    console.print(f"  [dim]Models:[/dim]")
    for role, model in model_plan.items():
        console.print(f"    [dim]{role:>8}:[/dim]  [cyan]{model}[/cyan]")

    if classification.skip_review:
        console.print(f"  [dim]Review:[/dim] [yellow]skipped[/yellow] (simple task)")
    if not classification.skip_research:
        console.print(f"  [dim]Research:[/dim] [green]enabled[/green] (heavy task)")

    # Pre-check models
    complexity_str = classification.complexity.value
    size_str = classification.size.value
    _log("MODELS", f"Ensuring models for '{classification.label}'...")
    ensure_models_for_complexity(complexity_str, size_str)

    slug = _slugify(prompt[:40])
    state = ProjectState(
        name=slug,
        description=prompt,
        output_dir=project_dir,
        complexity=complexity_str,
        size=size_str,
    )
    ctx = ContextManager(state)

    # -- Phase 0: Research (heavy tasks only)
    research_brief = ""
    if not classification.skip_research and is_internet_allowed():
        console.print()
        _log("PHASE 0", "Researching — web search, docs, best practices")
        research_brief = research_task(prompt)
        if research_brief and not research_brief.startswith("["):
            # Summarize research using a reasoning model if available
            _log("RESEARCH", f"Gathered {len(research_brief)} chars of research context")

    # -- Phase 1: Planning
    console.print()
    _log("PHASE 1", "Planning project architecture")

    # For heavy tasks with research, augment the planning prompt
    plan_prompt = prompt
    if research_brief and not research_brief.startswith("["):
        plan_prompt = prompt + PLANNER_RESEARCH_CONTEXT.format(research_brief=research_brief[:8000])

    plan = create_plan(plan_prompt, ctx)
    ctx.set_plan(plan)

    # Re-classify with full plan for more accurate routing
    refined = classify_task(plan=plan)
    if refined.label != classification.label:
        console.print(f"  [dim]Refined classification:[/dim] [bold]{refined.label}[/bold]")
        classification = refined
        ctx.state.complexity = classification.complexity.value
        ctx.state.size = classification.size.value

    task_count = len(plan.get("tasks", []))
    _log("PLAN", f"{task_count} task(s) created")

    for t in plan.get("tasks", []):
        deps = f" [dim](after {t.get('depends_on', [])})[/dim]" if t.get("depends_on") else ""
        console.print(f"          {t.get('id', '?')}. [white]{t.get('file', '')}[/white]{deps}")

    # -- Phase 2: Building
    console.print()
    _log("PHASE 2", "Building — generate, review, verify, fix")
    success = execute_plan(ctx, project_dir)

    # -- Save metadata
    settings_mgr.save_project_metadata({
        "name": plan.get("project_name", slug),
        "prompt": prompt,
        "output_dir": str(project_dir),
        "last_modified": datetime.now().isoformat(),
        "completed": success,
        "classification": classification.label,
    })

    # -- Final status
    console.print()
    if success:
        _log("DONE", "Build complete — all files verified")
    else:
        _log("DONE", "Build finished with issues — type 'plan' to inspect")

    _auto_save(ctx, project_dir)

    # -- Phase 3: Post-build runtime verification
    if success:
        run_cmd, run_cwd = _detect_run_command(project_dir)
        if run_cmd:
            console.print()
            _log("PHASE 3", "Runtime verification -- running the project to check for errors")
            _install_deps_if_needed(project_dir)

            exit_code, run_output = _run_and_capture(run_cmd, run_cwd)

            if exit_code not in (0, -2) and run_output.strip():
                _log("VERIFY", f"Runtime error detected (exit code {exit_code})")
                MAX_POST_BUILD_FIXES = 3
                for fix_attempt in range(1, MAX_POST_BUILD_FIXES + 1):
                    _log("FIX", f"Post-build fix {fix_attempt}/{MAX_POST_BUILD_FIXES}")
                    error_msg = run_output[-3000:]
                    fix_prompt = (
                        f"The project was just built but fails to run. "
                        f"EXACT error output:\n\n```\n{error_msg}\n```\n\n"
                        f"Command: {' '.join(run_cmd)}\n"
                        f"Fix the code. Output corrected files with ===FILE:=== format."
                    )
                    _run_fix_prompt(ctx, project_dir, fix_prompt)
                    _install_deps_if_needed(project_dir)

                    exit_code, run_output = _run_and_capture(run_cmd, run_cwd)
                    if exit_code in (0, -2):
                        _log("VERIFY", "Runtime verification passed after fix")
                        break
                else:
                    _log("VERIFY", "Could not auto-fix runtime errors -- you can fix manually in chat")
            elif exit_code in (0, -2):
                _log("VERIFY", "Runtime verification passed")

    # -- Git auto-commit
    _git_auto_commit(project_dir, settings_mgr, f"build: {prompt[:60]}")

    return ctx, project_dir


# ═══════════════════════════════════════════════════════════════════
# Agentic mode — autonomous modify-in-place
# ═══════════════════════════════════════════════════════════════════

def _cmd_agentic(
    ctx: ContextManager,
    project_dir: Path,
    user_request: str,
    settings_mgr: SettingsManager,
) -> None:
    """Autonomous modification: classify → scan → reason → modify files → auto-run → auto-fix → commit."""

    # ── Step 1: Classify the task so we use the right models ──
    classification = classify_task(prompt=user_request)
    complexity_str = classification.complexity.value
    size_str = classification.size.value

    console.print(f"\n  [dim]Classification:[/dim] [bold]{classification.label}[/bold]"
                  f"  [dim](complexity={complexity_str}, size={size_str})[/dim]")

    model_plan = describe_model_plan(complexity_str, size_str)
    console.print(f"  [dim]Models:[/dim]")
    for role, model in model_plan.items():
        console.print(f"    [dim]{role:>8}:[/dim]  [cyan]{model}[/cyan]")

    # Pre-check models are available (offer to pull if missing)
    ensure_models_for_complexity(complexity_str, size_str)

    # ── Step 2: Refresh context from disk ──
    _scan_project_files(ctx, project_dir)

    # Build file contents string
    file_parts = []
    for path, content in sorted(ctx.state.files.items()):
        trimmed = content[:6000]
        file_parts.append(f"### {path}\n```\n{trimmed}\n```")
    file_contents = "\n\n".join(file_parts) if file_parts else "(no files yet)"

    # Project summary
    project_summary = ctx.get_project_summary_for_chat()

    # Git status
    git_status = ""
    if git_manager.git_available() and git_manager.is_git_repo(project_dir):
        changed = git_manager.changed_files(project_dir)
        if changed:
            git_status = f"Modified files: {', '.join(changed[:20])}"
        else:
            git_status = "Clean working tree"

    # ── Step 3: Build prompt and call model with proper routing ──
    full_prompt = AGENTIC_TASK.format(
        project_summary=project_summary,
        file_contents=file_contents,
        user_request=user_request,
        git_status=git_status,
    )

    ctx.add_chat("user", user_request)

    _log("AGENTIC", "Analyzing and modifying project...")
    messages = [
        {"role": "system", "content": AGENTIC_SYSTEM},
        {"role": "user", "content": full_prompt},
    ]

    response = call_model(
        "coder", messages, stream=True,
        complexity=complexity_str, size=size_str,
    )

    # ── Step 4: Apply file changes (files before commands) ──
    files_written = _apply_file_changes(response, project_dir, ctx)

    # Execute any ===RUN:=== or ===BACKGROUND:=== commands
    commands_run = _apply_run_commands(response, project_dir)

    # ── Build clean display text: always strip file/command blocks ──
    # We strip regardless of files_written count — prevents raw code spilling into panel
    # even when the parser matched a different format from what the stripper expects.
    display_text = response
    # Remove ===FILE:...===END=== blocks
    display_text = re.sub(r"===FILE:.*?===END===", "", display_text, flags=re.DOTALL)
    # Remove ===FILE: path=== + ``` block
    display_text = re.sub(
        r"===FILE:\s*.+?\s*===[ \t]*\n```\w*[ \t]*\n.*?\n```",
        "", display_text, flags=re.DOTALL
    )
    # Remove remaining ===FILE: path=== blocks (raw content fallback)
    display_text = re.sub(
        r"===FILE:\s*.+?\s*===[ \t]*\n.*?(?=\n===(?:FILE|RUN|BACKGROUND)|$)",
        "", display_text, flags=re.DOTALL
    )
    # Remove markdown headings that are just file paths (### FILE: path)
    display_text = re.sub(
        r"\n#{1,4}\s+(?:FILE[:\s]+)?[a-zA-Z0-9_/. -]+\.[a-zA-Z0-9]+[ \t]*\n```\w*[ \t]*\n.*?\n```",
        "", display_text, flags=re.DOTALL
    )
    # Remove ===RUN:=== and ===BACKGROUND:=== lines
    display_text = re.sub(r"===(RUN|BACKGROUND):\s*.+?===", "", display_text, flags=re.IGNORECASE)
    # Collapse multiple blank lines
    display_text = re.sub(r"\n{3,}", "\n\n", display_text).strip()

    if files_written > 0:
        _log("APPLIED", f"Modified {files_written} file(s)")
    if commands_run > 0:
        _log("APPLIED", f"Executed {commands_run} command(s)")

    if display_text:
        console.print()
        try:
            console.print(Panel(Markdown(display_text), border_style="cyan", padding=(1, 2)))
        except Exception:
            console.print(Panel(display_text, border_style="cyan", padding=(1, 2)))

    ctx.add_chat("assistant", response[:3000])
    _auto_save(ctx, project_dir)

    # ── Step 5: Auto-run the project after code changes ──
    if files_written > 0:
        _agentic_auto_run(ctx, project_dir, settings_mgr, user_request,
                          complexity_str, size_str)

    # Auto-commit after agentic changes
    if files_written > 0:
        _git_auto_commit(project_dir, settings_mgr, user_request[:60])

    console.print()


def _agentic_auto_run(
    ctx: ContextManager,
    project_dir: Path,
    settings_mgr: SettingsManager,
    user_request: str,
    complexity: str,
    size: str,
) -> None:
    """Auto-run after agentic code generation: install deps → detect → run → auto-fix loop."""
    console.print()
    _log("AUTO-RUN", "Attempting to run the project after code changes...")

    # Install dependencies first
    _install_deps_if_needed(project_dir)

    # Detect how to run
    run_cmd, run_cwd = _detect_run_command(project_dir)
    if not run_cmd:
        _log("AUTO-RUN", "Could not detect run command — skipping auto-run")
        return

    MAX_AUTO_FIX = 3
    for attempt in range(1, MAX_AUTO_FIX + 1):
        _log("AUTO-RUN", f"{' '.join(run_cmd)} (in {run_cwd.name})")
        exit_code, output = _run_and_capture(run_cmd, run_cwd)

        if exit_code == 0:
            _log("AUTO-RUN", "Project ran successfully ✓")
            return

        if exit_code == -2:
            # User pressed Ctrl+C — don't auto-fix, just return
            return

        _log("AUTO-RUN", f"Process exited with code {exit_code}")

        if attempt >= MAX_AUTO_FIX:
            _log("AUTO-FIX", f"Could not auto-fix after {MAX_AUTO_FIX} attempts")
            console.print("  [dim]You can describe the issue and JCode will help fix it.[/dim]")
            return

        # Auto-fix: feed the error back to the model
        _log("AUTO-FIX", f"Attempt {attempt}/{MAX_AUTO_FIX} — analyzing runtime error...")
        error_msg = output[-3000:] if len(output) > 3000 else output

        fix_prompt = (
            f"The project failed to run after your last changes.\n\n"
            f"EXACT error output:\n```\n{error_msg}\n```\n\n"
            f"Command: {' '.join(run_cmd)}\n"
            f"Working directory: {run_cwd}\n\n"
            f"Read the error carefully. Find and fix the broken file(s). "
            f"Output COMPLETE corrected files using ===FILE: path=== ... ===END=== format. "
            f"If dependencies are missing, add ===RUN: npm install xyz=== or similar.\n"
            f"Do NOT give advice — just fix the code."
        )

        _run_fix_prompt(ctx, project_dir, fix_prompt)

        # Re-install deps in case fix added new packages
        _install_deps_if_needed(project_dir)

        _log("AUTO-FIX", "Re-running after fix...")


def _scan_project_files(ctx: ContextManager, project_dir: Path) -> None:
    """Scan project directory and load file contents into context."""
    if not project_dir.exists():
        return
    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", ".next", "dist", "build"}
    for f in project_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            if any(part in skip_dirs for part in f.relative_to(project_dir).parts):
                continue
            try:
                rel = str(f.relative_to(project_dir))
                content = f.read_text(errors="replace")
                ctx.record_file(rel, content)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════
# Fix prompt helper — used by /run auto-fix and agentic auto-fix
# ═══════════════════════════════════════════════════════════════════

def _run_fix_prompt(ctx: ContextManager, project_dir: Path, fix_prompt: str) -> int:
    """Call the model with a fix prompt and apply file changes + run commands.

    Returns number of files written. Used internally by auto-fix loops —
    this DOES modify files (unlike _cmd_chat which is read-only).
    """
    _scan_project_files(ctx, project_dir)

    file_parts = []
    for path, content in sorted(ctx.state.files.items()):
        trimmed = content[:6000]
        file_parts.append(f"### {path}\n```\n{trimmed}\n```")
    file_contents = "\n\n".join(file_parts) if file_parts else "(no files yet)"

    full_prompt = f"{fix_prompt}\n\n## All Project Files\n{file_contents}"

    _log("FIX", "Generating fix...")
    messages = [
        {"role": "system", "content": AGENTIC_SYSTEM},
        {"role": "user", "content": full_prompt},
    ]
    response = call_model("coder", messages, stream=True)

    files_written = _apply_file_changes(response, project_dir, ctx)
    cmds_run = _apply_run_commands(response, project_dir)

    if files_written > 0:
        _log("FIX", f"Fixed {files_written} file(s)")
    if cmds_run > 0:
        _log("FIX", f"Ran {cmds_run} command(s)")

    return files_written


# ═══════════════════════════════════════════════════════════════════
# Chat — conversational mode (read-only)
# ═══════════════════════════════════════════════════════════════════

def _cmd_chat(ctx: ContextManager, project_dir: Path, user_message: str) -> None:
    """
    Chat mode: reasoning, explanations, web search — but NO file modifications.
    The model can see all project files for context but cannot change them.
    """

    # Refresh file contents from disk (read-only context)
    _scan_project_files(ctx, project_dir)

    # Build file contents string (all files, capped per file)
    file_parts = []
    for path, content in sorted(ctx.state.files.items()):
        trimmed = content[:6000]
        file_parts.append(f"### {path}\n```\n{trimmed}\n```")
    file_contents = "\n\n".join(file_parts) if file_parts else "(no files yet)"

    # Build chat history string (last 20 messages)
    chat_lines = []
    for msg in ctx.chat_history[-20:]:
        role = msg["role"].upper()
        chat_lines.append(f"{role}: {msg['content'][:800]}")
    chat_history_str = "\n".join(chat_lines) if chat_lines else "(start of conversation)"

    # Build the prompt
    project_summary = ctx.get_project_summary_for_chat()
    full_prompt = CHAT_CONTEXT.format(
        project_summary=project_summary,
        file_contents=file_contents,
        chat_history=chat_history_str,
        user_message=user_message,
    )

    # Record user message
    ctx.add_chat("user", user_message)

    # Call the model
    _log("THINKING", "Processing your request...")
    messages = [
        {"role": "system", "content": CHAT_SYSTEM},
        {"role": "user", "content": full_prompt},
    ]

    response = call_model("coder", messages, stream=True)

    # Display the response (strip any ===FILE:=== or ===RUN:=== blocks — chat mode is read-only)
    display_text = re.sub(
        r"===FILE:.*?===END===", "", response, flags=re.DOTALL
    ).strip()
    display_text = re.sub(
        r"===(RUN|BACKGROUND):\s*.+?===", "", display_text, flags=re.IGNORECASE
    ).strip()

    if display_text:
        console.print()
        try:
            console.print(Panel(Markdown(display_text), border_style="dim", padding=(1, 2)))
        except Exception:
            console.print(Panel(display_text, border_style="dim", padding=(1, 2)))

    # Record assistant response
    ctx.add_chat("assistant", response[:3000])
    _auto_save(ctx, project_dir)
    console.print()


def _strip_content_fences(content: str) -> str:
    """Strip markdown code fences from file content.

    Models often wrap file content in ```lang ... ``` despite instructions.
    This removes them so the raw content gets written to disk.
    """
    content = content.strip()
    # Strip opening fence: ```json, ```javascript, ```python, ```, etc.
    content = re.sub(r"^```\w*\s*\n?", "", content)
    # Strip closing fence (at end)
    content = re.sub(r"\n?```\s*$", "", content)
    return content.strip()


def _apply_file_changes(response: str, project_dir: Path, ctx: ContextManager) -> int:
    """
    Parse file blocks from model response and write files.
    Handles every format that local models produce:

    FORMAT 1 (ideal):    ===FILE: path=== ... ===END===
    FORMAT 2 (common):   ===FILE: path=== ```lang ... ```  (no ===END===)
    FORMAT 4 (fallback): ===FILE: path=== raw content until next marker
    FORMAT 3 (heading):  ### path  OR  ### FILE: path  OR  **path**  + code block
    FORMAT 5 (#### FILE):  #### FILE: path  OR  #### path  + code block

    Returns count of files written.
    """
    files_written = 0
    written_paths: set[str] = set()

    # ── Pre-process: normalise ===END=== that ended up inside a ``` block ──
    # The model sometimes wraps the entire file block in a markdown fence, so you get:
    # ```\n===FILE: x===\ncontent\n===END===\n```
    # Strip the outer fence, keep the inner markers.
    response = re.sub(r"^```\w*\s*\n(===(?:FILE|END))", r"\1", response, flags=re.MULTILINE)
    response = re.sub(r"\n===END===\n```", "\n===END===", response)

    # ── Helper: write one file ────────────────────────────────────
    def _write(rel_path: str, content: str) -> bool:
        rel_path = rel_path.strip().lstrip("/")
        content = _strip_content_fences(content)
        # Remove stray ===END=== lines that leaked into content
        content = re.sub(r"^===END===$", "", content, flags=re.MULTILINE).strip()
        if not rel_path or not content:
            return False
        if rel_path in written_paths:
            return False
        # Sanity: must look like a valid file path
        if len(rel_path) > 200 or "\n" in rel_path:
            return False
        full_path = project_dir / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        ctx.record_file(rel_path, content)
        console.print(f"           [dim]wrote[/dim] [white]{rel_path}[/white]")
        written_paths.add(rel_path)
        return True

    # ── FORMAT 1: ===FILE: path=== ... ===END=== ─────────────────
    for rel_path, content in re.findall(
        r"===FILE:\s*(.+?)\s*===[ \t]*\n(.*?)===END===",
        response, re.DOTALL
    ):
        if _write(rel_path, content):
            files_written += 1

    # ── FORMAT 2: ===FILE: path=== followed by ``` block ─────────
    fmt2 = re.compile(
        r"===FILE:\s*(.+?)\s*===[ \t]*\n"
        r"```\w*[ \t]*\n"
        r"(.*?)"
        r"\n```",
        re.DOTALL,
    )
    for m in fmt2.finditer(response):
        if _write(m.group(1), m.group(2)):
            files_written += 1

    # ── FORMAT 4: ===FILE: path=== + raw content (ultimate fallback) ─
    if not written_paths:
        markers = list(re.finditer(r"===FILE:\s*(.+?)\s*===[ \t]*\n", response))
        for i, m in enumerate(markers):
            start = m.end()
            if i + 1 < len(markers):
                end = markers[i + 1].start()
            else:
                nxt = re.search(r"\n===(RUN|BACKGROUND):", response[start:])
                end = start + nxt.start() if nxt else len(response)
            if _write(m.group(1), response[start:end]):
                files_written += 1

    # ── FORMAT 3 & 5: Markdown headings + code block ─────────────
    # Catches:
    #   ### main.py          (plain heading)
    #   ### FILE: main.py    (FILE: prefix)
    #   #### FILE: main.py
    #   **main.py**
    #   ### Updated `main.py`
    fmt35 = re.compile(
        r"(?:^|\n)"
        # heading variants: ###/####/## with optional label words + optional backticks
        r"(?:#{1,4}\s+(?:(?:FILE|Updated|Modified|File)[:\s]+)?"
        r"[`'\"]?([a-zA-Z0-9_/.\\ -]+\.[a-zA-Z0-9]+)[`'\"]?"
        # OR bold **filename**
        r"|\*\*([a-zA-Z0-9_/.\\ -]+\.[a-zA-Z0-9]+)\*\*)"
        r"[ \t]*\n+"
        r"```\w*[ \t]*\n"
        r"(.*?)"
        r"\n```",
        re.DOTALL,
    )
    for m in fmt35.finditer(response):
        rel_path = (m.group(1) or m.group(2) or "").strip()
        content = m.group(3)
        if rel_path and "." in rel_path and len(content.strip()) > 5:
            if _write(rel_path, content):
                files_written += 1

    if files_written > 0:
        console.print(f"           [green]✓ {files_written} file(s) written to disk[/green]")
    return files_written


def _apply_run_commands(response: str, project_dir: Path) -> int:
    """
    Parse ===RUN: command=== and ===BACKGROUND: command=== blocks and execute them.
    Returns count of commands executed.

    ===RUN: command=== — runs synchronously, waits for completion
    ===BACKGROUND: command=== — runs in background (for servers/watchers)
    """
    commands_run = 0

    # Find all ===RUN:=== and ===BACKGROUND:=== blocks in order
    pattern = re.compile(r"===(RUN|BACKGROUND):\s*(.+?)\s*===", re.IGNORECASE)
    matches = list(pattern.finditer(response))

    if not matches:
        return 0

    _log("EXEC", f"Running {len(matches)} command(s)")

    for m in matches:
        cmd_type = m.group(1).upper()
        cmd = m.group(2).strip()

        if not cmd:
            continue

        # Safety: skip obviously dangerous commands
        dangerous = ("rm -rf /", "rm -rf ~", "sudo rm", ":(){", "mkfs", "dd if=")
        if any(d in cmd.lower() for d in dangerous):
            _log("EXEC", f"  ⚠ Skipped dangerous command: {cmd}")
            continue

        # Skip commands that would launch interactive/blocking programs.
        # The user can run those manually with /run or by typing the command.
        _interactive_signals = (
            "python3 main.py", "python main.py",
            "node index.js", "node app.js", "node server.js",
            "npm start", "yarn start", "cargo run", "go run",
            "ruby ", "php -S",
        )
        if any(cmd.lower().startswith(s) for s in _interactive_signals) and cmd_type == "RUN":
            _log("EXEC", f"  ↷ Skipped interactive program (use /run to launch): {cmd}")
            continue

        if cmd_type == "BACKGROUND":
            _log("EXEC", f"  ⚡ [background] {cmd}")
            try:
                subprocess.Popen(
                    cmd,
                    shell=True,
                    cwd=project_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                commands_run += 1
                console.print(f"           [dim]started in background[/dim]")
            except Exception as e:
                _log("EXEC", f"  ✗ Failed: {e}")
        else:
            _log("EXEC", f"  ▶ {cmd}")
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                commands_run += 1
                if result.stdout.strip():
                    # Show first 20 lines of output
                    lines = result.stdout.strip().split("\n")
                    for line in lines[:20]:
                        console.print(f"           [dim]{line}[/dim]")
                    if len(lines) > 20:
                        console.print(f"           [dim]... ({len(lines) - 20} more lines)[/dim]")
                if result.returncode != 0:
                    err = result.stderr.strip()[:500] if result.stderr else ""
                    if err:
                        _log("EXEC", f"  ⚠ exit {result.returncode}: {err[:200]}")
                    else:
                        _log("EXEC", f"  ⚠ exit {result.returncode}")
                    # Stop executing remaining commands on failure
                    _log("EXEC", "  Stopping — fix the error before continuing")
                    break
            except subprocess.TimeoutExpired:
                _log("EXEC", f"  ⚠ Timed out (120s): {cmd}")
                break
            except Exception as e:
                _log("EXEC", f"  ✗ Failed: {e}")
                break

    return commands_run


# ═══════════════════════════════════════════════════════════════════
# Run command — smart detection with dep install
# ═══════════════════════════════════════════════════════════════════

def _cmd_run(ctx: ContextManager, project_dir: Path, settings_mgr: SettingsManager) -> None:
    """Auto-detect and run the project. If it fails, auto-fix and retry."""
    if not project_dir or not project_dir.exists():
        console.print("  [dim]No project directory.[/dim]")
        return

    _log("RUN", f"Detecting how to run {project_dir.name}")

    # Install dependencies first if needed
    _install_deps_if_needed(project_dir)

    # Find the run command
    run_cmd, run_cwd = _detect_run_command(project_dir)
    if not run_cmd:
        console.print("  [dim]Could not detect how to run this project.[/dim]")
        console.print("  [dim]Ask JCode: 'how do I run this project?'[/dim]")
        return

    MAX_RUN_FIX_ATTEMPTS = 5
    for attempt in range(1, MAX_RUN_FIX_ATTEMPTS + 1):
        _log("RUN", f"{' '.join(run_cmd)} (in {run_cwd.name})")

        exit_code, output = _run_and_capture(run_cmd, run_cwd)

        if exit_code == 0:
            _log("RUN", "Process exited successfully")
            return

        if exit_code == -2:
            return

        _log("RUN", f"Process exited with code {exit_code}")

        if attempt >= MAX_RUN_FIX_ATTEMPTS:
            _log("RUN", f"Failed after {MAX_RUN_FIX_ATTEMPTS} fix attempts")
            console.print(
                "  [dim]Auto-fix could not resolve the issue. Try fixing manually:[/dim]"
            )
            console.print(f"  [dim]Tell JCode what you see and it will help.[/dim]")
            return

        _log("FIX", f"Attempt {attempt}/{MAX_RUN_FIX_ATTEMPTS} -- auto-fixing runtime error")
        error_msg = output[-3000:] if len(output) > 3000 else output

        fix_prompt = (
            f"The project failed to run. Here is the EXACT error output:\n\n"
            f"```\n{error_msg}\n```\n\n"
            f"Command: {' '.join(run_cmd)}\n"
            f"Working directory: {run_cwd}\n\n"
            f"Read the error, find the affected file(s) in the project, and fix them. "
            f"Output the corrected files using ===FILE:=== format. "
            f"Do NOT give advice or suggestions — just fix the code."
        )
        _run_fix_prompt(ctx, project_dir, fix_prompt)

        _install_deps_if_needed(project_dir)

        _log("FIX", "Re-running after fix...")


def _cmd_test(project_dir: Path, ctx: ContextManager) -> None:
    """Detect and run project tests."""
    if not project_dir.exists():
        console.print("  [dim]No project directory.[/dim]")
        return

    _log("TEST", "Detecting test runner...")

    # Python: pytest or unittest
    if (project_dir / "pytest.ini").exists() or (project_dir / "setup.cfg").exists() or \
       list(project_dir.rglob("test_*.py")) or list(project_dir.rglob("*_test.py")):
        _log("TEST", "Running pytest")
        exit_code, output = _run_and_capture(["python3", "-m", "pytest", "-v"], project_dir)
        return

    # Node: npm test
    pkg_json = project_dir / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            if "test" in pkg.get("scripts", {}):
                _log("TEST", "Running npm test")
                exit_code, output = _run_and_capture(["npm", "test"], project_dir)
                return
        except Exception:
            pass

    console.print("  [dim]No test runner detected.[/dim]")
    console.print("  [dim]Supported: pytest, npm test[/dim]")


def _detect_run_command(project_dir: Path) -> tuple[list[str] | None, Path | None]:
    """Detect the command needed to run this project. Returns (cmd, cwd) or (None, None)."""
    # 1. Python: look for main entry points
    for entry in ("main.py", "app.py", "manage.py", "server.py", "run.py"):
        candidate = project_dir / entry
        if candidate.exists():
            return ["python3", str(candidate)], project_dir
        for subdir in ("backend", "src", "server", "api"):
            candidate = project_dir / subdir / entry
            if candidate.exists():
                return ["python3", str(candidate)], project_dir / subdir

    # 2. Node: package.json with start/dev script (search root + common subdirs)
    node_search_dirs = [project_dir] + [
        project_dir / d for d in ("backend", "server", "api", "frontend", "client", "app")
    ]
    for search_dir in node_search_dirs:
        pkg_json = search_dir / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                scripts = pkg.get("scripts", {})
                if "start" in scripts:
                    return ["npm", "start"], search_dir
                elif "dev" in scripts:
                    return ["npm", "run", "dev"], search_dir
            except json.JSONDecodeError:
                _log("RUN", f"⚠ {pkg_json} has invalid JSON — cannot detect run command")
            except Exception:
                pass

    # 3. Node.js: common entry files in root and subdirs
    #    (fallback when package.json has no scripts or doesn't exist)
    node_entries = ("app.js", "index.js", "server.js", "main.js")
    for entry in node_entries:
        candidate = project_dir / entry
        if candidate.exists():
            return ["node", str(candidate)], project_dir
    for subdir in ("server", "backend", "src", "api"):
        sub_path = project_dir / subdir
        if sub_path.is_dir():
            for entry in node_entries:
                candidate = sub_path / entry
                if candidate.exists():
                    return ["node", str(candidate)], sub_path

    # 4. HTML: look for index.html
    for loc in [project_dir, project_dir / "public", project_dir / "frontend",
                project_dir / "client", project_dir / "dist"]:
        index_html = loc / "index.html"
        if index_html.exists():
            return ["open", str(index_html)], loc

    # 5. package.json exists but has NO scripts — try `node` on main field
    for search_dir in node_search_dirs:
        pkg_json = search_dir / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                main_file = pkg.get("main")
                if main_file and (search_dir / main_file).exists():
                    return ["node", str(search_dir / main_file)], search_dir
            except Exception:
                pass

    # 6. Any .py file
    py_files = list(project_dir.glob("*.py"))
    if py_files:
        return ["python3", str(py_files[0])], project_dir

    return None, None


def _run_and_capture(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """
    Run a subprocess, stream output to console AND capture it.
    Returns (exit_code, captured_output).
    exit_code -2 means user interrupted (Ctrl+C).
    """
    console.print(f"  [dim]Running: {' '.join(cmd)}[/dim]")
    console.print(f"  [dim]Press Ctrl+C to stop[/dim]\n")

    captured_lines = []
    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in iter(process.stdout.readline, ""):
            console.print(f"  {line.rstrip()}")
            captured_lines.append(line)
        process.wait()
        return process.returncode, "".join(captured_lines)
    except KeyboardInterrupt:
        process.terminate()
        console.print("\n  [dim]Process stopped.[/dim]")
        return -2, "".join(captured_lines)
    except FileNotFoundError:
        msg = f"Command not found: {cmd[0]}"
        console.print(f"  [dim]{msg}[/dim]")
        return 1, msg
    except Exception as e:
        msg = f"Error: {e}"
        console.print(f"  [dim]{msg}[/dim]")
        return 1, msg


def _install_deps_if_needed(project_dir: Path) -> None:
    """Install project dependencies if package manager files exist."""
    # Node: package.json without node_modules
    for search_dir in [project_dir] + [project_dir / d for d in ("backend", "server", "frontend", "client")]:
        pkg_json = search_dir / "package.json"
        node_modules = search_dir / "node_modules"
        if pkg_json.exists() and not node_modules.exists():
            _log("DEPS", f"Installing npm packages in {search_dir.name}/...")
            try:
                subprocess.run(
                    ["npm", "install"],
                    cwd=search_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                _log("DEPS", "npm install complete")
            except Exception as e:
                console.print(f"  [dim]npm install failed: {e}[/dim]")

    # Python: requirements.txt
    req_txt = project_dir / "requirements.txt"
    if req_txt.exists():
        _log("DEPS", "Installing Python requirements...")
        try:
            subprocess.run(
                ["python3", "-m", "pip", "install", "-r", str(req_txt), "-q"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            _log("DEPS", "pip install complete")
        except Exception as e:
            console.print(f"  [dim]pip install failed: {e}[/dim]")


# ═══════════════════════════════════════════════════════════════════
# Project info commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_models() -> None:
    """Show available models and how they're routed."""
    from jcode.config import MODEL_REGISTRY, _is_model_local, describe_model_plan

    console.print()
    console.print("  [bold white]Installed Models & Routing[/bold white]\n")

    # Show installed models grouped by category
    categories: dict[str, list] = {}
    for spec in MODEL_REGISTRY:
        if _is_model_local(spec.name):
            categories.setdefault(spec.category, []).append(spec)

    if not categories:
        console.print("  [yellow]No registered models found locally.[/yellow]")
        console.print("  [dim]Install models with: ollama pull <model>[/dim]")
        console.print("  [dim]Recommended: ollama pull qwen2.5-coder:14b[/dim]")
        console.print()
        return

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("Model", style="white")
    table.add_column("Category", style="cyan")
    table.add_column("Size", justify="center")
    table.add_column("Thinking", justify="center")
    table.add_column("Tools", justify="center")

    for cat in ("coding", "reasoning", "agentic", "fast", "general"):
        specs = categories.get(cat, [])
        for spec in sorted(specs, key=lambda s: s.priority):
            table.add_row(
                spec.name,
                spec.category,
                spec.size_class,
                "✓" if spec.supports_thinking else "",
                "✓" if spec.supports_tools else "",
            )

    console.print(table)
    console.print()

    # Show routing for each classification level
    console.print("  [bold white]Model Routing by Classification[/bold white]\n")
    for label in ("simple/small", "medium/medium", "heavy/large"):
        parts = label.split("/")
        plan = describe_model_plan(parts[0], parts[1])
        console.print(f"  [dim]{label:>12}:[/dim]  "
                      f"planner=[cyan]{plan['planner']}[/cyan]  "
                      f"coder=[cyan]{plan['coder']}[/cyan]  "
                      f"reviewer=[cyan]{plan['reviewer']}[/cyan]")
    console.print()


# ═══════════════════════════════════════════════════════════════════
# Project info commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_plan(ctx: ContextManager | None) -> None:
    """Show the current plan."""
    if not ctx or not ctx.state.plan:
        console.print("  [dim]No active plan.[/dim]")
        return

    plan = ctx.state.plan
    console.print(
        Panel(
            f"[bold white]{plan.get('project_name', 'Project')}[/bold white]\n"
            f"[dim]{plan.get('architecture_summary', '')}[/dim]",
            title="Plan",
            border_style="cyan",
        )
    )

    summary = ctx.get_task_summary()
    if summary:
        console.print(summary)


def _cmd_files(project_dir: Path | None) -> None:
    """List all project files."""
    if not project_dir or not project_dir.exists():
        console.print("  [dim]No project directory yet.[/dim]")
        return

    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", ".next", "dist", "build"}
    files = []
    for f in project_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            if not any(part in skip_dirs for part in f.relative_to(project_dir).parts):
                files.append(f)

    if not files:
        console.print("  [dim]No files yet.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("File", style="white")
    table.add_column("Size", justify="right", style="dim")

    for f in sorted(files):
        rel = f.relative_to(project_dir)
        table.add_row(str(rel), _format_size(f.stat().st_size))

    console.print(table)


def _cmd_tree(ctx: ContextManager | None, project_dir: Path | None) -> None:
    """Show the project tree."""
    if not project_dir or not project_dir.exists():
        console.print("  [dim]No project directory yet.[/dim]")
        return
    name = project_dir.name
    if ctx and ctx.state.plan:
        name = ctx.state.plan.get("project_name", project_dir.name)
    print_tree(project_dir, name)


# ═══════════════════════════════════════════════════════════════════
# Update / Uninstall
# ═══════════════════════════════════════════════════════════════════

def _cmd_update() -> None:
    """Self-update JCode from git."""
    jcode_root = Path(__file__).resolve().parent.parent

    _log("UPDATE", f"Installed at {jcode_root}")
    console.print(f"  [dim]Current version: v{__version__}[/dim]")

    if not (jcode_root / ".git").exists():
        console.print("  [dim]Not a git install. Cannot auto-update.[/dim]")
        return

    _log("UPDATE", "Pulling latest changes")
    try:
        result = subprocess.run(
            ["git", "-C", str(jcode_root), "pull", "--ff-only"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            console.print(f"  [dim]Git pull failed: {result.stderr.strip()}[/dim]")
            return
        if "Already up to date" in result.stdout:
            console.print("  [cyan]Already on the latest version.[/cyan]")
            return
        console.print(f"  [dim]{result.stdout.strip()}[/dim]")
    except FileNotFoundError:
        console.print("  [dim]Git is not installed.[/dim]")
        return
    except subprocess.TimeoutExpired:
        console.print("  [dim]Git pull timed out.[/dim]")
        return

    _log("UPDATE", "Re-installing dependencies")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(jcode_root), "-q"],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"  [dim]pip install failed: {e.stderr.strip()}[/dim]")
        return

    try:
        result = subprocess.run(
            [sys.executable, "-c", "from jcode import __version__; print(__version__)"],
            capture_output=True, text=True,
        )
        new_version = result.stdout.strip()
    except Exception:
        new_version = "unknown"

    _log("UPDATE", f"Updated to v{new_version}")
    console.print("  [dim]Restart JCode to use the new version.[/dim]")


def _cmd_uninstall(settings_mgr: SettingsManager) -> None:
    """Uninstall JCode: remove package + config."""
    console.print()
    console.print("  [bold white]Uninstall JCode[/bold white]")
    console.print()

    jcode_root = Path(__file__).resolve().parent.parent
    config_dir = Path.home() / ".jcode"

    console.print("  [dim]This will:[/dim]")
    console.print("    [dim]1. Uninstall the jcode package[/dim]")
    console.print(f"    [dim]2. Remove config at[/dim] [cyan]{config_dir}[/cyan]")
    console.print("    [dim]Your project files will NOT be deleted.[/dim]")
    console.print()

    choice = _select_one("Proceed with uninstall?", [
        "Yes -- uninstall JCode",
        "No  -- cancel",
    ])

    if choice != 0:
        console.print("  [dim]Cancelled.[/dim]")
        return

    _log("UNINSTALL", "Removing jcode package")
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "jcode", "-y"],
        capture_output=True, text=True,
    )

    if config_dir.exists():
        _log("UNINSTALL", "Removing config directory")
        shutil.rmtree(config_dir, ignore_errors=True)

    _log("UNINSTALL", "Done")
    console.print(f"\n  [dim]To remove the source code:[/dim] [cyan]rm -rf {jcode_root}[/cyan]\n")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _auto_save(ctx: ContextManager | None, project_dir: Path | None) -> None:
    """Auto-save session if applicable."""
    if ctx and project_dir and project_dir.exists():
        try:
            session_file = project_dir / ".jcode_session.json"
            ctx.save_session(session_file)
        except Exception:
            pass


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = "".join(c if c.isalnum() or c in " _-" else "" for c in text)
    slug = slug.strip().replace(" ", "_").lower()
    return slug[:50] or "project"


def _format_size(size: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


if __name__ == "__main__":
    main()
