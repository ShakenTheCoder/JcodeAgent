"""
Ollama client wrapper — talks to the local Ollama server.

v3.1 — Speed-first. NEVER pulls models. Handles timeouts gracefully.

Key rules:
  1. Only use locally installed models
  2. If a model isn't available, fall back to what IS available
  3. Never block a build with a model download
  4. Handle Ollama being busy (concurrent JCode instances) gracefully
  5. Filter <think> blocks from reasoning models during streaming
"""

from __future__ import annotations

import re
import threading

import ollama
from rich.console import Console

from jcode.config import (
    PLANNER_MODEL, CODER_MODEL, REVIEWER_MODEL, ANALYZER_MODEL,
    PLANNER_OPTIONS, CODER_OPTIONS, REVIEWER_OPTIONS, ANALYZER_OPTIONS,
    get_model_for_role, get_all_required_models, _is_model_local,
)

console = Console()

# Cache of models we've already verified exist (thread-safe)
_verified_models: set[str] = set()
_verified_lock = threading.Lock()

# Lock for streaming output (only one stream at a time to console)
_stream_lock = threading.Lock()


def _ensure_model(model: str) -> None:
    """Check that the model is available. NEVER pulls — warns and falls back instead."""
    with _verified_lock:
        if model in _verified_models:
            return

    # Check if available locally
    try:
        ollama.show(model)
        with _verified_lock:
            _verified_models.add(model)
        return
    except ollama.ResponseError:
        pass

    # Model not available — warn but don't pull
    console.print(f"[yellow]⚠ Model {model} not installed. Using fallback.[/yellow]")
    with _verified_lock:
        _verified_models.add(model)  # Don't keep checking


def ensure_models_for_complexity(complexity: str) -> None:
    """Verify all models needed for a complexity level are available.
    Reports missing models but NEVER pulls them during builds."""
    models = get_all_required_models(complexity)
    missing = []
    for model in models:
        if not _is_model_local(model):
            missing.append(model)
    if missing:
        console.print(f"[yellow]⚠ Missing models: {', '.join(missing)}. Using available models.[/yellow]")
        console.print(f"[dim]  Install with: ollama pull {' && ollama pull '.join(missing)}[/dim]")


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

    try:
        if stream:
            return _stream(model, messages, options)
        else:
            return _generate_silent(model, messages, options)
    except Exception as e:
        err_str = str(e).lower()
        if "busy" in err_str or "timeout" in err_str or "connection" in err_str:
            console.print(f"\n[yellow]⚠ Ollama is busy (another instance running?). Retrying...[/yellow]")
            import time
            time.sleep(3)
            try:
                if stream:
                    return _stream(model, messages, options)
                else:
                    return _generate_silent(model, messages, options)
            except Exception as retry_err:
                console.print(f"\n[red]✗ Ollama error: {retry_err}[/red]")
                console.print("[dim]  Is another JCode instance running? Only one can generate at a time.[/dim]")
                return ""
        raise


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
    text = resp["message"]["content"]
    # Strip <think> blocks from reasoning models
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return text


def _stream(model: str, messages: list[dict], options: dict) -> str:
    """Stream tokens to the console and return the full text.
    Filters out <think>...</think> blocks from reasoning models.
    Uses a lock so parallel streams don't interleave."""
    chunks: list[str] = []
    in_think = False

    with _stream_lock:
        for chunk in ollama.chat(
            model=model,
            messages=messages,
            options=options,
            stream=True,
        ):
            token = chunk["message"]["content"]
            chunks.append(token)

            # Filter <think> blocks — don't show them to the user
            if "<think>" in token:
                in_think = True
                continue
            if "</think>" in token:
                in_think = False
                continue
            if in_think:
                continue

            console.print(token, end="", highlight=False)
        console.print()  # newline after stream

    full_text = "".join(chunks)
    # Also strip any complete <think> blocks from the final text
    full_text = re.sub(r"<think>.*?</think>", "", full_text, flags=re.DOTALL).strip()
    return full_text
