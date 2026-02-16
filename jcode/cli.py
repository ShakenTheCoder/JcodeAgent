"""
JCode CLI v2.1 — Rich interactive shell for the 4-role coding agent.

Launch flow:
  1. First-run setup wizard (if needed)
  2. Check Ollama connection
  3. Interactive launcher: new / continue / import
  4. Build pipeline: plan → generate → review → verify → fix
  5. REPL for inspection / additional commands

Commands:
  build <prompt>  — full pipeline: plan → generate → review → verify → fix
  plan            — show current plan
  files           — list generated files
  tree            — show project tree
  projects        — list saved projects
  resume          — resume last project
  update          — self-update JCode to latest version
  save / load     — manual session management
  settings        — show/edit settings
  clear           — clear screen
  help            — show help
  quit / exit     — exit
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

BANNER = (
    "     ╦╔═╗╔═╗╔╦╗╔═╗\n"
    "     ║║  ║ ║ ║║║╣\n"
    "    ╚╝╚═╝╚═╝═╩╝╚═╝  v" + __version__ + "\n"
    "  ─────────────────────────\n"
    "  Local AI Coding Agent\n"
    "  🧠 Planner  · 💻 Coder\n"
    "  🔍 Reviewer · 🔬 Analyzer"
)

HELP_TEXT = """
**Available commands:**

