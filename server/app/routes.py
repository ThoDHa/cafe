"""API routes over the order service and SSE hub (design section 4).

The router is a factory so create_app can close over real instances
with test-injected paths. Service calls run in a worker thread via
asyncio.to_thread (sqlite access blocks); broadcasts happen on the
event loop thread, where the hub's queues live.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app import schemas
from app.events import EventHub
from app.orders import OrderService


def create_router(
    service: OrderService, hub: EventHub, menu: schemas.MenuDocument
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get(
        "/menu",
        response_model=schemas.MenuDocument,
        summary="Read the menu",
        description="The full validated menu: five categories, modifier "
        "groups, and every orderable drink with its customization "
        "allowance (FR-1).",
    )
    async def read_menu() -> schemas.MenuDocument:
        return menu

    @router.post(
        "/orders",
        response_model=schemas.Order,
        status_code=201,
        summary="Place an order",
        description="Validates every line against the live menu and assigns "
        "the daily order number (FR-3, FR-7). Broadcasts order:new.",
        responses={422: {"model": schemas.ApiError}},
    )
    async def place_order(payload: schemas.OrderCreate) -> schemas.Order:
        order = await asyncio.to_thread(service.create, payload)
        hub.broadcast(schemas.OrderNewEvent(type="order:new", order=order))
        return order

    @router.get(
        "/orders",
        response_model=list[schemas.Order],
        summary="List orders",
        description="Newest first. Filter by status=active (placed plus "
        "in_progress) for the barista board, or by a single lifecycle "
        "status (FR-5).",
        responses={422: {"model": schemas.ApiError}},
    )
    async def list_orders(status: str | None = None) -> list[schemas.Order]:
        return await asyncio.to_thread(service.list, status)

    @router.get(
        "/orders/{order_id}",
        response_model=schemas.Order,
        summary="Read one order",
        description="One order by id: the guest status view and the "
        "reconnect refetch (FR-4).",
        responses={404: {"model": schemas.ApiError}},
    )
    async def read_order(order_id: UUID) -> schemas.Order:
        return await asyncio.to_thread(service.get, order_id)

    @router.patch(
        "/orders/{order_id}/status",
        response_model=schemas.Order,
        summary="Transition an order",
        description="Applies one legal transition (placed to in_progress, "
        "in_progress to completed, placed to completed, placed to "
        "cancelled) and broadcasts order:status (FR-5, FR-7).",
        responses={404: {"model": schemas.ApiError}, 422: {"model": schemas.ApiError}},
    )
    async def update_status(
        order_id: UUID, payload: schemas.OrderStatusUpdate
    ) -> schemas.Order:
        order = await asyncio.to_thread(
            service.transition, order_id, payload.status
        )
        hub.broadcast(schemas.OrderStatusEvent(type="order:status", order=order))
        return order

    @router.get(
        "/events",
        summary="Live order events (SSE)",
        description="Server-Sent Events stream: order:new on placement, "
        "order:status on every transition, and a heartbeat every 25 "
        "seconds while idle. Payloads are the camelCase event models "
        "from the schema.",
    )
    async def events() -> StreamingResponse:
        queue = hub.subscribe()
        return StreamingResponse(
            hub.stream(queue),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return router
