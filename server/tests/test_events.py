"""SSE hub tests: broadcast fanout, heartbeat formatting, idle-stream
keepalive, and the full endpoint lifecycle against a real uvicorn
server on an ephemeral port (design section 4: order:new,
order:status, heartbeats).

ASGITransport cannot host an infinite stream (it awaits the full ASGI
cycle), so the endpoint tests run a real server thread.
"""

import asyncio
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx2
import uvicorn

from app import schemas
from app.events import EventHub
from app.main import create_app

AFFOGATO_LINE = {
    "itemId": "ca-phe-kem",
    "temperature": "hot",
    "quantity": 1,
}

READ_DEADLINE_SECONDS = 5.0
UNIT_TIMEOUT_SECONDS = 1.0


async def _next(stream):
    return await asyncio.wait_for(anext(stream), timeout=UNIT_TIMEOUT_SECONDS)


def _run(coroutine) -> None:
    asyncio.run(coroutine)


def _order_fixture(number: int = 1) -> schemas.Order:
    line = schemas.OrderLineView(
        item_id="ca-phe-kem",
        item_name="Affogato",
        item_name_vi="Cà Phê Kem",
        temperature=schemas.Temperature.hot,
        quantity=1,
    )
    now = datetime.now(UTC)
    return schemas.Order(
        id=uuid4(),
        order_number=number,
        status=schemas.OrderStatus.placed,
        items=[line],
        created_at=now,
        updated_at=now,
    )


def _parse_data(chunk: str) -> dict:
    data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
    return json.loads(data_line[len("data: ") :])


def _sse_payload(text: str, event_name: str) -> dict:
    chunk = next(c for c in text.split("\n\n") if f"event: {event_name}" in c)
    return _parse_data(chunk)


class _LiveServer:
    def __init__(self, app) -> None:
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        for _ in range(200):
            if self._server.started:
                break
            time.sleep(0.02)
        assert self._server.started, "uvicorn did not start"
        self.port = self._server.servers[0].sockets[0].getsockname()[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5.0)


def test_broadcast_delivers_to_every_subscriber() -> None:
    hub = EventHub(heartbeat_seconds=25.0)
    first = hub.subscribe()
    second = hub.subscribe()
    assert hub.subscriber_count == 2

    event = schemas.OrderNewEvent(type="order:new", order=_order_fixture())
    hub.broadcast(event)

    assert first.get_nowait() is event
    assert second.get_nowait() is event

    hub.unsubscribe(first)
    assert hub.subscriber_count == 1


def test_stream_formats_events_and_unsubscribes_on_close() -> None:
    async def scenario() -> None:
        hub = EventHub(heartbeat_seconds=25.0)
        queue = hub.subscribe()
        stream = hub.stream(queue)

        hub.broadcast(
            schemas.OrderNewEvent(type="order:new", order=_order_fixture())
        )
        chunk = await _next(stream)
        assert chunk.startswith("event: order:new\n")
        payload = _parse_data(chunk)
        assert payload["type"] == "order:new"
        assert payload["order"]["orderNumber"] == 1

        await stream.aclose()
        assert hub.subscriber_count == 0

    _run(scenario())


def test_idle_stream_yields_heartbeats() -> None:
    async def scenario() -> None:
        hub = EventHub(heartbeat_seconds=0.01)
        queue = hub.subscribe()
        stream = hub.stream(queue)

        chunk = await _next(stream)
        assert chunk.startswith("event: heartbeat\n")
        assert _parse_data(chunk)["type"] == "heartbeat"

        await stream.aclose()

    _run(scenario())


def _read_until(chunks: list[str], iterator, predicate) -> None:
    deadline = time.monotonic() + READ_DEADLINE_SECONDS
    for chunk in iterator:
        chunks.append(chunk)
        if predicate("".join(chunks)):
            return
        assert time.monotonic() < deadline, f"timed out; got: {chunks}"
    raise AssertionError(f"stream ended before predicate matched: {chunks}")


def test_events_endpoint_streams_the_order_lifecycle(tmp_path: Path) -> None:
    server = _LiveServer(
        create_app(db_path=tmp_path / "cafe.db", heartbeat_seconds=0.05)
    )
    try:
        with httpx2.Client(base_url=server.base_url) as client:
            with client.stream("GET", "/api/events") as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith(
                    "text/event-stream"
                )

                placed = client.post(
                    "/api/orders",
                    json={"customerName": "Lan", "items": [AFFOGATO_LINE]},
                )
                assert placed.status_code == 201
                order = placed.json()

                iterator = response.iter_text()
                chunks: list[str] = []
                _read_until(
                    chunks, iterator, lambda text: "event: order:new" in text
                )
                new_payload = _sse_payload("".join(chunks), "order:new")
                assert new_payload["order"]["id"] == order["id"]
                assert new_payload["order"]["orderNumber"] == order["orderNumber"]

                patched = client.patch(
                    f"/api/orders/{order['id']}/status",
                    json={"status": "completed"},
                )
                assert patched.status_code == 200

                _read_until(
                    chunks,
                    iterator,
                    lambda text: "event: order:status" in text,
                )
                status_payload = _sse_payload("".join(chunks), "order:status")
                assert status_payload["order"]["status"] == "completed"
    finally:
        server.close()


def test_a_closed_stream_does_not_break_later_broadcasts(
    tmp_path: Path,
) -> None:
    server = _LiveServer(
        create_app(db_path=tmp_path / "cafe.db", heartbeat_seconds=0.05)
    )
    try:
        with httpx2.Client(base_url=server.base_url) as client:
            with client.stream("GET", "/api/events") as response:
                assert response.status_code == 200
                iterator = response.iter_text()
                chunks: list[str] = []
                _read_until(chunks, iterator, lambda _: len(chunks) >= 1)

                with client.stream("GET", "/api/events") as second_response:
                    assert second_response.status_code == 200

                placed = client.post(
                    "/api/orders", json={"items": [AFFOGATO_LINE]}
                )
                assert placed.status_code == 201
                _read_until(
                    chunks, iterator, lambda text: "order:new" in text
                )
    finally:
        server.close()
