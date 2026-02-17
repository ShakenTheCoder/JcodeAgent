"""
JCode configuration — models, roles, paths, defaults.

v0.8.0 — Adaptive model tiering.

Key design principles:
  1. NEVER pull models during builds — only use what's locally installed.
  2. Two tiers: FAST (7b) and DEFAULT (14b). No 32b by default.
  3. Complexity detection is tight — simple tasks stay simple.
  4. Escalation happens ONLY on failure, not preemptively.
  5. Prefer the smallest model that can do the job.
"""

from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum


# ═══════════════════════════════════════════════════════════════════
# Adaptive Model Tiering
# ═══════════════════════════════════════════════════════════════════
#
# Only two tiers used by default (matches installer):
#   FAST    — 7b models: quick generation, lint review, config files
#   DEFAULT — 14b models: planning, code generation, deep review
#
# 32b models are NEVER required. If installed, they serve as
# escalation targets when a file fails generation 3+ times.
#
#   Complexity  │ Planner    │ Coder   │ Reviewer │ Analyzer
#   ────────────┼────────────┼─────────┼──────────┼─────────
#   simple      │ fast       │ fast    │ fast     │ fast
#   medium      │ default    │ default │ fast     │ fast
#   complex     │ default    │ default │ default  │ default
# ═══════════════════════════════════════════════════════════════════

# ── Model Tiers ────────────────────────────────────────────────────
MODEL_TIERS = {
    "fast": {
        "reasoning": "deepseek-r1:14b",
        "coding":    "qwen2.5-coder:7b",
    },
    "default": {
        "reasoning": "deepseek-r1:14b",
        "coding":    "qwen2.5-coder:14b",
    },
    "strong": {
        "reasoning": "deepseek-r1:14b",
        "coding":    "qwen2.5-coder:14b",
    },
}

# Which family each role uses
ROLE_FAMILY = {
    "planner":  "reasoning",
    "coder":    "coding",
    "reviewer": "coding",
    "analyzer": "reasoning",
}

# Complexity → tier mapping per role
ROLE_TIER_MAP = {
    "simple": {
        "planner":  "fast",
        "coder":    "default",   # Always use 14b coder — quality matters
        "reviewer": "fast",
        "analyzer": "fast",
    },
    "medium": {
        "planner":  "default",
        "coder":    "default",
        "reviewer": "fast",
        "analyzer": "fast",
    },
    "complex": {
        "planner":  "default",
        "coder":    "default",
        "reviewer": "default",
        "analyzer": "default",
    },
    "large": {
        "planner":  "default",
        "coder":    "default",
        "reviewer": "default",
        "analyzer": "default",
    },
}

# ── Locally installed models cache ─────────────────────────────────
_local_models: set[str] | None = None


def _get_local_models() -> set[str]:
    """Return the set of models installed locally. Cached after first call."""
    global _local_models
    if _local_models is not None:
        return _local_models
    try:
        import ollama as _ollama
        response = _ollama.list()
        # Handle both old and new ollama API formats
        models = response.get("models", []) if isinstance(response, dict) else []
        if not models and hasattr(response, 'models'):
            models = response.models or []
        names = set()
        for m in models:
            name = m.get("name", "") if isinstance(m, dict) else getattr(m, "model", "")
            if name:
                # Normalize: "qwen2.5-coder:14b" and "qwen2.5-coder:14b-..." both match "qwen2.5-coder:14b"
                names.add(name.split("-q")[0] if "-q" in name else name)
        _local_models = names
    except Exception:
        _local_models = set()
    return _local_models


def _is_model_local(model: str) -> bool:
    """Check if a model is installed locally."""
    local = _get_local_models()
    return model in local


def get_model_for_role(role: str, complexity: str = "medium") -> str:
    """Resolve the concrete model name for a role at a given complexity.
    Falls back to whatever is locally available — never triggers a pull."""
    tier = ROLE_TIER_MAP.get(complexity, ROLE_TIER_MAP["medium"]).get(role, "default")
    family = ROLE_FAMILY.get(role, "coding")
    model = MODEL_TIERS[tier][family]

    # If the resolved model isn't local, fall back through tiers
    if not _is_model_local(model):
        # Try all tiers in preference order for this family
        for fallback_tier in ("default", "fast", "strong"):
            fallback = MODEL_TIERS[fallback_tier][family]
            if _is_model_local(fallback):
                return fallback
        # Last resort: return whatever we have, ollama_client will handle it
    return model


def get_escalation_model(role: str) -> str | None:
    """Get a stronger model for escalation (only if locally available).
    Returns None if no stronger model is available."""
    family = ROLE_FAMILY.get(role, "coding")
    # Check if a 32b model is available locally
    candidates = [
        "qwen2.5-coder:32b" if family == "coding" else "deepseek-r1:32b",
    ]
    for model in candidates:
        if _is_model_local(model):
            return model
    return None


def get_all_required_models(complexity: str = "medium") -> list[str]:
    """Return the unique set of models needed for a given complexity level.
    Only returns models that are locally installed."""
    models = set()
    tier_map = ROLE_TIER_MAP.get(complexity, ROLE_TIER_MAP["medium"])
    for role, tier in tier_map.items():
        family = ROLE_FAMILY[role]
        model = MODEL_TIERS[tier][family]
        if _is_model_local(model):
            models.add(model)
    return sorted(models)


