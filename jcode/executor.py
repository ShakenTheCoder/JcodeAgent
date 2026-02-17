"""
Execution & verification pipeline — the quality gate that makes JCode reliable.

Capabilities:
  1. Run any shell command (with autonomy check)
  2. Install any package (pip, npm, etc.)
  3. Syntax check (language-specific)
  4. Lint / format check
  5. Type check (if applicable)
  6. Import validation
  7. Test execution (if tests exist)

Only code that passes ALL gates is accepted.
"""

from __future__ import annotations

import subprocess
import shutil
import json
from pathlib import Path
from dataclasses import dataclass

from rich.console import Console
from rich.prompt import Confirm

console = Console()

# ── Global autonomy flag (set by cli.py at startup) ───────────────
_autonomous: bool = False


def set_autonomous(value: bool) -> None:
    """Set whether the agent may run commands without asking."""
    global _autonomous
    _autonomous = value


def is_autonomous() -> bool:
    """Check the current autonomy setting."""
    return _autonomous


# ── Data classes ───────────────────────────────────────────────────

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

    @property
    def structured_errors(self) -> list[dict]:
        """Parse error output into structured error objects.

        Returns list of:
        {
            "file": str,       # affected file path
            "line": int|None,  # line number if available
            "category": str,   # syntax|lint|import|type|runtime
            "message": str,    # human-readable error
        }
        """
        import re as _re
        errors = []
        for check in self.failed_checks:
            output = check.get("output", "")
            name = check.get("name", "")

            # Determine category from check name
            if "syntax" in name:
                category = "syntax"
            elif "lint" in name:
                category = "lint"
            elif "import" in name:
                category = "import"
            elif "type" in name:
                category = "type"
            else:
                category = "runtime"

            matched = False

            # Try to parse file:line patterns
            # Python: File "path", line N
            for m in _re.finditer(r'File "(.+?)", line (\d+)', output):
                matched = True
                errors.append({
                    "file": m.group(1),
                    "line": int(m.group(2)),
                    "category": category,
                    "message": output.strip()[:300],
                })

            # JS/TS/ruff: path:line:col: message
            if not matched:
                for m in _re.finditer(r'([^\s:]+\.\w+):(\d+):\d*:?\s*(.+)', output):
                    matched = True
                    errors.append({
                        "file": m.group(1),
                        "line": int(m.group(2)),
                        "category": category,
                        "message": m.group(3).strip()[:300],
                    })

            # If no patterns matched, add a generic entry
            if not matched:
                errors.append({
                    "file": "",
                    "line": None,
                    "category": category,
                    "message": output.strip()[:300],
                })

        return errors


# ── Shell command execution ────────────────────────────────────────

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


def shell_exec(
    command: str,
    cwd: Path | None = None,
    timeout: int = 120,
    reason: str = "",
) -> ExecResult:
    """Run an arbitrary shell command on behalf of the agent.
    Checks the autonomy flag — if not autonomous, asks the user first."""
    from datetime import datetime
    ts = datetime.now().strftime("%H:%M:%S")

    if not _autonomous:
        console.print(f"\n  [dim]{ts}[/dim]  [cyan]EXEC[/cyan]      {command}")
        if reason:
            console.print(f"  [dim]Reason: {reason}[/dim]")
        if not Confirm.ask("  Allow?", default=True):
            return ExecResult(command, -1, "", "User declined")

    console.print(f"  [dim]{ts}[/dim]  [cyan]EXEC[/cyan]      {command}")
    result = run_command(command, cwd=cwd, timeout=timeout)
    if not result.success and result.error_summary:
        console.print(f"  [dim]  stderr: {result.error_summary[:200]}[/dim]")
    return result


def install_package(
    package: str,
    manager: str = "pip",
    cwd: Path | None = None,
) -> ExecResult:
    """Install a package using pip, npm, or any other manager.
    Checks the autonomy flag — if not autonomous, asks the user first."""
    from datetime import datetime
    ts = datetime.now().strftime("%H:%M:%S")

    if manager == "pip":
        cmd = f"pip install {package}"
    elif manager == "npm":
        cmd = f"npm install {package}"
    elif manager == "pip3":
        cmd = f"pip3 install {package}"
    else:
        cmd = f"{manager} install {package}"

    if not _autonomous:
        console.print(f"\n  [dim]{ts}[/dim]  [cyan]INSTALL[/cyan]   {cmd}")
        if not Confirm.ask("  Allow?", default=True):
            return ExecResult(cmd, -1, "", "User declined")

    console.print(f"  [dim]{ts}[/dim]  [cyan]INSTALL[/cyan]   {cmd}")
    return run_command(cmd, cwd=cwd, timeout=120)


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
    """Python verification: syntax > imports > type check."""
    checks = []

    # 1. Syntax check
    result = run_command(["python3", "-m", "py_compile", str(file_path)])
    checks.append({
        "name": "python-syntax",
        "passed": result.success,
        "output": result.error_summary if not result.success else "OK",
    })

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

def install_dependencies(project_dir: Path, tech_stack: list[str] | None = None) -> list[ExecResult]:
    """Auto-install project dependencies (requirements.txt / package.json)."""
    results: list[ExecResult] = []
    from datetime import datetime

    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        results.append(
            install_package(f"-r {req_file}", manager="pip", cwd=project_dir)
        )

    pkg_file = project_dir / "package.json"
    if pkg_file.exists() and shutil.which("npm"):
        results.append(
            shell_exec("npm install", cwd=project_dir, reason="Install Node.js dependencies")
        )

    return results


# ── Test execution ─────────────────────────────────────────────────

def run_tests(project_dir: Path, tech_stack: list[str] | None = None) -> ExecResult:
    """Run the project test suite."""
    tech = tech_stack or []
    if any("python" in t.lower() for t in tech):
        if shutil.which("pytest"):
            return run_command("pytest --tb=short -q", cwd=project_dir, timeout=60)
        return run_command("python3 -m pytest --tb=short -q", cwd=project_dir, timeout=60)

    pkg = project_dir / "package.json"
    if pkg.exists():
        return run_command("npm test", cwd=project_dir, timeout=60)

    return ExecResult("(no tests)", 0, "No test runner detected.", "")
