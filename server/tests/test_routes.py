"""Route integration tests: every endpoint from design section 4
against the real app with an isolated temp database per test.

Asserts the documented error shape 422 {"error", "details"} for
validation and transition rejections and 404 for unknown ids, the
daily number on creation, active listing order, restart persistence
(FR-9), and the static image mount.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

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


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "cafe.db"


@pytest.fixture
def client(db_path: Path):
    with TestClient(create_app(db_path=db_path)) as test_client:
        yield test_client


def place(client: TestClient, line: dict | None = None) -> dict:
    response = client.post(
        "/api/orders",
        json={"customerName": "Lan", "items": [line or AFFOGATO_LINE]},
    )
    assert response.status_code == 201
    return response.json()


def test_menu_serves_the_validated_document(client: TestClient) -> None:
    response = client.get("/api/menu")

    assert response.status_code == 200
    menu = response.json()
    assert menu["version"] == 1
    assert menu["orderRules"] == {
        "notesMaxLength": 200,
        "minQuantity": 1,
        "maxQuantity": 10,
    }
    assert [category["id"] for category in menu["categories"]] == [
        "ca-phe",
        "mat-cha",
        "tra",
        "giai-khat",
        "kem",
    ]
    assert len(menu["items"]) == 36
    cortado = next(item for item in menu["items"] if item["id"] == "cortado")
    assert cortado["nameVi"] == "Cortado"
    assert cortado["temperatures"] == ["hot"]
    assert cortado["imagePath"] is None


def test_place_order_returns_201_with_daily_number_and_snapshot(
    client: TestClient,
) -> None:
    first = place(client, MATCHA_LINE)
    second = place(client)

    assert first["orderNumber"] == 1
    assert first["status"] == "placed"
    assert first["customerName"] == "Lan"
    assert len(first["id"]) == 36
    line = first["items"][0]
    assert line["itemId"] == "matcha-sua"
    assert line["itemName"] == "Matcha Latte"
    assert line["itemNameVi"] == "Matcha Sữa"
    assert line["milkOptionName"] == "Oat milk"
    assert line["sweetenerTypeName"] == "Condensed milk"
    assert line["sweetnessLevelName"] == "50%"
    assert line["coldFoamName"] == "Salted Cold Foam"
    assert line["notes"] == "extra hot, please"
    assert first["createdAt"] == first["updatedAt"]
    assert second["orderNumber"] == 2


@pytest.mark.parametrize(
    "line,expected_detail",
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
            {**AFFOGATO_LINE, "milkOptionId": "whole-milk"},
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
            {
                "itemId": "sua-da",
                "temperature": "hot",
                "quantity": 1,
                "coldFoamId": "foam-salted",
            },
            "order line 1: cold foam option foam-salted is not offered hot "
            "on Vietnamese Iced Coffee",
        ),
    ],
    ids=[
        "unknown-item",
        "unoffered-temperature",
        "disallowed-group",
        "unknown-option",
        "option-wrong-temperature",
        "cold-foam-on-hot",
    ],
)
def test_menu_validation_rejections_return_specific_messages(
    client: TestClient, line: dict, expected_detail: str
) -> None:
    response = client.post("/api/orders", json={"items": [line]})

    assert response.status_code == 422
    assert response.json() == {
        "error": "order line 1 is invalid",
        "details": [expected_detail],
    }


@pytest.mark.parametrize(
    "line,fragment",
    [
        ({**AFFOGATO_LINE, "quantity": 0}, "items[0].quantity"),
        ({**AFFOGATO_LINE, "quantity": 11}, "items[0].quantity"),
        ({**AFFOGATO_LINE, "notes": "x" * 201}, "items[0].notes"),
        ({**AFFOGATO_LINE, "temperature": "frozen"}, "items[0].temperature"),
    ],
    ids=["quantity-low", "quantity-high", "notes-too-long", "bad-temperature"],
)
def test_schema_rejections_use_the_documented_error_shape(
    client: TestClient, line: dict, fragment: str
) -> None:
    response = client.post("/api/orders", json={"items": [line]})

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "request validation failed"
    assert any(fragment in detail for detail in body["details"])


def test_empty_order_is_rejected_with_documented_shape(
    client: TestClient,
) -> None:
    response = client.post("/api/orders", json={"items": []})

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "request validation failed"
    assert any("items" in detail for detail in body["details"])


def test_unknown_order_id_returns_404_shape(client: TestClient) -> None:
    response = client.get(f"/api/orders/{uuid4()}")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "order not found"
    assert len(body["details"]) == 1
    assert "no order with id" in body["details"][0]


def test_malformed_order_id_returns_422_shape(client: TestClient) -> None:
    response = client.get("/api/orders/not-a-uuid")

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "request validation failed"
    assert any("order_id" in detail for detail in body["details"])


def test_list_active_orders_newest_first(client: TestClient) -> None:
    first = place(client)
    second = place(client)
    third = place(client)
    client.patch(f"/api/orders/{second['id']}/status", json={"status": "in_progress"})
    client.patch(f"/api/orders/{third['id']}/status", json={"status": "completed"})

    active = client.get("/api/orders", params={"status": "active"})
    completed = client.get("/api/orders", params={"status": "completed"})
    everything = client.get("/api/orders")
    bogus = client.get("/api/orders", params={"status": "paused"})

    assert active.status_code == 200
    assert [order["id"] for order in active.json()] == [second["id"], first["id"]]
    assert [order["id"] for order in completed.json()] == [third["id"]]
    assert [order["id"] for order in everything.json()] == [
        third["id"],
        second["id"],
        first["id"],
    ]
    assert bogus.status_code == 422
    assert bogus.json()["error"] == "invalid status filter"


@pytest.mark.parametrize(
    "path",
    [
        ["in_progress"],
        ["completed"],
        ["cancelled"],
        ["in_progress", "completed"],
    ],
    ids=["start", "fast-path", "cancel", "start-then-complete"],
)
def test_patch_applies_every_legal_transition(
    client: TestClient, path: list[str]
) -> None:
    order = place(client)

    for target in path:
        response = client.patch(
            f"/api/orders/{order['id']}/status", json={"status": target}
        )
        assert response.status_code == 200
        assert response.json()["status"] == target


def test_patch_rejects_illegal_transition_with_specific_message(
    client: TestClient,
) -> None:
    order = place(client)
    client.patch(f"/api/orders/{order['id']}/status", json={"status": "completed"})

    response = client.patch(
        f"/api/orders/{order['id']}/status", json={"status": "in_progress"}
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": "invalid status transition",
        "details": ["order 1 cannot move from completed to in_progress"],
    }


def test_patch_unknown_order_returns_404(client: TestClient) -> None:
    response = client.patch(
        f"/api/orders/{uuid4()}/status", json={"status": "cancelled"}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "order not found"


def test_orders_survive_a_restart_on_the_same_database(
    db_path: Path,
) -> None:
    with TestClient(create_app(db_path=db_path)) as first_client:
        created = place(first_client, MATCHA_LINE)

    with TestClient(create_app(db_path=db_path)) as second_client:
        fetched = second_client.get(f"/api/orders/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json() == created

        follow_up = place(second_client)
        assert follow_up["orderNumber"] == 2


def test_images_mount_serves_files_from_the_assets_directory(
    db_path: Path, tmp_path: Path
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "matcha-sua.jpg").write_bytes(b"pretend-jpeg-bytes")

    with TestClient(create_app(db_path=db_path, assets_dir=assets)) as client:
        served = client.get("/images/menu/matcha-sua.jpg")
        missing = client.get("/images/menu/does-not-exist.jpg")

    assert served.status_code == 200
    assert served.content == b"pretend-jpeg-bytes"
    assert missing.status_code == 404
