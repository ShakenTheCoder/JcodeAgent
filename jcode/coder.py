"""
Coder module — generates files and applies targeted patches.
Uses structured memory (architecture + file index) instead of raw plan dumps.

v2.0 — Supports parallel generation via silent mode for WorkerPool.
"""

from __future__ import annotations

import re

from rich.console import Console

from jcode.ollama_client import call_coder, call_model_silent
from jcode.prompts import CODER_SYSTEM, CODER_TASK, CODER_PATCH
from jcode.context import ContextManager

console = Console()


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if the model wrapped output."""
    text = text.strip()
    # Strip <think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.match(r"^```\w*\n(.*?)```\s*$", text, re.DOTALL)
    if m:
        return m.group(1)
    return text


def generate_file(task: dict, ctx: ContextManager, parallel: bool = False) -> str:
    """
    Generate complete file content from a task.
    Uses architecture summary + file index instead of full plan JSON.

    Args:
        task: Task dict with 'file', 'description', 'depends_on' keys.
        ctx: The ContextManager for structured memory access.
        parallel: If True, use silent (non-streaming) generation for thread safety.
    """
    file_path = task["file"]
    description = task["description"]

    # Gather dependency context (sliced, not everything)
    dep_files = ctx.get_related_files(task)
    existing_context = ""
    if dep_files:
        existing_context = f"## Related Files\n{ctx.get_file_context(dep_files)}"

    # Build messages with structured memory
    messages = [
        {"role": "system", "content": CODER_SYSTEM},
    ]

    prompt = CODER_TASK.format(
        architecture=ctx.get_architecture(),
        file_index=ctx.get_file_index_str(),
        file_path=file_path,
        task_description=description,
        existing_context=existing_context,
    )
    messages.append({"role": "user", "content": prompt})

    _, coder_ctx = ctx.get_context_sizes()
    complexity = ctx.get_complexity()

    if parallel:
        # Silent mode for parallel workers — no streaming, no coder_history mutation
        console.print(f"  [dim]⚡ Generating[/dim] [cyan]{file_path}[/cyan]")
        raw = call_model_silent("coder", messages, num_ctx=coder_ctx, complexity=complexity)
    else:
        # Sequential mode with streaming
        ctx.reset_coder_history()
        ctx.add_coder_message("system", CODER_SYSTEM)
        ctx.add_coder_message("user", prompt)
        console.print(f"\n  [dim]Generating[/dim] [cyan]{file_path}[/cyan]\n")
        raw = call_coder(ctx.get_coder_messages(), stream=True, num_ctx=coder_ctx, complexity=complexity)
        ctx.add_coder_message("assistant", raw)

    content = _strip_fences(raw)
    ctx.record_file(file_path, content)
    return content


def patch_file(
    file_path: str,
    error: str,
    review_feedback: str,
    ctx: ContextManager,
    parallel: bool = False,
) -> str:
    """
    Apply a targeted, minimal patch to an existing file.
    This is the key differentiator — small diffs, not full rewrites.

    Args:
        parallel: If True, use silent (non-streaming) generation.
    """
    file_content = ctx.state.files.get(file_path, "")

    prompt = CODER_PATCH.format(
        architecture=ctx.get_architecture(),
        file_path=file_path,
        file_content=file_content,
        error=error,
        review_feedback=review_feedback or "(no reviewer feedback)",
    )

    _, coder_ctx = ctx.get_context_sizes()
    complexity = ctx.get_complexity()

    if parallel:
        messages = [
            {"role": "system", "content": CODER_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        console.print(f"  [dim]⚡ Patching[/dim] [cyan]{file_path}[/cyan]")
        raw = call_model_silent("coder", messages, num_ctx=coder_ctx, complexity=complexity)
    else:
        ctx.reset_coder_history()
        ctx.add_coder_message("system", CODER_SYSTEM)
        ctx.add_coder_message("user", prompt)
        console.print(f"\n  [dim]Patching[/dim] [cyan]{file_path}[/cyan]\n")
        raw = call_coder(ctx.get_coder_messages(), stream=True, num_ctx=coder_ctx, complexity=complexity)
        ctx.add_coder_message("assistant", raw)

    content = _strip_fences(raw)
    ctx.record_file(file_path, content)
    return content
