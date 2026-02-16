"""
Coder module — generates files and applies targeted patches.
Uses structured memory (architecture + file index) instead of raw plan dumps.
"""

from __future__ import annotations

import re

from rich.console import Console

from jcode.ollama_client import call_coder
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


def generate_file(task: dict, ctx: ContextManager) -> str:
    """
    Generate complete file content from a task.
    Uses architecture summary + file index instead of full plan JSON.
    """
    file_path = task["file"]
    description = task["description"]

    # Gather dependency context (sliced, not everything)
    dep_files = ctx.get_related_files(task)
    existing_context = ""
    if dep_files:
        existing_context = f"## Related Files\n{ctx.get_file_context(dep_files)}"

    # Build messages with structured memory
    ctx.reset_coder_history()
    ctx.add_coder_message("system", CODER_SYSTEM)

    prompt = CODER_TASK.format(
        architecture=ctx.get_architecture(),
        file_index=ctx.get_file_index_str(),
        file_path=file_path,
        task_description=description,
        existing_context=existing_context,
    )
    ctx.add_coder_message("user", prompt)

    console.print(f"\n[bold green]💻 Generating [cyan]{file_path}[/cyan]…[/bold green]\n")

    _, coder_ctx = ctx.get_context_sizes()
    raw = call_coder(ctx.get_coder_messages(), stream=True, num_ctx=coder_ctx)
    content = _strip_fences(raw)

    ctx.add_coder_message("assistant", raw)
    ctx.record_file(file_path, content)

    return content


def patch_file(
    file_path: str,
    error: str,
    review_feedback: str,
    ctx: ContextManager,
) -> str:
    """
    Apply a targeted, minimal patch to an existing file.
    This is the key differentiator — small diffs, not full rewrites.
    """
    file_content = ctx.state.files.get(file_path, "")

    ctx.reset_coder_history()
    ctx.add_coder_message("system", CODER_SYSTEM)

    prompt = CODER_PATCH.format(
        architecture=ctx.get_architecture(),
        file_path=file_path,
        file_content=file_content,
        error=error,
        review_feedback=review_feedback or "(no reviewer feedback)",
    )
    ctx.add_coder_message("user", prompt)

    console.print(f"\n[bold yellow]🔧 Patching [cyan]{file_path}[/cyan]…[/bold yellow]\n")

    _, coder_ctx = ctx.get_context_sizes()
    raw = call_coder(ctx.get_coder_messages(), stream=True, num_ctx=coder_ctx)
    content = _strip_fences(raw)

    ctx.add_coder_message("assistant", raw)
    ctx.record_file(file_path, content)

    return content
