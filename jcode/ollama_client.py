"""
Ollama client wrapper — talks to the local Ollama server.
Supports all 4 roles: planner, coder, reviewer, analyzer.
"""

from __future__ import annotations

import ollama
from rich.console import Console

from jcode.config import (
    PLANNER_MODEL, CODER_MODEL, REVIEWER_MODEL, ANALYZER_MODEL,
    PLANNER_OPTIONS, CODER_OPTIONS, REVIEWER_OPTIONS, ANALYZER_OPTIONS,
)

console = Console()

# Cache of models we've already verified exist
_verified_models: set[str] = set()


def _ensure_model(model: str) -> None:
    """Pull the model if it isn't already downloaded."""
    if model in _verified_models:
        return
    try:
        ollama.show(model)
        _verified_models.add(model)
    except ollama.ResponseError:
        console.print(f"[yellow]Model [bold]{model}[/bold] not found locally. Pulling…[/yellow]")
        progress = console.status(f"[cyan]Downloading {model}…[/cyan]")
        progress.start()
        ollama.pull(model)
        progress.stop()
        console.print(f"[green]✓ Model {model} ready.[/green]")
        _verified_models.add(model)


def check_ollama_running() -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        ollama.list()
        return True
    except Exception:
        return False


# ── Unified generation function ────────────────────────────────────

def call_model(
    role: str,
    messages: list[dict[str, str]],
    stream: bool = True,
    num_ctx: int | None = None,
) -> str:
    """
    Send messages to the appropriate model based on role.

    Args:
        role: One of 'planner', 'coder', 'reviewer', 'analyzer'.
        messages: Chat messages.
        stream: Whether to stream output to console.
        num_ctx: Override context window size.
    """
    model_map = {
        "planner": (PLANNER_MODEL, PLANNER_OPTIONS),
        "coder": (CODER_MODEL, CODER_OPTIONS),
        "reviewer": (REVIEWER_MODEL, REVIEWER_OPTIONS),
        "analyzer": (ANALYZER_MODEL, ANALYZER_OPTIONS),
    }

    model, base_options = model_map[role]
    _ensure_model(model)

    options = base_options.copy()
    if num_ctx:
        options["num_ctx"] = num_ctx

    if stream:
        return _stream(model, messages, options)
    else:
        resp = ollama.chat(
            model=model,
            messages=messages,
            options=options,
        )
        return resp["message"]["content"]


# Legacy convenience wrappers (used by existing callers)

def call_planner(messages, stream=True, num_ctx=None) -> str:
    return call_model("planner", messages, stream, num_ctx)

def call_coder(messages, stream=True, num_ctx=None) -> str:
    return call_model("coder", messages, stream, num_ctx)

def call_reviewer(messages, stream=True, num_ctx=None) -> str:
    return call_model("reviewer", messages, stream, num_ctx)

def call_analyzer(messages, stream=True, num_ctx=None) -> str:
    return call_model("analyzer", messages, stream, num_ctx)


def _stream(model: str, messages: list[dict], options: dict) -> str:
    """Stream tokens to the console and return the full text."""
    chunks: list[str] = []
    for chunk in ollama.chat(
        model=model,
        messages=messages,
        options=options,
        stream=True,
    ):
        token = chunk["message"]["content"]
        chunks.append(token)
        console.print(token, end="", highlight=False)
    console.print()  # newline after stream
    return "".join(chunks)
