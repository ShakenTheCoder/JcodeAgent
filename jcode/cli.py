"""
JCode CLI v3.0 — Minimal, clean terminal interface.

Colors: cyan + white only. No emojis. No clutter.

Launch flow:
  1. First-run setup wizard (if needed)
  2. Check Ollama connection
  3. Interactive launcher: new project / continue existing
  4. Build pipeline: plan > generate > review > verify > fix
  5. REPL for inspection / additional commands
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.history import InMemoryHistory

from jcode import __version__
from jcode.config import ProjectState, detect_complexity
from jcode.context import ContextManager
from jcode.planner import create_plan
from jcode.iteration import execute_plan
from jcode.file_manager import print_tree
from jcode.ollama_client import check_ollama_running
from jcode.settings import SettingsManager

console = Console()

# ═══════════════════════════════════════════════════════════════════
# ASCII Art — blocky pixel style
# ═══════════════════════════════════════════════════════════════════

BANNER = r"""
     ██╗ ██████╗ ██████╗ ██████╗ ███████╗
     ██║██╔════╝██╔═══██╗██╔══██╗██╔════╝
     ██║██║     ██║   ██║██║  ██║█████╗
██   ██║██║     ██║   ██║██║  ██║██╔══╝
╚█████╔╝╚██████╗╚██████╔╝██████╔╝███████╗
 ╚════╝  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝"""

TAG_LINE = "your local, unlimited & private software engineer"

HELP_TEXT = """
**Available commands:**

