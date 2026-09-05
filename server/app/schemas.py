"""The API contract, as pydantic models.

One source of truth (design D4, D9): these models drive request
validation, the interactive documentation at /docs and /redoc, and
the generated TypeScript types consumed by the web app. Field names
serialize to camelCase to match menu.json and the OpenAPI surface.
"""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Union
from uuid import UUID

from pydantic import AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

NOTES_MAX_LENGTH = 200
QUANTITY_MIN = 1
QUANTITY_MAX = 10
CUSTOMER_NAME_MAX_LENGTH = 60


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(alias=to_camel, serialization_alias=to_camel),
        populate_by_name=True,
        from_attributes=True,
    )


class Temperature(str, Enum):
    """Service temperature of a drink, from the nong/da tags."""

    hot = "hot"
    iced = "iced"


class OrderStatus(str, Enum):
    """Lifecycle states from FR-7. Legal transitions: placed to
    in_progress, in_progress to completed, placed to completed,
    placed to cancelled. Everything else is rejected."""

    placed = "placed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ModifierDimension(str, Enum):
    """Which frozen customization dimension a modifier group expresses."""

    milk = "milk"
    sweetener_type = "sweetener_type"
    sweetness_level = "sweetness_level"
    cold_foam = "cold_foam"


class OrderRules(_ContractModel):
    """Frozen per-line bounds shared by both surfaces (PRD section 4)."""

    notes_max_length: int = Field(
        description="Maximum characters of free text per order line.",
        examples=[200],
    )
    min_quantity: int = Field(
        description="Minimum units per order line.",
        examples=[1],
    )
    max_quantity: int = Field(
        description="Maximum units per order line.",
        examples=[10],
    )


class Category(_ContractModel):
    """One of the five drink sections of the recipes drink menu."""

    id: str = Field(
        description="Stable category slug, e.g. ca-phe.",
        examples=["ca-phe"],
    )
    name_vi: str = Field(
        description="Section heading as printed on the house drink menu.",
        examples=["Cà Phê"],
    )
    name: str = Field(
        description="English section label.",
        examples=["Coffee"],
    )


class ModifierOption(_ContractModel):
    """One selectable option within a modifier group."""

    id: str = Field(
        description="Stable option slug, e.g. oat-milk.",
        examples=["oat-milk"],
    )
    name: str = Field(
        description="Display name spelled out to guests and baristas.",
        examples=["Oat milk"],
    )
    temperatures: list[Temperature] = Field(
        description="Service temperatures at which this option is offered.",
        examples=[["hot", "iced"]],
    )


class ModifierGroup(_ContractModel):
    """A customization group allowed on one or more menu items."""

    id: str = Field(
        description="Stable group slug, e.g. milk-matcha-latte.",
        examples=["milk-matcha-latte"],
    )
    dimension: ModifierDimension = Field(
        description="Which customization dimension this group expresses."
    )
    name: str = Field(
        description="Display name of the group.",
        examples=["Milk"],
    )
    required: bool = Field(
        description="True when the guest must make exactly one selection.",
        examples=[True],
    )
    options: list[ModifierOption] = Field(
        description="Selectable options, each scoped to temperatures."
    )
    default_option_id: Optional[str] = Field(
        default=None,
        description="Default selection when options do not vary by temperature.",
        examples=["condensed-milk"],
    )
    default_by_temperature: Optional[dict[str, str]] = Field(
        default=None,
        description="Default selection per temperature when options vary "
        "by temperature, e.g. Matcha Sữa hot defaults to whole milk.",
        examples=[{"hot": "whole-milk", "iced": "milk-plus-cream"}],
    )


class MenuItem(_ContractModel):
    """One orderable drink with its customization allowance."""

    id: str = Field(
        description="Stable item slug, e.g. matcha-sua.",
        examples=["matcha-sua"],
    )
    name: str = Field(
        description="English name.",
        examples=["Matcha Latte"],
    )
    name_vi: str = Field(
        description="Vietnamese name as printed on the house drink menu.",
        examples=["Matcha Sữa"],
    )
    description: str = Field(
        description="English description from the house drink menu.",
        examples=["Koicha whisked thick, your sweetener and milk of choice."],
    )
    category_id: str = Field(
        description="Owning category slug.",
        examples=["mat-cha"],
    )
    temperatures: list[Temperature] = Field(
        description="Offered service temperatures, at least one.",
        examples=[["hot", "iced"]],
    )
    modifier_group_ids: list[str] = Field(
        description="Customization groups allowed on this item, per cafe.md.",
        examples=[["milk-matcha-latte", "sweetener-matcha", "sweetness", "cold-foam"]],
    )
    image_path: Optional[str] = Field(
        default=None,
        description="Optional photo served at /images/menu/<itemId>.<ext>; "
        "absent means the on-brand placeholder.",
        examples=["/images/menu/matcha-sua.jpg"],
    )


