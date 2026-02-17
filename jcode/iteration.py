"""
Iteration engine v5.0 — Parallel DAG-based task execution.

Architecture:
  1. Compute execution waves from the task DAG
  2. For each wave, run ALL tasks in parallel via WorkerPool
  3. Each task pipeline: GENERATE → REVIEW → VERIFY → FIX
  4. Within a wave, generate all in parallel, review all in parallel
  5. Fix only failures (sequentially per task, with escalation)

Pipeline per wave:
  Phase A: Generate all files in the wave concurrently
  Phase B: Review all generated files concurrently
  Phase C: Verify all files (static analysis)
  Phase D: Fix only failures (multi-strategy, sequential)

Worker Pool:
  - Max 6 concurrent workers
  - CPU-aware adaptive concurrency
  - Thread-safe model calls via silent mode
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from jcode.config import MAX_ITERATIONS, MAX_TASK_FAILURES, TaskStatus, get_model_for_role
from jcode.context import ContextManager
from jcode.coder import generate_file, patch_file
from jcode.reviewer import review_file
from jcode.analyzer import analyze_error
from jcode.planner import refine_plan
from jcode.file_manager import ensure_project_dir, write_file, print_tree
from jcode.executor import verify_file, install_dependencies, shell_exec, run_tests
from jcode.worker_pool import WorkerPool
from jcode.task_graph import compute_waves, get_ready_wave, get_dag_stats

console = Console()


def _log(tag: str, message: str) -> None:
    """Timestamped log line matching cli.py format."""
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"  [dim]{ts}[/dim]  [cyan]{tag:<10}[/cyan]  {message}")


def execute_plan(ctx: ContextManager, output_dir: Path) -> bool:
    """
    Execute the full plan using parallel wave-based DAG processing.

    Strategy:
      1. Compute waves (topological layers of the DAG)
      2. For each wave:
         a. Generate ALL files in parallel
         b. Review (only for medium+ complexity)
         c. Verify ALL files
         d. Fix only failures (sequentially)

    Simple projects skip review entirely for speed.
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

    # Show model tiering info
    complexity = ctx.get_complexity()
    size = ctx.get_size()
    skip_review = complexity == "simple"

    _log("ENGINE", f"Classification: [bold]{complexity}/{size}[/bold]")
    _log("ENGINE", f"Coder model:    {get_model_for_role('coder', complexity, size)}")
    if not skip_review:
        _log("ENGINE", f"Reviewer model: {get_model_for_role('reviewer', complexity, size)}")

    # Compute waves for display
    try:
        all_waves = compute_waves(dag)
        _log("ENGINE", f"{len(dag)} task(s) in {len(all_waves)} wave(s) — parallel execution enabled")
        for i, wave in enumerate(all_waves):
            files = ", ".join(t.file for t in wave)
            _log("WAVE", f"  {i}: [{len(wave)} task(s)] {files}")
    except ValueError as e:
        _log("WARNING", f"DAG issue: {e} — falling back to sequential")
        all_waves = [[t] for t in dag]

    if skip_review:
        _log("ENGINE", "Pipeline: Generate ‖ → Verify → Fix (review skipped for simple)")
    else:
        _log("ENGINE", "Pipeline: Generate ‖ → Review ‖ → Verify → Fix failures")

    # -- Install deps before building
    install_dependencies(output_dir, ctx.state.tech_stack)

    # -- Index existing project files into vector memory (for RAG)
    ctx.index_memory()

    # -- Create worker pool
    pool = WorkerPool()
    start_time = time.monotonic()

    try:
        # -- Wave execution loop
        global_iteration = 0

        while not ctx.all_tasks_terminal() and global_iteration < MAX_ITERATIONS:
            global_iteration += 1
            ready = get_ready_wave(dag)

            if not ready:
                pending = [t for t in dag if not t.is_terminal]
                if pending:
                    _log("DEADLOCK", "No tasks ready -- possible dependency issue")
                    for t in pending:
                        t.status = TaskStatus.SKIPPED
                        _log("SKIP", f"Task {t.id}: {t.file}")
                break

            wave_num = global_iteration
            _log("WAVE", f"── Wave {wave_num}: {len(ready)} task(s) ──")

            # Phase A: Generate all files in parallel
            _log("PHASE A", f"Generating {len(ready)} file(s) in parallel")
            _parallel_generate(ready, ctx, output_dir, pool)

            # Phase B: Review (skip for simple projects — just verify)
            if not skip_review:
                generated = [t for t in ready if t.status == TaskStatus.GENERATED]
                if generated:
                    _log("PHASE B", f"Reviewing {len(generated)} file(s) in parallel")
                    _parallel_review(generated, ctx, output_dir, pool)

            # Phase C: Verify all files
            _log("PHASE C", "Verifying files (static analysis)")
            _parallel_verify(ready, ctx, output_dir)

            # Phase D: Fix only failures (sequential per task)
            needs_fix = [t for t in ready if t.status == TaskStatus.NEEDS_FIX]
            if needs_fix:
                _log("PHASE D", f"Fixing {len(needs_fix)} failed file(s)")
                for task_node in needs_fix:
                    file_path = output_dir / task_node.file
                    verification = verify_file(file_path, output_dir)
                    _multi_strategy_fix(task_node, ctx, output_dir, verification)

            _show_task_progress(ctx)
            _auto_save_session(ctx, output_dir)

            # Re-index vector memory with newly generated files
            ctx.index_memory()

    finally:
        pool.shutdown(wait=True)

    elapsed = time.monotonic() - start_time

    # -- Post-build: install deps again (new files may have added some)
    install_dependencies(output_dir, ctx.state.tech_stack)

    # -- Run tests if they exist
    _log("TEST", "Checking for test suite...")
    test_result = run_tests(output_dir, ctx.state.tech_stack)
    if test_result.command != "(no tests)":
        if test_result.success:
            _log("TEST", "[cyan]All tests passed[/cyan]")
        else:
            _log("TEST", f"Tests failed: {test_result.error_summary[:200]}")
    else:
        _log("TEST", "No test runner detected -- skipping")

    # -- Final summary
    console.print()
    print_tree(output_dir, plan.get("project_name", "project"))

    verified = sum(1 for t in dag if t.status == TaskStatus.VERIFIED)
    failed = sum(1 for t in dag if t.status == TaskStatus.FAILED)
    skipped = sum(1 for t in dag if t.status == TaskStatus.SKIPPED)

    ctx.state.completed = (failed == 0 and skipped == 0)

    console.print()
    _log("RESULT", f"Verified: {verified}  |  Failed: {failed}  |  Skipped: {skipped}")
    _log("RESULT", f"Total time: {elapsed:.1f}s  |  Iterations: {global_iteration}")

    _auto_save_session(ctx, output_dir)
    return ctx.state.completed


