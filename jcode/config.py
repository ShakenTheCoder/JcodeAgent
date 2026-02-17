"""
JCode configuration — multi-model orchestration engine.

v0.9.0 — Intelligent multi-model routing.

Design philosophy:
  1. NEVER pull models during builds — only use what's locally installed.
  2. Different models for different jobs — the RIGHT model for each role.
  3. Task classification: complexity (heavy/medium/simple) × size (large/medium/small).
  4. Model categories: coding, reasoning, agentic, fast.
  5. For SIMPLE tasks → be FAST (small models, skip review).
  6. For HEAVY tasks → deep research, reasoning, multiple passes.
  7. Graceful fallback — always degrade to what's available locally.

Model Registry (2025/2026 Ollama ecosystem):
  ┌─────────────────────┬───────────┬─────────────────────────────────────┐
  │ Category            │ Role      │ Best Models (in preference order)   │
  ├─────────────────────┼───────────┼─────────────────────────────────────┤
  │ coding              │ coder     │ qwen3-coder, devstral, qwen2.5-c.  │
  │ reasoning           │ planner   │ deepseek-r1, qwen3, magistral      │
  │ agentic             │ orchestr. │ gpt-oss, qwen3, glm-4.7            │
  │ fast                │ reviewer  │ qwen2.5-coder:7b, glm-4.7-flash   │
  │ embedding           │ memory    │ all-minilm, nomic-embed-text       │
  │ summarizer          │ compress  │ phi4, gemma3:4b                    │
  └─────────────────────┴───────────┴─────────────────────────────────────┘
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum


# ═══════════════════════════════════════════════════════════════════
# Model Registry — multi-model, multi-category
# ═══════════════════════════════════════════════════════════════════
#
# Each model is registered with its category and size class.
# The router picks the best LOCAL model for each role + classification.

@dataclass(frozen=True)
class ModelSpec:
    """A model in the registry with its capabilities."""
    name: str               # e.g. "devstral:24b"
    category: str           # coding | reasoning | agentic | fast | general | embedding | summarizer
    size_class: str         # small (≤8b) | medium (9-20b) | large (21b+)
    priority: int = 50      # Lower = preferred (within same category+size)
    supports_tools: bool = False
    supports_thinking: bool = False
    context_window: int = 32768
    is_embedding: bool = False


# ── Full Model Registry ───────────────────────────────────────────
# Models are ordered by preference within each category.
# JCode will pick the FIRST locally-available model that fits.

MODEL_REGISTRY: list[ModelSpec] = [
    # ── CODING models (for file generation, patching) ──────────────
    # Prefer qwen3-coder (2026) > devstral > qwen2.5-coder > deepseek-coder
    ModelSpec("qwen3-coder:32b",      "coding",    "large",  5),
    ModelSpec("devstral:24b",          "coding",    "large",  10, supports_tools=True),
    ModelSpec("devstral-small:24b",    "coding",    "large",  15, supports_tools=True),
    ModelSpec("qwen2.5-coder:32b",    "coding",    "large",  20),
    ModelSpec("deepseek-coder:33b",    "coding",    "large",  25),
    ModelSpec("qwen3-coder:8b",       "coding",    "small",  5),
    ModelSpec("qwen2.5-coder:14b",    "coding",    "medium", 10),
    ModelSpec("deepcoder:14b",         "coding",    "medium", 15),
    ModelSpec("deepseek-coder:6.7b",   "coding",    "small",  12),
    ModelSpec("qwen2.5-coder:7b",     "coding",    "small",  10),

    # ── REASONING models (for planning, analysis, deep thinking) ───
    # DeepSeek-R1 is the strongest local reasoning model
    ModelSpec("deepseek-r1:70b",      "reasoning", "large",  5,  supports_thinking=True),
    ModelSpec("deepseek-r1:32b",      "reasoning", "large",  10, supports_thinking=True),
    ModelSpec("deepseek-r1:14b",      "reasoning", "medium", 10, supports_thinking=True),
    ModelSpec("magistral:24b",         "reasoning", "large",  15, supports_thinking=True),
    ModelSpec("phi4-reasoning:14b",    "reasoning", "medium", 20, supports_thinking=True),
    ModelSpec("qwen3:14b",            "reasoning", "medium", 25, supports_tools=True, supports_thinking=True),
    ModelSpec("qwen3:8b",             "reasoning", "small",  10, supports_tools=True, supports_thinking=True),
    ModelSpec("deepseek-r1:8b",       "reasoning", "small",  15, supports_thinking=True),
    ModelSpec("deepseek-r1:1.5b",     "reasoning", "small",  30, supports_thinking=True),

    # ── AGENTIC models (for autonomous orchestration, tool use) ────
    ModelSpec("gpt-oss:20b",          "agentic",   "medium", 10, supports_tools=True),
    ModelSpec("qwen3:14b",            "agentic",   "medium", 15, supports_tools=True, supports_thinking=True),
    ModelSpec("glm-4.7:30b",          "agentic",   "large",  15, supports_tools=True, supports_thinking=True),
    ModelSpec("qwen3:8b",             "agentic",   "small",  10, supports_tools=True, supports_thinking=True),

    # ── FAST models (for review, quick checks, simple tasks) ───────
    ModelSpec("glm-4.7-flash:30b",    "fast",      "large",  10, supports_tools=True, supports_thinking=True),
    ModelSpec("qwen2.5-coder:7b",     "fast",      "small",  10),
    ModelSpec("qwen3:4b",             "fast",      "small",  15, supports_tools=True),
    ModelSpec("qwen3:1.7b",           "fast",      "small",  25, supports_tools=True),

    # ── SUMMARIZER models (for memory compression, context summaries) ──
    ModelSpec("phi4:14b",             "summarizer", "medium", 10),
    ModelSpec("phi3.5:latest",        "summarizer", "small",  15),
    ModelSpec("gemma3:4b",            "summarizer", "small",  20),

    # ── EMBEDDING models (for vector memory / RAG retrieval) ───────
    ModelSpec("all-minilm:latest",    "embedding", "small",  10, is_embedding=True),
    ModelSpec("nomic-embed-text:latest", "embedding", "small", 15, is_embedding=True),

    # ── GENERAL models (fallback for any role) ─────────────────────
    ModelSpec("llama3.3:latest",      "general",   "small",  40),
    ModelSpec("llama3.1:latest",      "general",   "small",  45),
    ModelSpec("llama3:latest",        "general",   "small",  50),
    ModelSpec("qwen3:8b",             "general",   "small",  30, supports_tools=True, supports_thinking=True),
    ModelSpec("qwen3:14b",            "general",   "medium", 30, supports_tools=True, supports_thinking=True),
]


# ═══════════════════════════════════════════════════════════════════
# Task Classification — complexity × size
# ═══════════════════════════════════════════════════════════════════
#
# complexity: how HARD is the task (algorithmic depth, system design)
#   heavy  → databases, auth, microservices, real-time, complex logic
#   medium → typical web apps, CRUD, API integrations
#   simple → static sites, scripts, single-purpose tools
#
# size: how BIG is the output (number of files, total LOC)
#   large  → 15+ files, full-stack apps
#   medium → 5-15 files, standard apps
#   small  → 1-4 files, quick projects

class Complexity(str, Enum):
    HEAVY  = "heavy"
    MEDIUM = "medium"
    SIMPLE = "simple"

class Size(str, Enum):
    LARGE  = "large"
    MEDIUM = "medium"
    SMALL  = "small"

@dataclass
class TaskClassification:
    """The full classification of a task."""
    complexity: Complexity
    size: Size
    skip_review: bool = False
    skip_research: bool = True
    needs_reasoning: bool = False

    @property
    def label(self) -> str:
        return f"{self.complexity.value}/{self.size.value}"

    @property
    def is_simple(self) -> bool:
        return self.complexity == Complexity.SIMPLE and self.size == Size.SMALL

    @property
    def is_heavy(self) -> bool:
        return self.complexity == Complexity.HEAVY


# ═══════════════════════════════════════════════════════════════════
# Role → Category Mapping per Classification
# ═══════════════════════════════════════════════════════════════════
#
# This 9-cell matrix maps (complexity × size) → model category per role.
# The model router uses this to pick the right model.
#
#   Classification    │ Planner       │ Coder        │ Reviewer     │ Analyzer
#   ──────────────────┼───────────────┼──────────────┼──────────────┼──────────
#   simple/small      │ fast          │ coding/small │ (skipped)    │ fast
#   simple/medium     │ fast          │ coding/med   │ fast         │ fast
#   simple/large      │ coding/med    │ coding/med   │ fast         │ fast
#   ──────────────────┼───────────────┼──────────────┼──────────────┼──────────
#   medium/small      │ coding/med    │ coding/med   │ fast         │ coding/small
#   medium/medium     │ coding/med    │ coding/med   │ coding/small │ coding/small
#   medium/large      │ reasoning/med │ coding/large │ coding/small │ coding/med
#   ──────────────────┼───────────────┼──────────────┼──────────────┼──────────
#   heavy/small       │ reasoning/med │ coding/med   │ coding/small │ reasoning/small
#   heavy/medium      │ reasoning/med │ coding/large │ coding/med   │ reasoning/med
#   heavy/large       │ reasoning/lrg │ coding/large │ coding/med   │ reasoning/med

@dataclass(frozen=True)
class ModelRequirement:
    """What category + size to look for."""
    category: str           # coding | reasoning | agentic | fast | general
    size_class: str         # small | medium | large


ROLE_ROUTING: dict[str, dict[str, ModelRequirement]] = {
    # ── SIMPLE ─────────────────────────────────────────────────────
    "simple/small": {
        "planner":  ModelRequirement("fast",      "small"),
        "coder":    ModelRequirement("coding",    "small"),
        "reviewer": ModelRequirement("fast",      "small"),   # skipped anyway
        "analyzer": ModelRequirement("fast",      "small"),
    },
    "simple/medium": {
        "planner":  ModelRequirement("fast",      "small"),
        "coder":    ModelRequirement("coding",    "medium"),
        "reviewer": ModelRequirement("fast",      "small"),
        "analyzer": ModelRequirement("fast",      "small"),
    },
    "simple/large": {
        "planner":  ModelRequirement("coding",    "medium"),
        "coder":    ModelRequirement("coding",    "medium"),
        "reviewer": ModelRequirement("fast",      "small"),
        "analyzer": ModelRequirement("fast",      "small"),
    },
    # ── MEDIUM ─────────────────────────────────────────────────────
    "medium/small": {
        "planner":  ModelRequirement("coding",    "medium"),
        "coder":    ModelRequirement("coding",    "medium"),
        "reviewer": ModelRequirement("fast",      "small"),
        "analyzer": ModelRequirement("coding",    "small"),
    },
    "medium/medium": {
        "planner":  ModelRequirement("coding",    "medium"),
        "coder":    ModelRequirement("coding",    "medium"),
        "reviewer": ModelRequirement("coding",    "small"),
        "analyzer": ModelRequirement("coding",    "small"),
    },
    "medium/large": {
        "planner":  ModelRequirement("reasoning", "medium"),
        "coder":    ModelRequirement("coding",    "large"),
        "reviewer": ModelRequirement("coding",    "small"),
        "analyzer": ModelRequirement("coding",    "medium"),
    },
    # ── HEAVY ──────────────────────────────────────────────────────
    "heavy/small": {
        "planner":  ModelRequirement("reasoning", "medium"),
        "coder":    ModelRequirement("coding",    "medium"),
        "reviewer": ModelRequirement("coding",    "small"),
        "analyzer": ModelRequirement("reasoning", "small"),
    },
    "heavy/medium": {
        "planner":  ModelRequirement("reasoning", "medium"),
        "coder":    ModelRequirement("coding",    "large"),
        "reviewer": ModelRequirement("coding",    "medium"),
        "analyzer": ModelRequirement("reasoning", "medium"),
    },
    "heavy/large": {
        "planner":  ModelRequirement("reasoning", "large"),
        "coder":    ModelRequirement("coding",    "large"),
        "reviewer": ModelRequirement("coding",    "medium"),
        "analyzer": ModelRequirement("reasoning", "medium"),
    },
}


# ═══════════════════════════════════════════════════════════════════
# Model Resolution Engine
# ═══════════════════════════════════════════════════════════════════

# Locally installed models cache
_local_models: set[str] | None = None
_local_models_full: dict[str, dict] | None = None


def _get_local_models() -> set[str]:
    """Return the set of model names installed locally. Cached."""
    global _local_models
    if _local_models is not None:
        return _local_models
    try:
        import ollama as _ollama
        response = _ollama.list()
        models = response.get("models", []) if isinstance(response, dict) else []
        if not models and hasattr(response, "models"):
            models = response.models or []
        names = set()
        for m in models:
            name = m.get("name", "") if isinstance(m, dict) else getattr(m, "model", "")
            if name:
                # Normalize quantization suffixes
                base = name.split("-q")[0] if "-q" in name else name
                names.add(base)
                # Also add without :latest for matching
                if ":latest" in base:
                    names.add(base.replace(":latest", ""))
        _local_models = names
    except Exception:
        _local_models = set()
    return _local_models


def refresh_local_models() -> set[str]:
    """Force-refresh the local models cache."""
    global _local_models
    _local_models = None
    return _get_local_models()


def _is_model_local(model: str) -> bool:
    """Check if a model is installed locally."""
    local = _get_local_models()
    
    # Exact match (with or without :latest normalization)
    if model in local:
        return True
    
    # Normalize :latest — "model" and "model:latest" are the same
    model_normalized = model if ":" in model else f"{model}:latest"
    model_without_latest = model.replace(":latest", "") if model.endswith(":latest") else model
    
    if model_normalized in local or model_without_latest in local:
        return True
    
    return False


def _find_best_model(
    category: str,
    size_class: str,
) -> str | None:
    """Find the best locally-available model matching category + size.

    Search strategy:
    1. Exact category + exact size → best priority
    2. Exact category + any size (prefer larger) → fallback
    3. Any category that can do the job → last resort
    """
    local = _get_local_models()

    # Phase 1: Exact match
    candidates = [
        spec for spec in MODEL_REGISTRY
        if spec.category == category
        and spec.size_class == size_class
        and _is_model_local(spec.name)
    ]
    if candidates:
        return min(candidates, key=lambda s: s.priority).name

    # Phase 2: Same category, any size (prefer ≥ requested size)
    size_order = {"small": 0, "medium": 1, "large": 2}
    req_size = size_order.get(size_class, 1)

    candidates = [
        spec for spec in MODEL_REGISTRY
        if spec.category == category
        and _is_model_local(spec.name)
    ]
    if candidates:
        # Prefer models >= requested size, then by priority
        candidates.sort(key=lambda s: (
            0 if size_order.get(s.size_class, 1) >= req_size else 1,
            s.priority,
        ))
        return candidates[0].name

    # Phase 3: Cross-category fallback
    # coding/reasoning/agentic can substitute for each other in a pinch
    fallback_map = {
        "coding":    ["coding", "general", "agentic", "fast"],
        "reasoning": ["reasoning", "coding", "general", "agentic"],
        "agentic":   ["agentic", "reasoning", "coding", "general"],
        "fast":      ["fast", "coding", "general"],
        "general":   ["general", "coding", "fast"],
    }
    for alt_cat in fallback_map.get(category, ["general"]):
        if alt_cat == category:
            continue
        candidates = [
            spec for spec in MODEL_REGISTRY
            if spec.category == alt_cat
            and _is_model_local(spec.name)
        ]
        if candidates:
            return min(candidates, key=lambda s: s.priority).name

    return None


def get_model_for_role(
    role: str,
    complexity: str = "medium",
    size: str = "medium",
) -> str:
    """Resolve the best locally-available model for a role + classification.

    This is the main entry point for the model routing system.
    Falls back gracefully — always returns SOMETHING.
    """
    classification_key = f"{complexity}/{size}"
    routing = ROLE_ROUTING.get(classification_key, ROLE_ROUTING["medium/medium"])
    req = routing.get(role, ModelRequirement("coding", "medium"))

    model = _find_best_model(req.category, req.size_class)
    if model:
        return model

    # Absolute last resort: return first available model
    local = _get_local_models()
    if local:
        return next(iter(local))

    # Nothing installed — return a common default (will fail gracefully)
    return "qwen2.5-coder:7b"


def get_escalation_model(role: str) -> str | None:
    """Get a stronger model for escalation when fixes fail.

    For analyzer/planner: prefer reasoning models (deep thinking).
    For coder: prefer large coding models.
    """
    if role in ("analyzer", "planner"):
        # Try reasoning models first (large → medium)
        for size in ("large", "medium"):
            model = _find_best_model("reasoning", size)
            if model:
                return model
        # Then large coding
        model = _find_best_model("coding", "large")
        if model:
            return model
    else:
        # For coder/reviewer: try large coding first
        model = _find_best_model("coding", "large")
        if model:
            return model
        # Then reasoning
        model = _find_best_model("reasoning", "large")
        if model:
            return model

    return None


def get_all_required_models(
    complexity: str = "medium",
    size: str = "medium",
) -> list[str]:
    """Return the unique set of models needed for a classification.
    Only returns models that are locally installed."""
    classification_key = f"{complexity}/{size}"
    routing = ROLE_ROUTING.get(classification_key, ROLE_ROUTING["medium/medium"])
    models = set()
    for role, req in routing.items():
        model = _find_best_model(req.category, req.size_class)
        if model:
            models.add(model)
    return sorted(models)


def get_model_spec(model_name: str) -> ModelSpec | None:
    """Look up the spec for a model by name."""
    for spec in MODEL_REGISTRY:
        if spec.name == model_name:
            return spec
    return None


def describe_model_plan(
    complexity: str = "medium",
    size: str = "medium",
) -> dict[str, str]:
    """Return a role → model name mapping for display purposes."""
    result = {}
    for role in ("planner", "coder", "reviewer", "analyzer"):
        model = get_model_for_role(role, complexity, size)
        result[role] = model
    return result


def get_embedding_model() -> str | None:
    """Return the best locally-available embedding model, or None."""
    for spec in MODEL_REGISTRY:
        if spec.is_embedding and _is_model_local(spec.name):
            return spec.name
    return None


def get_summarizer_model() -> str | None:
    """Return the best locally-available summarizer model for memory compression."""
    model = _find_best_model("summarizer", "small")
    if model:
        return model
    model = _find_best_model("summarizer", "medium")
    if model:
        return model
    # Fallback: fast coding model can summarize too
    return _find_best_model("fast", "small")


# ── Legacy constants (backward compat — resolved dynamically) ─────
PLANNER_MODEL = "qwen2.5-coder:14b"
CODER_MODEL = "qwen2.5-coder:14b"
REVIEWER_MODEL = "qwen2.5-coder:7b"
ANALYZER_MODEL = "qwen2.5-coder:14b"


# ── Generation Parameters ──────────────────────────────────────────
BASE_PLANNER_CTX = 8192
BASE_CODER_CTX = 8192

PLANNER_OPTIONS = {
    "temperature": 0.3,       # Low temp → reliable JSON output
    "top_p": 0.9,
    "num_ctx": BASE_PLANNER_CTX,
}

CODER_OPTIONS = {
    "temperature": 0.15,      # Very low → deterministic code
    "top_p": 0.95,
    "num_ctx": BASE_CODER_CTX,
}

REVIEWER_OPTIONS = {
    "temperature": 0.3,
    "top_p": 0.9,
    "num_ctx": 4096,
}

ANALYZER_OPTIONS = {
    "temperature": 0.2,
    "top_p": 0.9,
    "num_ctx": 4096,
}

# Special options for reasoning models (allow longer output for thinking)
REASONING_OPTIONS = {
    "temperature": 0.4,
    "top_p": 0.95,
    "num_ctx": 16384,
}

# Special options for agentic models
AGENTIC_OPTIONS = {
    "temperature": 0.3,
    "top_p": 0.9,
    "num_ctx": 16384,
}

# Context window scaling by classification
COMPLEXITY_SCALING = {
    "simple": 1.0,      # 8k
    "medium": 1.5,      # 12k
    "heavy":  2.5,       # 20k
}

SIZE_SCALING = {
    "small":  1.0,
    "medium": 1.5,
    "large":  2.5,
}

# ── Worker Pool Settings ───────────────────────────────────────────
MAX_WORKERS = 4
MIN_WORKERS = 1
CPU_HIGH_THRESHOLD = 85.0
CPU_LOW_THRESHOLD = 50.0
WORKER_POLL_INTERVAL = 2.0

# ── Limits ─────────────────────────────────────────────────────────
MAX_ITERATIONS = 10
MAX_FILE_READ_CHARS = 12000
MAX_TASK_FAILURES = 5
MAX_DIFF_LINES = 80

# ── Project Defaults ───────────────────────────────────────────────
DEFAULT_OUTPUT_DIR = Path.cwd()


# ═══════════════════════════════════════════════════════════════════
# Task State Machine (unchanged from v0.8.x)
# ═══════════════════════════════════════════════════════════════════

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    GENERATED = "generated"
    REVIEWING = "reviewing"
    NEEDS_FIX = "needs_fix"
    VERIFIED = "verified"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskNode:
    """A single task in the DAG."""
    id: int
    file: str
    description: str
    depends_on: list[int] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    failure_count: int = 0
    review_feedback: str = ""
    error_summary: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.VERIFIED, TaskStatus.FAILED, TaskStatus.SKIPPED)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "description": self.description,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "failure_count": self.failure_count,
            "review_feedback": self.review_feedback,
            "error_summary": self.error_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskNode":
        return cls(
            id=d["id"],
            file=d["file"],
            description=d["description"],
            depends_on=d.get("depends_on", []),
            status=TaskStatus(d.get("status", "pending")),
            failure_count=d.get("failure_count", 0),
            review_feedback=d.get("review_feedback", ""),
            error_summary=d.get("error_summary", ""),
        )


@dataclass
class ProjectState:
    """Full project state with structured memory."""
    name: str = ""
    description: str = ""
    tech_stack: list[str] = field(default_factory=list)
    output_dir: Path = DEFAULT_OUTPUT_DIR
    plan: dict | None = None
    files: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    iteration: int = 0
    completed: bool = False
    complexity: str = "medium"
    size: str = "medium"
    created_at: str = ""
    last_modified: str = ""

    # ── Structured Memory ──────────────────────────────────────────
    architecture_summary: str = ""
    file_index: dict[str, str] = field(default_factory=dict)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    failure_log: list[dict] = field(default_factory=list)

    # ── Task DAG ───────────────────────────────────────────────────
    task_nodes: list[dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# Task Classification Engine
# ═══════════════════════════════════════════════════════════════════

# Keyword signals for complexity detection
_HEAVY_SIGNALS = [
    "database", "postgres", "mongo", "mysql", "redis", "sqlite", "supabase",
    "auth", "jwt", "oauth", "login", "signup", "session", "password",
    "docker", "ci/cd", "deploy", "kubernetes", "microservice", "k8s",
    "graphql", "grpc", "websocket", "real-time", "streaming",
    "machine learning", "neural", "tensorflow", "pytorch", "ai model",
    "payment", "stripe", "billing", "subscription",
    "multi-tenant", "rbac", "permission", "role-based",
    # App-type signals — short prompts that imply complex full-stack apps
    "like tinder", "like uber", "like airbnb", "like twitter", "like instagram",
    "like spotify", "like slack", "like discord", "like shopify", "like amazon",
    "like linkedin", "like facebook", "like reddit", "like youtube", "like tiktok",
    "like whatsapp", "like netflix", "like doordash", "like lyft",
    "tinder for", "uber for", "airbnb for", "twitter for", "instagram for",
    "spotify for", "slack for", "discord for", "shopify for",
    "a tinder", "an uber", "an airbnb", "a twitter", "an instagram",
    "a spotify", "a slack", "a discord", "a shopify",
    # Domain signals — imply complex architecture
    "social network", "social media", "marketplace", "e-commerce", "ecommerce",
    "dating app", "matching system", "recommendation engine",
    "real-time chat", "messaging app", "live stream",
    "booking system", "reservation", "scheduling platform",
    "fintech", "banking", "trading platform", "crypto",
    "saas", "multi-user", "collaboration tool",
]

_MEDIUM_SIGNALS = [
    "api", "rest", "crud", "backend", "server", "endpoint",
    "react", "next", "vue", "angular", "svelte", "frontend",
    "full-stack", "fullstack", "backend and frontend",
    "dashboard", "admin panel", "cms",
    "upload", "file system", "storage",
    "email", "notification", "queue",
    "testing", "test suite", "e2e",
    # Domain signals — imply moderate complexity
    "web app", "webapp", "mobile app", "desktop app",
    "portfolio", "blog with", "forum", "wiki",
    "game", "multiplayer", "leaderboard",
    "search", "filter", "pagination",
    "profile", "user profile", "account",
    "analytics", "tracking", "metrics",
]

_SIMPLE_SIGNALS = [
    "simple", "basic", "minimal", "small", "quick", "tiny",
    "hello world", "calculator", "todo", "counter", "timer",
    "landing page", "static", "single page",
    "script", "utility", "tool", "cli tool",
]


def classify_task(prompt: str | None = None, plan: dict | None = None) -> TaskClassification:
    """Classify a task by complexity and size.

    Can be called with a string prompt (pre-plan) or a dict plan (post-plan).
    Returns a TaskClassification with all routing decisions.
    """
    if plan:
        return _classify_from_plan(plan)
    if prompt:
        return _classify_from_prompt(prompt)
    return TaskClassification(Complexity.SIMPLE, Size.SMALL, skip_review=True, skip_research=True)


# ── LLM-based pre-classification ──────────────────────────────────

_CLASSIFY_PROMPT = """\
You are a task classifier for a coding agent. Given a user's build request, \
classify the task's COMPLEXITY and SIZE.

