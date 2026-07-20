"""In-memory job_id -> asyncio.Task registry for the currently-streaming
generation job (see app/generation_worker.py, app/api/generation.py).

Deliberately NOT Redis-backed: this service runs as a single
process/container (docker-compose.yml wiring is PR #6), so there is
exactly one event loop that could ever hold the Task object a future
cancel() call needs. If this service is ever scaled to multiple
replicas, POST /generate/{job_id}/cancel (PR #5) would need to route to
whichever replica owns the task instead of looking it up here -- flagged
now, not solved, since neither the mandatory scope nor the optional
single-EC2-box bonus deployment (Phase 18) requires multi-replica
support.
"""

import asyncio

_tasks: dict[str, asyncio.Task] = {}


def register(job_id: str, task: asyncio.Task) -> None:
    _tasks[job_id] = task


def get(job_id: str) -> asyncio.Task | None:
    return _tasks.get(job_id)


def discard(job_id: str) -> None:
    _tasks.pop(job_id, None)