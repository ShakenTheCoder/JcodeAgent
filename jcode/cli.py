"""
JCode CLI v6.0 — Pure chat-driven project interaction.

Level 1 (Home):
  build <prompt>   — create a new project from scratch
  projects         — list & select a project to enter
  help / quit

Level 2 (Project):
  Everything is natural language — the agent reads your intent:
    - "fix the errors"       → modifies files
    - "add dark mode"        → implements feature
    - "how does routing work" → discusses without changing code
    - "run"                  → detects & runs the project
    - "back"                 → returns to home
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
from jcode.config import ProjectState, detect_complexity
from jcode.context import ContextManager
from jcode.planner import create_plan
from jcode.iteration import execute_plan
from jcode.file_manager import print_tree
from jcode.ollama_client import check_ollama_running, call_model
from jcode.settings import SettingsManager
from jcode.executor import set_autonomous
from jcode.web import set_internet_access, web_search, fetch_page, search_and_summarize
from jcode.prompts import CHAT_SYSTEM, CHAT_CONTEXT

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

HOME_HELP = """
[bold white]Commands[/bold white]

  [cyan]build[/cyan] <prompt>     Plan, generate, review, verify, fix — fully automated
  [cyan]projects[/cyan]           List all saved projects (select to enter)
  [cyan]continue[/cyan]           Resume the last project
  [cyan]update[/cyan]             Update JCode to latest version
  [cyan]uninstall[/cyan]          Remove JCode — projects are saved to Desktop
  [cyan]clear[/cyan]              Clear the terminal
  [cyan]help[/cyan]               Show this help
  [cyan]quit[/cyan]               Exit
"""

PROJECT_HELP = """
[bold white]Project Mode[/bold white]

  Just type naturally — JCode understands your intent.

  [cyan]Ask for changes:[/cyan]
    "fix the login bug"
    "add a dark mode toggle"
    "refactor the API routes to use async/await"

  [cyan]Ask questions:[/cyan]
    "how does the authentication work?"
    "what technologies are we using?"
    "suggest improvements for performance"

  [cyan]Utility:[/cyan]
    [cyan]run[/cyan]          Detect and run the project
    [cyan]plan[/cyan]         Show current build plan and task statuses
    [cyan]files[/cyan]        List generated files
    [cyan]tree[/cyan]         Show project directory tree
    [cyan]rebuild[/cyan]      Re-run the full build pipeline
    [cyan]clear[/cyan]        Clear the terminal
    [cyan]back[/cyan]         Return to home
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
    """Entry point for the JCode CLI."""
    settings_mgr = SettingsManager()
    history = InMemoryHistory()

    # -- First-run: auto-create projects dir
    if settings_mgr.is_first_run():
        _first_run_setup(settings_mgr)

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
            "  [dim]Then pull models:[/dim]  [cyan]ollama pull deepseek-r1:14b && ollama pull qwen2.5-coder:14b[/cyan]",
        )
        sys.exit(1)
    console.print("  [cyan]Ollama connected[/cyan]")

    # -- Projects dir
    projects_dir = settings_mgr.get_default_output_dir()
    console.print(f"  [dim]Projects directory:[/dim] [cyan]{projects_dir}[/cyan]")
    console.print()

    # -- Permissions (only ask if never asked before)
    _check_permissions(settings_mgr)

    # -- Hint
    console.print(
        "  Type [cyan]'help'[/cyan] for commands, [cyan]'build <prompt>'[/cyan] to start.\n"
    )

    # -- Home REPL
    _home_repl(settings_mgr, history)


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
            "Yes -- install packages and run commands automatically",
            "No  -- ask me before each action",
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
            "Yes -- search the web and read documentation",
            "No  -- work offline only",
        ])
        settings_mgr.settings.internet_access = (choice == 0)
        settings_mgr.save_settings()

    set_internet_access(settings_mgr.settings.internet_access)

    if settings_mgr.settings.internet_access:
        console.print("  [cyan]Internet access: on[/cyan]")
    else:
        console.print("  [dim]Internet access: off[/dim]")
    console.print()


def _first_run_setup(settings_mgr: SettingsManager) -> None:
    """Silent first-run: create default projects dir."""
    default_dir = Path("~/jcode_projects").expanduser().resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    settings_mgr.set_default_output_dir(str(default_dir))


# ═══════════════════════════════════════════════════════════════════
# Level 1: Home REPL
# ═══════════════════════════════════════════════════════════════════

