"""
Project scanner — reads an existing project directory and builds
structured context for JCode to understand the codebase.

Capabilities:
  1. Detect project type (Python, Node, React, etc.)
  2. Detect tech stack from config files
  3. Read all source files into context
  4. Build dependency graph from imports
  5. Generate architecture summary

v0.7.0 — JCode lives inside your project.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from rich.console import Console

from jcode.config import ProjectState
from jcode.context import ContextManager

console = Console()

# Directories to always skip
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".next", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".tox", "egg-info", ".eggs", "coverage", ".nyc_output",
    ".turbo", ".cache", ".parcel-cache", "target", "vendor",
}

# File extensions we consider source code
SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".sql",
    ".sh", ".bash", ".env", ".cfg", ".ini", ".xml", ".graphql",
    ".prisma", ".svelte", ".vue", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift",
    ".r", ".R", ".jl", ".lua", ".ex", ".exs", ".erl",
}

# Max file size to read (skip binaries and huge files)
MAX_FILE_SIZE = 100_000  # 100KB


# ═══════════════════════════════════════════════════════════════════
# Project type detection
# ═══════════════════════════════════════════════════════════════════

def detect_project_type(project_dir: Path) -> str:
    """
    Detect the primary project type from files present.
    Returns a human-readable label.
    """
    markers = {
        "package.json":     "Node.js",
        "next.config.js":   "Next.js",
        "next.config.mjs":  "Next.js",
        "next.config.ts":   "Next.js",
        "vite.config.ts":   "Vite",
        "vite.config.js":   "Vite",
        "nuxt.config.ts":   "Nuxt",
        "svelte.config.js": "SvelteKit",
        "angular.json":     "Angular",
        "requirements.txt": "Python",
        "pyproject.toml":   "Python",
        "setup.py":         "Python",
        "Pipfile":          "Python",
        "Cargo.toml":       "Rust",
        "go.mod":           "Go",
        "pom.xml":          "Java (Maven)",
        "build.gradle":     "Java (Gradle)",
        "Gemfile":          "Ruby",
        "composer.json":    "PHP",
        "Dockerfile":       "Docker",
        "docker-compose.yml": "Docker Compose",
        "docker-compose.yaml": "Docker Compose",
    }

    # Check specific markers (order matters — more specific first)
    for marker, ptype in markers.items():
        if (project_dir / marker).exists():
            # Refine Node.js detection
            if ptype == "Node.js":
                pkg = project_dir / "package.json"
                try:
                    data = json.loads(pkg.read_text())
                    deps = {
                        **data.get("dependencies", {}),
                        **data.get("devDependencies", {}),
                    }
                    if "next" in deps:
                        return "Next.js"
                    if "react" in deps and "vite" in deps:
                        return "React + Vite"
                    if "react" in deps:
                        return "React"
                    if "vue" in deps:
                        return "Vue"
                    if "svelte" in deps:
                        return "Svelte"
                    if "express" in deps:
                        return "Express.js"
                    if "fastify" in deps:
                        return "Fastify"
                except Exception:
                    pass
            return ptype

    # Fallback: check for common file patterns
    if list(project_dir.glob("*.py")):
        return "Python"
    if list(project_dir.glob("*.html")):
        return "HTML/CSS"
    if list(project_dir.glob("*.js")):
        return "JavaScript"

    return "Unknown"


def detect_tech_stack(project_dir: Path) -> list[str]:
    """
    Detect the tech stack from project configuration files.
    Returns a list of technologies.
    """
    stack: list[str] = []

    # Python
    req = project_dir / "requirements.txt"
    if req.exists():
        try:
            content = req.read_text()
            known = {
                "flask": "Flask", "django": "Django", "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy", "pandas": "Pandas",
                "numpy": "NumPy", "pytest": "pytest", "celery": "Celery",
                "redis": "Redis", "psycopg2": "PostgreSQL",
                "pymongo": "MongoDB", "requests": "Requests",
                "beautifulsoup4": "BeautifulSoup", "scrapy": "Scrapy",
            }
            for line in content.split("\n"):
                pkg = line.strip().split("==")[0].split(">=")[0].split("<=")[0].lower()
                if pkg in known:
                    stack.append(known[pkg])
        except Exception:
            pass

    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        stack.append("Python")

    # Node.js
    pkg_json = project_dir / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text())
            deps = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }
            known_node = {
                "react": "React", "next": "Next.js", "vue": "Vue",
                "svelte": "Svelte", "angular": "Angular",
                "express": "Express", "fastify": "Fastify",
                "tailwindcss": "Tailwind CSS", "typescript": "TypeScript",
                "prisma": "Prisma", "mongoose": "Mongoose",
                "socket.io": "Socket.IO", "jest": "Jest",
                "vitest": "Vitest", "vite": "Vite",
                "three": "Three.js", "d3": "D3.js",
            }
            for dep, label in known_node.items():
                if dep in deps:
                    stack.append(label)
        except Exception:
            pass

    # Docker
    if (project_dir / "Dockerfile").exists():
        stack.append("Docker")
    if (project_dir / "docker-compose.yml").exists() or (project_dir / "docker-compose.yaml").exists():
        stack.append("Docker Compose")

    # TypeScript
    if (project_dir / "tsconfig.json").exists():
        if "TypeScript" not in stack:
            stack.append("TypeScript")

    # Dedup while preserving order
    seen = set()
    deduped = []
    for item in stack:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


# ═══════════════════════════════════════════════════════════════════
# File scanning
# ═══════════════════════════════════════════════════════════════════

def scan_files(project_dir: Path) -> dict[str, str]:
    """
    Scan all source files in the project directory.
    Returns a dict of {relative_path: content}.
    Skips binaries, huge files, and ignored directories.
    """
    files: dict[str, str] = {}

    if not project_dir.exists():
        return files

    for f in sorted(project_dir.rglob("*")):
        if not f.is_file():
            continue

        # Skip hidden files
        if f.name.startswith(".") and f.name != ".env":
            continue

        # Skip ignored directories
        try:
            rel_parts = f.relative_to(project_dir).parts
        except ValueError:
            continue

        if any(part in SKIP_DIRS for part in rel_parts):
            continue

        # Skip non-source files
        if f.suffix.lower() not in SOURCE_EXTENSIONS:
            continue

        # Skip huge files
        try:
            if f.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue

        # Read file
        try:
            rel_path = str(f.relative_to(project_dir))
            content = f.read_text(encoding="utf-8", errors="replace")
            files[rel_path] = content
        except Exception:
            continue

    return files


def build_file_index(files: dict[str, str]) -> dict[str, str]:
    """
    Build a file index: {path: brief_description}.
    Uses filename and first few lines to infer purpose.
    """
    index: dict[str, str] = {}
    for path, content in files.items():
        # Try to extract a module docstring or first comment
        desc = _infer_file_purpose(path, content)
        index[path] = desc
    return index


def _infer_file_purpose(path: str, content: str) -> str:
    """Infer a file's purpose from its name and content."""
    name = Path(path).stem.lower()
    suffix = Path(path).suffix.lower()

    # Known config files
    config_files = {
        "package.json": "Node.js package configuration",
        "tsconfig.json": "TypeScript configuration",
        "tailwind.config.ts": "Tailwind CSS configuration",
        "tailwind.config.js": "Tailwind CSS configuration",
        "postcss.config.js": "PostCSS configuration",
        "next.config.js": "Next.js configuration",
        "vite.config.ts": "Vite configuration",
        "requirements.txt": "Python dependencies",
        "pyproject.toml": "Python project configuration",
        ".gitignore": "Git ignore rules",
        "Dockerfile": "Docker image definition",
        "docker-compose.yml": "Docker Compose services",
    }

    basename = Path(path).name
    if basename in config_files:
        return config_files[basename]

    # Try to extract docstring (Python)
    if suffix == ".py":
        doc_match = re.match(r'^(?:#!/.*\n)?(?:#.*\n)*\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')',
                             content, re.DOTALL)
        if doc_match:
            doc = (doc_match.group(1) or doc_match.group(2) or "").strip()
            first_line = doc.split("\n")[0].strip()
            if first_line:
                return first_line[:100]

    # Try to extract first comment (JS/TS)
    if suffix in (".js", ".jsx", ".ts", ".tsx"):
        comment_match = re.match(r'\s*/\*\*?\s*(.*?)(?:\*/|\n)', content)
        if comment_match:
            return comment_match.group(1).strip()[:100]

    # Common name patterns
    name_hints = {
        "index": "Entry point / main module",
        "main": "Main application entry point",
        "app": "Application setup",
        "server": "Server configuration",
        "config": "Configuration",
        "utils": "Utility functions",
        "helpers": "Helper functions",
        "types": "Type definitions",
        "models": "Data models",
        "routes": "Route definitions",
        "api": "API endpoints",
        "auth": "Authentication",
        "db": "Database connection",
        "database": "Database connection",
        "middleware": "Middleware",
        "test": "Tests",
        "spec": "Tests",
        "layout": "Page layout",
        "page": "Page component",
        "component": "UI component",
        "style": "Styles",
        "global": "Global styles/config",
    }

    for hint_key, hint_val in name_hints.items():
        if hint_key in name:
            return hint_val

    return f"{suffix.lstrip('.')} source file"