class MenuDocument(_ContractModel):
    """The full validated menu served at GET /api/menu."""

    version: int = Field(
        description="Menu document format version.",
        examples=[1],
    )
    order_rules: OrderRules = Field(description="Frozen per-line bounds.")
    categories: list[Category] = Field(
        description="The five drink sections in display order."
    )
    modifier_groups: list[ModifierGroup] = Field(
        description="Shared customization groups referenced by items."
    )
    items: list[MenuItem] = Field(description="Every orderable drink.")


class OrderLine(_ContractModel):
    """One drink line in a placed order: the full selection snapshot
    (FR-2). Validated against the live menu: the item must exist,
    the temperature must be offered, and every selection must belong
    to a group the item allows at that temperature."""

    item_id: str = Field(
        description="Menu item id.",
        examples=["matcha-sua"],
    )
    temperature: Temperature = Field(
        description="Chosen service temperature; must be offered by the item."
    )
    quantity: int = Field(
        ge=QUANTITY_MIN,
        le=QUANTITY_MAX,
        description=f"Units of this line, {QUANTITY_MIN} to {QUANTITY_MAX}.",
        examples=[2],
    )
    milk_option_id: Optional[str] = Field(
        default=None,
        description="Chosen milk option; must belong to the item's milk "
        "group at the chosen temperature.",
        examples=["oat-milk"],
    )
    sweetener_type_id: Optional[str] = Field(
        default=None,
        description="Chosen sweetener; must belong to the item's sweetener "
        "group.",
        examples=["condensed-milk"],
    )
    sweetness_level_id: Optional[str] = Field(
        default=None,
        description="Chosen sweetness step; one of full, 75, 50, 25, none.",
        examples=["50"],
    )
    cold_foam_id: Optional[str] = Field(
        default=None,
        description="Chosen cold foam build; allowed only when temperature "
        "is iced.",
        examples=["foam-salted"],
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=NOTES_MAX_LENGTH,
        description=f"Free text for the barista, at most {NOTES_MAX_LENGTH} "
        "characters.",
        examples=["extra hot, please"],
    )


class OrderCreate(_ContractModel):
    """Request body of POST /api/orders."""

    customer_name: Optional[str] = Field(
        default=None,
        max_length=CUSTOMER_NAME_MAX_LENGTH,
        description="Optional name shown to the barista on the queue card.",
        examples=["Lan"],
    )
    items: list[OrderLine] = Field(
        min_length=1,
        description="Order lines; at least one.",
    )


class OrderLineView(_ContractModel):
    """An order line as served in responses, with every selection
    resolved to its display name so both surfaces can spell out
    modifiers without a menu lookup (FR-5)."""

    item_id: str = Field(description="Menu item id.", examples=["matcha-sua"])
    item_name: str = Field(description="English item name.", examples=["Matcha Latte"])
    item_name_vi: str = Field(
        description="Vietnamese item name.", examples=["Matcha Sữa"]
    )
    temperature: Temperature = Field(description="Chosen service temperature.")
    quantity: int = Field(
        ge=QUANTITY_MIN,
        le=QUANTITY_MAX,
        description=f"Units of this line, {QUANTITY_MIN} to {QUANTITY_MAX}.",
        examples=[2],
    )
    milk_option_id: Optional[str] = Field(
        default=None, description="Chosen milk option id.", examples=["oat-milk"]
    )
    milk_option_name: Optional[str] = Field(
        default=None, description="Chosen milk, spelled out.", examples=["Oat milk"]
    )
    sweetener_type_id: Optional[str] = Field(
        default=None,
        description="Chosen sweetener id.",
        examples=["condensed-milk"],
    )
    sweetener_type_name: Optional[str] = Field(
        default=None,
        description="Chosen sweetener, spelled out.",
        examples=["Condensed milk"],
    )
    sweetness_level_id: Optional[str] = Field(
        default=None, description="Chosen sweetness step id.", examples=["50"]
    )
    sweetness_level_name: Optional[str] = Field(
        default=None, description="Chosen sweetness, spelled out.", examples=["50%"]
    )
    cold_foam_id: Optional[str] = Field(
        default=None, description="Chosen cold foam id.", examples=["foam-salted"]
    )
    cold_foam_name: Optional[str] = Field(
        default=None,
        description="Chosen cold foam, spelled out.",
        examples=["Salted Cold Foam"],
    )
    notes: Optional[str] = Field(
        default=None, description="Free text for the barista.", examples=["extra hot"]
    )


