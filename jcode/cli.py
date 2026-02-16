"""
JCode CLI v4.0 — Clean, autonomous terminal interface.

Colors: cyan + white only. No emojis. No clutter.

Launch flow:
  1. Banner + greeting + hint
  2. First-run setup (auto, no customization prompts)
  3. Autonomy approval (install packages / run commands)
  4. Check Ollama
  5. REPL:  build <prompt>  |  continue  |  help  |  uninstall
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

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
from jcode.executor import set_autonomous

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

GREETING = "Welcome back." if Path("~/.jcode/settings.json").expanduser().exists() else "Welcome."

HELP_TEXT = """
[bold white]Commands[/bold white]

  [cyan]build[/cyan] <prompt>     Plan, generate, review, verify, fix — fully automated
  [cyan]continue[/cyan]           Resume the last project or pick from saved ones
  [cyan]projects[/cyan]           List all saved projects
  [cyan]plan[/cyan]               Show current plan and task statuses
  [cyan]files[/cyan]              List generated files
  [cyan]tree[/cyan]               Show project directory tree
  [cyan]update[/cyan]             Update JCode to latest version
  [cyan]uninstall[/cyan]          Remove JCode — projects are saved to Desktop
  [cyan]clear[/cyan]              Clear the terminal
  [cyan]help[/cyan]               Show this help
  [cyan]quit[/cyan]               Exit
