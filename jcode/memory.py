"""
Project memory engine — vector-based retrieval-augmented generation (RAG).

This is what lets smaller models compete with frontier models.
Instead of dumping the entire codebase into context, we:
  1. Embed every file using all-minilm (or similar embedding model)
  2. Store embeddings in-memory (per project session)
  3. At generation time, retrieve ONLY the most relevant context
  4. Optional: summarize project state using a lightweight model

This module is OPTIONAL — if no embedding model is installed,
JCode falls back to the existing sliced-context approach in context.py.

v0.9.1 — Initial implementation.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from dataclasses import dataclass, field

from rich.console import Console

console = Console()

# Thread lock for embedding operations
_embed_lock = threading.Lock()


@dataclass
class FileEmbedding:
    """A file with its embedding vector and metadata."""
    path: str                    # relative file path
    content_hash: str            # hash of content (detect changes)
    summary: str                 # one-line summary of file purpose
    embedding: list[float] = field(default_factory=list)


class ProjectMemory:
    """
    In-memory vector store for project files.

    Backed by Ollama embedding models (all-minilm, nomic-embed-text).
    Falls back gracefully if no embedding model is available.

    Usage:
        memory = ProjectMemory()
        memory.index_files(ctx.state.files, ctx.state.file_index)
        relevant = memory.retrieve("implement user authentication", top_k=5)
    """

    def __init__(self) -> None:
        self._embeddings: dict[str, FileEmbedding] = {}
        self._model: str | None = None
        self._available: bool | None = None  # tri-state: None=unknown

    @property
    def is_available(self) -> bool:
        """Check if embedding is available (lazy init)."""
        if self._available is not None:
            return self._available

        from jcode.config import get_embedding_model
        model = get_embedding_model()
        if model:
            self._model = model
            self._available = True
            console.print(f"  [dim]Memory: embedding via {model}[/dim]")
        else:
            self._available = False
        return self._available

    def _embed(self, text: str) -> list[float]:
        """Generate embedding vector for text using Ollama."""
        if not self._model:
            return []
        try:
            import ollama
            response = ollama.embed(model=self._model, input=text)
            # Handle different response formats
            if isinstance(response, dict):
                embeddings = response.get("embeddings", [])
                if embeddings:
                    return embeddings[0]
                return response.get("embedding", [])
            return []
        except Exception as e:
            console.print(f"  [dim]Embedding error: {e}[/dim]")
            return []

    def _content_hash(self, content: str) -> str:
        """Fast hash for change detection."""
        import hashlib
        return hashlib.md5(content.encode()[:4096]).hexdigest()

    def index_files(
        self,
        files: dict[str, str],
        file_index: dict[str, str] | None = None,
    ) -> int:
        """Index all project files into the vector store.

        Args:
            files: dict of {relative_path: file_content}
            file_index: dict of {relative_path: description} from planner

        Returns:
            Number of files indexed.
        """
        if not self.is_available:
            return 0

        indexed = 0
        file_index = file_index or {}

        with _embed_lock:
            for path, content in files.items():
                if not content or not content.strip():
                    continue

                content_hash = self._content_hash(content)

                # Skip if already indexed with same content
                existing = self._embeddings.get(path)
                if existing and existing.content_hash == content_hash:
                    continue

                # Build embedding text: summary + first 1000 chars of content
                summary = file_index.get(path, "")
                embed_text = f"File: {path}\nPurpose: {summary}\n\n{content[:1500]}"

                embedding = self._embed(embed_text)
                if embedding:
                    self._embeddings[path] = FileEmbedding(
                        path=path,
                        content_hash=content_hash,
                        summary=summary,
                        embedding=embedding,
                    )
                    indexed += 1

        return indexed

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        exclude: list[str] | None = None,
    ) -> list[str]:
        """Retrieve the most relevant file paths for a query.

        Args:
            query: The task description or search query.
            top_k: Number of results to return.
            exclude: File paths to exclude from results.

        Returns:
            List of file paths, ordered by relevance (most relevant first).
        """
        if not self.is_available or not self._embeddings:
            return []

        exclude = set(exclude or [])
        query_embedding = self._embed(query)
        if not query_embedding:
            return []

        # Compute cosine similarity
        scored: list[tuple[float, str]] = []
        for path, fe in self._embeddings.items():
            if path in exclude or not fe.embedding:
                continue
            sim = self._cosine_similarity(query_embedding, fe.embedding)
            scored.append((sim, path))

        # Sort by similarity (descending)
        scored.sort(key=lambda x: x[0], reverse=True)
        return [path for _, path in scored[:top_k]]

    def get_relevant_context(
        self,
        query: str,
        files: dict[str, str],
        top_k: int = 5,
        max_chars: int = 8000,
    ) -> str:
        """Retrieve and format the most relevant file contents for a query.

        This is the main entry point for RAG-enhanced generation.
        Returns formatted file contents ready for prompt injection.
        """
        relevant_paths = self.retrieve(query, top_k=top_k)
        if not relevant_paths:
            return ""

        parts: list[str] = []
        total_chars = 0
        for path in relevant_paths:
            content = files.get(path, "")
            if not content:
                continue
            # Trim to fit budget
            remaining = max_chars - total_chars
            if remaining <= 0:
                break
            trimmed = content[:remaining]
            parts.append(f"### {path}\n```\n{trimmed}\n```")
            total_chars += len(trimmed)

        return "\n\n".join(parts) if parts else ""

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def clear(self) -> None:
        """Clear all embeddings."""
        with _embed_lock:
            self._embeddings.clear()

    @property
    def size(self) -> int:
        """Number of indexed files."""
        return len(self._embeddings)

    def to_dict(self) -> dict:
        """Serialize for session save."""
        return {
            "model": self._model,
            "embeddings": {
                path: {
                    "path": fe.path,
                    "content_hash": fe.content_hash,
                    "summary": fe.summary,
                    "embedding": fe.embedding,
                }
                for path, fe in self._embeddings.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectMemory":
        """Restore from session data."""
        mem = cls()
        mem._model = data.get("model")
        mem._available = bool(mem._model)
        for path, fe_data in data.get("embeddings", {}).items():
            mem._embeddings[path] = FileEmbedding(
                path=fe_data["path"],
                content_hash=fe_data["content_hash"],
                summary=fe_data.get("summary", ""),
                embedding=fe_data.get("embedding", []),
            )
        return mem
