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
  │ coding              │ coder     │ devstral, qwen2.5-coder, deepcoder │
  │ reasoning           │ planner   │ deepseek-r1, qwen3, magistral      │
  │ agentic             │ orchestr. │ gpt-oss, qwen3, glm-4.7            │
  │ fast                │ reviewer  │ qwen2.5-coder:7b, glm-4.7-flash   │
  └─────────────────────┴───────────┴─────────────────────────────────────┘
"""

from __future__ import annotations

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
    category: str           # coding | reasoning | agentic | fast | general
    size_class: str         # small (≤8b) | medium (9-20b) | large (21b+)
    priority: int = 50      # Lower = preferred (within same category+size)
    supports_tools: bool = False
    supports_thinking: bool = False
    context_window: int = 32768


# ── Full Model Registry ───────────────────────────────────────────
# Models are ordered by preference within each category.
# JCode will pick the FIRST locally-available model that fits.

MODEL_REGISTRY: list[ModelSpec] = [
    # ── CODING models (for file generation, patching) ──────────────
    ModelSpec("devstral:24b",          "coding",    "large",  10, supports_tools=True),
    ModelSpec("devstral-small:24b",    "coding",    "large",  15, supports_tools=True),
    ModelSpec("qwen2.5-coder:32b",    "coding",    "large",  20),
    ModelSpec("qwen2.5-coder:14b",    "coding",    "medium", 10),
    ModelSpec("deepcoder:14b",         "coding",    "medium", 15),
    ModelSpec("qwen2.5-coder:7b",     "coding",    "small",  10),

    # ── REASONING models (for planning, analysis, deep thinking) ───
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

    # ── GENERAL models (fallback for any role) ─────────────────────
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
    if model in local:
        return True
    # Try base name without tag
    base = model.split(":")[0]
    return any(m.startswith(base) for m in local)


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
]

_MEDIUM_SIGNALS = [
    "api", "rest", "crud", "backend", "server", "endpoint",
    "react", "next", "vue", "angular", "svelte", "frontend",
    "full-stack", "fullstack", "backend and frontend",
    "dashboard", "admin panel", "cms",
    "upload", "file system", "storage",
    "email", "notification", "queue",
    "testing", "test suite", "e2e",
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


def _classify_from_prompt(prompt: str) -> TaskClassification:
    """Classify from user prompt (before planning)."""
    lower = prompt.lower()
    heavy_score = sum(1 for kw in _HEAVY_SIGNALS if kw in lower)
    medium_score = sum(1 for kw in _MEDIUM_SIGNALS if kw in lower)
    simple_score = sum(1 for kw in _SIMPLE_SIGNALS if kw in lower)

    # Determine complexity
    if heavy_score >= 2 or (heavy_score >= 1 and medium_score >= 2):
        complexity = Complexity.HEAVY
    elif medium_score >= 2 or heavy_score >= 1:
        complexity = Complexity.MEDIUM
    elif simple_score > 0 and heavy_score == 0 and medium_score == 0:
        complexity = Complexity.SIMPLE
    else:
        # Default: heuristic based on prompt length
        if len(prompt.split()) > 50:
            complexity = Complexity.MEDIUM
        else:
            complexity = Complexity.SIMPLE

    # Estimate size from prompt (rough — will be refined after planning)
    word_count = len(prompt.split())
    if word_count > 80 or "full" in lower or "complete" in lower or "entire" in lower:
        size = Size.LARGE
    elif word_count > 30 or complexity == Complexity.HEAVY:
        size = Size.MEDIUM
    else:
        size = Size.SMALL

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
