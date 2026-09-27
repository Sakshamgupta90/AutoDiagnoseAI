"""In-process event log per job.

Jobs run as background tasks and append typed events here; SSE connections
replay from the last event id they saw and then wait for new ones. Reconnects
therefore never re-run the orchestrator (or re-bill Bedrock).
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15.0


@dataclass
class Event:
    id: int
    type: str
    data: dict[str, Any]


@dataclass
class JobChannel:
    events: list[Event] = field(default_factory=list)
    done: bool = False
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)


class JobManager:
    def __init__(self) -> None:
        self._channels: dict[str, JobChannel] = {}
        self._tasks: set[asyncio.Task] = set()

    def open(self, job_id: str) -> None:
        self._channels[job_id] = JobChannel()

    def has(self, job_id: str) -> bool:
        return job_id in self._channels

    def is_running(self, job_id: str) -> bool:
        ch = self._channels.get(job_id)
        return bool(ch and not ch.done)

    async def emit(self, job_id: str, type_: str, data: dict[str, Any]) -> None:
        ch = self._channels[job_id]
        async with ch.cond:
            ch.events.append(Event(len(ch.events) + 1, type_, data))
            ch.cond.notify_all()

    async def close(self, job_id: str) -> None:
        ch = self._channels[job_id]
        async with ch.cond:
            ch.done = True
            ch.cond.notify_all()

    def run(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)  # keep a reference so the task isn't garbage-collected
        task.add_done_callback(self._tasks.discard)

    async def subscribe(self, job_id: str, after: int = 0) -> AsyncIterator[Event | None]:
        """Yields events after `after`; yields None when a heartbeat is due. Ends when the job is done."""
        ch = self._channels[job_id]
        cursor = after
        while True:
            async with ch.cond:
                if cursor >= len(ch.events) and not ch.done:
                    try:
                        await asyncio.wait_for(ch.cond.wait(), timeout=HEARTBEAT_SECONDS)
                    except TimeoutError:
                        pass
                pending = ch.events[cursor:]
                finished = ch.done
            if not pending and not finished:
                yield None
                continue
            for event in pending:
                cursor = event.id
                yield event
            if finished and cursor >= len(ch.events):
                return


jobs = JobManager()
