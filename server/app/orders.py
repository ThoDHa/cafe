"""Order lifecycle service: menu validation, FR-7 transitions, and
daily numbering, on top of the sqlite OrderStore.

Routes join this module at the assembly checkpoint; everything here is
framework-free so the transition matrix and validation rules stay
unit-testable.
"""

from datetime import UTC, datetime
from uuid import UUID

from app import schemas
from app.db import OrderStore

LEGAL_TRANSITIONS: dict[schemas.OrderStatus, frozenset[schemas.OrderStatus]] = {
    schemas.OrderStatus.placed: frozenset(
        {
            schemas.OrderStatus.in_progress,
            schemas.OrderStatus.completed,
            schemas.OrderStatus.cancelled,
        }
    ),
    schemas.OrderStatus.in_progress: frozenset({schemas.OrderStatus.completed}),
    schemas.OrderStatus.completed: frozenset(),
    schemas.OrderStatus.cancelled: frozenset(),
}

ACTIVE_STATUSES = (schemas.OrderStatus.placed, schemas.OrderStatus.in_progress)

_SELECTION_FIELDS: tuple[tuple[str, schemas.ModifierDimension], ...] = (
    ("milk_option_id", schemas.ModifierDimension.milk),
    ("sweetener_type_id", schemas.ModifierDimension.sweetener_type),
    ("sweetness_level_id", schemas.ModifierDimension.sweetness_level),
    ("cold_foam_id", schemas.ModifierDimension.cold_foam),
)

_DIMENSION_LABELS = {
    dimension: dimension.value.replace("_", " ")
    for dimension in schemas.ModifierDimension
}


class ApiError(Exception):
    """Raised for every documented failure: 422 validation and
    transition rejections, 404 unknown orders. Rendered by one handler
    into the design's {"error", "details"} shape."""

    def __init__(self, status_code: int, error: str, details: list[str]) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error
        self.details = details


def _not_found(order_id: UUID) -> ApiError:
    return ApiError(404, "order not found", [f"no order with id {order_id}"])


class OrderService:
    def __init__(self, store: OrderStore, menu: schemas.MenuDocument) -> None:
        self._store = store
        self._items_by_id = {item.id: item for item in menu.items}
        self._groups_by_id = {
            group.id: group for group in menu.modifier_groups
        }

    def create(
        self, payload: schemas.OrderCreate, now: datetime | None = None
    ) -> schemas.Order:
        problems: list[tuple[int, str]] = []
        for index, line in enumerate(payload.items, start=1):
            problems.extend(self._line_problems(index, line))
        if problems:
            raise self._invalid_order_error(problems)
        snapshots = [self._line_view(line) for line in payload.items]
        return self._store.insert_order(
            items=snapshots,
            customer_name=payload.customer_name,
            now=now if now is not None else datetime.now(UTC),
        )

    def get(self, order_id: UUID) -> schemas.Order:
        order = self._store.get_order(order_id)
        if order is None:
            raise _not_found(order_id)
        return order

    def transition(
        self,
        order_id: UUID,
        target: schemas.OrderStatus,
        now: datetime | None = None,
    ) -> schemas.Order:
        current = self.get(order_id)
        if target not in LEGAL_TRANSITIONS[current.status]:
            raise ApiError(
                422,
                "invalid status transition",
                [
                    f"order {current.order_number} cannot move from "
                    f"{current.status.value} to {target.value}"
                ],
            )
        updated = self._store.update_status(
            order_id,
            target,
            now if now is not None else datetime.now(UTC),
        )
        if updated is None:
            raise _not_found(order_id)
        return updated

    def list(self, status: str | None = None) -> list[schemas.Order]:
        if status is None:
            return self._store.list_orders()
        if status == "active":
            return self._store.list_orders(statuses=list(ACTIVE_STATUSES))
        try:
            target = schemas.OrderStatus(status)
        except ValueError:
            raise ApiError(
                422,
                "invalid status filter",
                [
                    "status must be 'active' or one of: "
                    + ", ".join(member.value for member in schemas.OrderStatus)
                    + f"; got '{status}'"
                ],
            ) from None
        return self._store.list_orders(statuses=[target])

    def _line_problems(
        self, index: int, line: schemas.OrderLine
    ) -> list[tuple[int, str]]:
        item = self._items_by_id.get(line.item_id)
        if item is None:
            return [(index, f"order line {index}: item {line.item_id} is not on the menu")]
        problems: list[tuple[int, str]] = []
        if line.temperature not in item.temperatures:
            problems.append(
                (index, f"order line {index}: {item.name} is not offered {line.temperature.value}")
            )
        for field, dimension in _SELECTION_FIELDS:
            option_id = getattr(line, field)
            if option_id is None:
                continue
            label = _DIMENSION_LABELS[dimension]
            groups = self._groups_for(item, dimension)
            if not groups:
                problems.append(
                    (
                        index,
                        f"order line {index}: {item.name} does not offer {label} selections",
                    )
                )
                continue
            offered = [
                option
                for group in groups
                for option in group.options
                if option.id == option_id
                and line.temperature in option.temperatures
            ]
            if offered:
                continue
            known = {
                option.id for group in groups for option in group.options
            }
            if option_id not in known:
                problems.append(
                    (
                        index,
                        f"order line {index}: unknown {label} option {option_id} "
                        f"for {item.name}",
                    )
                )
            else:
                problems.append(
                    (
                        index,
                        f"order line {index}: {label} option {option_id} is not "
                        f"offered {line.temperature.value} on {item.name}",
                    )
                )
        return problems

    def _invalid_order_error(
        self, problems: list[tuple[int, str]]
    ) -> ApiError:
        bad_lines = sorted({index for index, _ in problems})
        if len(bad_lines) == 1:
            error = f"order line {bad_lines[0]} is invalid"
        else:
            joined = ", ".join(str(index) for index in bad_lines)
            error = f"order lines {joined} are invalid"
        return ApiError(422, error, [message for _, message in problems])

    def _line_view(self, line: schemas.OrderLine) -> schemas.OrderLineView:
        item = self._items_by_id[line.item_id]

        def name_of(dimension: schemas.ModifierDimension, option_id: str) -> str | None:
            for group in self._groups_for(item, dimension):
                for option in group.options:
                    if option.id == option_id:
                        return option.name
            return None

        return schemas.OrderLineView(
            item_id=item.id,
            item_name=item.name,
            item_name_vi=item.name_vi,
            temperature=line.temperature,
            quantity=line.quantity,
            milk_option_id=line.milk_option_id,
            milk_option_name=name_of(
                schemas.ModifierDimension.milk, line.milk_option_id
            )
            if line.milk_option_id
            else None,
            sweetener_type_id=line.sweetener_type_id,
            sweetener_type_name=name_of(
                schemas.ModifierDimension.sweetener_type, line.sweetener_type_id
            )
            if line.sweetener_type_id
            else None,
            sweetness_level_id=line.sweetness_level_id,
            sweetness_level_name=name_of(
                schemas.ModifierDimension.sweetness_level, line.sweetness_level_id
            )
            if line.sweetness_level_id
            else None,
            cold_foam_id=line.cold_foam_id,
            cold_foam_name=name_of(
                schemas.ModifierDimension.cold_foam, line.cold_foam_id
            )
            if line.cold_foam_id
            else None,
            notes=line.notes,
        )

    def _groups_for(
        self, item: schemas.MenuItem, dimension: schemas.ModifierDimension
    ) -> list[schemas.ModifierGroup]:
        return [
            self._groups_by_id[group_id]
            for group_id in item.modifier_group_ids
            if self._groups_by_id[group_id].dimension == dimension
        ]