class Order(_ContractModel):
    """An order as served by every order endpoint and both event
    payloads. Status changes live here; the daily number is short
    and callable (FR-3)."""

    id: UUID = Field(
        description="Order id, stable across its lifetime.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    order_number: int = Field(
        ge=1,
        description="Daily order number, reset each day.",
        examples=[7],
    )
    status: OrderStatus = Field(description="Current lifecycle status.")
    customer_name: Optional[str] = Field(
        default=None, description="Guest-given name, if any.", examples=["Lan"]
    )
    items: list[OrderLineView] = Field(
        min_length=1, description="Line snapshots with resolved names."
    )
    created_at: datetime = Field(
        description="Placement time, ISO 8601 UTC.",
        examples=["2026-09-03T15:04:05Z"],
    )
    updated_at: datetime = Field(
        description="Last transition time, ISO 8601 UTC.",
        examples=["2026-09-03T15:09:11Z"],
    )


class OrderStatusUpdate(_ContractModel):
    """Request body of PATCH /api/orders/{id}/status. Rejected with
    422 when the transition is illegal (FR-7)."""

    status: OrderStatus = Field(
        description="Target status; must be reachable from the current one.",
        examples=["in_progress"],
    )


class ApiError(_ContractModel):
    """Error shape for 422 validation and transition rejections and
    404 unknown orders: a specific message plus per-line detail
    strings (FR-7)."""

    error: str = Field(
        description="What went wrong, in one sentence.",
        examples=["order line 1 is invalid"],
    )
    details: list[str] = Field(
        description="Specific per-problem messages.",
        examples=[["item tan-cha is not on the menu"]],
    )


class OrderNewEvent(_ContractModel):
    """SSE payload broadcast when an order is placed; consumed by the
    barista surface."""

    type: Literal["order:new"] = Field(
        description="Event discriminator.", examples=["order:new"]
    )
    order: Order = Field(description="The freshly placed order.")


class OrderStatusEvent(_ContractModel):
    """SSE payload broadcast on every status transition; consumed by
    both surfaces."""

    type: Literal["order:status"] = Field(
        description="Event discriminator.", examples=["order:status"]
    )
    order: Order = Field(description="The order in its new state.")


class HeartbeatEvent(_ContractModel):
    """SSE keepalive sent every 25 seconds so idle connections and
    proxies keep the stream open."""

    type: Literal["heartbeat"] = Field(
        description="Event discriminator.", examples=["heartbeat"]
    )
    sent_at: datetime = Field(
        description="Heartbeat time, ISO 8601 UTC.",
        examples=["2026-09-03T15:04:30Z"],
    )


ServerEvent = Union[OrderNewEvent, OrderStatusEvent, HeartbeatEvent]

_ORDER_LINE_EXAMPLE = {
    "itemId": "matcha-sua",
    "temperature": "iced",
    "quantity": 2,
    "milkOptionId": "oat-milk",
    "sweetenerTypeId": "condensed-milk",
    "sweetnessLevelId": "50",
    "coldFoamId": "foam-salted",
    "notes": "extra hot, please",
}

_ORDER_LINE_VIEW_EXAMPLE = {
    "itemId": "matcha-sua",
    "itemName": "Matcha Latte",
    "itemNameVi": "Matcha Sữa",
    "temperature": "iced",
    "quantity": 2,
    "milkOptionId": "oat-milk",
    "milkOptionName": "Oat milk",
    "sweetenerTypeId": "condensed-milk",
    "sweetenerTypeName": "Condensed milk",
    "sweetnessLevelId": "50",
    "sweetnessLevelName": "50%",
    "coldFoamId": "foam-salted",
    "coldFoamName": "Salted Cold Foam",
    "notes": None,
}

