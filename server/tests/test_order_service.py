"""Unit tests for the order lifecycle service.

Covers the FR-7 transition matrix (every legal and illegal pair),
creation validation against the live menu with a specific message per
rejection path, and daily numbering across the local-midnight
boundary.
"""

from datetime import UTC, datetime, time, timedelta
from functools import cache
from pathlib import Path
from uuid import uuid4

import pytest

from app.db import OrderStore
from app.orders import ApiError, OrderService
from app.schemas import MenuDocument, OrderCreate, OrderStatus

MENU_PATH = Path(__file__).resolve().parents[2] / "menu" / "menu.json"

AFFOGATO_LINE = {"itemId": "ca-phe-kem", "temperature": "hot", "quantity": 1}

MATCHA_LINE = {
    "itemId": "matcha-sua",
    "temperature": "iced",
    "quantity": 2,
    "milkOptionId": "oat-milk",
    "sweetenerTypeId": "condensed-milk",
    "sweetnessLevelId": "50",
    "coldFoamId": "foam-salted",
    "notes": "extra hot, please",
}


@cache
def menu() -> MenuDocument:
    return MenuDocument.model_validate_json(MENU_PATH.read_text(encoding="utf-8"))


def make_service(tmp_path: Path) -> OrderService:
    return OrderService(OrderStore(tmp_path / "cafe.db"), menu())


def payload(line: dict | None = None) -> OrderCreate:
    return OrderCreate.model_validate(
        {"customerName": "Lan", "items": [line if line is not None else AFFOGATO_LINE]}
    )


def place(service: OrderService, line: dict | None = None):
    return service.create(payload(line))


def order_in_status(service: OrderService, status: OrderStatus):
    if status == OrderStatus.placed:
        return place(service)
    order = place(service)
    return service.transition(order.id, status)


ALL_STATUS_PAIRS = [
    (start, target) for start in OrderStatus for target in OrderStatus
]
LEGAL_PAIRS = {
    (OrderStatus.placed, OrderStatus.in_progress),
    (OrderStatus.in_progress, OrderStatus.completed),
    (OrderStatus.placed, OrderStatus.completed),
    (OrderStatus.placed, OrderStatus.cancelled),
}


def test_create_snapshots_resolved_names_and_assigns_number(tmp_path) -> None:
    service = make_service(tmp_path)
    now = datetime(2026, 9, 3, 7, 30, tzinfo=UTC)

    order = service.create(payload(MATCHA_LINE), now=now)

    assert order.order_number == 1
    assert order.status == OrderStatus.placed
    assert order.customer_name == "Lan"
    assert order.created_at == now
    assert order.updated_at == now
    line = order.items[0]
    assert line.item_name == "Matcha Latte"
    assert line.item_name_vi == "Matcha Sữa"
    assert line.milk_option_name == "Oat milk"
    assert line.sweetener_type_name == "Condensed milk"
    assert line.sweetness_level_name == "50%"
    assert line.cold_foam_name == "Salted Cold Foam"
    assert line.notes == "extra hot, please"


def test_create_accepts_boundary_values(tmp_path) -> None:
    service = make_service(tmp_path)

    max_quantity = service.create(
        payload({**AFFOGATO_LINE, "quantity": 10, "notes": "x" * 200})
    )
    minimal = service.create(payload())

    assert max_quantity.items[0].quantity == 10
    assert minimal.items[0].notes is None


@pytest.mark.parametrize(
    "line,detail",
    [
        (
            {"itemId": "tan-cha", "temperature": "hot", "quantity": 1},
            "order line 1: item tan-cha is not on the menu",
        ),
        (
            {"itemId": "cortado", "temperature": "iced", "quantity": 1},
            "order line 1: Cortado is not offered iced",
        ),
        (
            {
                **AFFOGATO_LINE,
                "milkOptionId": "whole-milk",
            },
            "order line 1: Affogato does not offer milk selections",
        ),
        (
            {**MATCHA_LINE, "milkOptionId": "buffalo-milk"},
            "order line 1: unknown milk option buffalo-milk for Matcha Latte",
        ),
        (
            {**MATCHA_LINE, "milkOptionId": "whole-milk"},
            "order line 1: milk option whole-milk is not offered iced on Matcha Latte",
        ),
        (
            {"itemId": "sua-da", "temperature": "hot", "quantity": 1, "coldFoamId": "foam-salted"},
            "order line 1: cold foam option foam-salted is not offered hot on Vietnamese Iced Coffee",
        ),
        (
            {**AFFOGATO_LINE, "sweetenerTypeId": "condensed-milk"},
            "order line 1: Affogato does not offer sweetener type selections",
        ),
    ],
    ids=[
        "unknown-item",
        "unoffered-temperature",
        "disallowed-group",
        "unknown-option",
        "option-wrong-temperature",
        "cold-foam-on-hot",
        "sweetener-on-plain-item",
    ],
)
def test_create_rejects_invalid_lines_with_specific_details(
    tmp_path, line: dict, detail: str
) -> None:
    service = make_service(tmp_path)

    with pytest.raises(ApiError) as excinfo:
        service.create(payload(line))

    assert excinfo.value.status_code == 422
    assert excinfo.value.error == "order line 1 is invalid"
    assert detail in excinfo.value.details