| Command | Description |
|---------|-------------|
| `build <prompt>` | Full pipeline: plan → generate → review → verify |
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

    # ── First-run setup wizard ─────────────────────────────────────
    if settings_mgr.is_first_run():
        _setup_wizard(settings_mgr)

    # ── Show banner ────────────────────────────────────────────────
    console.print(Panel(BANNER, border_style="bright_blue", expand=False))

    # ── Check Ollama ───────────────────────────────────────────────
    if not check_ollama_running():
        console.print("[red]⚠ Ollama is not running![/red]")
        console.print("[dim]Start it with: ollama serve[/dim]")
        console.print("[dim]Then pull models: ollama pull deepseek-r1:14b && ollama pull qwen2.5-coder:14b[/dim]")
        sys.exit(1)

    console.print("[green]✔ Ollama connected[/green]\n")

    # ── Interactive Launcher ───────────────────────────────────────
    ctx, output_dir = _interactive_launcher(settings_mgr)

    # ── Main REPL ──────────────────────────────────────────────────
    console.print("[dim]Type 'help' for commands, or 'build <prompt>' to start a new build.[/dim]\n")

    while True:
        try:
            user_input = pt_prompt(
                "jcode> ",
                history=history,
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            _auto_save_on_exit(ctx, output_dir)
            break

        if not user_input:
            continue

        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # ── Command dispatch ───────────────────────────────────────
        if cmd in ("quit", "exit", "q"):
            _auto_save_on_exit(ctx, output_dir)
            console.print("[dim]Goodbye![/dim]")
            break

        elif cmd == "help":
            console.print(Markdown(HELP_TEXT))

        elif cmd == "clear":
            console.clear()

        elif cmd == "build":
            if not args:
                console.print("[yellow]Usage: build <describe what you want to build>[/yellow]")
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
            console.print(f"[yellow]Unknown command: {cmd}. Type 'help' for options.[/yellow]")


# ═══════════════════════════════════════════════════════════════════
# Interactive Launcher
# ═══════════════════════════════════════════════════════════════════

def _interactive_launcher(settings_mgr: SettingsManager) -> tuple[ContextManager | None, Path | None]:
    """
    Interactive project launcher — shown on every startup.
    Returns (ctx, output_dir) or (None, None) if user skips.
    """
    console.print("[bold]What would you like to do?[/bold]\n")

    projects = settings_mgr.list_projects()
    has_projects = len(projects) > 0

    options = []
    options.append(("new", "🆕 Create a new project"))
    if has_projects:
        options.append(("continue", "📂 Continue a previous project"))
    options.append(("import", "📥 Import a project (local path or GitHub URL)"))
    options.append(("skip", "⏭️  Skip — go straight to the command prompt"))

    for i, (_, label) in enumerate(options, 1):
        console.print(f"  [cyan]{i}[/cyan]  {label}")

    console.print()
    choice_str = pt_prompt("Choose [1]: ").strip()
    if not choice_str:
        choice_str = "1"

    try:
        choice_idx = int(choice_str) - 1
        choice_key = options[choice_idx][0]
    except (ValueError, IndexError):
        choice_key = "skip"

    if choice_key == "new":
        return _launcher_new_project(settings_mgr)
    elif choice_key == "continue":
        return _launcher_continue_project(settings_mgr, projects)
    elif choice_key == "import":
        return _launcher_import_project(settings_mgr)
    else:
        return None, None


def _launcher_new_project(settings_mgr: SettingsManager) -> tuple[ContextManager | None, Path | None]:
    """Create a new project from a prompt."""
    console.print()
    prompt = pt_prompt("Describe what you want to build:\n> ").strip()

    if not prompt:
        console.print("[dim]No prompt entered. Skipping.[/dim]")
        return None, None

    # Optional: clone a GitHub repo as a base
    clone_url = pt_prompt(
        "Clone a GitHub repo as starting point? (paste URL or press Enter to skip): "
    ).strip()

    ctx, output_dir = _cmd_build(prompt, settings_mgr, clone_url=clone_url or None)
    return ctx, output_dir


def _launcher_continue_project(
    settings_mgr: SettingsManager, projects: list[dict]
) -> tuple[ContextManager | None, Path | None]:
    """Show a numbered list of projects and let the user pick one."""
    console.print()
    table = Table(title="Your Projects", show_lines=False)
    table.add_column("#", width=3, style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Last Modified", style="dim")

    for i, p in enumerate(projects, 1):
        status = "[green]✅ Complete[/green]" if p.get("completed") else "[yellow]⚠ In Progress[/yellow]"
        table.add_row(
            str(i),
            p.get("name", "?"),
            status,
            p.get("last_modified", "?")[:16],
        )

    console.print(table)
    console.print()

    pick = pt_prompt(f"Select project [1-{len(projects)}]: ").strip()
    try:
        idx = int(pick) - 1
        proj = projects[idx]
    except (ValueError, IndexError):
        console.print("[dim]Invalid selection. Skipping.[/dim]")
        return None, None

    output_dir = Path(proj.get("output_dir", ""))
    session_file = output_dir / ".jcode_session.json"

    if not session_file.exists():
        console.print(f"[yellow]No session file found at {session_file}[/yellow]")
        console.print("[dim]The project exists but has no resumable session.[/dim]")
        return None, output_dir

    ctx = ContextManager.load_session(session_file)
    console.print(f"\n[green]✔ Loaded: {proj.get('name', '?')}[/green]")
    console.print(f"[dim]📁 {output_dir}[/dim]")

    # Offer to continue building if not complete
    if not proj.get("completed", False):
        if Confirm.ask("Resume building where you left off?", default=True):
            execute_plan(ctx, output_dir)

    return ctx, output_dir


def _launcher_import_project(settings_mgr: SettingsManager) -> tuple[ContextManager | None, Path | None]:
    """Import from local path or GitHub URL."""
    console.print()
    source = pt_prompt("Enter local path or GitHub URL: ").strip()

    if not source:
        console.print("[dim]Nothing entered. Skipping.[/dim]")
        return None, None

    default_dir = settings_mgr.get_default_output_dir()

    if source.startswith("http://") or source.startswith("https://") or source.startswith("git@"):
        # GitHub clone
        repo_name = source.rstrip("/").split("/")[-1].replace(".git", "")
        target_dir = default_dir / repo_name
        console.print(f"[dim]Cloning into {target_dir}...[/dim]")

        try:
            subprocess.run(
                ["git", "clone", source, str(target_dir)],
                check=True, capture_output=True, text=True,
            )
            console.print(f"[green]✔ Cloned: {source}[/green]")
        except FileNotFoundError:
            console.print("[red]Git is not installed. Please install git first.[/red]")
            return None, None
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Clone failed: {e.stderr.strip()}[/red]")
            return None, None

        output_dir = target_dir
    else:
        # Local path
        output_dir = Path(source).expanduser().resolve()
        if not output_dir.exists():
            console.print(f"[red]Path not found: {output_dir}[/red]")
            return None, None

    # Check for existing session
    session_file = output_dir / ".jcode_session.json"
    ctx = None
    if session_file.exists():
        ctx = ContextManager.load_session(session_file)
        console.print(f"[green]✔ Session found and loaded[/green]")
    else:
        console.print(f"[dim]No existing session. You can 'build <prompt>' to start working on this project.[/dim]")

    # Save as a known project
    settings_mgr.save_project_metadata({
        "name": output_dir.name,
        "prompt": "(imported)",
        "output_dir": str(output_dir),
        "last_modified": datetime.now().isoformat(),
        "completed": False,
    })

    console.print(f"[dim]📁 {output_dir}[/dim]")
    return ctx, output_dir


# ═══════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_build(
    prompt: str,
    settings_mgr: SettingsManager,
    clone_url: str | None = None,
) -> tuple[ContextManager, Path]:
    """Full pipeline: plan → generate → review → verify."""
    # ── Choose output directory ────────────────────────────────────
    default_dir = settings_mgr.get_default_output_dir()
    dir_input = pt_prompt(
        f"Output directory [{default_dir}]: ",
    ).strip()

    if dir_input:
        output_dir = Path(dir_input).expanduser().resolve()
    else:
        output_dir = default_dir

    # Append project slug to base dir
    slug = _slugify(prompt[:40])
    output_dir = output_dir / slug

    console.print(f"[dim]📁 Output: {output_dir}[/dim]")

    # ── Optional: clone repo into output dir ───────────────────────
    if clone_url:
        console.print(f"[dim]Cloning {clone_url}...[/dim]")
        try:
            subprocess.run(
                ["git", "clone", clone_url, str(output_dir)],
                check=True, capture_output=True, text=True,
            )
            console.print(f"[green]✔ Repository cloned[/green]")
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            console.print(f"[yellow]⚠ Clone failed, continuing with empty project: {e}[/yellow]")

    # ── Detect complexity ──────────────────────────────────────────
    complexity = detect_complexity(prompt)
    console.print(f"[dim]📊 Detected complexity: {complexity}[/dim]")

    # ── Create context ─────────────────────────────────────────────
    state = ProjectState(
        prompt=prompt,
        output_dir=output_dir,
        complexity=complexity,
    )
    ctx = ContextManager(state)

    # ── Phase 1: Planning ──────────────────────────────────────────
    console.print(Panel("[bold]Phase 1: Planning[/bold]", border_style="magenta"))
    plan = create_plan(prompt, ctx)
    ctx.set_plan(plan)

    task_count = len(plan.get("tasks", []))
    console.print(f"[green]✔ Plan created: {task_count} task(s)[/green]")

    # Show task list
    for t in plan.get("tasks", []):
        deps = f" (depends: {t.get('depends_on', [])})" if t.get("depends_on") else ""
        console.print(f"  {t.get('id', '?')}. [cyan]{t.get('file', '')}[/cyan]{deps}")

    # ── Phase 2: Execution ─────────────────────────────────────────
    console.print(Panel("[bold]Phase 2: Building[/bold]", border_style="green"))
    success = execute_plan(ctx, output_dir)

    # ── Save project metadata ──────────────────────────────────────
    settings_mgr.save_project_metadata({
        "name": plan.get("project_name", slug),
        "prompt": prompt,
        "output_dir": str(output_dir),
        "last_modified": datetime.now().isoformat(),
        "completed": success,
    })

    if success:
        console.print(Panel("[bold green]🎉 Build complete![/bold green]", border_style="green"))
    else:
        console.print(Panel("[bold yellow]⚠ Build finished with issues. Use 'plan' to see task statuses.[/bold yellow]", border_style="yellow"))

    return ctx, output_dir


def _cmd_plan(ctx: ContextManager | None) -> None:
    """Show the current plan."""
    if not ctx or not ctx.state.plan:
        console.print("[dim]No active plan. Use 'build <prompt>' first.[/dim]")
        return

    plan = ctx.state.plan
    console.print(Panel(
        f"[bold]{plan.get('project_name', 'Project')}[/bold]\n"
        f"{plan.get('architecture_summary', '')}",
        title="📋 Current Plan",
        border_style="cyan",
    ))

    summary = ctx.get_task_summary()
    if summary:
        console.print(summary)


def _cmd_files(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """List all generated files."""
    if not output_dir or not output_dir.exists():
        console.print("[dim]No project directory yet.[/dim]")
        return

    files = list(output_dir.rglob("*"))
    files = [f for f in files if f.is_file() and not f.name.startswith(".")]

    if not files:
        console.print("[dim]No files generated yet.[/dim]")
        return

    table = Table(title="Generated Files")
    table.add_column("File", style="cyan")
    table.add_column("Size", justify="right")

    for f in sorted(files):
        rel = f.relative_to(output_dir)
        size = f.stat().st_size
        table.add_row(str(rel), _format_size(size))

    console.print(table)


def _cmd_tree(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Show the project tree."""
    if not output_dir or not output_dir.exists():
        console.print("[dim]No project directory yet.[/dim]")
        return

    name = "Project"
    if ctx and ctx.state.plan:
        name = ctx.state.plan.get("project_name", "Project")
    print_tree(output_dir, name)


def _cmd_projects(settings_mgr: SettingsManager) -> None:
    """List saved projects."""
    projects = settings_mgr.list_projects()
    if not projects:
        console.print("[dim]No saved projects.[/dim]")
        return

    table = Table(title="Saved Projects")
    table.add_column("#", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Last Modified")
    table.add_column("Path", style="dim")

    for i, p in enumerate(projects, 1):
        status = "[green]✅[/green]" if p.get("completed") else "[yellow]⚠[/yellow]"
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
        console.print("[dim]No previous project to resume.[/dim]")
        return None, None

    output_dir = Path(proj.get("output_dir", ""))
    session_file = output_dir / ".jcode_session.json"

    if not session_file.exists():
        console.print(f"[yellow]No session file found at {session_file}[/yellow]")
        return None, None

    ctx = ContextManager.load_session(session_file)
    console.print(f"[green]✔ Resumed project: {proj.get('name', '?')}[/green]")
    console.print(f"[dim]📁 {output_dir}[/dim]")

    return ctx, output_dir


def _cmd_update() -> None:
    """Self-update JCode by pulling latest from git and re-installing."""
    # Find the JCode package installation directory
    jcode_root = Path(__file__).resolve().parent.parent

    console.print(f"[dim]JCode installed at: {jcode_root}[/dim]")
    console.print(f"[dim]Current version: v{__version__}[/dim]")

    # Check if it's a git repo
    if not (jcode_root / ".git").exists():
        console.print("[yellow]⚠ JCode was not installed from git. Cannot auto-update.[/yellow]")
        console.print("[dim]Re-install with: curl -fsSL https://jcode.dev/install.sh | bash[/dim]")
        return

    console.print("[dim]Pulling latest changes...[/dim]")
    try:
        result = subprocess.run(
            ["git", "-C", str(jcode_root), "pull", "--ff-only"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            console.print(f"[yellow]⚠ Git pull failed: {result.stderr.strip()}[/yellow]")
            console.print("[dim]You may have local changes. Try: git stash && jcode update[/dim]")
            return

        if "Already up to date" in result.stdout:
            console.print("[green]✔ Already on the latest version.[/green]")
            return

        console.print(f"[dim]{result.stdout.strip()}[/dim]")
    except FileNotFoundError:
        console.print("[red]Git is not installed.[/red]")
        return
    except subprocess.TimeoutExpired:
        console.print("[yellow]⚠ Git pull timed out.[/yellow]")
        return

    # Re-install the package
    console.print("[dim]Re-installing dependencies...[/dim]")
    pip_cmd = sys.executable.replace("python", "pip")
    # Fallback: use python -m pip
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(jcode_root), "-q"],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]⚠ pip install failed: {e.stderr.strip()}[/yellow]")
        return

    # Read new version
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from jcode import __version__; print(__version__)"],
            capture_output=True, text=True,
        )
        new_version = result.stdout.strip()
    except Exception:
        new_version = "unknown"

    console.print(f"[green]✔ Updated to v{new_version}[/green]")
    console.print("[dim]Restart JCode to use the new version.[/dim]")


def _cmd_save(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Manually save the current session."""
    if not ctx or not output_dir:
        console.print("[dim]Nothing to save.[/dim]")
        return

    session_file = output_dir / ".jcode_session.json"
    ctx.save_session(session_file)
    console.print(f"[green]✔ Session saved to {session_file}[/green]")


def _cmd_load(path_str: str) -> tuple[ContextManager | None, Path | None]:
    """Load a session from a file."""
    if not path_str:
        console.print("[yellow]Usage: load <path-to-session-file>[/yellow]")
        return None, None

    session_file = Path(path_str).expanduser().resolve()
    if not session_file.exists():
        console.print(f"[red]File not found: {session_file}[/red]")
        return None, None

    ctx = ContextManager.load_session(session_file)
    output_dir = Path(ctx.state.output_dir) if ctx.state.output_dir else session_file.parent
    console.print(f"[green]✔ Session loaded from {session_file}[/green]")
    return ctx, output_dir


def _cmd_settings(settings_mgr: SettingsManager) -> None:
    """Show and optionally edit settings."""
    s = settings_mgr.settings
    console.print(Panel(
        f"Default output dir: [cyan]{s.default_output_dir}[/cyan]\n"
        f"Auto-save sessions: {'✅' if s.auto_save_sessions else '❌'}\n"
        f"Last project:       [dim]{s.last_project or 'None'}[/dim]",
        title="⚙️ Settings",
        border_style="cyan",
    ))

    change = pt_prompt("Change default output directory? (enter new path or skip): ").strip()
    if change:
        new_path = Path(change).expanduser().resolve()
        settings_mgr.set_default_output_dir(str(new_path))
        console.print(f"[green]✔ Default output updated to: {new_path}[/green]")


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _setup_wizard(settings_mgr: SettingsManager) -> None:
    """First-run setup wizard."""
    console.print(Panel(
        "[bold]Welcome to JCode! 🚀[/bold]\n\n"
        "Let's set up your workspace.\n"
        "JCode is a local AI coding agent powered by Ollama.\n"
        "It uses 4 specialized roles to build your projects:\n"
        "  🧠 Planner  — architecture & task decomposition\n"
        "  💻 Coder    — code generation & patching\n"
        "  🔍 Reviewer — pre-execution bug catching\n"
        "  🔬 Analyzer — error diagnosis & fix strategy",
        title="First-Time Setup",
        border_style="bright_blue",
    ))

    default_path = "~/jcode_projects"
    dir_input = pt_prompt(
        f"Where should projects be saved? [{default_path}]: ",
    ).strip()

    output_dir = dir_input if dir_input else default_path
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    settings_mgr.set_default_output_dir(str(output_path))
    console.print(f"[green]✔ Projects will be saved to: {output_path}[/green]\n")


def _auto_save_on_exit(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Auto-save session on exit if applicable."""
    if ctx and output_dir and output_dir.exists():
        try:
            session_file = output_dir / ".jcode_session.json"
            ctx.save_session(session_file)
            console.print(f"[dim]Session auto-saved to {session_file}[/dim]")
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
