"""
Git integration for JCode — version control, commits, push, GitHub.

Capabilities:
  1. Detect & auto-install git
  2. Init repos, create .gitignore
  3. Stage, commit, status, log, diff
  4. Remote management (GitHub)
  5. Push / pull
  6. Clone repos into CWD

v0.7.0 — JCode lives inside your project.
"""

from __future__ import annotations

import os
import re
import subprocess
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()


# ═══════════════════════════════════════════════════════════════════
# Git availability
# ═══════════════════════════════════════════════════════════════════

def git_available() -> bool:
    """Check if git is installed and accessible."""
    return shutil.which("git") is not None


def ensure_git() -> bool:
    """
    Ensure git is installed. If not, attempt to install it.
    Returns True if git is available after the check.
    """
    if git_available():
        return True

    console.print("  [yellow]Git is not installed.[/yellow]")
    console.print("  [dim]Attempting to install git...[/dim]")

    if sys.platform == "darwin":
        # macOS: xcode-select installs git
        result = _run_git_cmd(["xcode-select", "--install"], cwd=None, raw=True)
        if result is None:
            console.print("  [dim]Please complete the Xcode command-line tools installation and restart JCode.[/dim]")
            return False
    elif sys.platform.startswith("linux"):
        # Try common package managers
        for mgr_cmd in [
            ["sudo", "apt-get", "install", "-y", "git"],
            ["sudo", "dnf", "install", "-y", "git"],
            ["sudo", "pacman", "-S", "--noconfirm", "git"],
            ["sudo", "apk", "add", "git"],
        ]:
            try:
                subprocess.run(mgr_cmd, capture_output=True, timeout=120)
                if git_available():
                    console.print("  [cyan]Git installed successfully.[/cyan]")
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
    elif sys.platform == "win32":
        console.print("  [dim]Please install git from https://git-scm.com/downloads[/dim]")
        return False

    if git_available():
        console.print("  [cyan]Git is now available.[/cyan]")
        return True

    console.print("  [yellow]Could not install git automatically.[/yellow]")
    console.print("  [dim]Install manually: https://git-scm.com/downloads[/dim]")
    return False


# ═══════════════════════════════════════════════════════════════════
# Low-level git command runner
# ═══════════════════════════════════════════════════════════════════

def _run_git_cmd(
    args: list[str],
    cwd: Path | str | None,
    raw: bool = False,
    timeout: int = 30,
) -> str | None:
    """
    Run a git (or arbitrary) command and return stdout.
    Returns None on failure.
    """
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if raw:
            return result.stdout + result.stderr
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _run_git(args: list[str], cwd: Path | str) -> tuple[bool, str]:
    """
    Run a git command. Returns (success, output).
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip()
            return False, err or output
        return True, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except FileNotFoundError:
        return False, "Git not found"
    except OSError as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════
# Repository detection
# ═══════════════════════════════════════════════════════════════════

def is_git_repo(path: Path) -> bool:
    """Check if the given path is inside a git repository."""
    ok, _ = _run_git(["rev-parse", "--is-inside-work-tree"], path)
    return ok


def get_repo_root(path: Path) -> Path | None:
    """Get the root of the git repository containing path."""
    ok, out = _run_git(["rev-parse", "--show-toplevel"], path)
    if ok and out:
        return Path(out)
    return None


def get_current_branch(path: Path) -> str:
    """Get the current branch name."""
    ok, out = _run_git(["branch", "--show-current"], path)
    return out if ok else "unknown"


def get_remote_url(path: Path) -> str | None:
    """Get the remote origin URL."""
    ok, out = _run_git(["remote", "get-url", "origin"], path)
    return out if ok else None


# ═══════════════════════════════════════════════════════════════════
# Init & .gitignore
# ═══════════════════════════════════════════════════════════════════

# Standard .gitignore entries for common project types
_GITIGNORE_TEMPLATE = """\
# Dependencies
node_modules/
.venv/
venv/
__pycache__/
*.pyc

# Build outputs
dist/
build/
.next/
out/
*.egg-info/

# Environment & secrets
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
*.log
npm-debug.log*

