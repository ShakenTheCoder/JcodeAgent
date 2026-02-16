"""
JCode configuration — models, roles, paths, defaults.

v0.2.0 — Multi-role architecture with structured memory & DAG tasks.
"""

from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum


# ── Model Configuration ────────────────────────────────────────────
PLANNER_MODEL = "deepseek-r1:14b"
CODER_MODEL = "qwen2.5-coder:14b"
REVIEWER_MODEL = "qwen2.5-coder:14b"      # Same weights, different prompt
ANALYZER_MODEL = "deepseek-r1:14b"         # Same weights, different prompt

# ── Generation Parameters ──────────────────────────────────────────
BASE_PLANNER_CTX = 16384
BASE_CODER_CTX = 16384

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
    "num_ctx": BASE_CODER_CTX,
}

ANALYZER_OPTIONS = {
    "temperature": 0.2,
    "top_p": 0.9,
    "num_ctx": BASE_PLANNER_CTX,
}

# Context window scaling
COMPLEXITY_SCALING = {
    "simple": 1.0,      # 16k
    "medium": 1.5,      # 24k
    "complex": 2.0,     # 32k
    "large": 2.5,       # 40k
}

# ── Limits ─────────────────────────────────────────────────────────
MAX_ITERATIONS = 8
MAX_FILE_READ_CHARS = 12000
MAX_TASK_FAILURES = 3         # Per task before escalation
MAX_DIFF_LINES = 80           # Prefer patches under this

# ── Project Defaults ───────────────────────────────────────────────
DEFAULT_OUTPUT_DIR = Path.cwd() / "jcode_output"


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

def detect_complexity(plan: dict) -> str:
    """Auto-detect project complexity from plan structure."""
    if not plan:
        return "medium"

    file_count = len(plan.get("structure", {}))
    tech_lower = " ".join(t.lower() for t in plan.get("tech_stack", []))

    score = 0

    if file_count <= 3:
        score += 1
    elif file_count <= 10:
        score += 2
    elif file_count <= 20:
        score += 3
    else:
        score += 4

    if any(kw in tech_lower for kw in ("sql", "database", "postgres", "mongo", "redis")):
        score += 1
    if any(kw in tech_lower for kw in ("api", "rest", "graphql", "grpc")):
        score += 1
    if any(kw in tech_lower for kw in ("auth", "jwt", "oauth", "session")):
        score += 1
    if any("test" in str(f).lower() for f in plan.get("structure", {}).keys()):
        score += 1
    if any(kw in tech_lower for kw in ("docker", "ci", "deploy")):
        score += 1

    if score <= 2:
        return "simple"
    elif score <= 4:
        return "medium"
    elif score <= 6:
        return "complex"
    return "large"


def get_context_size(complexity: str, is_planner: bool = True) -> int:
    """Calculate context window size based on project complexity."""
    base = BASE_PLANNER_CTX if is_planner else BASE_CODER_CTX
    multiplier = COMPLEXITY_SCALING.get(complexity, 1.5)
    return int(base * multiplier)