| Command | Description |
|---------|-------------|
| `build <prompt>` | Full pipeline: plan > generate > review > verify |
| `plan` | Show current plan |
| `files` | List generated files |
| `tree` | Show project directory tree |
| `projects` | List all saved projects |
| `resume` | Resume the last project |
| `update` | Update JCode to latest version |
| `save` | Manually save current session |
| `load <path>` | Load a session file |
| `settings` | View/edit settings |
| `clear` | Clear screen |
| `help` | Show this help |
| `quit` / `exit` | Exit JCode |
"""


def main():
    """Entry point for the JCode CLI."""
    settings_mgr = SettingsManager()
    ctx: ContextManager | None = None
    output_dir: Path | None = None
    history = InMemoryHistory()

    # -- First-run setup wizard
    if settings_mgr.is_first_run():
        _setup_wizard(settings_mgr)

    # -- Banner
    console.print(BANNER, style="bold cyan", highlight=False)
    console.print(
        f"  v{__version__}  |  {TAG_LINE}",
        style="dim white",
    )
    console.print()

    # -- Check Ollama
    if not check_ollama_running():
        console.print("  [bold red]Ollama is not running.[/bold red]")
        console.print("  [dim]Start it with:[/dim]  ollama serve", style="white")
        console.print(
            "  [dim]Then pull models:[/dim]  ollama pull deepseek-r1:14b && ollama pull qwen2.5-coder:14b",
            style="white",
        )
        sys.exit(1)

    console.print("  [cyan]Ollama connected[/cyan]")
    console.print()

    # -- Interactive Launcher
    result = _interactive_launcher(settings_mgr)
    if result:
        ctx, output_dir = result

    # -- Main REPL
    console.print("[dim]Type 'help' for commands, 'build <prompt>' to start.[/dim]\n")

    while True:
        try:
            user_input = pt_prompt("jcode> ", history=history).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            _auto_save_on_exit(ctx, output_dir)
            break

        if not user_input:
            continue

        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            _auto_save_on_exit(ctx, output_dir)
            console.print("[dim]Goodbye.[/dim]")
            break
        elif cmd == "help":
            console.print(Markdown(HELP_TEXT))
        elif cmd == "clear":
            console.clear()
        elif cmd == "build":
            if not args:
                console.print("[dim]Usage: build <describe what you want>[/dim]")
                continue
            ctx, output_dir = _cmd_build(args, settings_mgr)
        elif cmd == "plan":
            _cmd_plan(ctx)
        elif cmd == "files":
            _cmd_files(ctx, output_dir)
        elif cmd == "tree":
            _cmd_tree(ctx, output_dir)
        elif cmd == "projects":
            _cmd_projects(settings_mgr)
        elif cmd == "resume":
            ctx, output_dir = _cmd_resume(settings_mgr)
        elif cmd == "update":
            _cmd_update()
        elif cmd == "save":
            _cmd_save(ctx, output_dir)
        elif cmd == "load":
            ctx, output_dir = _cmd_load(args)
        elif cmd == "settings":
            _cmd_settings(settings_mgr)
        else:
            console.print(f"[dim]Unknown command: {cmd}. Type 'help'.[/dim]")


# ═══════════════════════════════════════════════════════════════════
# Interactive Launcher
# ═══════════════════════════════════════════════════════════════════

def _interactive_launcher(
    settings_mgr: SettingsManager,
) -> tuple[ContextManager, Path] | None:
    """
    Startup launcher.  Two choices:
      1  New project   — blank or clone from GitHub
      2  Continue      — pick from saved projects
    """
    projects = settings_mgr.list_projects()
    has_projects = bool(projects)

    console.print("  [bold white]What would you like to do?[/bold white]\n")

    console.print("    [cyan]1[/cyan]  New project", style="white")
    if has_projects:
        console.print("    [cyan]2[/cyan]  Continue an existing project", style="white")
    console.print()

    choice = pt_prompt("  > ").strip()

    if choice == "1":
        return _launcher_new_project(settings_mgr)
    elif choice == "2" and has_projects:
        return _launcher_continue_project(settings_mgr, projects)
    elif choice == "2" and not has_projects:
        console.print("[dim]  No projects yet. Starting a new one.[/dim]\n")
        return _launcher_new_project(settings_mgr)
    else:
        return _launcher_new_project(settings_mgr)


def _launcher_new_project(
    settings_mgr: SettingsManager,
) -> tuple[ContextManager, Path] | None:
    """New project flow — describe it, optionally clone, pick directory."""
    console.print()

    # -- Show and confirm output directory
    default_dir = settings_mgr.get_default_output_dir()
    console.print(f"  [dim]Save location:[/dim] [cyan]{default_dir}[/cyan]")

    change = pt_prompt("  Change? (enter new path or press Enter to keep): ").strip()
    if change:
        default_dir = Path(change).expanduser().resolve()
        settings_mgr.set_default_output_dir(str(default_dir))
        console.print(f"  [cyan]Updated to: {default_dir}[/cyan]")

    console.print()

    # -- Project type
    console.print("  [bold white]How do you want to start?[/bold white]\n")
    console.print("    [cyan]1[/cyan]  Blank project — describe what to build", style="white")
    console.print("    [cyan]2[/cyan]  Clone from GitHub — start from an existing repo", style="white")
    console.print()

    start_choice = pt_prompt("  > ").strip()

    clone_url = None
    if start_choice == "2":
        console.print()
        clone_url = pt_prompt("  GitHub URL: ").strip()
        if not clone_url:
            console.print("  [dim]No URL entered. Starting blank.[/dim]")
            clone_url = None

    # -- Prompt
    console.print()
    prompt = pt_prompt("  Describe what you want to build:\n  > ").strip()
    if not prompt:
        console.print("  [dim]No description. Returning to prompt.[/dim]")
        return None

    return _cmd_build(prompt, settings_mgr, clone_url=clone_url)


def _launcher_continue_project(
    settings_mgr: SettingsManager, projects: list[dict],
) -> tuple[ContextManager, Path] | None:
    """Pick a project from the saved list and resume it."""
    console.print()

    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("#", width=4, style="cyan", justify="right")
    table.add_column("Project", style="bold white")
    table.add_column("Status", justify="center")
    table.add_column("Last Modified", style="dim")

    for i, p in enumerate(projects, 1):
        status = "[cyan]done[/cyan]" if p.get("completed") else "[dim]in progress[/dim]"
        table.add_row(
            str(i),
            p.get("name", "?"),
            status,
            p.get("last_modified", "?")[:16],
        )

    console.print(table)
    console.print()

    pick = pt_prompt(f"  Select [1-{len(projects)}]: ").strip()
    try:
        idx = int(pick) - 1
        proj = projects[idx]
    except (ValueError, IndexError):
        console.print("  [dim]Invalid selection.[/dim]")
        return None

    output_dir = Path(proj.get("output_dir", ""))
    session_file = output_dir / ".jcode_session.json"

    if not session_file.exists():
        console.print(f"  [dim]No session file at {session_file}[/dim]")
        console.print("  [dim]Project exists but has no resumable session.[/dim]")
        return None

    ctx = ContextManager.load_session(session_file)
    console.print(f"\n  [cyan]Loaded: {proj.get('name', '?')}[/cyan]")
    console.print(f"  [dim]{output_dir}[/dim]")

    if not proj.get("completed", False):
        console.print()
        if Confirm.ask("  Resume building where you left off?", default=True):
            execute_plan(ctx, output_dir)

    return ctx, output_dir


# ═══════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_build(
    prompt: str,
    settings_mgr: SettingsManager,
    clone_url: str | None = None,
) -> tuple[ContextManager, Path]:
    """Full pipeline: plan > generate > review > verify."""

    # -- Output directory
    default_dir = settings_mgr.get_default_output_dir()
    slug = _slugify(prompt[:40])
    output_dir = default_dir / slug

    console.print(f"\n  [dim]Output:[/dim] [cyan]{output_dir}[/cyan]")

    # -- Clone if requested
    if clone_url:
        console.print(f"  [dim]Cloning {clone_url}...[/dim]")
        try:
            subprocess.run(
                ["git", "clone", clone_url, str(output_dir)],
                check=True, capture_output=True, text=True,
            )
            console.print("  [cyan]Repository cloned[/cyan]")
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            console.print(f"  [dim]Clone failed, continuing blank: {e}[/dim]")

    # -- Detect complexity
    complexity = detect_complexity(prompt)
    console.print(f"  [dim]Complexity:[/dim] {complexity}")

    # -- Create context
    state = ProjectState(
        name=slug,
        description=prompt,
        output_dir=output_dir,
        complexity=complexity,
    )
    ctx = ContextManager(state)

    # -- Phase 1: Planning
    console.print()
    console.print(
        Panel(
            "[bold white]Phase 1  PLANNING[/bold white]",
            border_style="cyan",
            expand=False,
            padding=(0, 2),
        )
    )
    plan = create_plan(prompt, ctx)
    ctx.set_plan(plan)

    task_count = len(plan.get("tasks", []))
    console.print(f"  [cyan]Plan created: {task_count} task(s)[/cyan]")

    for t in plan.get("tasks", []):
        deps = f"  [dim](deps: {t.get('depends_on', [])})[/dim]" if t.get("depends_on") else ""
        console.print(f"    {t.get('id', '?')}. [white]{t.get('file', '')}[/white]{deps}")

    # -- Phase 2: Building
    console.print()
    console.print(
        Panel(
            "[bold white]Phase 2  BUILDING[/bold white]",
            border_style="cyan",
            expand=False,
            padding=(0, 2),
        )
    )
    success = execute_plan(ctx, output_dir)

    # -- Save metadata
    settings_mgr.save_project_metadata({
        "name": plan.get("project_name", slug),
        "prompt": prompt,
        "output_dir": str(output_dir),
        "last_modified": datetime.now().isoformat(),
        "completed": success,
    })

    if success:
        console.print(
            Panel(
                "[bold cyan]Build complete.[/bold cyan]",
                border_style="cyan",
                expand=False,
                padding=(0, 2),
            )
        )
    else:
        console.print(
            Panel(
                "[bold white]Build finished with issues.  Use 'plan' to see statuses.[/bold white]",
                border_style="dim",
                expand=False,
                padding=(0, 2),
            )
        )

    return ctx, output_dir


def _cmd_plan(ctx: ContextManager | None) -> None:
    """Show the current plan."""
    if not ctx or not ctx.state.plan:
        console.print("  [dim]No active plan. Use 'build <prompt>' first.[/dim]")
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


def _cmd_files(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """List all generated files."""
    if not output_dir or not output_dir.exists():
        console.print("  [dim]No project directory yet.[/dim]")
        return

    files = [f for f in output_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]
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


def _cmd_projects(settings_mgr: SettingsManager) -> None:
    """List saved projects."""
    projects = settings_mgr.list_projects()
    if not projects:
        console.print("  [dim]No saved projects.[/dim]")
        return

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


def _cmd_resume(settings_mgr: SettingsManager) -> tuple[ContextManager | None, Path | None]:
    """Resume the last project."""
    proj = settings_mgr.get_last_project()
    if not proj:
        console.print("  [dim]No previous project to resume.[/dim]")
        return None, None

    output_dir = Path(proj.get("output_dir", ""))
    session_file = output_dir / ".jcode_session.json"

    if not session_file.exists():
        console.print(f"  [dim]No session file at {session_file}[/dim]")
        return None, None

    ctx = ContextManager.load_session(session_file)
    console.print(f"  [cyan]Resumed: {proj.get('name', '?')}[/cyan]")
    console.print(f"  [dim]{output_dir}[/dim]")
    return ctx, output_dir


def _cmd_update() -> None:
    """Self-update JCode from git."""
    jcode_root = Path(__file__).resolve().parent.parent

    console.print(f"  [dim]Install path: {jcode_root}[/dim]")
    console.print(f"  [dim]Current version: v{__version__}[/dim]")

    if not (jcode_root / ".git").exists():
        console.print("  [dim]Not a git install. Cannot auto-update.[/dim]")
        return

    console.print("  [dim]Pulling latest...[/dim]")
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

    console.print("  [dim]Re-installing...[/dim]")
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

    console.print(f"  [cyan]Updated to v{new_version}[/cyan]")
    console.print("  [dim]Restart JCode to use the new version.[/dim]")


def _cmd_save(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Manually save the current session."""
    if not ctx or not output_dir:
        console.print("  [dim]Nothing to save.[/dim]")
        return

    session_file = output_dir / ".jcode_session.json"
    ctx.save_session(session_file)
    console.print(f"  [cyan]Session saved to {session_file}[/cyan]")


