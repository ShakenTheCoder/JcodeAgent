"""
Iteration engine v3.0 — DAG-based task execution with log-style progress.

Pipeline per task:
  1. GENERATE  → Coder produces the file
  2. REVIEW    → Reviewer critiques it
  3. VERIFY    → Static analysis + syntax + lint
  4. ANALYZE   → If errors: Analyzer diagnoses root cause
  5. PATCH     → Coder applies targeted fix
  6. Repeat 3-5 until verified or max failures
  7. ESCALATE  → If all attempts fail

Progress is shown as timestamped log lines.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from jcode.config import MAX_ITERATIONS, MAX_TASK_FAILURES, TaskStatus
from jcode.context import ContextManager
from jcode.coder import generate_file, patch_file
from jcode.reviewer import review_file
from jcode.analyzer import analyze_error
from jcode.planner import refine_plan
from jcode.file_manager import ensure_project_dir, write_file, print_tree
from jcode.executor import verify_file, install_dependencies, shell_exec

console = Console()


def _log(tag: str, message: str) -> None:
    """Timestamped log line matching cli.py format."""
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"  [dim]{ts}[/dim]  [cyan]{tag:<10}[/cyan]  {message}")


def execute_plan(ctx: ContextManager, output_dir: Path) -> bool:
    """
    Execute the full plan using DAG-ordered task processing.
    Each task goes through: generate > review > verify > fix loop.
    """
    ctx.state.output_dir = output_dir
    ensure_project_dir(output_dir)

    plan = ctx.state.plan
    if not plan:
        _log("ERROR", "No plan to execute")
        return False

    dag = ctx.get_task_dag()
    if not dag:
        _log("ERROR", "Plan has no tasks")
        return False

    _log("ENGINE", f"Executing {len(dag)} task(s) via DAG pipeline")
    _log("ENGINE", "Pipeline: Generate > Review > Verify > Fix")

    # ── Install deps before building ───────────────────────────────
    install_dependencies(output_dir, ctx.state.tech_stack)

    # ── DAG execution loop ─────────────────────────────────────────
    global_iteration = 0

    while not ctx.all_tasks_terminal() and global_iteration < MAX_ITERATIONS:
        global_iteration += 1
        ready = ctx.get_ready_tasks()

        if not ready:
            pending = [t for t in dag if not t.is_terminal]
            if pending:
                _log("DEADLOCK", "No tasks ready — possible dependency issue")
                for t in pending:
                    t.status = TaskStatus.SKIPPED
                    _log("SKIP", f"Task {t.id}: {t.file}")
            break

        for task_node in ready:
            _process_task(task_node, ctx, output_dir)

        _show_task_progress(ctx)
        _auto_save_session(ctx, output_dir)

    # ── Post-build: install deps again (new files may have added some) ──
    install_dependencies(output_dir, ctx.state.tech_stack)

    # ── Final summary ──────────────────────────────────────────────
    console.print()
    print_tree(output_dir, plan.get("project_name", "project"))

    verified = sum(1 for t in dag if t.status == TaskStatus.VERIFIED)
    failed = sum(1 for t in dag if t.status == TaskStatus.FAILED)
    skipped = sum(1 for t in dag if t.status == TaskStatus.SKIPPED)

    ctx.state.completed = (failed == 0 and skipped == 0)

    console.print()
    _log("RESULT", f"Verified: {verified}  |  Failed: {failed}  |  Skipped: {skipped}")
    _log("RESULT", f"Iterations used: {global_iteration}")

    _auto_save_session(ctx, output_dir)
    return ctx.state.completed


def _process_task(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """
    Full pipeline for a single task:
    Generate > Review > Verify > (Analyze+Patch loop)
    """
    task_dict = {
        "id": task_node.id,
        "file": task_node.file,
        "description": task_node.description,
        "depends_on": task_node.depends_on,
    }

    _log("TASK", f"#{task_node.id} {task_node.file}")
    _log("TASK", f"  {task_node.description[:80]}")

    # ── Step 1: Generate ───────────────────────────────────────────
    task_node.status = TaskStatus.IN_PROGRESS
    _log("GENERATE", task_node.file)
    content = generate_file(task_dict, ctx)
    write_file(output_dir, task_node.file, content)
    task_node.status = TaskStatus.GENERATED

    # ── Step 2: Review ─────────────────────────────────────────────
    _log("REVIEW", task_node.file)
    task_node.status = TaskStatus.REVIEWING
    review = review_file(task_node.file, ctx)

    if not review.get("approved", True):
        issues = review.get("issues", [])
        critical_issues = [i for i in issues if i.get("severity") in ("critical", "warning")]

        if critical_issues:
            feedback = "\n".join(f"- [{i['severity']}] {i['description']}" for i in critical_issues)
            task_node.review_feedback = feedback
            task_node.status = TaskStatus.NEEDS_FIX
            _log("REVIEW", f"  {len(critical_issues)} issue(s) found — patching")

            content = patch_file(
                task_node.file,
                error="Reviewer found issues before execution",
                review_feedback=feedback,
                ctx=ctx,
            )
            write_file(output_dir, task_node.file, content)
            task_node.status = TaskStatus.GENERATED
        else:
            _log("REVIEW", "  Approved")
    else:
        _log("REVIEW", "  Approved")

    # ── Step 3: Verify (static analysis) ───────────────────────────
    file_path = output_dir / task_node.file
    _log("VERIFY", task_node.file)
    verification = verify_file(file_path, output_dir)

    if verification.passed:
        task_node.status = TaskStatus.VERIFIED
        _log("VERIFY", f"  [cyan]passed[/cyan]")
        return

    _log("VERIFY", f"  failed: {verification.summary[:120]}")

    # ── Step 4: Fix loop (Analyze > Patch > Verify) ───────────────
    while task_node.failure_count < MAX_TASK_FAILURES:
        task_node.failure_count += 1
        task_node.status = TaskStatus.NEEDS_FIX

        error_output = verification.summary
        _log("ANALYZE", f"  Fix attempt {task_node.failure_count}/{MAX_TASK_FAILURES}")

        analysis = analyze_error(task_node.file, error_output, ctx)
        task_node.error_summary = analysis.get("root_cause", error_output)

        ctx.record_failure(
            file_path=task_node.file,
            error=task_node.error_summary,
            fix=analysis.get("fix_strategy", ""),
            iteration=ctx.state.iteration,
        )
        ctx.bump_iteration()

        _log("PATCH", task_node.file)
        content = patch_file(
            task_node.file,
            error=task_node.error_summary,
            review_feedback=analysis.get("fix_strategy", ""),
            ctx=ctx,
        )
        write_file(output_dir, task_node.file, content)

        _log("VERIFY", task_node.file)
        verification = verify_file(file_path, output_dir)
        if verification.passed:
            task_node.status = TaskStatus.VERIFIED
            _log("VERIFY", f"  [cyan]passed[/cyan] after {task_node.failure_count} fix(es)")
            return

        _log("VERIFY", f"  still failing: {verification.summary[:100]}")

    # Exhausted fix attempts — escalate
    _escalate_failed_task(task_node, ctx, output_dir)


def _escalate_failed_task(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """
    Handle a task that failed all fix attempts.
    Offers 4 strategies.
    """
    _log("ESCALATE", f"Task {task_node.id} failed after {MAX_TASK_FAILURES} attempts")
    _log("ESCALATE", f"  Last error: {task_node.error_summary[:150]}")
    console.print()

    console.print("    [cyan]1[/cyan]  Re-generate from scratch")
    console.print("    [cyan]2[/cyan]  Simplify (reduce scope, try again)")
    console.print("    [cyan]3[/cyan]  Skip this task and continue")
    console.print("    [cyan]4[/cyan]  Pause — let me look at the error")
    console.print()

    choice = Prompt.ask("  Choose", choices=["1", "2", "3", "4"], default="1")

    if choice == "1":
        _escalate_regenerate(task_node, ctx, output_dir)
    elif choice == "2":
        _escalate_simplify(task_node, ctx, output_dir)
    elif choice == "3":
        task_node.status = TaskStatus.SKIPPED
        _log("SKIP", f"Task {task_node.id}: {task_node.file}")
    elif choice == "4":
        _escalate_pause(task_node, ctx, output_dir)


def _escalate_regenerate(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """Throw away all patches, regenerate from scratch."""
    _log("REGEN", f"Task {task_node.id}: starting fresh")

    task_node.failure_count = 0
    task_node.error_summary = ""
    task_node.review_feedback = ""
    task_node.status = TaskStatus.IN_PROGRESS

    task_dict = {
        "id": task_node.id,
        "file": task_node.file,
        "description": task_node.description,
        "depends_on": task_node.depends_on,
    }

    content = generate_file(task_dict, ctx)
    write_file(output_dir, task_node.file, content)
    task_node.status = TaskStatus.GENERATED

    file_path = output_dir / task_node.file
    verification = verify_file(file_path, output_dir)

    if verification.passed:
        task_node.status = TaskStatus.VERIFIED
        _log("VERIFY", f"  [cyan]passed[/cyan] on re-generation")
    else:
        task_node.status = TaskStatus.FAILED
        _log("VERIFY", f"  Re-generation also failed — task marked FAILED")
        _log("VERIFY", f"  {verification.summary[:200]}")


def _escalate_simplify(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """Generate a minimal, simplified version of the file."""
    _log("SIMPLIFY", f"Task {task_node.id}: generating minimal version")

    task_node.failure_count = 0
    task_node.status = TaskStatus.IN_PROGRESS

    simplified_task = {
        "id": task_node.id,
        "file": task_node.file,
        "description": (
            f"{task_node.description}\n\n"
            f"IMPORTANT: Previous attempts failed with: {task_node.error_summary[:300]}\n"
            f"Generate a MINIMAL, simplified version that compiles cleanly.\n"
            f"Use only standard library imports. Add TODO comments for complex parts.\n"
            f"Prioritize correctness over completeness."
        ),
        "depends_on": task_node.depends_on,
    }

    content = generate_file(simplified_task, ctx)
    write_file(output_dir, task_node.file, content)
    task_node.status = TaskStatus.GENERATED

    file_path = output_dir / task_node.file
    verification = verify_file(file_path, output_dir)

    if verification.passed:
        task_node.status = TaskStatus.VERIFIED
        _log("VERIFY", f"  [cyan]passed[/cyan] with simplified version")
    else:
        task_node.status = TaskStatus.FAILED
        _log("VERIFY", f"  Simplified version also failed — task marked FAILED")
        _log("VERIFY", f"  {verification.summary[:200]}")


def _escalate_pause(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """Pause and let the user inspect the error."""
    file_path = output_dir / task_node.file

    console.print()
    _log("PAUSED", f"Task {task_node.id}: {task_node.file}")
    _log("PAUSED", f"  Error: {task_node.error_summary[:300]}")
    _log("PAUSED", f"  File:  {file_path}")
    console.print()

    console.print("    [cyan]1[/cyan]  Re-verify (after manual edit)")
    console.print("    [cyan]2[/cyan]  Provide guidance (tell the AI what to fix)")
    console.print("    [cyan]3[/cyan]  Skip this task")
    console.print()

    choice = Prompt.ask("  Choose", choices=["1", "2", "3"], default="1")

    if choice == "1":
        verification = verify_file(file_path, output_dir)
        if verification.passed:
            task_node.status = TaskStatus.VERIFIED
            _log("VERIFY", f"  [cyan]passed[/cyan] after manual edit")
        else:
            task_node.status = TaskStatus.FAILED
            _log("VERIFY", f"  Still failing: {verification.summary[:200]}")

    elif choice == "2":
        guidance = Prompt.ask("  What should the AI fix?")
        task_node.failure_count = 0
        task_node.status = TaskStatus.NEEDS_FIX

        content = patch_file(
            task_node.file,
            error=task_node.error_summary,
            review_feedback=f"User guidance: {guidance}",
            ctx=ctx,
        )
        write_file(output_dir, task_node.file, content)

        verification = verify_file(file_path, output_dir)
        if verification.passed:
            task_node.status = TaskStatus.VERIFIED
            _log("VERIFY", f"  [cyan]passed[/cyan] with user guidance")
        else:
            task_node.status = TaskStatus.FAILED
            _log("VERIFY", f"  Still failing — task marked FAILED")

    elif choice == "3":
        task_node.status = TaskStatus.SKIPPED
        _log("SKIP", f"Task {task_node.id}")


def _show_task_progress(ctx: ContextManager) -> None:
    """Show a compact task status table."""
    dag = ctx.get_task_dag()
    console.print()
    for t in dag:
        status_label = {
            TaskStatus.PENDING:     "[dim]pending[/dim]",
            TaskStatus.IN_PROGRESS: "[white]working[/white]",
            TaskStatus.GENERATED:   "[white]generated[/white]",
            TaskStatus.REVIEWING:   "[white]reviewing[/white]",
            TaskStatus.NEEDS_FIX:   "[white]fixing[/white]",
            TaskStatus.VERIFIED:    "[cyan]verified[/cyan]",
            TaskStatus.FAILED:      "[red]failed[/red]",
            TaskStatus.SKIPPED:     "[dim]skipped[/dim]",
        }.get(t.status, "[dim]?[/dim]")
        console.print(f"  {status_label:>30}  {t.id}. {t.file}")
    console.print()


def _auto_save_session(ctx: ContextManager, output_dir: Path) -> None:
    """Auto-save session to project directory."""
    try:
        session_file = output_dir / ".jcode_session.json"
        ctx.save_session(session_file)
    except Exception:
        pass
