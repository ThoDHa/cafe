"""Round-trip and bootstrap tests for the sqlite order store.

The store is the FR-9 persistence gate: every field written must
survive a close and reopen unchanged, the file must run in WAL mode
per design D2, and CAFE_DB_PATH must relocate it for volumes.
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.db import DEFAULT_DB_PATH, DB_PATH_ENV, OrderStore, resolve_db_path
from app.schemas import OrderLineView

MATCHA_LINE = dict(
    item_id="matcha-sua",
    item_name="Matcha Latte",
    item_name_vi="Matcha Sữa",
    temperature="iced",
    quantity=2,
    milk_option_id="oat-milk",
    milk_option_name="Oat milk",
    sweetener_type_id="condensed-milk",
    sweetener_type_name="Condensed milk",
    sweetness_level_id="50",
    sweetness_level_name="50%",
    cold_foam_id="foam-salted",
    cold_foam_name="Salted Cold Foam",
    notes=None,
)


def line_view(**overrides: object) -> OrderLineView:
    fields = {**MATCHA_LINE, **overrides}
    return OrderLineView.model_validate(fields)


def place(
    store: OrderStore,
    *,
    customer_name: str | None = "Lan",
    items: list[OrderLineView] | None = None,
    now: datetime | None = None,
):
    return store.insert_order(
        items=items if items is not None else [line_view()],
        customer_name=customer_name,
        now=now if now is not None else datetime.now(UTC),
    )


def test_order_round_trips_across_reopen(tmp_path) -> None:
    db_path = tmp_path / "cafe.db"
    store = OrderStore(db_path)
    order = place(store, customer_name="Lan")
    store.close()

    reopened = OrderStore(db_path)
    fetched = reopened.get_order(order.id)

    assert fetched == order
    assert fetched.order_number == 1
    assert fetched.status == "placed"
    assert fetched.customer_name == "Lan"
    assert fetched.items[0].item_name_vi == "Matcha Sữa"
    assert fetched.items[0].milk_option_name == "Oat milk"


def test_order_round_trips_with_null_customer_name(tmp_path) -> None:
    store = OrderStore(tmp_path / "cafe.db")
    order = place(store, customer_name=None)
    store.close()

    fetched = OrderStore(tmp_path / "cafe.db").get_order(order.id)
    assert fetched is not None
    assert fetched.customer_name is None


def test_order_numbers_increment_within_a_day(tmp_path) -> None:
    store = OrderStore(tmp_path / "cafe.db")
    first = place(store)
    second = place(store)
    third = place(store)

    assert [first.order_number, second.order_number, third.order_number] == [1, 2, 3]


def test_list_orders_returns_newest_first(tmp_path) -> None:
    store = OrderStore(tmp_path / "cafe.db")
    place(store)
    place(store)
    newest = place(store)

    listed = store.list_orders()

    assert len(listed) == 3
    assert listed[0].id == newest.id


def test_list_orders_filters_by_status(tmp_path) -> None:
    store = OrderStore(tmp_path / "cafe.db")
    placed = place(store)
    in_progress = place(store)
    now = datetime.now(UTC)
    store.update_status(in_progress.id, "in_progress", now + timedelta(seconds=1))

    active = store.list_orders(statuses=["placed", "in_progress"])
    only_completed = store.list_orders(statuses=["completed"])

    assert [order.id for order in active] == [in_progress.id, placed.id]
    assert only_completed == []


def test_update_status_changes_status_and_updated_at(tmp_path) -> None:
    store = OrderStore(tmp_path / "cafe.db")
    created = place(store, now=datetime(2026, 9, 3, 7, 0, tzinfo=UTC))

    updated = store.update_status(
        created.id, "in_progress", datetime(2026, 9, 3, 7, 5, tzinfo=UTC)
    )

    assert updated is not None
    assert updated.status == "in_progress"
    assert updated.created_at == created.created_at
    assert updated.updated_at > created.updated_at


def test_update_status_of_unknown_order_returns_none(tmp_path) -> None:
    store = OrderStore(tmp_path / "cafe.db")
    assert store.update_status(uuid4(), "cancelled", datetime.now(UTC)) is None


def test_get_order_of_unknown_id_returns_none(tmp_path) -> None:
    store = OrderStore(tmp_path / "cafe.db")
    assert store.get_order(uuid4()) is None


def test_store_runs_the_database_in_wal_mode(tmp_path) -> None:
    db_path = tmp_path / "cafe.db"
    OrderStore(db_path).close()

    mode = sqlite3.connect(db_path).execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_resolve_db_path_honors_env_override(tmp_path, monkeypatch) -> None:
    override = tmp_path / "volume" / "cafe.db"
    monkeypatch.setenv(DB_PATH_ENV, str(override))

    assert resolve_db_path() == override


def test_default_db_path_points_at_server_data() -> None:
    assert DEFAULT_DB_PATH.name == "cafe.db"
    assert DEFAULT_DB_PATH.parent.name == "data"
    assert DEFAULT_DB_PATH.parent.parent.name == "server"