def _cmd_load(path_str: str) -> tuple[ContextManager | None, Path | None]:
    """Load a session from a file."""
    if not path_str:
        console.print("  [dim]Usage: load <path-to-session-file>[/dim]")
        return None, None

    session_file = Path(path_str).expanduser().resolve()
    if not session_file.exists():
        console.print(f"  [dim]File not found: {session_file}[/dim]")
        return None, None

    ctx = ContextManager.load_session(session_file)
    output_dir = Path(ctx.state.output_dir) if ctx.state.output_dir else session_file.parent
    console.print(f"  [cyan]Session loaded from {session_file}[/cyan]")
    return ctx, output_dir


def _cmd_settings(settings_mgr: SettingsManager) -> None:
    """Show and optionally edit settings."""
    s = settings_mgr.settings
    console.print(
        Panel(
            f"Default output dir:  [cyan]{s.default_output_dir}[/cyan]\n"
            f"Auto-save sessions:  {'yes' if s.auto_save_sessions else 'no'}\n"
            f"Last project:        [dim]{s.last_project or 'None'}[/dim]",
            title="Settings",
            border_style="cyan",
        )
    )

    change = pt_prompt("  Change default output directory? (enter new path or skip): ").strip()
    if change:
        new_path = Path(change).expanduser().resolve()
        settings_mgr.set_default_output_dir(str(new_path))
        console.print(f"  [cyan]Updated to: {new_path}[/cyan]")


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _setup_wizard(settings_mgr: SettingsManager) -> None:
    """First-run setup — minimal, no clutter."""
    console.print()
    console.print("  [bold cyan]First-Time Setup[/bold cyan]")
    console.print("  [dim]JCode needs a directory to save your projects.[/dim]")
    console.print()

    default_path = "~/jcode_projects"
    dir_input = pt_prompt(f"  Save location [{default_path}]: ").strip()

    output_dir = dir_input if dir_input else default_path
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    settings_mgr.set_default_output_dir(str(output_path))
    console.print(f"  [cyan]Projects will be saved to: {output_path}[/cyan]\n")


def _auto_save_on_exit(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Auto-save session on exit if applicable."""
    if ctx and output_dir and output_dir.exists():
        try:
            session_file = output_dir / ".jcode_session.json"
            ctx.save_session(session_file)
            console.print(f"  [dim]Session saved to {session_file}[/dim]")
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
