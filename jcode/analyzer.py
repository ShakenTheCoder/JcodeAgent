"""
Analyzer module — parses errors/stack traces into actionable fixes.

Instead of blindly feeding raw errors back to the coder,
the analyzer distills them into precise fix instructions.
"""

from __future__ import annotations

import json
import re

from rich.console import Console

from jcode.ollama_client import call_analyzer
from jcode.prompts import ANALYZER_SYSTEM, ANALYZER_TASK
from jcode.context import ContextManager

console = Console()


def _extract_json(text: str) -> dict:
    """Extract JSON from analyzer output."""
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

    return {
        "root_cause": "Could not parse analysis",
        "affected_file": "",
        "affected_function": None,
        "fix_strategy": text[:500],
        "is_dependency_issue": False,
        "severity": "warning",
    }


def analyze_error(
    file_path: str,
    error_output: str,
    ctx: ContextManager,
) -> dict:
    """
    Analyze an error and return a structured diagnosis.

    Returns:
        {
            "root_cause": str,
            "affected_file": str,
            "affected_function": str | None,
            "fix_strategy": str,
            "is_dependency_issue": bool,
            "severity": "critical" | "warning" | "info"
        }
    """
    file_content = ctx.state.files.get(file_path, "")
    previous_fixes = ctx.get_failure_log_str(file_path)

    ctx.reset_channel("analyzer")
    ctx.add_message("analyzer", "system", ANALYZER_SYSTEM)

    prompt = ANALYZER_TASK.format(
        architecture=ctx.get_architecture(),
        error_output=error_output[-2000:],  # Last 2k chars of error
        file_path=file_path,
        file_content=file_content[:8000],
        previous_fixes=previous_fixes,
    )
    ctx.add_message("analyzer", "user", prompt)

    console.print(f"  [dim]Analyzing error in[/dim] [cyan]{file_path}[/cyan]")

    planner_ctx, _ = ctx.get_context_sizes()
    complexity = ctx.get_complexity()
    size = ctx.get_size()
    raw = call_analyzer(
        ctx.get_messages("analyzer"),
        stream=False,  # Analysis doesn't need streaming
        num_ctx=planner_ctx,
        complexity=complexity,
        size=size,
    )

    result = _extract_json(raw)

    # Display analysis
    console.print(f"    [dim]Root cause:[/dim] {result.get('root_cause', 'Unknown')}")
    console.print(f"    [dim]Fix:[/dim] {result.get('fix_strategy', '')}")

    return result