# ── Legacy constants (kept for backward compat, resolved dynamically) ──
PLANNER_MODEL = MODEL_TIERS["default"]["reasoning"]
CODER_MODEL = MODEL_TIERS["default"]["coding"]
REVIEWER_MODEL = MODEL_TIERS["fast"]["coding"]
ANALYZER_MODEL = MODEL_TIERS["default"]["reasoning"]


# ── Generation Parameters ──────────────────────────────────────────
BASE_PLANNER_CTX = 8192
BASE_CODER_CTX = 8192

PLANNER_OPTIONS = {
    "temperature": 0.6,
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
    "num_ctx": 4096,           # Reviews don't need big context
}

ANALYZER_OPTIONS = {
    "temperature": 0.2,
    "top_p": 0.9,
    "num_ctx": 4096,
}

# Context window scaling
COMPLEXITY_SCALING = {
    "simple": 1.0,      # 8k
    "medium": 1.5,      # 12k
    "complex": 2.0,     # 16k
    "large": 3.0,       # 24k
}

# ── Worker Pool Settings ───────────────────────────────────────────
MAX_WORKERS = 6               # Maximum concurrent workers
MIN_WORKERS = 1               # Minimum concurrent workers
CPU_HIGH_THRESHOLD = 85.0     # Reduce concurrency above this %
CPU_LOW_THRESHOLD = 50.0      # Increase concurrency below this %
WORKER_POLL_INTERVAL = 2.0    # Seconds between CPU checks

# ── Limits ─────────────────────────────────────────────────────────
MAX_ITERATIONS = 15
MAX_FILE_READ_CHARS = 12000
MAX_TASK_FAILURES = 8         # Per task before escalation — generous retry budget
MAX_DIFF_LINES = 80           # Prefer patches under this

# ── Project Defaults ───────────────────────────────────────────────
DEFAULT_OUTPUT_DIR = Path.cwd()  # v0.7.0: CWD-aware by default


# ── Task State Machine ─────────────────────────────────────────────

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
    created_at: str = ""
    last_modified: str = ""

    # ── Structured Memory ──────────────────────────────────────────
    architecture_summary: str = ""
    file_index: dict[str, str] = field(default_factory=dict)   # path → purpose
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    failure_log: list[dict] = field(default_factory=list)

    # ── Task DAG ───────────────────────────────────────────────────
    task_nodes: list[dict] = field(default_factory=list)


# ── Complexity Detection ───────────────────────────────────────────

def detect_complexity(plan) -> str:
    """Auto-detect project complexity from plan structure.

    Accepts either a dict (plan) or a string (prompt).
    When called with a string prompt (before planning), returns a
    keyword-based estimate.  When called with the full plan dict,
    uses structural analysis.

    The default is SIMPLE — complexity only goes up when there is
    strong evidence of a complex system (databases, auth, multi-service).
    """
    if not plan:
        return "simple"

    # ── String prompt (pre-plan estimate) ──────────────────────────
    if isinstance(plan, str):
        prompt_lower = plan.lower()
        score = 0

        # Only count truly complex signals
        if any(kw in prompt_lower for kw in ("database", "postgres", "mongo", "mysql", "redis", "sqlite")):
            score += 2
        if any(kw in prompt_lower for kw in ("auth", "jwt", "oauth", "login", "signup", "session")):
            score += 2
        if any(kw in prompt_lower for kw in ("docker", "ci/cd", "deploy", "kubernetes", "microservice")):
            score += 2
        if any(kw in prompt_lower for kw in ("graphql", "grpc", "websocket", "real-time")):
            score += 1
        if any(kw in prompt_lower for kw in ("full-stack", "fullstack", "backend and frontend")):
            score += 1

        # Simple keywords that actively REDUCE complexity
        if any(kw in prompt_lower for kw in ("simple", "basic", "minimal", "small", "quick", "tiny", "hello world")):
            score -= 2

        if score <= 0:
            return "simple"
        elif score <= 2:
            return "medium"
        return "complex"

    # ── Dict plan (full structural analysis) ───────────────────────
    file_count = len(plan.get("structure", {}))
    tech_lower = " ".join(t.lower() for t in plan.get("tech_stack", []))

    score = 0

    # File count is the primary signal
    if file_count <= 5:
        score += 0  # simple
    elif file_count <= 12:
        score += 2
    elif file_count <= 25:
        score += 3
    else:
        score += 4

    # Tech stack signals
    if any(kw in tech_lower for kw in ("database", "postgres", "mongo", "mysql", "redis")):
        score += 2
    if any(kw in tech_lower for kw in ("auth", "jwt", "oauth", "session")):
        score += 1
    if any(kw in tech_lower for kw in ("docker", "ci", "deploy")):
        score += 1
    if any(kw in tech_lower for kw in ("react", "next", "vue", "angular", "svelte")):
        score += 1

    if score <= 1:
        return "simple"
    elif score <= 3:
        return "medium"
    elif score <= 5:
        return "complex"
    return "large"


def get_context_size(complexity: str, is_planner: bool = True) -> int:
    """Calculate context window size based on project complexity."""
    base = BASE_PLANNER_CTX if is_planner else BASE_CODER_CTX
    multiplier = COMPLEXITY_SCALING.get(complexity, 1.5)
    return int(base * multiplier)