COMPLEXITY:
- simple: trivial scripts, hello world, calculators, static pages, single-file utilities
- medium: CRUD apps, REST APIs, dashboards, single-framework frontends, CLI tools with multiple commands
- heavy: full-stack apps with auth/database/real-time, social networks, marketplaces, \
apps that clone major platforms (tinder, uber, airbnb, etc.), microservices, ML pipelines

SIZE:
- small: 1-4 files, can be done quickly
- medium: 5-14 files, moderate scope
- large: 15+ files, extensive scope

IMPORTANT: When someone says "build a tinder for X" or "build an uber for Y", \
that implies a FULL application with matching/swiping/profiles/auth/database — \
that is ALWAYS heavy/large.

Respond with ONLY a JSON object, no other text:
{"complexity": "simple|medium|heavy", "size": "small|medium|large"}
"""


def _llm_classify(prompt: str) -> tuple[Complexity, Size] | None:
    """Use the fastest available model to classify task complexity.

    Returns (Complexity, Size) or None if LLM classification fails/unavailable.
    This adds ~1-3s but prevents catastrophic misclassification of short prompts
    like "build a tinder for linkedin" → simple/small.
    """
    try:
        # Use the fastest available model for classification
        model = _find_best_model("fast", "small")
        if not model:
            model = _find_best_model("coding", "small")
        if not model:
            # Try any available model
            local = _get_local_models()
            if local:
                model = next(iter(local))
            else:
                return None

        import ollama as _ollama
        resp = _ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": _CLASSIFY_PROMPT},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.0, "num_ctx": 1024, "num_predict": 80},
        )
        text = resp["message"]["content"].strip()

        # Strip <think> blocks from reasoning models
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Extract JSON from response (model might wrap in ```json ... ```)
        json_match = re.search(r'\{[^}]+\}', text)
        if not json_match:
            return None
        data = json.loads(json_match.group())

        complexity_str = data.get("complexity", "").lower()
        size_str = data.get("size", "").lower()

        complexity_map = {"simple": Complexity.SIMPLE, "medium": Complexity.MEDIUM, "heavy": Complexity.HEAVY}
        size_map = {"small": Size.SMALL, "medium": Size.MEDIUM, "large": Size.LARGE}

        c = complexity_map.get(complexity_str)
        s = size_map.get(size_str)
        if c and s:
            return (c, s)
        return None
    except Exception:
        return None


def _classify_from_prompt(prompt: str) -> TaskClassification:
    """Classify from user prompt (before planning).

    Uses a 2-phase approach:
    1. LLM reasoning (fast model) — understands semantic meaning
    2. Keyword scoring — validates and can override LLM
    Falls back to keyword-only if LLM unavailable.
    """
    lower = prompt.lower()
    heavy_score = sum(1 for kw in _HEAVY_SIGNALS if kw in lower)
    medium_score = sum(1 for kw in _MEDIUM_SIGNALS if kw in lower)
    simple_score = sum(1 for kw in _SIMPLE_SIGNALS if kw in lower)

    # Phase 1: Try LLM classification (semantic understanding)
    llm_result = _llm_classify(prompt)

    # Phase 2: Keyword scoring + LLM fusion
    if llm_result:
        llm_complexity, llm_size = llm_result

        # If keywords strongly disagree with LLM, use the HIGHER classification
        # (err on the side of giving the task more resources)
        if heavy_score >= 2 or (heavy_score >= 1 and medium_score >= 2):
            kw_complexity = Complexity.HEAVY
        elif medium_score >= 2 or heavy_score >= 1:
            kw_complexity = Complexity.MEDIUM
        elif simple_score > 0 and heavy_score == 0 and medium_score == 0:
            kw_complexity = Complexity.SIMPLE
        else:
            kw_complexity = None  # No keyword opinion

        # Take the higher of LLM vs keyword complexity
        complexity_order = {Complexity.SIMPLE: 0, Complexity.MEDIUM: 1, Complexity.HEAVY: 2}
        if kw_complexity is not None:
            complexity = max(llm_complexity, kw_complexity, key=lambda c: complexity_order[c])
        else:
            complexity = llm_complexity

        size = llm_size
    else:
        # LLM unavailable — pure keyword scoring (improved defaults)
        if heavy_score >= 2 or (heavy_score >= 1 and medium_score >= 2):
            complexity = Complexity.HEAVY
        elif medium_score >= 2 or heavy_score >= 1:
            complexity = Complexity.MEDIUM
        elif simple_score > 0 and heavy_score == 0 and medium_score == 0:
            complexity = Complexity.SIMPLE
        else:
            # Default: MEDIUM (not SIMPLE) — err on the side of caution
            # Only classify as SIMPLE when explicit simple signals are present
            complexity = Complexity.MEDIUM

        # Estimate size from prompt (rough — will be refined after planning)
        word_count = len(prompt.split())
        if word_count > 80 or "full" in lower or "complete" in lower or "entire" in lower:
            size = Size.LARGE
        elif word_count > 30 or complexity == Complexity.HEAVY:
            size = Size.MEDIUM
        else:
            # Default to MEDIUM for ambiguous prompts (not SMALL)
            size = Size.MEDIUM if complexity != Complexity.SIMPLE else Size.SMALL

    return TaskClassification(
        complexity=complexity,
        size=size,
        skip_review=(complexity == Complexity.SIMPLE and size == Size.SMALL),
        skip_research=(complexity != Complexity.HEAVY),
        needs_reasoning=(complexity == Complexity.HEAVY),
    )


def _classify_from_plan(plan: dict) -> TaskClassification:
    """Classify from a completed plan (more accurate)."""
    file_count = len(plan.get("structure", {}))
    tech_stack = " ".join(t.lower() for t in plan.get("tech_stack", []))
    description = plan.get("description", "").lower()

    # Size from file count
    if file_count <= 4:
        size = Size.SMALL
    elif file_count <= 14:
        size = Size.MEDIUM
    else:
        size = Size.LARGE

    # Complexity from tech stack + description
    heavy_score = sum(1 for kw in _HEAVY_SIGNALS if kw in tech_stack or kw in description)
    medium_score = sum(1 for kw in _MEDIUM_SIGNALS if kw in tech_stack or kw in description)

    if heavy_score >= 2:
        complexity = Complexity.HEAVY
    elif heavy_score >= 1 or medium_score >= 2 or file_count > 12:
        complexity = Complexity.MEDIUM
    else:
        complexity = Complexity.SIMPLE

    return TaskClassification(
        complexity=complexity,
        size=size,
        skip_review=(complexity == Complexity.SIMPLE and size == Size.SMALL),
        skip_research=(complexity != Complexity.HEAVY),
        needs_reasoning=(complexity == Complexity.HEAVY),
    )


# ── Legacy compatibility wrapper ───────────────────────────────────
def detect_complexity(plan) -> str:
    """Legacy wrapper — returns old-style complexity string.
    Maps: heavy→complex, medium→medium, simple→simple.
    """
    tc = classify_task(prompt=plan if isinstance(plan, str) else None,
                       plan=plan if isinstance(plan, dict) else None)
    # Map to old-style strings for backward compat
    if tc.complexity == Complexity.HEAVY:
        return "complex"
    return tc.complexity.value


def get_context_size(
    complexity: str,
    size: str = "medium",
    is_planner: bool = True,
) -> int:
    """Calculate context window size based on classification."""
    base = BASE_PLANNER_CTX if is_planner else BASE_CODER_CTX
    c_mult = COMPLEXITY_SCALING.get(complexity, 1.5)
    s_mult = SIZE_SCALING.get(size, 1.0)
    # Combined multiplier (capped at 4x to avoid OOM)
    return min(int(base * c_mult * s_mult), 65536)