def test_create_reports_every_invalid_line(tmp_path) -> None:
    service = make_service(tmp_path)
    order = OrderCreate.model_validate(
        {
            "items": [
                {"itemId": "tan-cha", "temperature": "hot", "quantity": 1},
                {"itemId": "cortado", "temperature": "iced", "quantity": 1},
            ]
        }
    )

    with pytest.raises(ApiError) as excinfo:
        service.create(order)

    assert excinfo.value.error == "order lines 1, 2 are invalid"
    assert len(excinfo.value.details) == 2


@pytest.mark.parametrize(
    "start,target", ALL_STATUS_PAIRS, ids=lambda value: value.value if isinstance(value, OrderStatus) else ""
)
def test_transition_matrix(tmp_path, start: OrderStatus, target: OrderStatus) -> None:
    service = make_service(tmp_path)
    order = order_in_status(service, start)

    if (start, target) in LEGAL_PAIRS:
        updated = service.transition(order.id, target)
        assert updated.status == target
        assert updated.updated_at >= updated.created_at
    else:
        with pytest.raises(ApiError) as excinfo:
            service.transition(order.id, target)
        assert excinfo.value.status_code == 422
        assert excinfo.value.error == "invalid status transition"
        assert (
            f"order {order.order_number} cannot move from {start.value} "
            f"to {target.value}" in excinfo.value.details
        )


def test_transition_of_unknown_order_raises_404(tmp_path) -> None:
    service = make_service(tmp_path)

    with pytest.raises(ApiError) as excinfo:
        service.transition(uuid4(), OrderStatus.cancelled)

    assert excinfo.value.status_code == 404
    assert excinfo.value.error == "order not found"


def test_get_unknown_order_raises_404(tmp_path) -> None:
    service = make_service(tmp_path)

    with pytest.raises(ApiError) as excinfo:
        service.get(uuid4())

    assert excinfo.value.status_code == 404


def test_order_numbers_reset_at_local_midnight(tmp_path) -> None:
    service = make_service(tmp_path)
    local_now = datetime.now().astimezone()
    before_midnight = datetime.combine(
        local_now.date() - timedelta(days=1), time(23, 59), tzinfo=local_now.tzinfo
    )
    after_midnight = datetime.combine(
        local_now.date(), time(0, 1), tzinfo=local_now.tzinfo
    )

    late_evening = service.create(payload(), now=before_midnight)
    first_today = service.create(payload(), now=after_midnight)
    second_today = service.create(
        payload(), now=after_midnight + timedelta(minutes=1)
    )

    assert late_evening.order_number == 1
    assert first_today.order_number == 1
    assert second_today.order_number == 2
    assert first_today.created_at == after_midnight


def test_list_returns_newest_first_with_filters(tmp_path) -> None:
    service = make_service(tmp_path)
    placed = place(service)
    started = place(service)
    service.transition(started.id, OrderStatus.in_progress)
    done = place(service)
    service.transition(done.id, OrderStatus.completed)
    cancelled = place(service)
    service.transition(cancelled.id, OrderStatus.cancelled)

    active = service.list("active")
    completed = service.list("completed")
    everything = service.list()

    assert [order.id for order in active] == [started.id, placed.id]
    assert [order.id for order in completed] == [done.id]
    assert [order.id for order in everything] == [
        cancelled.id,
        done.id,
        started.id,
        placed.id,
    ]


def test_list_rejects_unknown_status_filter(tmp_path) -> None:
    service = make_service(tmp_path)

    with pytest.raises(ApiError) as excinfo:
        service.list("paused")

    assert excinfo.value.status_code == 422
    assert excinfo.value.error == "invalid status filter"