# =====================================================================
# Parallel Phase A: Generate all files in a wave concurrently
# =====================================================================

def _parallel_generate(
    wave: list,
    ctx: ContextManager,
    output_dir: Path,
    pool: WorkerPool,
) -> None:
    """Generate all files in the wave concurrently via WorkerPool."""

    def _gen_worker(task_node) -> str:
        """Worker function for a single file generation."""
        task_dict = {
            "id": task_node.id,
            "file": task_node.file,
            "description": task_node.description,
            "depends_on": task_node.depends_on,
        }
        task_node.status = TaskStatus.IN_PROGRESS
        content = generate_file(task_dict, ctx, parallel=True)
        write_file(output_dir, task_node.file, content)
        task_node.status = TaskStatus.GENERATED
        return content

    if len(wave) == 1:
        # Single task — use streaming for better UX
        task_node = wave[0]
        task_dict = {
            "id": task_node.id,
            "file": task_node.file,
            "description": task_node.description,
            "depends_on": task_node.depends_on,
        }
        task_node.status = TaskStatus.IN_PROGRESS
        _log("GENERATE", task_node.file)
        content = generate_file(task_dict, ctx, parallel=False)
        write_file(output_dir, task_node.file, content)
        task_node.status = TaskStatus.GENERATED
        return

    # Multiple tasks — parallel silent generation
    futures = []
    for node in wave:
        _log("GENERATE", f"⚡ {node.file}")
        future = pool.submit(_gen_worker, node, task_id=node.id)
        futures.append(future)

    results = pool.collect(futures)
    for r in results:
        if not r.success:
            _log("GENERATE", f"  ⚠ Task {r.task_id} failed: {r.error[:100]}")
        else:
            _log("GENERATE", f"  ✓ Task {r.task_id} done ({r.duration_ms}ms)")