"""


# ═══════════════════════════════════════════════════════════════════
# Selection widget — space to toggle, enter to confirm
# ═══════════════════════════════════════════════════════════════════

def _select_one(title: str, options: list[str]) -> int | None:
    """Interactive single-select: arrow keys to move, enter to confirm.
    Returns the 0-based index or None if cancelled.
    Falls back to numbered input when terminal does not support raw mode.
    """
    try:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
    except Exception:
        # Fallback: simple numbered selection
        return _select_one_fallback(title, options)

    selected = 0

    def _render():
        # Move cursor up len(options)+1 lines and re-draw
        for _ in range(len(options) + 1):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.write(f"  {title}\n")
        for i, opt in enumerate(options):
            marker = "[cyan]>[/cyan] " if i == selected else "  "
            style = "bold white" if i == selected else "dim"
            console.print(f"    {marker}[{style}]{opt}[/{style}]", highlight=False)
        sys.stdout.flush()

    # Initial draw
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
            if ch == "\x03":  # Ctrl-C
                selected = None
                break
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":  # Up
                    selected = (selected - 1) % len(options)
                elif seq == "[B":  # Down
                    selected = (selected + 1) % len(options)
            _render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    console.print()
    return selected


def _select_one_fallback(title: str, options: list[str]) -> int | None:
    """Simple numbered fallback for non-TTY environments."""
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


def _select_multi(title: str, options: list[str], defaults: list[bool] | None = None) -> list[int]:
    """Interactive multi-select: space to toggle, enter to confirm.
    Returns list of 0-based selected indices.
    Falls back to numbered input when terminal does not support raw mode.
    """
    toggled = list(defaults) if defaults else [False] * len(options)
    try:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
    except Exception:
        return _select_multi_fallback(title, options, toggled)

    cursor = 0

    def _render():
        for _ in range(len(options) + 2):
            sys.stdout.write("\033[A\033[2K")
        sys.stdout.write(f"  {title}\n")
        for i, opt in enumerate(options):
            ptr = "[cyan]>[/cyan]" if i == cursor else " "
            box = "[cyan][x][/cyan]" if toggled[i] else "[dim][ ][/dim]"
            style = "bold white" if i == cursor else "dim"
            console.print(f"   {ptr} {box} [{style}]{opt}[/{style}]", highlight=False)
        console.print("  [dim]space = toggle  |  enter = confirm[/dim]", highlight=False)

    console.print(f"  {title}")
    for i, opt in enumerate(options):
        ptr = "[cyan]>[/cyan]" if i == cursor else " "
        box = "[cyan][x][/cyan]" if toggled[i] else "[dim][ ][/dim]"
        style = "bold white" if i == cursor else "dim"
        console.print(f"   {ptr} {box} [{style}]{opt}[/{style}]", highlight=False)
    console.print("  [dim]space = toggle  |  enter = confirm[/dim]", highlight=False)

    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\r" or ch == "\n":
                break
            if ch == "\x03":
                return []
            if ch == " ":
                toggled[cursor] = not toggled[cursor]
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    cursor = (cursor - 1) % len(options)
                elif seq == "[B":
                    cursor = (cursor + 1) % len(options)
            _render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    console.print()
    return [i for i, t in enumerate(toggled) if t]


def _select_multi_fallback(title: str, options: list[str], toggled: list[bool]) -> list[int]:
    """Fallback multi-select."""
    console.print(f"\n  {title}")
    for i, opt in enumerate(options, 1):
        tag = "[cyan]x[/cyan]" if toggled[i - 1] else " "
        console.print(f"    [{tag}] [cyan]{i}[/cyan]  {opt}")
    console.print()
    raw = pt_prompt("  Toggle (e.g. 1 3): ").strip()
    for tok in raw.split():
        try:
            idx = int(tok) - 1
            if 0 <= idx < len(options):
                toggled[idx] = not toggled[idx]
        except ValueError:
            pass
    return [i for i, t in enumerate(toggled) if t]


# ═══════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════

def main():
    """Entry point for the JCode CLI."""
    settings_mgr = SettingsManager()
    ctx: ContextManager | None = None
    output_dir: Path | None = None
    history = InMemoryHistory()

    # -- First-run: auto-create projects dir, no questions
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
    console.print(f"  [cyan]Ollama connected[/cyan]")

    # -- Greeting + default save dir
    projects_dir = settings_mgr.get_default_output_dir()
    console.print(f"  [dim]Projects directory:[/dim] [cyan]{projects_dir}[/cyan]")
    console.print()

    # -- Autonomy approval
    _autonomy_check(settings_mgr)

    # -- Hint
    console.print(
        "  Type [cyan]'help'[/cyan] for commands, [cyan]'build <prompt>'[/cyan] to start.\n"
    )

    # -- Main REPL
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
            console.print(HELP_TEXT, highlight=False)
        elif cmd == "clear":
            console.clear()
        elif cmd == "build":
            if not args:
                console.print("  [dim]Usage:[/dim] [cyan]build <describe what you want>[/cyan]")
                continue
            result = _cmd_build(args, settings_mgr)
            if result:
                ctx, output_dir = result
        elif cmd == "continue":
            result = _cmd_continue(settings_mgr)
            if result:
                ctx, output_dir = result
        elif cmd == "plan":
            _cmd_plan(ctx)
        elif cmd == "files":
            _cmd_files(ctx, output_dir)
        elif cmd == "tree":
            _cmd_tree(ctx, output_dir)
        elif cmd == "projects":
            _cmd_projects(settings_mgr)
        elif cmd == "update":
            _cmd_update()
        elif cmd == "uninstall":
            _cmd_uninstall(settings_mgr)
        elif cmd == "save":
            _cmd_save(ctx, output_dir)
        else:
            # Treat anything else as an implicit build prompt
            result = _cmd_build(user_input, settings_mgr)
            if result:
                ctx, output_dir = result


# ═══════════════════════════════════════════════════════════════════
# First-run & autonomy
# ═══════════════════════════════════════════════════════════════════

def _first_run_setup(settings_mgr: SettingsManager) -> None:
    """Silent first-run: create default projects dir, no prompts."""
    default_dir = Path("~/jcode_projects").expanduser().resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    settings_mgr.set_default_output_dir(str(default_dir))


def _autonomy_check(settings_mgr: SettingsManager) -> None:
    """Ask the user once per session whether JCode may install packages
    and run terminal commands autonomously.  Stores the answer on the
    settings object (not persisted to disk — per-session only)."""
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

    settings_mgr._autonomous = (choice == 0)
    set_autonomous(choice == 0)

    if settings_mgr._autonomous:
        console.print("  [cyan]Autonomous mode enabled for this session.[/cyan]\n")
    else:
        console.print("  [dim]Confirmation mode — you'll be asked before each action.[/dim]\n")


# ═══════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_build(
    prompt: str,
    settings_mgr: SettingsManager,
) -> tuple[ContextManager, Path] | None:
    """Full autonomous pipeline: plan > generate > review > verify > fix."""

    # -- Output directory
    default_dir = settings_mgr.get_default_output_dir()
    slug = _slugify(prompt[:40])
    output_dir = default_dir / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n  [dim]Project:[/dim] [cyan]{slug}[/cyan]")
    console.print(f"  [dim]Output:[/dim]  [cyan]{output_dir}[/cyan]")

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
    _log("PHASE 1", "Planning project architecture")
    plan = create_plan(prompt, ctx)
    ctx.set_plan(plan)

    task_count = len(plan.get("tasks", []))
    _log("PLAN", f"{task_count} task(s) created")

    for t in plan.get("tasks", []):
        deps = f" [dim](after {t.get('depends_on', [])})[/dim]" if t.get("depends_on") else ""
        console.print(f"          {t.get('id', '?')}. [white]{t.get('file', '')}[/white]{deps}")

    # -- Phase 2: Building (fully automatic)
    console.print()
    _log("PHASE 2", "Building — generate, review, verify, fix")
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
        _log("DONE", "Build complete — all files verified")
    else:
        _log("DONE", "Build finished with issues — type 'plan' to inspect")

    console.print(f"  [dim]Saved to:[/dim] [cyan]{output_dir}[/cyan]\n")
    return ctx, output_dir


def _cmd_continue(settings_mgr: SettingsManager) -> tuple[ContextManager, Path] | None:
    """Resume the last project, or pick from the list."""
    projects = settings_mgr.list_projects()

    if not projects:
        console.print("  [dim]No saved projects. Use 'build <prompt>' to start one.[/dim]")
        return None

    if len(projects) == 1:
        proj = projects[0]
    else:
        names = [f"{p.get('name', '?')}  [dim]({('done' if p.get('completed') else 'in progress')})[/dim]" for p in projects]
        idx = _select_one("Pick a project to continue:", names)
        if idx is None:
            return None
        proj = projects[idx]

    output_dir = Path(proj.get("output_dir", ""))
    session_file = output_dir / ".jcode_session.json"

    if not session_file.exists():
        console.print(f"  [dim]No session file at {session_file}[/dim]")
        return None

    ctx = ContextManager.load_session(session_file)
    _log("LOADED", f"{proj.get('name', '?')}")
    console.print(f"  [dim]{output_dir}[/dim]")

    if not proj.get("completed", False):
        console.print()
        choice = _select_one("Resume building?", ["Yes — continue where I left off", "No — just inspect"])
        if choice == 0:
            execute_plan(ctx, output_dir)

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

    # Explain what will happen
    projects_dir = settings_mgr.get_default_output_dir()
    desktop = Path.home() / "Desktop" / "jcode_projects_backup"
    jcode_root = Path(__file__).resolve().parent.parent
    config_dir = Path.home() / ".jcode"

    console.print(f"  [dim]This will:[/dim]")
    console.print(f"    [dim]1. Copy your projects to[/dim] [cyan]{desktop}[/cyan]")
    console.print(f"    [dim]2. Uninstall the jcode package[/dim]")
    console.print(f"    [dim]3. Remove config at[/dim] [cyan]{config_dir}[/cyan]")
    console.print()

    choice = _select_one("Proceed with uninstall?", [
        "Yes — uninstall and save projects to Desktop",
        "No  — cancel",
    ])

    if choice != 0:
        console.print("  [dim]Cancelled.[/dim]")
        return

    # Step 1: Copy projects to Desktop
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

    # Step 2: pip uninstall
    _log("UNINSTALL", "Removing jcode package")
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "jcode", "-y"],
        capture_output=True, text=True,
    )

    # Step 3: Remove config
    if config_dir.exists():
        _log("UNINSTALL", "Removing config directory")
        shutil.rmtree(config_dir, ignore_errors=True)

    _log("UNINSTALL", "Done")
    console.print(f"\n  [cyan]Your projects are saved at:[/cyan] {desktop}")
    console.print(f"  [dim]To remove the source code:[/dim] [cyan]rm -rf {jcode_root}[/cyan]\n")
    sys.exit(0)


def _cmd_save(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Manually save the current session."""
    if not ctx or not output_dir:
        console.print("  [dim]Nothing to save.[/dim]")
        return
    session_file = output_dir / ".jcode_session.json"
    ctx.save_session(session_file)
    _log("SAVED", str(session_file))


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _log(tag: str, message: str) -> None:
    """Structured log line: [HH:MM:SS] TAG  message"""
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"  [dim]{ts}[/dim]  [cyan]{tag:<10}[/cyan]  {message}")


def _auto_save_on_exit(ctx: ContextManager | None, output_dir: Path | None) -> None:
    """Auto-save session on exit if applicable."""
    if ctx and output_dir and output_dir.exists():
        try:
            session_file = output_dir / ".jcode_session.json"
            ctx.save_session(session_file)
            _log("SAVED", str(session_file))
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
