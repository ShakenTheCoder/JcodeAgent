"""
File system manager — creates project directories and writes files to disk.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.tree import Tree

console = Console()


def ensure_project_dir(base: Path) -> Path:
    """Create the output directory if it doesn't exist. Return the path."""
    base.mkdir(parents=True, exist_ok=True)
    return base


def write_file(base: Path, rel_path: str, content: str) -> Path:
    """
    Write content to a file inside the project directory.
    Creates parent directories as needed.
    Returns the absolute path of the written file.
    """
    full = base / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


def read_file(base: Path, rel_path: str) -> str | None:
    """Read a file from the project directory. Returns None if not found."""
    full = base / rel_path
    if full.is_file():
        return full.read_text(encoding="utf-8")
    return None


def print_tree(base: Path, title: str | None = None) -> None:
    """Pretty-print the project directory tree using Rich."""
    label = title or base.name
    tree = Tree(f"📁 [bold cyan]{label}[/bold cyan]")
    _build_tree(base, tree)
    console.print(tree)


def _build_tree(directory: Path, tree: Tree) -> None:
    """Recursively build a Rich Tree from a directory."""
    # Sort: directories first, then files
    entries = sorted(
        directory.iterdir(),
        key=lambda p: (not p.is_dir(), p.name.lower()),
    )
    for entry in entries:
        if entry.name.startswith(".") or entry.name == "__pycache__":
            continue
        if entry.is_dir():
            branch = tree.add(f"📁 [bold]{entry.name}[/bold]")
            _build_tree(entry, branch)
        else:
            icon = _file_icon(entry.suffix)
            tree.add(f"{icon} {entry.name}")


def _file_icon(suffix: str) -> str:
    """Return a short tag based on file extension."""
    icons = {
        ".py": "py",
        ".js": "js",
        ".ts": "ts",
        ".jsx": "jsx",
        ".tsx": "tsx",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".toml": "toml",
        ".yaml": "yaml",
        ".yml": "yml",
        ".md": "md",
        ".txt": "txt",
        ".sql": "sql",
        ".sh": "sh",
        ".env": "env",
    }
    return icons.get(suffix, "--")