def _home_repl(settings_mgr: SettingsManager, history: InMemoryHistory) -> None:
    """Top-level REPL: build, projects, continue, help, quit."""
    while True:
        try:
            user_input = pt_prompt("jcode> ", history=history).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break
        elif cmd == "help":
            console.print(HOME_HELP, highlight=False)
        elif cmd == "clear":
            console.clear()
        elif cmd == "build":
            if not args:
                console.print("  [dim]Usage:[/dim] [cyan]build <describe what you want>[/cyan]")
                continue
            result = _cmd_build(args, settings_mgr)
            if result:
                ctx, output_dir = result
                _project_repl(ctx, output_dir, settings_mgr)
        elif cmd in ("continue", "projects"):
            result = _cmd_select_project(settings_mgr)
            if result:
                ctx, output_dir = result
                _project_repl(ctx, output_dir, settings_mgr)
        elif cmd == "update":
            _cmd_update()
        elif cmd == "uninstall":
            _cmd_uninstall(settings_mgr)
        else:
            # Treat anything else as an implicit build prompt
            result = _cmd_build(user_input, settings_mgr)
            if result:
                ctx, output_dir = result
                _project_repl(ctx, output_dir, settings_mgr)


# ═══════════════════════════════════════════════════════════════════
# Level 2: Project REPL — pure chat
# ═══════════════════════════════════════════════════════════════════