_ORDER_EXAMPLE = {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "orderNumber": 7,
    "status": "placed",
    "customerName": "Lan",
    "items": [_ORDER_LINE_VIEW_EXAMPLE],
    "createdAt": "2026-09-03T15:04:05Z",
    "updatedAt": "2026-09-03T15:04:05Z",
}

_ORDER_IN_PROGRESS_EXAMPLE = _ORDER_EXAMPLE | {
    "status": "in_progress",
    "updatedAt": "2026-09-03T15:09:11Z",
}

OrderNewEvent.model_config["json_schema_extra"] = {
    "example": {"type": "order:new", "order": _ORDER_EXAMPLE}
}

OrderStatusEvent.model_config["json_schema_extra"] = {
    "example": {"type": "order:status", "order": _ORDER_IN_PROGRESS_EXAMPLE}
}

HeartbeatEvent.model_config["json_schema_extra"] = {
    "example": {"type": "heartbeat", "sentAt": "2026-09-03T15:04:30Z"}
}

OrderLine.model_config["json_schema_extra"] = {"example": _ORDER_LINE_EXAMPLE}

OrderCreate.model_config["json_schema_extra"] = {
    "example": {"customerName": "Lan", "items": [_ORDER_LINE_EXAMPLE]}
}

Order.model_config["json_schema_extra"] = {"example": _ORDER_EXAMPLE}

OrderLineView.model_config["json_schema_extra"] = {"example": _ORDER_LINE_VIEW_EXAMPLE}

OrderStatusUpdate.model_config["json_schema_extra"] = {"example": {"status": "in_progress"}}

ApiError.model_config["json_schema_extra"] = {
    "example": {
        "error": "order line 1 is invalid",
        "details": ["item tan-cha is not on the menu"],
    }
}

OrderRules.model_config["json_schema_extra"] = {
    "example": {"notesMaxLength": 200, "minQuantity": 1, "maxQuantity": 10}
}

Category.model_config["json_schema_extra"] = {
    "example": {"id": "ca-phe", "nameVi": "Cà Phê", "name": "Coffee"}
}

ModifierOption.model_config["json_schema_extra"] = {
    "example": {"id": "oat-milk", "name": "Oat milk", "temperatures": ["hot", "iced"]}
}

ModifierGroup.model_config["json_schema_extra"] = {
    "example": {
        "id": "milk-matcha-latte",
        "dimension": "milk",
        "name": "Milk",
        "required": True,
        "options": [
            {"id": "whole-milk", "name": "Whole milk", "temperatures": ["hot"]},
            {"id": "oat-milk", "name": "Oat milk", "temperatures": ["hot", "iced"]},
        ],
        "defaultByTemperature": {"hot": "whole-milk", "iced": "oat-milk"},
    }
}

MenuItem.model_config["json_schema_extra"] = {
    "example": {
        "id": "matcha-sua",
        "name": "Matcha Latte",
        "nameVi": "Matcha Sữa",
        "description": "Koicha whisked thick, your sweetener and milk of choice.",
        "categoryId": "mat-cha",
        "temperatures": ["hot", "iced"],
        "modifierGroupIds": [
            "milk-matcha-latte",
            "sweetener-matcha",
            "sweetness",
            "cold-foam",
        ],
        "imagePath": None,
    }
}

MenuDocument.model_config["json_schema_extra"] = {
    "example": {
        "version": 1,
        "orderRules": {"notesMaxLength": 200, "minQuantity": 1, "maxQuantity": 10},
        "categories": [{"id": "ca-phe", "nameVi": "Cà Phê", "name": "Coffee"}],
        "modifierGroups": [ModifierGroup.model_config["json_schema_extra"]["example"]],
        "items": [MenuItem.model_config["json_schema_extra"]["example"]],
    }
}

CONTRACT_MODELS = (
    MenuDocument,
    OrderRules,
    Category,
    ModifierGroup,
    ModifierOption,
    MenuItem,
    OrderLine,
    OrderCreate,
    OrderLineView,
    Order,
    OrderStatusUpdate,
    ApiError,
    OrderNewEvent,
    OrderStatusEvent,
    HeartbeatEvent,
)
