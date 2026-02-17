"""
JCode CLI v7.0 — CWD-aware, dual-mode (agentic + chat), git-native.

JCode now lives inside your project directory.

Flow:
  1. Open VS Code → create/open project folder → open terminal
  2. Run `jcode` — it scans the current directory
  3. Chat naturally or let it build autonomously

Modes:
  AGENTIC — autonomous: plan → generate → review → verify → commit
  CHAT    — conversational: ask questions, discuss, get explanations

The intent router classifies user input without calling the LLM,
so common commands are instant.
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
from jcode.config import ProjectState, detect_complexity, get_model_for_role, get_all_required_models
from jcode.context import ContextManager
from jcode.planner import create_plan
from jcode.iteration import execute_plan
from jcode.file_manager import print_tree
from jcode.ollama_client import check_ollama_running, call_model, ensure_models_for_complexity
from jcode.settings import SettingsManager
from jcode.executor import set_autonomous
from jcode.web import set_internet_access, web_search, fetch_page, search_and_summarize
from jcode.prompts import CHAT_SYSTEM, CHAT_CONTEXT, AGENTIC_SYSTEM, AGENTIC_TASK
from jcode.intent import Intent, classify_intent, intent_label
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
[bold white]Commands[/bold white]

  [bold cyan]Modes[/bold cyan]
  [cyan]mode[/cyan]               Show or switch mode (agentic / chat)
  [cyan]mode agentic[/cyan]       Switch to agentic mode (autonomous changes)
  [cyan]mode chat[/cyan]          Switch to chat mode (conversation only)

  [bold cyan]Build & Modify[/bold cyan]
  [cyan]build[/cyan] <prompt>     Plan and build a new project from scratch
  Just type naturally  "fix the login bug", "add dark mode", etc.

  [bold cyan]Git[/bold cyan]
  [cyan]commit[/cyan] [message]   Stage all changes and commit
  [cyan]push[/cyan]              Push to remote
  [cyan]pull[/cyan]              Pull from remote
  [cyan]status[/cyan]            Show git status
  [cyan]log[/cyan]               Show recent commits
  [cyan]diff[/cyan]              Show uncommitted changes
  [cyan]git remote[/cyan] <url>  Set up GitHub remote

  [bold cyan]Project[/bold cyan]
  [cyan]run[/cyan]               Detect and run the project
  [cyan]test[/cyan]              Run project tests
  [cyan]files[/cyan]             List all project files
  [cyan]tree[/cyan]              Show directory tree
  [cyan]plan[/cyan]              Show current build plan

  [bold cyan]Utility[/bold cyan]
  [cyan]version[/cyan]            Show JCode version
  [cyan]update[/cyan]             Update JCode to latest version
  [cyan]clear[/cyan]              Clear the terminal
  [cyan]help[/cyan]               Show this help
  [cyan]quit[/cyan]               Exit
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
            "  [dim]Then pull models:[/dim]  [cyan]ollama pull deepseek-r1:7b && ollama pull qwen2.5-coder:7b[/cyan]",
        )
        sys.exit(1)
    console.print("  [cyan]Ollama connected[/cyan]")
    console.print("  [dim]Smart model tiering enabled — models auto-selected by complexity[/dim]")

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
    console.print(f"  [cyan]Mode:[/cyan] {mode}")

    # -- Hint
    console.print()
    console.print(
        "  Type naturally or use [cyan]'help'[/cyan] for commands.\n"
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
# Main REPL — intent-driven, single loop
# ═══════════════════════════════════════════════════════════════════

def _repl(
    ctx: ContextManager,
    project_dir: Path,
    settings_mgr: SettingsManager,
    mode: str,
    history: InMemoryHistory,
) -> None:
    """Single REPL loop — routes user input by intent."""
    proj_name = ctx.state.name or project_dir.name

    while True:
        try:
            mode_indicator = "⚡" if mode == "agentic" else "💬"
            user_input = pt_prompt(
                f"{mode_indicator} {proj_name}> ", history=history,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            _auto_save(ctx, project_dir)
            break

        if not user_input:
            continue

        # Classify intent
        intent, content = classify_intent(user_input)

        # Route by intent
        if intent == Intent.QUIT:
            _auto_save(ctx, project_dir)
            console.print("  [dim]Goodbye.[/dim]\n")
            break

        elif intent == Intent.NAVIGATE:
            lower = user_input.lower().strip()
            if lower.startswith("mode "):
                new_mode = lower.split(None, 1)[1].strip()
                if new_mode in ("agentic", "chat"):
                    mode = new_mode
                    settings_mgr.settings.default_mode = mode
                    settings_mgr.save_settings()
                    console.print(f"  [cyan]Switched to {mode} mode[/cyan]")
                else:
                    console.print(f"  [cyan]Current mode:[/cyan] {mode}")
                    console.print(f"  [dim]Available: 'mode agentic' or 'mode chat'[/dim]")
            elif lower == "mode":
                console.print(f"  [cyan]Current mode:[/cyan] {mode}")
                console.print(f"  [dim]Switch: 'mode agentic' or 'mode chat'[/dim]")
            else:
                _handle_navigate(lower, ctx, project_dir, settings_mgr, mode)

        elif intent == Intent.BUILD:
            prompt = content if content else user_input
            ctx, project_dir = _cmd_build(prompt, ctx, project_dir, settings_mgr)
            proj_name = ctx.state.name or project_dir.name

        elif intent == Intent.MODIFY:
            if mode == "agentic":
                _cmd_agentic(ctx, project_dir, user_input, settings_mgr)
            else:
                _cmd_chat(ctx, project_dir, user_input)

        elif intent == Intent.CHAT:
            _cmd_chat(ctx, project_dir, user_input)

        elif intent == Intent.GIT:
            _handle_git(user_input, content, ctx, project_dir, settings_mgr)

        elif intent == Intent.RUN:
            lower = user_input.lower().strip()
            if lower == "rebuild":
                _log("REBUILD", "Re-running build pipeline")
                execute_plan(ctx, project_dir)
                _auto_save(ctx, project_dir)
                _git_auto_commit(project_dir, settings_mgr, "rebuild project")
            elif lower in ("test", "tests"):
                _cmd_test(project_dir, ctx)
            else:
                _cmd_run(ctx, project_dir, settings_mgr)


# ═══════════════════════════════════════════════════════════════════
# Navigation handler
# ═══════════════════════════════════════════════════════════════════

def _handle_navigate(
    cmd: str,
    ctx: ContextManager,
    project_dir: Path,
    settings_mgr: SettingsManager,
    mode: str,
) -> None:
    """Handle navigation/utility commands."""
    if cmd == "help":
        console.print(HELP_TEXT, highlight=False)
    elif cmd == "clear":
        console.clear()
    elif cmd == "files":
        _cmd_files(project_dir)
    elif cmd == "tree":
        _cmd_tree(ctx, project_dir)
    elif cmd == "plan":
        _cmd_plan(ctx)
    elif cmd == "version":
        console.print(f"\n  [bold cyan]JCode[/bold cyan] [white]v{__version__}[/white]")
        console.print(f"  [dim]https://github.com/ShakenTheCoder/JcodeAgent[/dim]\n")
    elif cmd == "update":
        _cmd_update()
    elif cmd == "uninstall":
        _cmd_uninstall(settings_mgr)
    elif cmd == "status":
        git_manager.print_status(project_dir)


# ═══════════════════════════════════════════════════════════════════
# Git handler
# ═══════════════════════════════════════════════════════════════════

def _handle_git(
    raw_input: str,
    content: str,
    ctx: ContextManager,
    project_dir: Path,
    settings_mgr: SettingsManager,
) -> None:
    """Handle git-related commands."""
    lower = raw_input.lower().strip()

    # Ensure git is available
    if not git_manager.ensure_git():
        return

    # Initialize repo if needed
    if not git_manager.is_git_repo(project_dir):
        _log("GIT", "Initializing git repository")
        git_manager.init_repo(project_dir, initial_commit=True)

    if lower in ("commit", "save"):
        ok, result = git_manager.auto_commit(project_dir)
        if ok:
            _log("GIT", f"Committed: {result}")
        else:
            console.print(f"  [dim]{result}[/dim]")

    elif lower.startswith("commit "):
        message = raw_input.split(None, 1)[1].strip()
        ok, result = git_manager.commit(project_dir, message)
        if ok:
            _log("GIT", f"Committed ({result}): {message}")
        else:
            console.print(f"  [dim]{result}[/dim]")

    elif lower == "push":
        ok, result = git_manager.push(project_dir)
        if ok:
            _log("GIT", result)
        else:
            console.print(f"  [yellow]{result}[/yellow]")
            if "No configured push destination" in result or "no upstream" in result.lower():
                console.print(f"  [dim]Set a remote: git remote <github-url>[/dim]")

    elif lower == "pull":
        ok, result = git_manager.pull(project_dir)
        if ok:
            _log("GIT", f"Pulled: {result}")
            _scan_project_files(ctx, project_dir)
        else:
            console.print(f"  [yellow]{result}[/yellow]")

    elif lower == "status":
        git_manager.print_status(project_dir)

    elif lower == "log":
        git_manager.print_log(project_dir)

    elif lower == "diff":
        diff_output = git_manager.diff(project_dir)
        if diff_output:
            console.print(Panel(diff_output, title="Git Diff", border_style="dim"))
        else:
            console.print("  [dim]No uncommitted changes[/dim]")

    elif lower.startswith("git remote ") or lower.startswith("remote "):
        url = raw_input.split(None, 2)[-1].strip()
        if git_manager.setup_github_remote(project_dir, url):
            _log("GIT", f"Remote set to: {url}")
        else:
            console.print(f"  [yellow]Failed to set remote[/yellow]")

    elif lower.startswith("clone "):
        url = raw_input.split(None, 1)[1].strip()
        _log("GIT", f"Cloning {url}")
        ok, cloned_path = git_manager.clone(url, project_dir)
        if ok and cloned_path:
            _log("GIT", f"Cloned to {cloned_path}")
        else:
            console.print(f"  [yellow]Clone failed[/yellow]")

    else:
        console.print("  [dim]Git commands: commit, push, pull, status, log, diff, git remote <url>[/dim]")


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
    """Full autonomous pipeline: plan > generate > review > verify > fix.
    Operates inside the current project directory (CWD)."""

    console.print(f"\n  [dim]Building in:[/dim] [cyan]{project_dir}[/cyan]")

    complexity = detect_complexity(prompt)
    console.print(f"  [dim]Complexity:[/dim] {complexity}")

    # Show model tier assignment
    console.print(f"  [dim]Models:[/dim]")
    console.print(f"    [dim]Planner:[/dim]  [cyan]{get_model_for_role('planner', complexity)}[/cyan]")
    console.print(f"    [dim]Coder:[/dim]    [cyan]{get_model_for_role('coder', complexity)}[/cyan]")
    console.print(f"    [dim]Reviewer:[/dim] [cyan]{get_model_for_role('reviewer', complexity)}[/cyan]")
    console.print(f"    [dim]Analyzer:[/dim] [cyan]{get_model_for_role('analyzer', complexity)}[/cyan]")

    # Pre-pull all required models for this complexity
    _log("MODELS", f"Ensuring models for '{complexity}' complexity...")
    ensure_models_for_complexity(complexity)

    slug = _slugify(prompt[:40])
    state = ProjectState(
        name=slug,
        description=prompt,
        output_dir=project_dir,
        complexity=complexity,
    )
    ctx = ContextManager(state)

    # -- Phase 1: Planning
    console.print()
    _log("PHASE 1", "Planning project architecture")
    plan = create_plan(prompt, ctx)
    ctx.set_plan(plan)

    task_count = len(plan.get("tasks", []))
    _log("PLAN", f"{task_count} task(s) created")

    for t in plan.get("tasks", []):
        deps = f" [dim](after {t.get('depends_on', [])})[/dim]" if t.get("depends_on") else ""
        console.print(f"          {t.get('id', '?')}. [white]{t.get('file', '')}[/white]{deps}")

    # -- Phase 2: Building
    console.print()
    _log("PHASE 2", "Building -- generate, review, verify, fix")
    success = execute_plan(ctx, project_dir)

    # -- Save metadata
    settings_mgr.save_project_metadata({
        "name": plan.get("project_name", slug),
        "prompt": prompt,
        "output_dir": str(project_dir),
        "last_modified": datetime.now().isoformat(),
        "completed": success,
    })

    # -- Final status
    console.print()
    if success:
        _log("DONE", "Build complete -- all files verified")
    else:
        _log("DONE", "Build finished with issues -- type 'plan' to inspect")

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
                    _cmd_chat(ctx, project_dir, fix_prompt)
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
    """Autonomous modification: scan → reason → modify files → commit."""

    # Refresh context from disk
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

    # Build the prompt
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

    response = call_model("coder", messages, stream=True)

    # Apply file changes
    files_written = _apply_file_changes(response, project_dir, ctx)

    # Display response text (strip file blocks)
    display_text = response
    if files_written > 0:
        display_text = re.sub(
            r"===FILE:.*?===END===", "", response, flags=re.DOTALL
        ).strip()
        _log("APPLIED", f"Modified {files_written} file(s)")

    if display_text:
        console.print()
        try:
            console.print(Panel(Markdown(display_text), border_style="cyan", padding=(1, 2)))
        except Exception:
            console.print(Panel(display_text, border_style="cyan", padding=(1, 2)))

    ctx.add_chat("assistant", response[:3000])
    _auto_save(ctx, project_dir)

    # Auto-commit after agentic changes
    if files_written > 0:
        _git_auto_commit(project_dir, settings_mgr, user_request[:60])

    console.print()


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
# Chat — conversational mode
# ═══════════════════════════════════════════════════════════════════

def _cmd_chat(ctx: ContextManager, project_dir: Path, user_message: str) -> None:
    """
    Send a message to the agent within the project context.
    The agent decides whether to modify files or just discuss.
    """

    # Refresh file contents from disk
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

    # Apply any file modifications found in the response
    files_written = _apply_file_changes(response, project_dir, ctx)

    # Display the text response (strip file blocks from display)
    display_text = response
    if files_written > 0:
        display_text = re.sub(
            r"===FILE:.*?===END===", "", response, flags=re.DOTALL
        ).strip()
        _log("APPLIED", f"Updated {files_written} file(s)")

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


def _apply_file_changes(response: str, project_dir: Path, ctx: ContextManager) -> int:
    """
    Parse ===FILE: path=== ... ===END=== blocks from response and write files.
    Returns count of files written.
    """
    files_written = 0

    # Explicit ===FILE:=== markers
    file_blocks = re.findall(
        r"===FILE:\s*(.+?)\s*===\s*\n(.*?)===END===",
        response,
        re.DOTALL,
    )
    for rel_path, content in file_blocks:
        rel_path = rel_path.strip()
        content = content.strip()
        if rel_path and content:
            full_path = project_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            ctx.record_file(rel_path, content)
            console.print(f"           [dim]wrote[/dim] [white]{rel_path}[/white]")
            files_written += 1

    return files_written


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
        _cmd_chat(ctx, project_dir, fix_prompt)

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

    # 2. Node: package.json with start/dev script
    for search_dir in [project_dir] + [project_dir / d for d in ("backend", "server", "api", "frontend", "client")]:
        pkg_json = search_dir / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                scripts = pkg.get("scripts", {})
                if "start" in scripts:
                    return ["npm", "start"], search_dir
                elif "dev" in scripts:
                    return ["npm", "run", "dev"], search_dir
            except Exception:
                pass

    # 3. HTML: look for index.html
    for loc in [project_dir, project_dir / "public", project_dir / "frontend",
                project_dir / "client", project_dir / "dist"]:
        index_html = loc / "index.html"
        if index_html.exists():
            return ["open", str(index_html)], loc

    # 4. Any .py file
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
