"""
Ollama client wrapper — talks to the local Ollama server.

v2.0 — Smart model tiering + thread-safe parallel generation.

Supports all 4 roles: planner, coder, reviewer, analyzer.
Dynamically selects model based on role + project complexity.
Thread-safe for parallel file generation via WorkerPool.
"""

from __future__ import annotations

import threading

import ollama
from rich.console import Console

from jcode.config import (
    PLANNER_MODEL, CODER_MODEL, REVIEWER_MODEL, ANALYZER_MODEL,
    PLANNER_OPTIONS, CODER_OPTIONS, REVIEWER_OPTIONS, ANALYZER_OPTIONS,
    get_model_for_role, get_all_required_models,
)

console = Console()

# Cache of models we've already verified exist (thread-safe)
_verified_models: set[str] = set()
_verified_lock = threading.Lock()

# Lock for streaming output (only one stream at a time to console)
_stream_lock = threading.Lock()


def _ensure_model(model: str) -> None:
    """Pull the model if it isn't already downloaded. Thread-safe."""
    with _verified_lock:
        if model in _verified_models:
            return

    # Check outside the lock (network call)
    try:
        ollama.show(model)
        with _verified_lock:
            _verified_models.add(model)
        return
    except ollama.ResponseError:
        pass

    # Pull needed
    console.print(f"[yellow]Model [bold]{model}[/bold] not found locally. Pulling…[/yellow]")
    progress = console.status(f"[cyan]Downloading {model}…[/cyan]")
    progress.start()
    try:
        ollama.pull(model)
    finally:
        progress.stop()
    console.print(f"[green]Model {model} ready.[/green]")

    with _verified_lock:
        _verified_models.add(model)


def ensure_models_for_complexity(complexity: str) -> None:
    """Pre-pull all models required for a given complexity level."""
    models = get_all_required_models(complexity)
    for model in models:
        _ensure_model(model)


def check_ollama_running() -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        ollama.list()
        return True
    except Exception:
        return False


def list_available_models() -> list[str]:
    """Return a list of model names available locally."""
    try:
        response = ollama.list()
        return [m.get("name", "") for m in response.get("models", [])]
    except Exception:
        return []


# ── Unified generation function ────────────────────────────────────

def call_model(
    role: str,
    messages: list[dict[str, str]],
    stream: bool = True,
    num_ctx: int | None = None,
    complexity: str = "medium",
) -> str:
    """
    Send messages to the appropriate model based on role + complexity.

    Args:
        role: One of 'planner', 'coder', 'reviewer', 'analyzer'.
        messages: Chat messages.
        stream: Whether to stream output to console.
        num_ctx: Override context window size.
        complexity: Project complexity for model tier selection.
    """
    # Resolve model dynamically based on role + complexity
    model = get_model_for_role(role, complexity)

    options_map = {
        "planner": PLANNER_OPTIONS,
        "coder": CODER_OPTIONS,
        "reviewer": REVIEWER_OPTIONS,
        "analyzer": ANALYZER_OPTIONS,
    }

    base_options = options_map.get(role, CODER_OPTIONS)
    _ensure_model(model)

    options = base_options.copy()
    if num_ctx:
        options["num_ctx"] = num_ctx

    if stream:
        return _stream(model, messages, options)
    else:
        return _generate_silent(model, messages, options)


def call_model_silent(
    role: str,
    messages: list[dict[str, str]],
    num_ctx: int | None = None,
    complexity: str = "medium",
) -> str:
    """
    Thread-safe silent generation (no streaming). Used by parallel workers.
    """
    return call_model(role, messages, stream=False, num_ctx=num_ctx, complexity=complexity)


# Legacy convenience wrappers (used by existing callers)

def call_planner(messages, stream=True, num_ctx=None, complexity="medium") -> str:
    return call_model("planner", messages, stream, num_ctx, complexity)

def call_coder(messages, stream=True, num_ctx=None, complexity="medium") -> str:
    return call_model("coder", messages, stream, num_ctx, complexity)

def call_reviewer(messages, stream=True, num_ctx=None, complexity="medium") -> str:
    return call_model("reviewer", messages, stream, num_ctx, complexity)

def call_analyzer(messages, stream=True, num_ctx=None, complexity="medium") -> str:
    return call_model("analyzer", messages, stream, num_ctx, complexity)


def _generate_silent(model: str, messages: list[dict], options: dict) -> str:
    """Non-streaming generation. Thread-safe."""
    resp = ollama.chat(
        model=model,
        messages=messages,
        options=options,
    )
    return resp["message"]["content"]


def _stream(model: str, messages: list[dict], options: dict) -> str:
    """Stream tokens to the console and return the full text.
    Uses a lock so parallel streams don't interleave."""
    chunks: list[str] = []
    with _stream_lock:
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
