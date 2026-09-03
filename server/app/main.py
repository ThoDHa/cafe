"""App assembly: API metadata and the documented contract surface.

Bare by design in the contract checkpoint: routes, db, and SSE land
in CAFE-1-2. The OpenAPI schema already carries every contract model
so /docs, /redoc, and the TypeScript generation pipeline work today.
"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic.json_schema import models_json_schema

from app import schemas

API_TITLE = "Cafe Ông Thọ ordering API"
API_DESCRIPTION = (
    "Ordering API for the Cafe Ông Thọ home cafe. Guests browse the "
    "menu, customize drinks within each item's rules, and follow their "
    "order's status live; the barista surface works the queue and moves "
    "orders through placed, in_progress, completed, or cancelled. "
    "Liveness arrives over Server-Sent Events at /api/events. The menu "
    "is the five drink sections of the recipes (Cà Phê, Mát-cha, Trà, "
    "Giải Khát, Kem) with the customization model frozen for v1: "
    "temperature, milk, sweetener type, sweetness level, cold foam on "
    "iced only, notes up to 200 characters, quantity 1 to 10 per line."
)
API_VERSION = "0.1.0"

app = FastAPI(title=API_TITLE, description=API_DESCRIPTION, version=API_VERSION)


def _include_contract_models(openapi_schema: dict) -> dict:
    _, definitions = models_json_schema(
        [(model, "validation") for model in schemas.CONTRACT_MODELS],
        ref_template="#/components/schemas/{model}",
    )
    schemas_by_name = openapi_schema.setdefault("components", {}).setdefault(
        "schemas", {}
    )
    schemas_by_name.update(definitions["$defs"])
    return openapi_schema


def _contract_openapi() -> dict:
    if app.openapi_schema is not None:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        routes=app.routes,
    )
    app.openapi_schema = _include_contract_models(openapi_schema)
    return app.openapi_schema


app.openapi = _contract_openapi