# =====================================================================
# Parallel Phase B: Review all generated files concurrently
# =====================================================================

def _parallel_review(
    wave: list,
    ctx: ContextManager,
    output_dir: Path,
    pool: WorkerPool,
) -> None:
    """Review all generated files in the wave concurrently."""

    def _review_worker(task_node) -> dict:
        """Worker function for reviewing a single file."""
        task_node.status = TaskStatus.REVIEWING
        review = review_file(task_node.file, ctx, parallel=True)

        if review.get("approved", True):
            return review

        issues = review.get("issues", [])
        critical_issues = [
            i for i in issues
            if i.get("severity") in ("critical", "warning")
        ]
        if not critical_issues:
            return review

        # Apply a patch for critical issues
        feedback = "\n".join(
            f"- [{i['severity']}] {i['description']}" for i in critical_issues
        )
        task_node.review_feedback = feedback
        task_node.status = TaskStatus.NEEDS_FIX

        content = patch_file(
            task_node.file,
            error="Reviewer found issues before execution",
            review_feedback=feedback,
            ctx=ctx,
            parallel=True,
        )
        write_file(output_dir, task_node.file, content)
        task_node.status = TaskStatus.GENERATED
        return review

    if len(wave) == 1:
        # Single file — use sequential review
        task_node = wave[0]
        _review_and_patch(task_node, ctx, output_dir)
        return

    # Multiple files — parallel review
    futures = []
    for node in wave:
        _log("REVIEW", f"⚡ {node.file}")
        future = pool.submit(_review_worker, node, task_id=node.id)
        futures.append(future)

    results = pool.collect(futures)
    for r in results:
        if not r.success:
            _log("REVIEW", f"  ⚠ Task {r.task_id} error: {r.error[:100]}")
        else:
            _log("REVIEW", f"  ✓ Task {r.task_id} reviewed ({r.duration_ms}ms)")


# =====================================================================
# Phase C: Verify all files (fast — runs locally, no model calls)
# =====================================================================

def _parallel_verify(
    wave: list,
    ctx: ContextManager,
    output_dir: Path,
) -> None:
    """Verify all files in the wave. Sets status to VERIFIED or NEEDS_FIX."""
    for task_node in wave:
        if task_node.is_terminal:
            continue
        file_path = output_dir / task_node.file
        _log("VERIFY", task_node.file)
        verification = verify_file(file_path, output_dir)

        if verification.passed:
            task_node.status = TaskStatus.VERIFIED
            _log("VERIFY", "  [cyan]passed[/cyan]")
        else:
            task_node.status = TaskStatus.NEEDS_FIX
            _log("VERIFY", f"  failed: {verification.summary[:120]}")


# =====================================================================
# Sequential review (for single-file waves)
# =====================================================================

