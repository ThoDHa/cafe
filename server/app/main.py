"""App assembly: contract models, order routes, SSE hub, static images.

create_app closes over real instances with injectable paths so every
test runs against an isolated database and asset directory. The
module-level app serves /docs, /redoc, and uvicorn (app.main:app)
with defaults from the environment (CAFE_DB_PATH).
"""

import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic.json_schema import models_json_schema

from app import schemas
from app.db import OrderStore
from app.events import HEARTBEAT_SECONDS, EventHub
from app.orders import ApiError, OrderService
from app.routes import create_router

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

REPO_ROOT = Path(__file__).resolve().parents[2]
MENU_PATH = REPO_ROOT / "menu" / "menu.json"
DEFAULT_ASSETS_DIR = REPO_ROOT / "menu" / "assets"

REQUEST_VALIDATION_ERROR = "request validation failed"


def load_menu(path: Path = MENU_PATH) -> schemas.MenuDocument:
    return schemas.MenuDocument.model_validate(json.loads(path.read_text()))


def _loc_text(loc: tuple) -> str:
    text = ""
    for piece in loc:
        if isinstance(piece, int):
            text += f"[{piece}]"
        elif text:
            text += f".{piece}"
        else:
            text += str(piece)
    return text


def _contract_openapi_for(application: FastAPI) -> Callable[[], dict]:
    def _openapi() -> dict:
        if application.openapi_schema is not None:
            return application.openapi_schema
        openapi_schema = get_openapi(
            title=API_TITLE,
            version=API_VERSION,
            description=API_DESCRIPTION,
            routes=application.routes,
        )
        _, definitions = models_json_schema(
            [(model, "validation") for model in schemas.CONTRACT_MODELS],
            ref_template="#/components/schemas/{model}",
        )
        schemas_by_name = openapi_schema.setdefault("components", {}).setdefault(
            "schemas", {}
        )
        schemas_by_name.update(definitions["$defs"])
        application.openapi_schema = openapi_schema
        return openapi_schema

    return _openapi


def create_app(
    *,
    db_path: Path | None = None,
    assets_dir: Path | None = None,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    menu_path: Path = MENU_PATH,
) -> FastAPI:
    menu = load_menu(menu_path)
    store = OrderStore(db_path)
    service = OrderService(store, menu)
    hub = EventHub(heartbeat_seconds)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        store.close()

    application = FastAPI(
        title=API_TITLE,
        description=API_DESCRIPTION,
        version=API_VERSION,
        lifespan=lifespan,
    )
    application.include_router(create_router(service, hub, menu))

    assets = Path(assets_dir) if assets_dir is not None else DEFAULT_ASSETS_DIR
    assets.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/images/menu", StaticFiles(directory=assets), name="menu-images"
    )

    @application.exception_handler(ApiError)
    async def _api_error(
        _request: Request, exc: ApiError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "details": exc.details},
        )

    @application.exception_handler(RequestValidationError)
    async def _request_validation(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            f"{_loc_text(error['loc'])}: {error['msg']}" for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": REQUEST_VALIDATION_ERROR, "details": details},
        )

    application.openapi = _contract_openapi_for(application)
    return application


app = create_app()
