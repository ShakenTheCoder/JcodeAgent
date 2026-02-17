"""
Task Graph Engine — DAG-based parallel task orchestration.

Features:
  1. Directed Acyclic Graph with dependency resolution
  2. Parallel execution of independent nodes
  3. Deterministic wave-based scheduling
  4. Integrates with WorkerPool for adaptive concurrency

The graph groups tasks into "waves":
  Wave 0: tasks with no dependencies (all run in parallel)
  Wave 1: tasks that depend only on wave-0 tasks (parallel)
  Wave 2: ...etc

Within each wave, all tasks run concurrently via the WorkerPool.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable

from rich.console import Console

from jcode.config import TaskNode, TaskStatus
from jcode.worker_pool import WorkerPool, WorkerResult

console = Console()


def compute_waves(dag: list[TaskNode]) -> list[list[TaskNode]]:
    """
    Compute execution waves from a task DAG using topological sort.

    Returns a list of waves, where each wave is a list of TaskNodes
    that can run in parallel (all dependencies are in earlier waves).

    Raises ValueError if the graph contains a cycle.
    """
    if not dag:
        return []

    # Build adjacency and in-degree
    id_to_node = {t.id: t for t in dag}
    in_degree: dict[int, int] = {t.id: 0 for t in dag}
    dependents: dict[int, list[int]] = defaultdict(list)

    for t in dag:
        for dep in t.depends_on:
            if dep in id_to_node:
                in_degree[t.id] += 1
                dependents[dep].append(t.id)

    # BFS topological sort in layers
    waves: list[list[TaskNode]] = []
    queue = deque([tid for tid, deg in in_degree.items() if deg == 0])

    processed = 0
    while queue:
        wave_ids = list(queue)
        queue.clear()

        wave_nodes = [id_to_node[tid] for tid in wave_ids]
        waves.append(wave_nodes)
        processed += len(wave_ids)

        for tid in wave_ids:
            for child in dependents.get(tid, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

    if processed < len(dag):
        # Some nodes were never reached — cycle detected
        unreached = [t for t in dag if t.id not in {n.id for w in waves for n in w}]
        raise ValueError(
            f"Cycle detected in task DAG. Unreachable tasks: "
            f"{[t.id for t in unreached]}"
        )

    return waves


def get_ready_wave(dag: list[TaskNode]) -> list[TaskNode]:
    """
    Get the next wave of tasks that are ready to execute.
    A task is ready if:
      - Its status is PENDING
      - All dependencies are in a terminal state (VERIFIED / SKIPPED)
    """
    terminal_ids = {
        t.id for t in dag
        if t.status in (TaskStatus.VERIFIED, TaskStatus.SKIPPED)
    }
    return [
        t for t in dag
        if t.status == TaskStatus.PENDING
        and all(dep in terminal_ids for dep in t.depends_on)
    ]


def execute_wave_parallel(
    wave: list[TaskNode],
    worker_fn: Callable[[TaskNode], Any],
    pool: WorkerPool,
) -> list[WorkerResult]:
    """
    Execute a wave of tasks in parallel using the worker pool.

    Args:
        wave: List of TaskNodes to execute concurrently.
        worker_fn: Function that processes a single TaskNode.
                   Signature: (TaskNode) -> Any
        pool: The WorkerPool to submit tasks to.

    Returns:
        List of WorkerResults, one per task.
    """
    # Submit all tasks in the wave
    futures = []
    for node in wave:
        future = pool.submit(worker_fn, node, task_id=node.id)
        futures.append(future)

    # Collect results (blocks until all complete)
    return pool.collect(futures)


def get_dag_stats(dag: list[TaskNode]) -> dict:
    """Return statistics about the DAG execution state."""
    stats = {
        "total": len(dag),
        "pending": 0,
        "in_progress": 0,
        "verified": 0,
        "failed": 0,
        "skipped": 0,
        "waves": 0,
    }
    for t in dag:
        if t.status == TaskStatus.PENDING:
            stats["pending"] += 1
        elif t.status in (TaskStatus.IN_PROGRESS, TaskStatus.GENERATED,
                          TaskStatus.REVIEWING, TaskStatus.NEEDS_FIX):
            stats["in_progress"] += 1
        elif t.status == TaskStatus.VERIFIED:
            stats["verified"] += 1
        elif t.status == TaskStatus.FAILED:
            stats["failed"] += 1
        elif t.status == TaskStatus.SKIPPED:
            stats["skipped"] += 1

    try:
        pending_nodes = [t for t in dag if not t.is_terminal]
        if pending_nodes:
            stats["waves"] = len(compute_waves(pending_nodes))
    except ValueError:
        stats["waves"] = -1  # cycle

    return stats
