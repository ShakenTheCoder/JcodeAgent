"""
Structured memory engine — replaces raw context dumps with
organized, sliced knowledge about the project.

This is what lets a 14B model compete with 200k-context frontier models.
Instead of "dump everything", we inject only what's relevant.

v2.0 — Thread-safe file recording for parallel generation.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from datetime import datetime

from jcode.config import (
    ProjectState, TaskNode, TaskStatus,
    MAX_FILE_READ_CHARS, detect_complexity, get_context_size,
)
from jcode.memory import ProjectMemory

# Thread lock for state mutations (file recording, failure logging)
_state_lock = threading.Lock()


class ContextManager:
    """
    Maintains structured project memory and conversation history.

    Memory layers:
    1. Architecture summary — what the system does
    2. File index — every file and its purpose
    3. Dependency graph — who imports whom
    4. Task DAG — ordered tasks with status
    5. Failure log — what broke and how it was fixed
    6. Conversation history per role (planner, coder)
    7. Vector memory — embedding-based retrieval (optional, via ProjectMemory)

    Thread-safety:
    - record_file() and record_failure() are thread-safe
    - Per-file memory isolation: each file's content is independent
    - Global summary memory: architecture + file_index are read-only during generation
    """

    def __init__(self, state: ProjectState | None = None) -> None:
        self.state = state or ProjectState()
        self.planner_history: list[dict[str, str]] = []
        self.coder_history: list[dict[str, str]] = []
        self.reviewer_history: list[dict[str, str]] = []
        self.analyzer_history: list[dict[str, str]] = []
        self.chat_history: list[dict[str, str]] = []    # per-project chat
        self._task_dag: list[TaskNode] = []
        self.memory: ProjectMemory = ProjectMemory()

    # ── Plan & State ───────────────────────────────────────────────

    def set_plan(self, plan: dict) -> None:
        self.state.plan = plan
        self.state.name = plan.get("project_name", "project")
        self.state.description = plan.get("description", "")
        self.state.tech_stack = plan.get("tech_stack", [])
        self.state.architecture_summary = plan.get("architecture_summary", "")
        self.state.complexity = detect_complexity(plan)

        # Build file index
        self.state.file_index = plan.get("structure", {})

        # Build task DAG
        self._task_dag = []
        for t in plan.get("tasks", []):
            node = TaskNode(
                id=t["id"],
                file=t["file"],
                description=t["description"],
                depends_on=t.get("depends_on", []),
            )
            self._task_dag.append(node)

        # Timestamps
        if not self.state.created_at:
            self.state.created_at = datetime.now().isoformat()
        self.state.last_modified = datetime.now().isoformat()

    # ── Task DAG ───────────────────────────────────────────────────

    def get_task_dag(self) -> list[TaskNode]:
        return self._task_dag

    def get_ready_tasks(self) -> list[TaskNode]:
        """Return tasks whose dependencies are all satisfied."""
        verified_ids = {
            t.id for t in self._task_dag
            if t.status in (TaskStatus.VERIFIED, TaskStatus.SKIPPED)
        }
        return [
            t for t in self._task_dag
            if t.status == TaskStatus.PENDING
            and all(dep in verified_ids for dep in t.depends_on)
        ]

    def get_task_by_id(self, task_id: int) -> TaskNode | None:
        for t in self._task_dag:
            if t.id == task_id:
                return t
        return None

    def all_tasks_terminal(self) -> bool:
        return all(t.is_terminal for t in self._task_dag)

    def get_task_summary(self) -> str:
        """Human-readable task status summary."""
        lines = []
        for t in self._task_dag:
            icon = {
                TaskStatus.PENDING: "[ ]",
                TaskStatus.IN_PROGRESS: "[~]",
                TaskStatus.GENERATED: "[w]",
                TaskStatus.REVIEWING: "[?]",
                TaskStatus.NEEDS_FIX: "[!]",
                TaskStatus.VERIFIED: "[x]",
                TaskStatus.FAILED: "[-]",
                TaskStatus.SKIPPED: "[>]",
            }.get(t.status, "[.]")
            fails = f" (fails: {t.failure_count})" if t.failure_count else ""
            lines.append(f"  {icon} Task {t.id}: {t.file} -- {t.description}{fails}")
        return "\n".join(lines)

    # ── Structured Memory Accessors ────────────────────────────────

    def get_architecture(self) -> str:
        """Return the architecture summary for injection into prompts."""
        return self.state.architecture_summary or "(no architecture defined)"

    def get_file_index_str(self) -> str:
        """Return formatted file index."""
        if not self.state.file_index:
            return "(empty)"
        lines = [f"- `{path}`: {purpose}" for path, purpose in self.state.file_index.items()]
        return "\n".join(lines)

    def get_spec_details(self) -> str:
        """Return the planner's spec contract details (schema, API, auth, deploy).

        These are injected into the coder prompt so the builder follows the
        architectural spec exactly — no stack drift.
        """
        plan = self.state.plan
        if not plan:
            return "(no spec)"

        parts: list[str] = []

        # Database schema
        schema = plan.get("database_schema")
        if schema:
            parts.append("### Database Schema")
            for table, info in schema.items():
                cols = info.get("columns", {})
                col_lines = ", ".join(f"{c}: {t}" for c, t in cols.items())
                parts.append(f"- **{table}**: {col_lines}")
                for rel in info.get("relationships", []):
                    parts.append(f"  - {rel}")

        # API surface
        api = plan.get("api_surface")
        if api:
            parts.append("### API Surface")
            for endpoint in api:
                parts.append(f"- {endpoint.get('method', '?')} {endpoint.get('path', '?')} — {endpoint.get('description', '')}")

        # Auth flow
        auth = plan.get("auth_flow")
        if auth and auth != "none":
            parts.append(f"### Auth Flow\n{auth}")

        # Deployment
        deploy = plan.get("deployment")
        if deploy:
            parts.append(f"### Deployment\n{deploy}")

        return "\n\n".join(parts) if parts else "(simple project — no formal spec)"

    def get_dependency_context(self, file_path: str) -> str:
        """Get contents of files that the given file depends on."""
        deps = self.state.dependency_graph.get(file_path, [])
        return self.get_file_context(deps)

    def record_file(self, rel_path: str, content: str) -> None:
        """Thread-safe: record a generated file's content and update memory index."""
        with _state_lock:
            self.state.files[rel_path] = content
            self.state.last_modified = datetime.now().isoformat()

    def index_memory(self) -> int:
        """Index all current files into the vector memory store.
        Returns number of files indexed (0 if embedding not available)."""
        return self.memory.index_files(self.state.files, self.state.file_index)

    def get_relevant_files(self, query: str, top_k: int = 5) -> str:
        """Use RAG to retrieve the most relevant file contents for a query.
        Falls back to empty string if embedding is not available."""
        return self.memory.get_relevant_context(
            query, self.state.files, top_k=top_k
        )

    def record_failure(self, file_path: str, error: str, fix: str, iteration: int) -> None:
        """Thread-safe: log a failure for the structured failure memory."""
        entry = {
            "file": file_path,
            "error": error[:500],
            "fix_applied": fix[:200],
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
        }
        with _state_lock:
            self.state.failure_log.append(entry)

    def get_failure_log_str(self, file_path: str | None = None) -> str:
        """Get formatted failure log, optionally filtered by file."""
        log = self.state.failure_log
        if file_path:
            log = [e for e in log if e["file"] == file_path]
        if not log:
            return "(no previous failures)"
        lines = []
        for e in log[-5:]:  # Last 5 entries
            lines.append(f"- [{e['file']}] {e['error'][:100]}")
        return "\n".join(lines)

    def record_error(self, error: str) -> None:
        self.state.errors.append(error)

    def clear_errors(self) -> None:
        self.state.errors.clear()

    def bump_iteration(self) -> int:
        self.state.iteration += 1
        return self.state.iteration

    def get_complexity(self) -> str:
        return self.state.complexity

    def get_size(self) -> str:
        return getattr(self.state, "size", "medium")

    def get_context_sizes(self) -> tuple[int, int]:
        c = self.state.complexity
        s = self.get_size()
        return get_context_size(c, s, True), get_context_size(c, s, False)

    # ── Conversation management ────────────────────────────────────

    def add_message(self, role_channel: str, role: str, content: str) -> None:
        """Add a message to a role's history."""
        msg = {"role": role, "content": content}
        getattr(self, f"{role_channel}_history").append(msg)

    def get_messages(self, role_channel: str) -> list[dict[str, str]]:
        return list(getattr(self, f"{role_channel}_history"))

    def reset_channel(self, role_channel: str) -> None:
        getattr(self, f"{role_channel}_history").clear()

    # Legacy aliases
    def add_planner_message(self, role, content):
        self.add_message("planner", role, content)
    def add_coder_message(self, role, content):
        self.add_message("coder", role, content)
    def get_planner_messages(self):
        return self.get_messages("planner")
    def get_coder_messages(self):
        return self.get_messages("coder")
    def reset_coder_history(self):
        self.reset_channel("coder")

    # ── Chat history (per-project conversation) ───────────────────

    def add_chat(self, role: str, content: str) -> None:
        """Add a message to the project chat history."""
        self.chat_history.append({"role": role, "content": content})

    def get_chat_messages(self) -> list[dict[str, str]]:
        """Return the full chat history for this project."""
        return list(self.chat_history)

    def get_project_summary_for_chat(self) -> str:
        """Build a context string describing the project for chat interactions."""
        parts = [
            f"Project: {self.state.name}",
            f"Description: {self.state.description}",
            f"Tech stack: {', '.join(self.state.tech_stack)}",
            f"Architecture: {self.state.architecture_summary or 'N/A'}",
            "",
            "Files:",
        ]
        for path, purpose in (self.state.file_index or {}).items():
            parts.append(f"  - {path}: {purpose}")

        return "\n".join(parts)

    # ── File context (sliced, not dumped) ──────────────────────────

    def get_file_context(self, rel_paths: list[str]) -> str:
        """Return formatted contents of specific files — sliced, not all."""
        parts: list[str] = []
        for p in rel_paths:
            content = self.state.files.get(p)
            if content:
                trimmed = content[:MAX_FILE_READ_CHARS]
                parts.append(f"### {p}\n```\n{trimmed}\n```")
        return "\n\n".join(parts) if parts else "(no existing files)"

    def get_related_files(self, task: dict) -> list[str]:
        """Resolve which files a task depends on."""
        depends = task.get("depends_on", [])
        if not depends:
            return []
        id_to_file = {t.id: t.file for t in self._task_dag}
        return [id_to_file[d] for d in depends if d in id_to_file]

    def get_plan_json(self) -> str:
        if self.state.plan:
            return json.dumps(self.state.plan, indent=2)
        return "{}"

    # ── Metadata ───────────────────────────────────────────────────

    def to_metadata(self) -> dict:
        return {
            "name": self.state.name,
            "description": self.state.description,
            "tech_stack": self.state.tech_stack,
            "output_dir": str(self.state.output_dir),
            "complexity": self.state.complexity,
            "file_count": len(self.state.files),
            "completed": self.state.completed,
            "created_at": self.state.created_at,
            "last_modified": self.state.last_modified,
        }

    # ── Serialization ──────────────────────────────────────────────

    def save_session(self, path: Path) -> None:
        data = {
            "state": {
                "name": self.state.name,
                "description": self.state.description,
                "tech_stack": self.state.tech_stack,
                "output_dir": str(self.state.output_dir),
                "plan": self.state.plan,
                "files": self.state.files,
                "errors": self.state.errors,
                "iteration": self.state.iteration,
                "completed": self.state.completed,
                "complexity": self.state.complexity,
                "size": self.state.size,
                "created_at": self.state.created_at,
                "last_modified": datetime.now().isoformat(),
                "architecture_summary": self.state.architecture_summary,
                "file_index": self.state.file_index,
                "dependency_graph": self.state.dependency_graph,
                "failure_log": self.state.failure_log,
                "task_nodes": [t.to_dict() for t in self._task_dag],
            },
            "planner_history": self.planner_history,
            "coder_history": self.coder_history,
            "chat_history": self.chat_history,
            "memory": self.memory.to_dict(),
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load_session(cls, path: Path) -> "ContextManager":
        data = json.loads(path.read_text())
        s = data["state"]
        state = ProjectState(
            name=s["name"],
            description=s["description"],
            tech_stack=s["tech_stack"],
            output_dir=Path(s["output_dir"]),
            plan=s["plan"],
            files=s["files"],
            errors=s["errors"],
            iteration=s["iteration"],
            completed=s["completed"],
            complexity=s.get("complexity", "medium"),
            size=s.get("size", "medium"),
            created_at=s.get("created_at", ""),
            last_modified=s.get("last_modified", ""),
            architecture_summary=s.get("architecture_summary", ""),
            file_index=s.get("file_index", {}),
            dependency_graph=s.get("dependency_graph", {}),
            failure_log=s.get("failure_log", []),
            task_nodes=s.get("task_nodes", []),
        )
        ctx = cls(state)
        # Rebuild DAG
        ctx._task_dag = [TaskNode.from_dict(d) for d in s.get("task_nodes", [])]
        ctx.planner_history = data.get("planner_history", [])
        ctx.coder_history = data.get("coder_history", [])
        ctx.chat_history = data.get("chat_history", [])
        # Restore vector memory
        if "memory" in data:
            ctx.memory = ProjectMemory.from_dict(data["memory"])
        return ctx