def _project_repl(
    ctx: ContextManager,
    output_dir: Path,
    settings_mgr: SettingsManager,
) -> None:
    """Per-project REPL: everything is chat unless it's a utility command."""
    proj_name = ctx.state.name or "project"
    history = InMemoryHistory()

    console.print(f"\n  [cyan]Entered project:[/cyan] [bold white]{proj_name}[/bold white]")
    console.print(f"  [dim]{output_dir}[/dim]")
    console.print(
        "  Chat naturally — ask questions, request changes, or type [cyan]'help'[/cyan].\n"
    )

    while True:
        try:
            user_input = pt_prompt(
                f"{proj_name}> ", history=history,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            _auto_save(ctx, output_dir)
            break

        if not user_input:
            continue

        cmd = user_input.lower().strip()

        # Utility commands (exact match only)
        if cmd in ("back", "home"):
            _auto_save(ctx, output_dir)
            console.print("  [dim]Returning to home.[/dim]\n")
            break
        elif cmd == "help":
            console.print(PROJECT_HELP, highlight=False)
            continue
        elif cmd == "clear":
            console.clear()
            continue
        elif cmd == "run":
            _cmd_run(ctx, output_dir)
            continue
        elif cmd == "plan":
            _cmd_plan(ctx)
            continue
        elif cmd == "files":
            _cmd_files(output_dir)
            continue
        elif cmd == "tree":
            _cmd_tree(ctx, output_dir)
            continue
        elif cmd == "rebuild":
            _log("REBUILD", "Re-running build pipeline")
            execute_plan(ctx, output_dir)
            _auto_save(ctx, output_dir)
            continue

        # Everything else → chat with the agent
        _cmd_chat(ctx, output_dir, user_input)


# ═══════════════════════════════════════════════════════════════════
# Build command
# ═══════════════════════════════════════════════════════════════════

def _cmd_build(
    prompt: str,
    settings_mgr: SettingsManager,
) -> tuple[ContextManager, Path] | None:
    """Full autonomous pipeline: plan > generate > review > verify > fix."""

    default_dir = settings_mgr.get_default_output_dir()
    slug = _slugify(prompt[:40])
    output_dir = default_dir / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n  [dim]Project:[/dim] [cyan]{slug}[/cyan]")
    console.print(f"  [dim]Output:[/dim]  [cyan]{output_dir}[/cyan]")

    complexity = detect_complexity(prompt)
    console.print(f"  [dim]Complexity:[/dim] {complexity}")

    state = ProjectState(
        name=slug,
        description=prompt,
        output_dir=output_dir,
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
    success = execute_plan(ctx, output_dir)

    # -- Save metadata
    settings_mgr.save_project_metadata({
        "name": plan.get("project_name", slug),
        "prompt": prompt,
        "output_dir": str(output_dir),
        "last_modified": datetime.now().isoformat(),
        "completed": success,
    })

    # -- Final status
    console.print()
    if success:
        _log("DONE", "Build complete -- all files verified")
    else:
        _log("DONE", "Build finished with issues -- type 'plan' to inspect")

    console.print(f"  [dim]Saved to:[/dim] [cyan]{output_dir}[/cyan]\n")

    _auto_save(ctx, output_dir)

    # -- Phase 3: Post-build runtime verification
    if success:
        run_cmd, run_cwd = _detect_run_command(output_dir)
        if run_cmd:
            console.print()
            _log("PHASE 3", "Runtime verification -- running the project to check for errors")
            _install_deps_if_needed(output_dir)

            exit_code, run_output = _run_and_capture(run_cmd, run_cwd)

            if exit_code not in (0, -2) and run_output.strip():
                _log("VERIFY", f"Runtime error detected (exit code {exit_code})")
                # Auto-fix loop
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
                    _cmd_chat(ctx, output_dir, fix_prompt)
                    _install_deps_if_needed(output_dir)

                    exit_code, run_output = _run_and_capture(run_cmd, run_cwd)
                    if exit_code in (0, -2):
                        _log("VERIFY", "Runtime verification passed after fix")
                        break
                else:
                    _log("VERIFY", "Could not auto-fix runtime errors -- you can fix manually in chat")
            elif exit_code in (0, -2):
                _log("VERIFY", "Runtime verification passed")

    return ctx, output_dir


# ═══════════════════════════════════════════════════════════════════
# Project selection
# ═══════════════════════════════════════════════════════════════════

def _cmd_select_project(
    settings_mgr: SettingsManager,
) -> tuple[ContextManager, Path] | None:
    """List projects, let user pick one, load its context."""
    projects = settings_mgr.list_projects()

    if not projects:
        console.print("  [dim]No saved projects. Use 'build <prompt>' to start one.[/dim]")
        return None

    # Show project table
    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("#", width=4, justify="right", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Status", justify="center")
    table.add_column("Last Modified", style="dim")
    table.add_column("Path", style="dim")

    for i, p in enumerate(projects, 1):
        status = "[cyan]done[/cyan]" if p.get("completed") else "[dim]in progress[/dim]"
        table.add_row(
            str(i),
            p.get("name", "?"),
            status,
            p.get("last_modified", "?")[:16],
            p.get("output_dir", "?"),
        )

    console.print(table)
    console.print()

    # Let user pick
    names = [
        f"{p.get('name', '?')}  [dim]({('done' if p.get('completed') else 'in progress')})[/dim]"
        for p in projects
    ]
    idx = _select_one("Select a project:", names)
    if idx is None:
        return None

    proj = projects[idx]
    output_dir = Path(proj.get("output_dir", ""))
    session_file = output_dir / ".jcode_session.json"

    if not session_file.exists():
        console.print(f"  [dim]No session data — loading from files on disk.[/dim]")
        state = ProjectState(
            name=proj.get("name", "project"),
            description=proj.get("prompt", ""),
            output_dir=output_dir,
            completed=proj.get("completed", False),
        )
        ctx = ContextManager(state)
        _scan_project_files(ctx, output_dir)
        _log("LOADED", f"{proj.get('name', '?')} ({_count_project_files(output_dir)} files)")
        return ctx, output_dir

    ctx = ContextManager.load_session(session_file)
    _scan_project_files(ctx, output_dir)
    _log("LOADED", f"{proj.get('name', '?')} ({_count_project_files(output_dir)} files)")
    return ctx, output_dir


def _scan_project_files(ctx: ContextManager, output_dir: Path) -> None:
    """Scan project directory and load file contents into context."""
    if not output_dir.exists():
        return
    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", ".next", "dist", "build"}
    for f in output_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            # Skip files inside ignored directories
            if any(part in skip_dirs for part in f.relative_to(output_dir).parts):
                continue
            try:
                rel = str(f.relative_to(output_dir))
                content = f.read_text(errors="replace")
                ctx.record_file(rel, content)
            except Exception:
                pass


def _count_project_files(output_dir: Path) -> int:
    """Count non-hidden files in project dir."""
    if not output_dir.exists():
        return 0
    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", ".next", "dist", "build"}
    count = 0
    for f in output_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            if not any(part in skip_dirs for part in f.relative_to(output_dir).parts):
                count += 1
    return count


# ═══════════════════════════════════════════════════════════════════
# Chat — the core of project interaction
# ═══════════════════════════════════════════════════════════════════

def _cmd_chat(ctx: ContextManager, output_dir: Path, user_message: str) -> None:
    """
    Send a message to the agent within the project context.
    The agent decides whether to modify files or just discuss.
    """

    # Refresh file contents from disk
    _scan_project_files(ctx, output_dir)

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
    files_written = _apply_file_changes(response, output_dir, ctx)

    # Display the text response (strip file blocks from display)
    display_text = response
    if files_written > 0:
        # Remove file blocks from what we display
        display_text = re.sub(
            r"===FILE:.*?===END===", "", response, flags=re.DOTALL
        ).strip()
        _log("APPLIED", f"Updated {files_written} file(s)")

    if display_text:
        console.print()
        # Try to render as markdown for nicer formatting
        try:
            console.print(Panel(Markdown(display_text), border_style="dim", padding=(1, 2)))
        except Exception:
            console.print(Panel(display_text, border_style="dim", padding=(1, 2)))

    # Record assistant response
    ctx.add_chat("assistant", response[:3000])
    _auto_save(ctx, output_dir)
    console.print()


def _apply_file_changes(response: str, output_dir: Path, ctx: ContextManager) -> int:
    """
    Parse ===FILE: path=== ... ===END=== blocks from response and write files.
    Also detect ```language\n...``` fenced code blocks that look like full files
    when preceded by a filename reference.
    Returns count of files written.
    """
    files_written = 0

    # Method 1: Explicit ===FILE:=== markers (preferred)
    file_blocks = re.findall(
        r"===FILE:\s*(.+?)\s*===\s*\n(.*?)===END===",
        response,
        re.DOTALL,
    )
    for rel_path, content in file_blocks:
        rel_path = rel_path.strip()
        content = content.strip()
        if rel_path and content:
            full_path = output_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            ctx.record_file(rel_path, content)
            console.print(f"           [dim]wrote[/dim] [white]{rel_path}[/white]")
            files_written += 1

    return files_written


# ═══════════════════════════════════════════════════════════════════
# Run command — smart detection with dep install
# ═══════════════════════════════════════════════════════════════════

def _cmd_run(ctx: ContextManager, output_dir: Path) -> None:
    """Auto-detect and run the project. If it fails, auto-fix and retry."""
    if not output_dir or not output_dir.exists():
        console.print("  [dim]No project directory.[/dim]")
        return

    _log("RUN", f"Detecting how to run {output_dir.name}")

    # Install dependencies first if needed
    _install_deps_if_needed(output_dir)

    # Find the run command
    run_cmd, run_cwd = _detect_run_command(output_dir)
    if not run_cmd:
        console.print("  [dim]Could not detect how to run this project.[/dim]")
        console.print("  [dim]Ask JCode: 'how do I run this project?'[/dim]")
        return

    MAX_RUN_FIX_ATTEMPTS = 5
    for attempt in range(1, MAX_RUN_FIX_ATTEMPTS + 1):
        _log("RUN", f"{' '.join(run_cmd)} (in {run_cwd.name})")

        # Try to run — capture output for error detection
        exit_code, output = _run_and_capture(run_cmd, run_cwd)

        if exit_code == 0:
            _log("RUN", "Process exited successfully")
            return

        if exit_code == -2:
            # User pressed Ctrl+C — not an error
            return

        # Run failed — auto-fix
        _log("RUN", f"Process exited with code {exit_code}")

        if attempt >= MAX_RUN_FIX_ATTEMPTS:
            _log("RUN", f"Failed after {MAX_RUN_FIX_ATTEMPTS} fix attempts")
            console.print(
                "  [dim]Auto-fix could not resolve the issue. Try fixing manually:[/dim]"
            )
            console.print(f"  [dim]Tell JCode what you see and it will help.[/dim]")
            return

        # Feed the error to the agent for fixing
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
        _cmd_chat(ctx, output_dir, fix_prompt)

        # Re-install deps in case the fix added new ones
        _install_deps_if_needed(output_dir)

        _log("FIX", "Re-running after fix...")


def _detect_run_command(output_dir: Path) -> tuple[list[str] | None, Path | None]:
    """Detect the command needed to run this project. Returns (cmd, cwd) or (None, None)."""
    # 1. Python: look for main entry points
    for entry in ("main.py", "app.py", "manage.py", "server.py", "run.py"):
        candidate = output_dir / entry
        if candidate.exists():
            return ["python3", str(candidate)], output_dir
        for subdir in ("backend", "src", "server", "api"):
            candidate = output_dir / subdir / entry
            if candidate.exists():
                return ["python3", str(candidate)], output_dir / subdir

    # 2. Node: package.json with start/dev script
    for search_dir in [output_dir] + [output_dir / d for d in ("backend", "server", "api", "frontend", "client")]:
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
    for loc in [output_dir, output_dir / "public", output_dir / "frontend",
                output_dir / "client", output_dir / "dist"]:
        index_html = loc / "index.html"
        if index_html.exists():
            return ["open", str(index_html)], loc

    # 4. Any .py file
    py_files = list(output_dir.glob("*.py"))
    if py_files:
        return ["python3", str(py_files[0])], output_dir

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


def _install_deps_if_needed(output_dir: Path) -> None:
    """Install project dependencies if package manager files exist."""
    # Node: package.json without node_modules
    for search_dir in [output_dir] + [output_dir / d for d in ("backend", "server", "frontend", "client")]:
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
    req_txt = output_dir / "requirements.txt"
    if req_txt.exists():
        _log("DEPS", "Installing Python requirements...")
        try:
            subprocess.run(
                ["python3", "-m", "pip", "install", "-r", str(req_txt), "-q"],
                cwd=output_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            _log("DEPS", "pip install complete")
        except Exception as e:
            console.print(f"  [dim]pip install failed: {e}[/dim]")


def _run_subprocess(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """Legacy wrapper — delegates to _run_and_capture."""
    return _run_and_capture(cmd, cwd)


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


def _cmd_files(output_dir: Path | None) -> None:
    """List all generated files."""
    if not output_dir or not output_dir.exists():
        console.print("  [dim]No project directory yet.[/dim]")
        return

    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", ".next", "dist", "build"}
    files = []
    for f in output_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            if not any(part in skip_dirs for part in f.relative_to(output_dir).parts):
                files.append(f)

    if not files:
        console.print("  [dim]No files generated yet.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("File", style="white")
    table.add_column("Size", justify="right", style="dim")

    for f in sorted(files):
        rel = f.relative_to(output_dir)
        table.add_row(str(rel), _format_size(f.stat().st_size))

    console.print(table)


def _cmd_tree(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Show the project tree."""
    if not output_dir or not output_dir.exists():
        console.print("  [dim]No project directory yet.[/dim]")
        return
    name = "Project"
    if ctx and ctx.state.plan:
        name = ctx.state.plan.get("project_name", "Project")
    print_tree(output_dir, name)


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
    """Uninstall JCode: move projects to Desktop, remove install + config."""
    console.print()
    console.print("  [bold white]Uninstall JCode[/bold white]")
    console.print()

    projects_dir = settings_mgr.get_default_output_dir()
    desktop = Path.home() / "Desktop" / "jcode_projects_backup"
    jcode_root = Path(__file__).resolve().parent.parent
    config_dir = Path.home() / ".jcode"

    console.print("  [dim]This will:[/dim]")
    console.print(f"    [dim]1. Copy your projects to[/dim] [cyan]{desktop}[/cyan]")
    console.print("    [dim]2. Uninstall the jcode package[/dim]")
    console.print(f"    [dim]3. Remove config at[/dim] [cyan]{config_dir}[/cyan]")
    console.print()

    choice = _select_one("Proceed with uninstall?", [
        "Yes -- uninstall and save projects to Desktop",
        "No  -- cancel",
    ])

    if choice != 0:
        console.print("  [dim]Cancelled.[/dim]")
        return

    if projects_dir.exists():
        _log("UNINSTALL", f"Copying projects to {desktop}")
        desktop.mkdir(parents=True, exist_ok=True)
        for item in projects_dir.iterdir():
            dest = desktop / item.name
            try:
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
            except Exception as e:
                console.print(f"  [dim]Could not copy {item.name}: {e}[/dim]")
        _log("UNINSTALL", "Projects saved")

    _log("UNINSTALL", "Removing jcode package")
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "jcode", "-y"],
        capture_output=True, text=True,
    )

    if config_dir.exists():
        _log("UNINSTALL", "Removing config directory")
        shutil.rmtree(config_dir, ignore_errors=True)

    _log("UNINSTALL", "Done")
    console.print(f"\n  [cyan]Your projects are saved at:[/cyan] {desktop}")
    console.print(f"  [dim]To remove the source code:[/dim] [cyan]rm -rf {jcode_root}[/cyan]\n")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _auto_save(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Auto-save session if applicable."""
    if ctx and output_dir and output_dir.exists():
        try:
            session_file = output_dir / ".jcode_session.json"
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
