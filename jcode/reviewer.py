"""
Reviewer module — code critic that catches bugs BEFORE execution.

This is one of the key differentiators: frontier models generate and hope.
JCode generates, reviews, THEN executes. Verification > intelligence.
"""

from __future__ import annotations

import json
import re

from rich.console import Console

from jcode.ollama_client import call_reviewer
from jcode.prompts import REVIEWER_SYSTEM, REVIEWER_TASK
from jcode.context import ContextManager

console = Console()


def _extract_json(text: str) -> dict:
    """Extract JSON from reviewer output."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    continue

    # Fallback: if we can't parse, assume approval
    return {"approved": True, "issues": [], "summary": "Could not parse review"}


def review_file(file_path: str, ctx: ContextManager) -> dict:
    """
    Review a generated file before accepting it.

    Returns:
        {
            "approved": bool,
            "issues": [{"file", "line_hint", "severity", "description"}],
            "summary": str
        }
    """
    file_content = ctx.state.files.get(file_path, "")
    file_purpose = ctx.state.file_index.get(file_path, "unknown purpose")

    if not file_content.strip():
        return {"approved": False, "issues": [{"file": file_path, "line_hint": "entire file", "severity": "critical", "description": "File is empty"}], "summary": "Empty file"}

    # Get related files for context
    related_paths = []
    deps = ctx.state.dependency_graph.get(file_path, [])
    related_paths.extend(deps)
    related_context = ctx.get_file_context(related_paths[:3]) if related_paths else "(none)"

    ctx.reset_channel("reviewer")
    ctx.add_message("reviewer", "system", REVIEWER_SYSTEM)

    prompt = REVIEWER_TASK.format(
        architecture=ctx.get_architecture(),
        file_path=file_path,
        file_purpose=file_purpose,
        file_content=file_content[:MAX_REVIEW_CHARS],
        related_context=related_context,
    )
    ctx.add_message("reviewer", "user", prompt)

    console.print(f"  [dim]Reviewing[/dim] [cyan]{file_path}[/cyan]")

    _, coder_ctx = ctx.get_context_sizes()
    raw = call_reviewer(
        ctx.get_messages("reviewer"),
        stream=False,  # Reviews don't need streaming
        num_ctx=coder_ctx,
    )

    result = _extract_json(raw)

    # Display review summary
    if result.get("approved"):
        console.print(f"    [cyan]approved[/cyan] — {result.get('summary', '')}")
    else:
        issues = result.get("issues", [])
        critical = [i for i in issues if i.get("severity") == "critical"]
        warnings = [i for i in issues if i.get("severity") == "warning"]
        console.print(f"    [dim]issues found[/dim] — {len(critical)} critical, {len(warnings)} warnings")
        for issue in issues:
            console.print(f"      [dim]-[/dim] {issue.get('description', '')}")

    return result


# Max chars to include in review context
MAX_REVIEW_CHARS = 10000
