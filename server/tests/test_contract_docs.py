"""Guards design D9: /docs and /openapi.json document the contract.

Every pydantic model in the contract must surface in the OpenAPI
schema with a description, and request/response shapes must expose
field-level descriptions, examples, and the frozen bounds.
"""

from fastapi.testclient import TestClient

from app.main import API_VERSION, app

client = TestClient(app)

CONTRACT_MODELS = [
    "MenuDocument",
    "OrderRules",
    "Category",
    "ModifierGroup",
    "ModifierOption",
    "MenuItem",
    "OrderLine",
    "OrderCreate",
    "OrderLineView",
    "Order",
    "OrderStatusUpdate",
    "ApiError",
    "OrderNewEvent",
    "OrderStatusEvent",
    "HeartbeatEvent",
]


def openapi() -> dict:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_openapi_exposes_every_contract_model() -> None:
    schemas = openapi()["components"]["schemas"]
    missing = set(CONTRACT_MODELS) - set(schemas)
    assert not missing, f"undocumented contract models: {sorted(missing)}"


def test_every_contract_model_is_documented_with_examples() -> None:
    schemas = openapi()["components"]["schemas"]
    for name in CONTRACT_MODELS:
        model = schemas[name]
        assert model.get("description"), f"{name} lacks a description"
        assert model.get("example"), f"{name} lacks an example"


def test_order_line_documents_the_frozen_bounds() -> None:
    line = openapi()["components"]["schemas"]["OrderLine"]["properties"]
    quantity = line["quantity"]
    assert quantity["description"]
    assert quantity["examples"]
    assert quantity["minimum"] == 1
    assert quantity["maximum"] == 10
    notes = line["notes"]
    assert notes["description"]
    string_variants = [
        variant for variant in notes["anyOf"] if variant.get("type") == "string"
    ]
    assert string_variants[0]["maxLength"] == 200


def test_order_documents_its_fields() -> None:
    order = openapi()["components"]["schemas"]["Order"]["properties"]
    for field in ("orderNumber", "status", "items", "createdAt", "updatedAt"):
        assert order[field]["description"], f"Order.{field} lacks a description"


def test_api_metadata_is_set() -> None:
    info = openapi()["info"]
    assert info["title"] == "Cafe Ông Thọ ordering API"
    assert info["description"]
    assert info["version"] == API_VERSION


def test_docs_serves_swagger_ui() -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()
