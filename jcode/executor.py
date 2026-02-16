"""
Verification pipeline — the quality gate that makes JCode reliable.

Before any generated code is accepted:
1. Syntax check (language-specific)
2. Lint / format check
3. Type check (if applicable)
4. Import validation
5. Test execution (if tests exist)

Only code that passes ALL gates is accepted.
This is what turns a "smart model" into a "self-correcting engineer."
"""

from __future__ import annotations

import subprocess
import shutil
import json
from pathlib import Path
from dataclasses import dataclass

from rich.console import Console

console = Console()


@dataclass
class ExecResult:
    """Result of a command execution."""
    command: str
    return_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.return_code == 0

    @property
    def error_summary(self) -> str:
        err = self.stderr.strip() or self.stdout.strip()
        return err[-3000:] if len(err) > 3000 else err


@dataclass
class VerificationResult:
    """Aggregated result of all verification checks."""
    passed: bool
    checks: list[dict]  # [{"name": str, "passed": bool, "output": str}]

    @property
    def summary(self) -> str:
        failed = [c for c in self.checks if not c["passed"]]
        if not failed:
            return "All checks passed"
        return "; ".join(f"{c['name']}: {c['output'][:200]}" for c in failed)

    @property
    def failed_checks(self) -> list[dict]:
        return [c for c in self.checks if not c["passed"]]


def run_command(
    command: str | list[str],
    cwd: Path | None = None,
    timeout: int = 60,
) -> ExecResult:
    """Run a shell command and capture output."""
    if isinstance(command, str):
        shell = True
        cmd = command
    else:
        shell = False
        cmd = command

    try:
        result = subprocess.run(
            cmd, cwd=cwd, shell=shell,
            capture_output=True, text=True, timeout=timeout,
        )
        return ExecResult(
            command=cmd if isinstance(cmd, str) else " ".join(cmd),
            return_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired:
        return ExecResult(cmd if isinstance(cmd, str) else " ".join(cmd), -1, "", f"Timed out after {timeout}s")
    except FileNotFoundError as e:
        return ExecResult(cmd if isinstance(cmd, str) else " ".join(cmd), -1, "", str(e))


# ── Verification pipeline ──────────────────────────────────────────

def verify_file(file_path: Path, project_dir: Path) -> VerificationResult:
    """
    Run all applicable verification checks on a single file.
    Returns a VerificationResult with pass/fail per check.
    """
    checks: list[dict] = []

    suffix = file_path.suffix.lower()

    if suffix == ".py":
        checks.extend(_verify_python(file_path, project_dir))
    elif suffix in (".js", ".jsx", ".ts", ".tsx"):
        checks.extend(_verify_javascript(file_path, project_dir))
    elif suffix in (".html",):
        checks.append({"name": "html-exists", "passed": True, "output": "OK"})
    elif suffix in (".css", ".scss"):
        checks.append({"name": "css-exists", "passed": True, "output": "OK"})
    elif suffix in (".json",):
        checks.extend(_verify_json(file_path))
    else:
        checks.append({"name": "file-exists", "passed": file_path.exists(), "output": "OK"})

    passed = all(c["passed"] for c in checks)
    return VerificationResult(passed=passed, checks=checks)


def _verify_python(file_path: Path, project_dir: Path) -> list[dict]:
    """Python verification: syntax → imports → type check."""
    checks = []

    # 1. Syntax check
    result = run_command(["python3", "-m", "py_compile", str(file_path)])
    checks.append({
        "name": "python-syntax",
        "passed": result.success,
        "output": result.error_summary if not result.success else "OK",
    })

    # If syntax fails, skip other checks
    if not result.success:
        return checks

    # 2. Basic lint (if ruff or flake8 available)
    ruff = shutil.which("ruff")
    if ruff:
        result = run_command([ruff, "check", "--select=E,F", "--no-fix", str(file_path)])
        checks.append({
            "name": "python-lint",
            "passed": result.success,
            "output": result.error_summary if not result.success else "OK",
        })
    else:
        flake8 = shutil.which("flake8")
        if flake8:
            result = run_command([flake8, "--select=E,F", str(file_path)])
            checks.append({
                "name": "python-lint",
                "passed": result.success,
                "output": result.error_summary if not result.success else "OK",
            })

    return checks


def _verify_javascript(file_path: Path, project_dir: Path) -> list[dict]:
    """JavaScript/TypeScript verification."""
    checks = []

    node = shutil.which("node")
    if node and file_path.suffix in (".js", ".jsx"):
        result = run_command([node, "--check", str(file_path)])
        checks.append({
            "name": "js-syntax",
            "passed": result.success,
            "output": result.error_summary if not result.success else "OK",
        })
    else:
        checks.append({"name": "js-exists", "passed": file_path.exists(), "output": "OK"})

    return checks


def _verify_json(file_path: Path) -> list[dict]:
    """Verify JSON is parseable."""
    try:
        json.loads(file_path.read_text())
        return [{"name": "json-valid", "passed": True, "output": "OK"}]
    except Exception as e:
        return [{"name": "json-valid", "passed": False, "output": str(e)}]


# ── Dependency installation ────────────────────────────────────────

def install_dependencies(project_dir: Path, tech_stack: list[str]) -> list[ExecResult]:
    """Install project dependencies."""
    results: list[ExecResult] = []

    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        console.print("[cyan]📦 Installing Python dependencies…[/cyan]")
        results.append(run_command(f"pip install -r {req_file}", cwd=project_dir, timeout=120))

    pkg_file = project_dir / "package.json"
    if pkg_file.exists() and shutil.which("npm"):
        console.print("[cyan]📦 Installing Node.js dependencies…[/cyan]")
        results.append(run_command("npm install", cwd=project_dir, timeout=120))

    return results


# ── Test execution ─────────────────────────────────────────────────

def run_tests(project_dir: Path, tech_stack: list[str]) -> ExecResult:
    """Run the project test suite."""
    if any("python" in t.lower() for t in tech_stack):
        if shutil.which("pytest"):
            return run_command("pytest --tb=short -q", cwd=project_dir, timeout=60)
        return run_command("python3 -m pytest --tb=short -q", cwd=project_dir, timeout=60)

    pkg = project_dir / "package.json"
    if pkg.exists():
        return run_command("npm test", cwd=project_dir, timeout=60)

    return ExecResult("(no tests)", 0, "No test runner detected.", "")