def _review_and_patch(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """Review the file, patch if needed, then re-review once to confirm."""
    max_review_rounds = 2

    for review_round in range(max_review_rounds):
        round_label = f"(round {review_round + 1})" if review_round > 0 else ""
        _log("REVIEW", f"{task_node.file} {round_label}")
        task_node.status = TaskStatus.REVIEWING
        review = review_file(task_node.file, ctx)

        if review.get("approved", True):
            _log("REVIEW", "  Approved")
            return

        issues = review.get("issues", [])
        critical_issues = [
            i for i in issues
            if i.get("severity") in ("critical", "warning")
        ]

        if not critical_issues:
            _log("REVIEW", "  Approved (suggestions only)")
            return

        feedback = "\n".join(
            f"- [{i['severity']}] {i['description']}" for i in critical_issues
        )
        task_node.review_feedback = feedback
        task_node.status = TaskStatus.NEEDS_FIX
        _log("REVIEW", f"  {len(critical_issues)} issue(s) found -- patching")

        content = patch_file(
            task_node.file,
            error="Reviewer found issues before execution",
            review_feedback=feedback,
            ctx=ctx,
        )
        write_file(output_dir, task_node.file, content)
        task_node.status = TaskStatus.GENERATED

    _log("REVIEW", "  Accepted after review patches")


# =====================================================================
# Multi-strategy fix loop — the heart of resilience
# =====================================================================

def _multi_strategy_fix(
    task_node,
    ctx: ContextManager,
    output_dir: Path,
    initial_verification,
) -> None:
    """
    Try up to MAX_TASK_FAILURES fix strategies, escalating in complexity:

    Attempts 1-3: Targeted patch (cheapest — just fix what is broken)
    Attempt 4:    Deep analysis with cross-file context
    Attempt 5:    Deep analysis + dependency re-check
    Attempt 6:    Full regeneration from scratch with error history
    Attempt 7:    Simplified/minimal version
    Attempt 8:    Research-based fix (analyze error class, apply known pattern)

    Each attempt: Analyze > Fix > Verify
    """
    verification = initial_verification

    while task_node.failure_count < MAX_TASK_FAILURES:
        task_node.failure_count += 1
        attempt = task_node.failure_count
        task_node.status = TaskStatus.NEEDS_FIX
        file_path = output_dir / task_node.file

        error_output = verification.summary

        # Choose strategy based on attempt number
        if attempt <= 3:
            # -- Strategy A: Targeted patch
            _log("FIX", f"  Attempt {attempt}/{MAX_TASK_FAILURES} [dim](targeted patch)[/dim]")
            verification = _strategy_targeted_patch(
                task_node, ctx, output_dir, error_output
            )

        elif attempt <= 5:
            # -- Strategy B: Deep analysis with cross-file context
            _log("FIX", f"  Attempt {attempt}/{MAX_TASK_FAILURES} [dim](deep analysis)[/dim]")
            verification = _strategy_deep_analysis(
                task_node, ctx, output_dir, error_output
            )

        elif attempt == 6:
            # -- Strategy C: Full regeneration from scratch
            _log("FIX", f"  Attempt {attempt}/{MAX_TASK_FAILURES} [dim](full regeneration)[/dim]")
            verification = _strategy_regenerate(
                task_node, ctx, output_dir, error_output
            )

        elif attempt == 7:
            # -- Strategy D: Simplified/minimal version
            _log("FIX", f"  Attempt {attempt}/{MAX_TASK_FAILURES} [dim](simplified build)[/dim]")
            verification = _strategy_simplify(
                task_node, ctx, output_dir, error_output
            )

        else:
            # -- Strategy E: Research-based fix (last resort)
            _log("FIX", f"  Attempt {attempt}/{MAX_TASK_FAILURES} [dim](research fix)[/dim]")
            verification = _strategy_research_fix(
                task_node, ctx, output_dir, error_output
            )

        if verification.passed:
            task_node.status = TaskStatus.VERIFIED
            _log("VERIFY", f"  [cyan]passed[/cyan] after {attempt} attempt(s)")
            return

        _log("VERIFY", f"  still failing: {verification.summary[:100]}")

    # Exhausted ALL fix attempts -- escalate
    _escalate_failed_task(task_node, ctx, output_dir)


# =====================================================================
# Fix strategies
# =====================================================================

def _strategy_targeted_patch(task_node, ctx, output_dir, error_output):
    """Strategy A: Simple analyze > patch > verify."""
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

    file_path = output_dir / task_node.file
    _log("VERIFY", task_node.file)
    return verify_file(file_path, output_dir)


def _strategy_deep_analysis(task_node, ctx, output_dir, error_output):
    """
    Strategy B: Deep analysis with cross-file dependency context.
    Feeds the analyzer not just the broken file, but also its dependencies.
    """
    # Gather dependency file contents for richer analysis
    dep_files = ctx.state.dependency_graph.get(task_node.file, [])
    cross_file_context = ""
    for dep_path in dep_files[:5]:
        dep_content = ctx.state.files.get(dep_path, "")
        if dep_content:
            cross_file_context += f"\n\n--- {dep_path} ---\n{dep_content[:3000]}"

    # Also look at files that import this file (reverse deps)
    importers = []
    for fpath, deps in ctx.state.dependency_graph.items():
        if task_node.file in deps:
            importers.append(fpath)
    for imp_path in importers[:3]:
        imp_content = ctx.state.files.get(imp_path, "")
        if imp_content:
            cross_file_context += f"\n\n--- {imp_path} (imports this file) ---\n{imp_content[:2000]}"

    # Build enriched error context
    all_failures = ctx.get_failure_log_str(task_node.file)
    enriched_error = (
        f"ERROR: {error_output}\n\n"
        f"PREVIOUS FIX ATTEMPTS:\n{all_failures}\n\n"
        f"CROSS-FILE CONTEXT:\n{cross_file_context}\n\n"
        f"NOTE: Previous targeted patches failed. Think deeper about the root cause. "
        f"The issue may be in how this file interacts with its dependencies."
    )

    analysis = analyze_error(task_node.file, enriched_error, ctx)
    task_node.error_summary = analysis.get("root_cause", error_output)

    # Check if the analyzer says it is a dependency issue
    if analysis.get("is_dependency_issue"):
        affected = analysis.get("affected_file", "")
        if affected and affected != task_node.file and affected in ctx.state.files:
            _log("FIX", f"  Dependency issue detected -- also patching {affected}")
            dep_content = patch_file(
                affected,
                error=f"Downstream file {task_node.file} fails because of this file: {task_node.error_summary}",
                review_feedback=analysis.get("fix_strategy", ""),
                ctx=ctx,
            )
            write_file(output_dir, affected, dep_content)

    ctx.record_failure(
        file_path=task_node.file,
        error=task_node.error_summary,
        fix=f"[deep] {analysis.get('fix_strategy', '')}",
        iteration=ctx.state.iteration,
    )
    ctx.bump_iteration()

    _log("PATCH", f"{task_node.file} (deep)")
    content = patch_file(
        task_node.file,
        error=task_node.error_summary,
        review_feedback=(
            f"DEEP ANALYSIS:\n{analysis.get('fix_strategy', '')}\n\n"
            f"Cross-file context was considered. "
            f"All previous fix attempts failed, so try a fundamentally different approach."
        ),
        ctx=ctx,
    )
    write_file(output_dir, task_node.file, content)

    file_path = output_dir / task_node.file
    _log("VERIFY", task_node.file)

    # Re-install deps in case the fix added new requirements
    install_dependencies(output_dir, ctx.state.tech_stack)

    return verify_file(file_path, output_dir)


def _strategy_regenerate(task_node, ctx, output_dir, error_output):
    """
    Strategy C: Throw away the file and regenerate from scratch,
    but with full knowledge of what went wrong.
    """
    _log("REGEN", f"Task {task_node.id}: fresh generation with error history")

    all_failures = ctx.get_failure_log_str(task_node.file)

    # Build an enriched task description
    enriched_task = {
        "id": task_node.id,
        "file": task_node.file,
        "description": (
            f"{task_node.description}\n\n"
            f"CRITICAL: This file has been generated before but failed verification "
            f"after {task_node.failure_count} attempts.\n\n"
            f"Previous errors:\n{all_failures}\n\n"
            f"Last error: {error_output[:500]}\n\n"
            f"Requirements:\n"
            f"1. Write clean, correct code that will pass syntax checks and linting.\n"
            f"2. Include ALL necessary imports.\n"
            f"3. Make sure all function signatures match what other files expect.\n"
            f"4. DO NOT repeat the same mistakes.\n"
            f"5. If unsure about an API, use the simplest correct approach."
        ),
        "depends_on": task_node.depends_on,
    }

    content = generate_file(enriched_task, ctx)
    write_file(output_dir, task_node.file, content)

    ctx.record_failure(
        file_path=task_node.file,
        error=error_output,
        fix="[regen] Full regeneration from scratch with error history",
        iteration=ctx.state.iteration,
    )
    ctx.bump_iteration()

    file_path = output_dir / task_node.file
    _log("VERIFY", task_node.file)
    return verify_file(file_path, output_dir)


def _strategy_simplify(task_node, ctx, output_dir, error_output):
    """
    Strategy D: Generate a minimal, simplified version that
    definitely compiles. Sacrifice features for correctness.
    """
    _log("SIMPLIFY", f"Task {task_node.id}: generating minimal version")

    simplified_task = {
        "id": task_node.id,
        "file": task_node.file,
        "description": (
            f"{task_node.description}\n\n"
            f"IMPORTANT: All previous attempts to generate this file failed.\n"
            f"Last error: {error_output[:300]}\n\n"
            f"Generate a MINIMAL, simplified version that DEFINITELY compiles.\n"
            f"Rules for this attempt:\n"
            f"1. Use ONLY standard library imports (no third-party packages).\n"
            f"2. Keep the implementation as simple as possible.\n"
            f"3. Add TODO comments for any complex parts you are skipping.\n"
            f"4. Make sure every function has a proper return value.\n"
            f"5. Use placeholder data instead of complex logic if needed.\n"
            f"6. Prioritize CORRECTNESS over completeness.\n"
            f"7. Test-compile the code mentally before outputting it."
        ),
        "depends_on": task_node.depends_on,
    }

    content = generate_file(simplified_task, ctx)
    write_file(output_dir, task_node.file, content)

    ctx.record_failure(
        file_path=task_node.file,
        error=error_output,
        fix="[simplify] Minimal version with stdlib only",
        iteration=ctx.state.iteration,
    )
    ctx.bump_iteration()

    file_path = output_dir / task_node.file
    _log("VERIFY", task_node.file)
    return verify_file(file_path, output_dir)


def _strategy_research_fix(task_node, ctx, output_dir, error_output):
    """
    Strategy E (last resort): Analyze the error class/pattern and apply
    known fix patterns. Feed the coder extremely explicit instructions.
    """
    _log("RESEARCH", f"Task {task_node.id}: analyzing error patterns")

    # Classify the error type
    error_lower = error_output.lower()
    fix_hints = []

    if "import" in error_lower or "modulenotfounderror" in error_lower:
        fix_hints.append("This is an import error. Remove the broken import or replace it with a correct one.")
        fix_hints.append("Check: is the module name spelled correctly? Is it installed? Is it a relative vs absolute import issue?")
    if "syntax" in error_lower or "syntaxerror" in error_lower:
        fix_hints.append("This is a syntax error. Check for missing colons, brackets, parentheses, or indentation issues.")
        fix_hints.append("Common causes: unclosed string literals, missing commas in lists/dicts, incorrect indentation.")
    if "indentation" in error_lower:
        fix_hints.append("Indentation error. Make sure all blocks use consistent indentation (4 spaces, no tabs).")
    if "undefined" in error_lower or "undeclared" in error_lower or "is not defined" in error_lower:
        fix_hints.append("A variable or function is used before it is defined. Check imports and declaration order.")
    if "type" in error_lower and "error" in error_lower:
        fix_hints.append("Type error. Check function arguments, return types, and variable assignments.")
    if "attribute" in error_lower:
        fix_hints.append("AttributeError. The object does not have the property/method you are accessing. Check the API docs.")
    if "key" in error_lower and "error" in error_lower:
        fix_hints.append("KeyError. A dictionary key does not exist. Use .get() with a default value.")
    if "cannot find module" in error_lower or "module not found" in error_lower:
        fix_hints.append("Node.js module not found. Check package.json dependencies and import paths.")
    if "jsx" in error_lower or "react" in error_lower:
        fix_hints.append("React/JSX error. Make sure React is imported and JSX syntax is correct.")
    if "unexpected token" in error_lower:
        fix_hints.append("JavaScript syntax error. Check for missing semicolons, brackets, or ES module syntax issues.")

    if not fix_hints:
        fix_hints.append("Analyze the error message carefully and fix the exact issue it describes.")
        fix_hints.append("If the error is unclear, rewrite the problematic section from scratch using the simplest correct approach.")

    hint_text = "\n".join(f"- {h}" for h in fix_hints)

    all_failures = ctx.get_failure_log_str(task_node.file)

    content = patch_file(
        task_node.file,
        error=error_output,
        review_feedback=(
            f"LAST RESORT FIX -- attempt {task_node.failure_count}/{MAX_TASK_FAILURES}\n\n"
            f"Error pattern analysis:\n{hint_text}\n\n"
            f"Previous fix attempts (ALL FAILED):\n{all_failures}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Read the error message VERY carefully.\n"
            f"2. Apply the specific fix hints above.\n"
            f"3. Do NOT repeat any previous fix attempts.\n"
            f"4. If a section of code keeps breaking, REWRITE IT completely.\n"
            f"5. Use the simplest possible approach that solves the problem.\n"
            f"6. Double-check every import statement.\n"
            f"7. Output the COMPLETE corrected file."
        ),
        ctx=ctx,
    )
    write_file(output_dir, task_node.file, content)

    ctx.record_failure(
        file_path=task_node.file,
        error=error_output,
        fix=f"[research] Pattern-based fix: {fix_hints[0][:100]}",
        iteration=ctx.state.iteration,
    )
    ctx.bump_iteration()

    file_path = output_dir / task_node.file
    _log("VERIFY", task_node.file)
    return verify_file(file_path, output_dir)


# =====================================================================
# Escalation — when ALL strategies fail
# =====================================================================

def _escalate_failed_task(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """
    Handle a task that failed ALL fix attempts.
    At this point, 8 attempts with 5 strategies have been tried.
    """
    _log("ESCALATE", f"Task {task_node.id} failed after {MAX_TASK_FAILURES} attempts")
    _log("ESCALATE", f"  Strategies tried: targeted patch, deep analysis, regeneration, simplify, research")
    _log("ESCALATE", f"  Last error: {task_node.error_summary[:150]}")
    console.print()

    console.print("    [cyan]1[/cyan]  Try again (reset counter, another round of fixes)")
    console.print("    [cyan]2[/cyan]  Provide guidance (tell the AI exactly what to fix)")
    console.print("    [cyan]3[/cyan]  Skip this task and continue")
    console.print("    [cyan]4[/cyan]  Pause -- let me edit the file manually")
    console.print()

    choice = Prompt.ask("  Choose", choices=["1", "2", "3", "4"], default="2")

    if choice == "1":
        _escalate_retry(task_node, ctx, output_dir)
    elif choice == "2":
        _escalate_guided_fix(task_node, ctx, output_dir)
    elif choice == "3":
        task_node.status = TaskStatus.SKIPPED
        _log("SKIP", f"Task {task_node.id}: {task_node.file}")
    elif choice == "4":
        _escalate_pause(task_node, ctx, output_dir)


def _escalate_retry(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """Reset failure counter and run the full fix loop again."""
    _log("RETRY", f"Task {task_node.id}: resetting counter for another round")
    task_node.failure_count = 0
    task_node.status = TaskStatus.NEEDS_FIX

    file_path = output_dir / task_node.file
    verification = verify_file(file_path, output_dir)

    if verification.passed:
        task_node.status = TaskStatus.VERIFIED
        _log("VERIFY", "  [cyan]passed[/cyan]")
        return

    _multi_strategy_fix(task_node, ctx, output_dir, verification)


def _escalate_guided_fix(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """Let the user tell the AI exactly what to fix."""
    console.print()
    _log("GUIDE", f"Current error: {task_node.error_summary[:200]}")
    console.print()
    guidance = Prompt.ask("  What should the AI fix?")

    # Apply the user guidance with a focused patch
    content = patch_file(
        task_node.file,
        error=task_node.error_summary,
        review_feedback=f"USER GUIDANCE (highest priority): {guidance}",
        ctx=ctx,
    )
    write_file(output_dir, task_node.file, content)

    file_path = output_dir / task_node.file
    verification = verify_file(file_path, output_dir)

    if verification.passed:
        task_node.status = TaskStatus.VERIFIED
        _log("VERIFY", "  [cyan]passed[/cyan] with user guidance")
    else:
        _log("VERIFY", f"  Still failing: {verification.summary[:200]}")
        console.print()
        console.print("    [cyan]1[/cyan]  Give more guidance")
        console.print("    [cyan]2[/cyan]  Skip this task")
        console.print("    [cyan]3[/cyan]  Pause and edit manually")
        console.print()
        choice = Prompt.ask("  Choose", choices=["1", "2", "3"], default="1")

        if choice == "1":
            _escalate_guided_fix(task_node, ctx, output_dir)
        elif choice == "2":
            task_node.status = TaskStatus.SKIPPED
            _log("SKIP", f"Task {task_node.id}")
        elif choice == "3":
            _escalate_pause(task_node, ctx, output_dir)


def _escalate_pause(task_node, ctx: ContextManager, output_dir: Path) -> None:
    """Pause and let the user inspect/edit the file."""
    file_path = output_dir / task_node.file

    console.print()
    _log("PAUSED", f"Task {task_node.id}: {task_node.file}")
    _log("PAUSED", f"  Error: {task_node.error_summary[:300]}")
    _log("PAUSED", f"  File:  {file_path}")
    console.print()
    console.print("  [dim]Edit the file in your editor, then choose:[/dim]")
    console.print()

    console.print("    [cyan]1[/cyan]  Re-verify (after manual edit)")
    console.print("    [cyan]2[/cyan]  Skip this task")
    console.print()

    choice = Prompt.ask("  Choose", choices=["1", "2"], default="1")

    if choice == "1":
        # Re-read the file from disk (user may have edited it)
        try:
            content = file_path.read_text()
            ctx.record_file(task_node.file, content)
        except Exception:
            pass

        verification = verify_file(file_path, output_dir)
        if verification.passed:
            task_node.status = TaskStatus.VERIFIED
            _log("VERIFY", "  [cyan]passed[/cyan] after manual edit")
        else:
            _log("VERIFY", f"  Still failing: {verification.summary[:200]}")
            task_node.status = TaskStatus.FAILED
    elif choice == "2":
        task_node.status = TaskStatus.SKIPPED
        _log("SKIP", f"Task {task_node.id}")


# =====================================================================
# Progress display
# =====================================================================

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
        fails = f" [dim]({t.failure_count} fixes)[/dim]" if t.failure_count > 0 else ""
        console.print(f"  {status_label:>30}  {t.id}. {t.file}{fails}")
    console.print()


def _auto_save_session(ctx: ContextManager, output_dir: Path) -> None:
    """Auto-save session to project directory."""
    try:
        session_file = output_dir / ".jcode_session.json"
        ctx.save_session(session_file)
    except Exception:
        pass