# ═══════════════════════════════════════════════════════════════════
# Dependency graph (import analysis)
# ═══════════════════════════════════════════════════════════════════

def build_dependency_graph(files: dict[str, str]) -> dict[str, list[str]]:
    """
    Build a simplified dependency graph from import statements.
    Returns {file_path: [list of local files it imports]}.
    Only tracks imports that resolve to files within the project.
    """
    graph: dict[str, list[str]] = {}
    all_paths = set(files.keys())

    for path, content in files.items():
        deps: list[str] = []
        suffix = Path(path).suffix.lower()

        if suffix == ".py":
            deps = _extract_python_imports(path, content, all_paths)
        elif suffix in (".js", ".jsx", ".ts", ".tsx"):
            deps = _extract_js_imports(path, content, all_paths)

        if deps:
            graph[path] = deps

    return graph


def _extract_python_imports(path: str, content: str, all_paths: set[str]) -> list[str]:
    """Extract local Python imports."""
    deps: list[str] = []
    pkg_dir = str(Path(path).parent)

    for line in content.split("\n"):
        line = line.strip()
        # from .module import ... or from package.module import ...
        m = re.match(r"from\s+(\.?\w[\w.]*)\s+import", line)
        if m:
            module = m.group(1)
            # Convert dotted path to file path
            if module.startswith("."):
                # Relative import
                rel = module.lstrip(".").replace(".", "/")
                candidate = f"{pkg_dir}/{rel}.py" if pkg_dir != "." else f"{rel}.py"
            else:
                candidate = module.replace(".", "/") + ".py"

            if candidate in all_paths:
                deps.append(candidate)

        # import module
        m = re.match(r"import\s+(\w[\w.]*)", line)
        if m:
            module = m.group(1)
            candidate = module.replace(".", "/") + ".py"
            if candidate in all_paths:
                deps.append(candidate)

    return deps


