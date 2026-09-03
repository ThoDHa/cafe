"""SSE hub: per-client queues, broadcast fanout, and heartbeats.

Design section 4: every connected GET /api/events client holds one
asyncio.Queue; order creation and status transitions broadcast to all
of them; idle connections receive a heartbeat every interval so dead
sockets surface and proxies keep the stream open. Single-process by
design (DESIGN.md process model: one uvicorn worker).
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app import schemas

HEARTBEAT_SECONDS = 25.0


def _format_event(event: schemas.ServerEvent) -> str:
    payload = event.model_dump(mode="json", by_alias=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.type}\ndata: {data}\n\n"


class EventHub:
    def __init__(self, heartbeat_seconds: float = HEARTBEAT_SECONDS) -> None:
        self._heartbeat_seconds = heartbeat_seconds
        self._subscribers: set[asyncio.Queue[schemas.ServerEvent]] = set()

    def subscribe(self) -> asyncio.Queue[schemas.ServerEvent]:
        queue: asyncio.Queue[schemas.ServerEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[schemas.ServerEvent]) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def broadcast(self, event: schemas.ServerEvent) -> None:
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)

    async def stream(
        self, queue: asyncio.Queue[schemas.ServerEvent]
    ) -> AsyncIterator[str]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=self._heartbeat_seconds
                    )
                except TimeoutError:
                    event = schemas.HeartbeatEvent(
                        type="heartbeat", sent_at=datetime.now(UTC)
                    )
                yield _format_event(event)
        finally:
            self.unsubscribe(queue)