# JCode session
.jcode_session.json
"""


def init_repo(path: Path, initial_commit: bool = True) -> bool:
    """
    Initialize a new git repository at the given path.
    Creates a .gitignore and optionally makes an initial commit.
    Returns True on success.
    """
    if is_git_repo(path):
        return True  # Already a repo

    ok, out = _run_git(["init"], path)
    if not ok:
        console.print(f"  [yellow]git init failed: {out}[/yellow]")
        return False

    console.print(f"  [cyan]Initialized git repository[/cyan]")

    # Create .gitignore if it doesn't exist
    gitignore = path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(_GITIGNORE_TEMPLATE)
        console.print(f"  [dim]Created .gitignore[/dim]")

    if initial_commit:
        # Stage everything and make initial commit
        _run_git(["add", "-A"], path)
        ok, out = _run_git(["commit", "-m", "Initial commit by JCode"], path)
        if ok:
            console.print(f"  [dim]Created initial commit[/dim]")

    return True


# ═══════════════════════════════════════════════════════════════════
# Stage, Commit, Status
# ═══════════════════════════════════════════════════════════════════

def stage_all(path: Path) -> bool:
    """Stage all changes (git add -A)."""
    ok, _ = _run_git(["add", "-A"], path)
    return ok


def stage_files(path: Path, files: list[str]) -> bool:
    """Stage specific files."""
    ok, _ = _run_git(["add", "--"] + files, path)
    return ok


def commit(path: Path, message: str) -> tuple[bool, str]:
    """
    Create a commit with the given message.
    Auto-stages all changes first.
    Returns (success, commit_hash_or_error).
    """
    stage_all(path)

    # Check if there's anything to commit
    ok, status = _run_git(["status", "--porcelain"], path)
    if ok and not status.strip():
        return True, "nothing to commit"

    ok, out = _run_git(["commit", "-m", message], path)
    if ok:
        # Extract short hash
        hash_ok, hash_out = _run_git(["rev-parse", "--short", "HEAD"], path)
        commit_hash = hash_out if hash_ok else "?"
        return True, commit_hash
    return False, out


def auto_commit(path: Path, description: str = "") -> tuple[bool, str]:
    """
    Create an automatic commit with a descriptive message.
    Used after JCode generates or modifies files.
    """
    # Build a meaningful commit message
    ok, status_out = _run_git(["status", "--porcelain"], path)
    if not ok or not status_out.strip():
        return True, "nothing to commit"

    lines = status_out.strip().split("\n")
    added = [l for l in lines if l.startswith("?") or l.startswith("A")]
    modified = [l for l in lines if l.startswith("M") or l.startswith(" M")]
    deleted = [l for l in lines if l.startswith("D") or l.startswith(" D")]

    parts = []
    if added:
        parts.append(f"add {len(added)} file(s)")
    if modified:
        parts.append(f"update {len(modified)} file(s)")
    if deleted:
        parts.append(f"remove {len(deleted)} file(s)")

    change_summary = ", ".join(parts) if parts else "update project"

    if description:
        msg = f"jcode: {description} — {change_summary}"
    else:
        msg = f"jcode: {change_summary}"

    # Truncate to 72 chars for git convention
    if len(msg) > 72:
        msg = msg[:69] + "..."

    return commit(path, msg)


# ═══════════════════════════════════════════════════════════════════
# Status, Log, Diff
# ═══════════════════════════════════════════════════════════════════

def status(path: Path) -> str:
    """Get git status output."""
    ok, out = _run_git(["status", "--short"], path)
    return out if ok else "(not a git repo)"


def log(path: Path, n: int = 10) -> str:
    """Get recent git log."""
    ok, out = _run_git(
        ["log", f"-{n}", "--oneline", "--decorate", "--graph"],
        path,
    )
    return out if ok else "(no commits)"


def diff(path: Path, staged: bool = False) -> str:
    """Get git diff output."""
    args = ["diff"]
    if staged:
        args.append("--staged")
    ok, out = _run_git(args, path)
    return out if ok else ""


def changed_files(path: Path) -> list[str]:
    """Get list of changed files (modified + untracked)."""
    ok, out = _run_git(["status", "--porcelain"], path)
    if not ok or not out:
        return []
    files = []
    for line in out.split("\n"):
        if line.strip():
            # Format: "XY filename" — extract filename
            fname = line[3:].strip()
            if fname:
                files.append(fname)
    return files


# ═══════════════════════════════════════════════════════════════════
# Remote & Push
# ═══════════════════════════════════════════════════════════════════

def add_remote(path: Path, url: str, name: str = "origin") -> bool:
    """Add a remote to the repository."""
    # Check if remote already exists
    existing = get_remote_url(path)
    if existing:
        if existing == url:
            return True
        # Update existing remote
        ok, _ = _run_git(["remote", "set-url", name, url], path)
        return ok

    ok, _ = _run_git(["remote", "add", name, url], path)
    return ok


def push(path: Path, remote: str = "origin", branch: str | None = None) -> tuple[bool, str]:
    """
    Push to remote. If branch is None, pushes current branch.
    Sets upstream on first push.
    """
    if not branch:
        branch = get_current_branch(path)

    # Try push with upstream set
    ok, out = _run_git(["push", "-u", remote, branch], path)
    if ok:
        return True, f"Pushed to {remote}/{branch}"
    return False, out


def pull(path: Path, remote: str = "origin", branch: str | None = None) -> tuple[bool, str]:
    """Pull from remote."""
    args = ["pull", remote]
    if branch:
        args.append(branch)
    ok, out = _run_git(args, path)
    if ok:
        return True, out
    return False, out


# ═══════════════════════════════════════════════════════════════════
# Clone
# ═══════════════════════════════════════════════════════════════════

def clone(url: str, target_dir: Path | None = None) -> tuple[bool, Path | None]:
    """
    Clone a repository. Returns (success, cloned_path).
    If target_dir is None, clones into CWD with repo name.
    """
    args = ["clone", url]
    cwd = Path.cwd()

    if target_dir:
        args.append(str(target_dir))
        cwd = target_dir.parent
        cwd.mkdir(parents=True, exist_ok=True)

    ok, out = _run_git(args, cwd)
    if not ok:
        return False, None

    # Determine cloned directory
    if target_dir:
        return True, target_dir

    # Extract from URL: https://github.com/user/repo.git -> repo
    repo_name = url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    cloned_path = cwd / repo_name
    return True, cloned_path


# ═══════════════════════════════════════════════════════════════════
# GitHub helpers
# ═══════════════════════════════════════════════════════════════════

def build_github_url(owner: str, repo: str, use_ssh: bool = False) -> str:
    """Build a GitHub URL from owner/repo."""
    if use_ssh:
        return f"git@github.com:{owner}/{repo}.git"
    return f"https://github.com/{owner}/{repo}.git"


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Parse owner/repo from a GitHub URL. Returns (owner, repo) or None."""
    patterns = [
        r"github\.com[:/]([^/]+)/([^/\s.]+?)(?:\.git)?$",
        r"^([^/\s]+)/([^/\s]+)$",  # owner/repo shorthand
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1), m.group(2)
    return None


