"""
Planner module — uses the reasoning model to understand requests,
design project structure, and create execution plans as a DAG.
"""

from __future__ import annotations

import json
import re

from rich.console import Console

from jcode.ollama_client import call_planner
from jcode.prompts import PLANNER_SYSTEM, PLANNER_REFINE
from jcode.context import ContextManager

console = Console()


def _extract_json(text: str) -> dict:
    """
    Extract the first JSON object from model output.
    Handles markdown fences and DeepSeek-R1 think tags.
    """
    # Strip <think>...</think> blocks from DeepSeek-R1
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Try code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Find first { … } block
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
    raise ValueError("No valid JSON object found in model output.")


def create_plan(user_prompt: str, ctx: ContextManager) -> dict:
    """
    Ask the planner to produce a project plan from a user prompt.
    Returns the parsed plan dict and initializes the task DAG.
    """
    ctx.add_planner_message("system", PLANNER_SYSTEM)
    ctx.add_planner_message("user", user_prompt)

    console.print("\n  [dim]Planning project architecture...[/dim]\n")

    raw = call_planner(ctx.get_planner_messages(), stream=True)
    ctx.add_planner_message("assistant", raw)

    plan = _extract_json(raw)
    ctx.set_plan(plan)

    planner_ctx, coder_ctx = ctx.get_context_sizes()
    console.print(
        f"\n[dim]Complexity: [bold]{ctx.get_complexity()}[/bold] "
        f"│ Planner ctx: {planner_ctx:,} │ Coder ctx: {coder_ctx:,}[/dim]"
    )

    return plan


def refine_plan(ctx: ContextManager) -> dict:
    """
    Ask the planner to revise its plan based on accumulated errors.
    """
    errors_text = "\n".join(f"- {e}" for e in ctx.state.errors)
    failure_log = ctx.get_failure_log_str()
    architecture = ctx.get_architecture()

    prompt = PLANNER_REFINE.format(
        errors=errors_text,
        failure_log=failure_log,
        architecture=architecture,
    )
    ctx.add_planner_message("user", prompt)

    console.print("\n  [dim]Revising plan based on errors...[/dim]\n")

    planner_ctx, _ = ctx.get_context_sizes()
    raw = call_planner(ctx.get_planner_messages(), stream=True, num_ctx=planner_ctx)
    ctx.add_planner_message("assistant", raw)

    plan = _extract_json(raw)
    ctx.set_plan(plan)
    ctx.clear_errors()
    return plan
