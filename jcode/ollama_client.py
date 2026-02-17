"""
Ollama client wrapper — talks to the local Ollama server.

v4.0 — Multi-model intelligent routing.

Key rules:
  1. Only use locally installed models — NEVER pull.
  2. Route each role to the best available model via config.get_model_for_role().
  3. Handle reasoning models (deepseek-r1, qwen3 /think) — filter <think> blocks.
  4. Handle Ollama being busy (concurrent instances) with retry logic.
  5. Thread-safe parallel generation for wave-based execution.
  6. Model-aware options (reasoning models get higher ctx, different temps).
"""

from __future__ import annotations

import re
import threading

import ollama
from rich.console import Console

from jcode.config import (
    PLANNER_MODEL, CODER_MODEL, REVIEWER_MODEL, ANALYZER_MODEL,
    PLANNER_OPTIONS, CODER_OPTIONS, REVIEWER_OPTIONS, ANALYZER_OPTIONS,
    REASONING_OPTIONS, AGENTIC_OPTIONS,
    get_model_for_role, get_all_required_models, _is_model_local,
    get_model_spec,
)

console = Console()

# Cache of models we've already verified exist (thread-safe)
_verified_models: set[str] = set()
_verified_lock = threading.Lock()

# Lock for streaming output (only one stream at a time to console)
_stream_lock = threading.Lock()


def _ensure_model(model: str) -> None:
    """Check that the model is available. NEVER pulls — warns and falls back."""
    with _verified_lock:
        if model in _verified_models:
            return

    try:
        ollama.show(model)
        with _verified_lock:
            _verified_models.add(model)
        return
    except ollama.ResponseError:
        pass

    console.print(f"[yellow]⚠ Model {model} not installed. Using fallback.[/yellow]")
    with _verified_lock:
        _verified_models.add(model)


def _is_reasoning_model(model: str) -> bool:
    """Check if a model is a reasoning model (produces <think> blocks)."""
    spec = get_model_spec(model)
    if spec and spec.supports_thinking:
        return True
    # Heuristic fallback for models not in registry
    lower = model.lower()
    return any(kw in lower for kw in ("deepseek-r1", "qwen3", "magistral", "phi4-reasoning", "glm-4"))


def _get_options_for_model(
    model: str,
    role: str,
    base_options: dict,
    num_ctx_override: int | None = None,
) -> dict:
    """Get generation options tuned for the specific model being used.

    Reasoning models get different temperatures and larger context.
    Agentic models get agentic options.
    """
    spec = get_model_spec(model)

    # Start with role-specific base
    options = base_options.copy()

    # Override with model-category-specific settings
    if spec:
        if spec.category == "reasoning":
            # Reasoning models need higher temp for exploration, bigger context
            options["temperature"] = max(options.get("temperature", 0.3), 0.35)
            options["num_ctx"] = max(options.get("num_ctx", 8192), REASONING_OPTIONS["num_ctx"])
        elif spec.category == "agentic":
            options["num_ctx"] = max(options.get("num_ctx", 8192), AGENTIC_OPTIONS["num_ctx"])
    elif _is_reasoning_model(model):
        # Fallback for unregistered reasoning models
        options["num_ctx"] = max(options.get("num_ctx", 8192), 16384)

    if num_ctx_override:
        options["num_ctx"] = num_ctx_override

    return options


def ensure_models_for_complexity(
    complexity: str,
    size: str = "medium",
) -> None:
    """Verify all models needed for a classification are available.
    Reports missing but NEVER pulls during builds."""
    models = get_all_required_models(complexity, size)
    if not models:
        console.print("[yellow]⚠ No models found for this classification. Install models with: ollama pull <model>[/yellow]")


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
        models = response.get("models", []) if isinstance(response, dict) else []
        if not models and hasattr(response, "models"):
            models = response.models or []
        return [
            (m.get("name", "") if isinstance(m, dict) else getattr(m, "model", ""))
            for m in models
        ]
    except Exception:
        return []


# ── Unified generation function ────────────────────────────────────

def call_model(
    role: str,
    messages: list[dict[str, str]],
    stream: bool = True,
    num_ctx: int | None = None,
    complexity: str = "medium",
    size: str = "medium",
    model_override: str | None = None,
) -> str:
    """
    Send messages to the best available model for role + classification.

    Args:
        role: One of 'planner', 'coder', 'reviewer', 'analyzer', 'chat'.
        messages: Chat messages.
        stream: Whether to stream output to console.
        num_ctx: Override context window size.
        complexity: Task complexity for model routing.
        size: Task size for model routing.
        model_override: Force a specific model (bypasses routing).
    """
    # Resolve model
    if model_override:
        model = model_override
    else:
        model = get_model_for_role(role, complexity, size)

    # Get role-specific base options
    options_map = {
        "planner": PLANNER_OPTIONS,
        "coder": CODER_OPTIONS,
        "reviewer": REVIEWER_OPTIONS,
        "analyzer": ANALYZER_OPTIONS,
        "chat": CODER_OPTIONS,       # Chat uses coder defaults
    }
    base_options = options_map.get(role, CODER_OPTIONS)

    _ensure_model(model)

    # Build final options (model-aware)
    options = _get_options_for_model(model, role, base_options, num_ctx)

    try:
        if stream:
            return _stream(model, messages, options)
        else:
            return _generate_silent(model, messages, options)
    except Exception as e:
        err_str = str(e).lower()
        if "busy" in err_str or "timeout" in err_str or "connection" in err_str:
            console.print(f"\n[yellow]⚠ Ollama busy. Retrying in 3s...[/yellow]")
            import time
            time.sleep(3)
            try:
                if stream:
                    return _stream(model, messages, options)
                else:
                    return _generate_silent(model, messages, options)
            except Exception as retry_err:
                console.print(f"\n[red]✗ Ollama error: {retry_err}[/red]")
                console.print("[dim]  Is another JCode instance running?[/dim]")
                return ""
        raise


def call_model_silent(
    role: str,
    messages: list[dict[str, str]],
    num_ctx: int | None = None,
    complexity: str = "medium",
    size: str = "medium",
    model_override: str | None = None,
) -> str:
    """Thread-safe silent generation (no streaming). Used by parallel workers."""
    return call_model(
        role, messages, stream=False, num_ctx=num_ctx,
        complexity=complexity, size=size, model_override=model_override,
    )


# Legacy convenience wrappers (backward compat)

def call_planner(messages, stream=True, num_ctx=None, complexity="medium", size="medium") -> str:
    return call_model("planner", messages, stream, num_ctx, complexity, size)

def call_coder(messages, stream=True, num_ctx=None, complexity="medium", size="medium") -> str:
    return call_model("coder", messages, stream, num_ctx, complexity, size)

def call_reviewer(messages, stream=True, num_ctx=None, complexity="medium", size="medium") -> str:
    return call_model("reviewer", messages, stream, num_ctx, complexity, size)

def call_analyzer(messages, stream=True, num_ctx=None, complexity="medium", size="medium") -> str:
    return call_model("analyzer", messages, stream, num_ctx, complexity, size)


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
    is_reasoning = _is_reasoning_model(model)

    with _stream_lock:
        for chunk in ollama.chat(
            model=model,
            messages=messages,
            options=options,
            stream=True,
        ):
            token = chunk["message"]["content"]
            chunks.append(token)

            # Filter <think> blocks from reasoning models
            if is_reasoning:
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