def setup_github_remote(
    path: Path,
    repo_url: str,
) -> bool:
    """
    Set up a GitHub remote for the project.
    Accepts full URL or owner/repo shorthand.
    """
    # Parse shorthand like "user/repo" into full URL
    parsed = parse_github_url(repo_url)
    if parsed and "/" not in repo_url.replace("github.com", ""):
        owner, repo = parsed
        repo_url = build_github_url(owner, repo)

    return add_remote(path, repo_url)


# ═══════════════════════════════════════════════════════════════════
# Display helpers
# ═══════════════════════════════════════════════════════════════════

def print_status(path: Path) -> None:
    """Pretty-print git status."""
    if not is_git_repo(path):
        console.print("  [dim]Not a git repository[/dim]")
        return

    branch = get_current_branch(path)
    remote = get_remote_url(path)

    console.print(f"  [cyan]Branch:[/cyan] {branch}")
    if remote:
        console.print(f"  [cyan]Remote:[/cyan] {remote}")

    st = status(path)
    if st:
        console.print(f"  [cyan]Changes:[/cyan]")
        for line in st.split("\n"):
            if line.strip():
                console.print(f"    {line}")
    else:
        console.print("  [dim]Working tree clean[/dim]")


def print_log(path: Path, n: int = 10) -> None:
    """Pretty-print git log."""
    if not is_git_repo(path):
        console.print("  [dim]Not a git repository[/dim]")
        return

    log_output = log(path, n)
    if log_output:
        console.print(f"  [cyan]Recent commits:[/cyan]")
        for line in log_output.split("\n"):
            console.print(f"    {line}")
    else:
        console.print("  [dim]No commits yet[/dim]")
