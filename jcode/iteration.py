"""
Iteration engine v2 — DAG-based task execution with 4-role pipeline.

Pipeline per task:
  1. GENERATE  → Coder produces the file
  2. REVIEW    → Reviewer critiques it (catches bugs before execution)
  3. VERIFY    → Static analysis + syntax + lint
  4. ANALYZE   → If errors: Analyzer diagnoses root cause
  5. PATCH     → Coder applies targeted fix
  6. Repeat 3-5 until verified or max failures

This is NOT a while-true loop. It's a state machine over a DAG.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from jcode.config import MAX_ITERATIONS, MAX_TASK_FAILURES, TaskStatus
from jcode.context import ContextManager
from jcode.coder import generate_file, patch_file
from jcode.reviewer import review_file
from jcode.analyzer import analyze_error
from jcode.planner import refine_plan
from jcode.file_manager import ensure_project_dir, write_file, print_tree
from jcode.executor import verify_file, install_dependencies

console = Console()


def execute_plan(ctx: ContextManager, output_dir: Path) -> bool:
    """
    Execute the full plan using DAG-ordered task processing.
    Each task goes through: generate → review → verify → fix loop.
    """
    ctx.state.output_dir = output_dir
    ensure_project_dir(output_dir)

    plan = ctx.state.plan
    if not plan:
        console.print("[red]No plan to execute![/red]")
        return False

    dag = ctx.get_task_dag()
    if not dag:
        console.print("[red]Plan has no tasks![/red]")
        return False

    console.print(Panel(
        f"[bold]Executing {len(dag)} task(s) via DAG pipeline[/bold]\n"
        f"[dim]Pipeline: Generate → Review → Verify → Fix[/dim]",
        title="⚡ JCode Engine v2",
        border_style="green",
    ))

    # ── DAG execution loop ─────────────────────────────────────────
    global_iteration = 0

    while not ctx.all_tasks_terminal() and global_iteration < MAX_ITERATIONS:
        global_iteration += 1
        ready = ctx.get_ready_tasks()

        if not ready:
            # Deadlock — no tasks can proceed
            pending = [t for t in dag if not t.is_terminal]
            if pending:
                console.print("[yellow]⚠ No ready tasks — possible dependency deadlock.[/yellow]")
                # Force-skip blocked tasks
                for t in pending:
                    t.status = TaskStatus.SKIPPED
                    console.print(f"  ⏭️  Skipped task {t.id}: {t.file}")
            break

        for task_node in ready:
            _process_task(task_node, ctx, output_dir)

        # Show progress
        _show_task_progress(ctx)

        # Auto-save
        _auto_save_session(ctx, output_dir)

    # ── Final summary ──────────────────────────────────────────────
    console.print()
    print_tree(output_dir, plan.get("project_name", "project"))

    verified = sum(1 for t in dag if t.status == TaskStatus.VERIFIED)
    failed = sum(1 for t in dag if t.status == TaskStatus.FAILED)
    skipped = sum(1 for t in dag if t.status == TaskStatus.SKIPPED)

    ctx.state.completed = (failed == 0 and skipped == 0)

    console.print(Panel(
        f"[bold]Results[/bold]\n"
        f"  ✅ Verified: {verified}\n"
        f"  ❌ Failed:   {failed}\n"
        f"  ⏭️  Skipped:  {skipped}\n"
        f"  🔄 Iterations used: {global_iteration}",
        title="📊 Summary",
        border_style="cyan",
    ))

    _auto_save_session(ctx, output_dir)
    return ctx.state.completed


def _process_task(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """
    Full pipeline for a single task:
    Generate → Review → Verify → (Analyze+Patch loop)
    """
    task_dict = {
        "id": task_node.id,
        "file": task_node.file,
        "description": task_node.description,
        "depends_on": task_node.depends_on,
    }

    console.print(Panel(
        f"[bold]Task {task_node.id}:[/bold] {task_node.description}\n"
        f"File: [cyan]{task_node.file}[/cyan]",
        border_style="blue",
    ))

    # ── Step 1: Generate ───────────────────────────────────────────
    task_node.status = TaskStatus.IN_PROGRESS
    content = generate_file(task_dict, ctx)
    write_file(output_dir, task_node.file, content)
    task_node.status = TaskStatus.GENERATED

    # ── Step 2: Review ─────────────────────────────────────────────
    task_node.status = TaskStatus.REVIEWING
    review = review_file(task_node.file, ctx)

    if not review.get("approved", True):
        # Has issues — feed reviewer feedback to coder for patch
        issues = review.get("issues", [])
        critical_issues = [i for i in issues if i.get("severity") in ("critical", "warning")]

        if critical_issues:
            feedback = "\n".join(f"- [{i['severity']}] {i['description']}" for i in critical_issues)
            task_node.review_feedback = feedback
            task_node.status = TaskStatus.NEEDS_FIX

            # Apply review-based patch
            content = patch_file(
                task_node.file,
                error="Reviewer found issues before execution",
                review_feedback=feedback,
                ctx=ctx,
            )
            write_file(output_dir, task_node.file, content)
            task_node.status = TaskStatus.GENERATED

    # ── Step 3: Verify (static analysis) ───────────────────────────
    file_path = output_dir / task_node.file
    verification = verify_file(file_path, output_dir)

    if verification.passed:
        task_node.status = TaskStatus.VERIFIED
        console.print(f"  [green]✅ Task {task_node.id} verified[/green]")
        return

    # ── Step 4: Fix loop (Analyze → Patch → Verify) ───────────────
    while task_node.failure_count < MAX_TASK_FAILURES:
        task_node.failure_count += 1
        task_node.status = TaskStatus.NEEDS_FIX

        error_output = verification.summary

        # Analyze the error
        analysis = analyze_error(task_node.file, error_output, ctx)
        task_node.error_summary = analysis.get("root_cause", error_output)

        # Log the failure
        ctx.record_failure(
            file_path=task_node.file,
            error=task_node.error_summary,
            fix=analysis.get("fix_strategy", ""),
            iteration=ctx.state.iteration,
        )
        ctx.bump_iteration()

        # Apply targeted patch
        content = patch_file(
            task_node.file,
            error=task_node.error_summary,
            review_feedback=analysis.get("fix_strategy", ""),
            ctx=ctx,
        )
        write_file(output_dir, task_node.file, content)

        # Re-verify
        verification = verify_file(file_path, output_dir)
        if verification.passed:
            task_node.status = TaskStatus.VERIFIED
            console.print(f"  [green]✅ Task {task_node.id} verified after {task_node.failure_count} fix(es)[/green]")
            return

    # Exhausted fix attempts
    task_node.status = TaskStatus.FAILED
    console.print(f"  [red]❌ Task {task_node.id} failed after {MAX_TASK_FAILURES} attempts[/red]")


def _show_task_progress(ctx: ContextManager) -> None:
    """Show a compact task status table."""
    dag = ctx.get_task_dag()
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Status", width=3)
    table.add_column("Task")
    table.add_column("File", style="cyan")

    for t in dag:
        icon = {
            TaskStatus.PENDING: "⬜",
            TaskStatus.IN_PROGRESS: "🔄",
            TaskStatus.GENERATED: "📝",
            TaskStatus.REVIEWING: "🔍",
            TaskStatus.NEEDS_FIX: "🔧",
            TaskStatus.VERIFIED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.SKIPPED: "⏭️",
        }.get(t.status, "❓")
        table.add_row(icon, f"Task {t.id}", t.file)

    console.print(table)


def _auto_save_session(ctx: ContextManager, output_dir: Path) -> None:
    """Auto-save session to project directory."""
    try:
        session_file = output_dir / ".jcode_session.json"
        ctx.save_session(session_file)
    except Exception:
        pass