def _extract_js_imports(path: str, content: str, all_paths: set[str]) -> list[str]:
    """Extract local JS/TS imports."""
    deps: list[str] = []
    file_dir = str(Path(path).parent)

    # import ... from './module' or require('./module')
    pattern = re.compile(r'''(?:import\s+.*?from\s+|require\s*\(\s*)['"](\.[^'"]+)['"]''')

    for m in pattern.finditer(content):
        rel_import = m.group(1)
        # Resolve relative path
        if file_dir == ".":
            candidate_base = rel_import.lstrip("./")
        else:
            candidate_base = str(Path(file_dir) / rel_import.lstrip("./"))

        # Try various extensions
        for ext in ("", ".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.tsx", "/index.ts"):
            candidate = candidate_base + ext
            if candidate in all_paths:
                deps.append(candidate)
                break

    return deps


# ═══════════════════════════════════════════════════════════════════
# Full project scan → ContextManager
# ═══════════════════════════════════════════════════════════════════

def scan_project(project_dir: Path) -> ContextManager:
    """
    Perform a complete scan of an existing project and return
    a fully populated ContextManager.

    This is the main entry point — used when JCode is launched
    inside an existing project directory.
    """
    console.print(f"  [dim]Scanning project...[/dim]")

    # 1. Detect project type and tech stack
    project_type = detect_project_type(project_dir)
    tech_stack = detect_tech_stack(project_dir)

    console.print(f"  [cyan]Project type:[/cyan] {project_type}")
    if tech_stack:
        console.print(f"  [cyan]Tech stack:[/cyan] {', '.join(tech_stack)}")

    # 2. Scan all source files
    files = scan_files(project_dir)
    file_count = len(files)
    console.print(f"  [cyan]Files found:[/cyan] {file_count}")

    # 3. Build file index
    file_index = build_file_index(files)

    # 4. Build dependency graph
    dep_graph = build_dependency_graph(files)

    # 5. Create ProjectState
    state = ProjectState(
        name=project_dir.name,
        description=f"{project_type} project",
        tech_stack=tech_stack,
        output_dir=project_dir,
        files=files,
        file_index=file_index,
        dependency_graph=dep_graph,
        architecture_summary=_build_architecture_summary(
            project_dir.name, project_type, tech_stack, file_index,
        ),
    )

    # 6. Create ContextManager
    ctx = ContextManager(state)

    console.print(f"  [dim]Project context loaded ({file_count} files)[/dim]")
    return ctx


def _build_architecture_summary(
    name: str,
    project_type: str,
    tech_stack: list[str],
    file_index: dict[str, str],
) -> str:
    """Build a brief architecture summary from scanned data."""
    parts = [
        f"{name} is a {project_type} project",
    ]
    if tech_stack:
        parts[0] += f" using {', '.join(tech_stack[:5])}"
    parts[0] += "."

    # Count by directory
    dirs: dict[str, int] = {}
    for path in file_index:
        d = str(Path(path).parent)
        if d == ".":
            d = "(root)"
        dirs[d] = dirs.get(d, 0) + 1

    if dirs:
        dir_summary = ", ".join(
            f"{d} ({c} files)" for d, c in sorted(dirs.items(), key=lambda x: -x[1])[:5]
        )
        parts.append(f"Structure: {dir_summary}.")

    return " ".join(parts)
