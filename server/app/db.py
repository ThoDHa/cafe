"""SQLite order storage: WAL-mode sqlite3 behind a small interface.

Design D2 and section 3.2: one orders table holding full line
snapshots as JSON text, daily order numbers assigned inside the insert
transaction, and the file location overridable through CAFE_DB_PATH
for the container volume. Timestamps are stored as UTC ISO 8601 with
microsecond precision so lexicographic comparison matches chronology.
"""

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app import schemas

DB_PATH_ENV = "CAFE_DB_PATH"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "cafe.db"

_CREATE_ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    order_number INTEGER NOT NULL,
    customer_name TEXT,
    status TEXT NOT NULL,
    items TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_MAX_TODAY_NUMBER = (
    "SELECT COALESCE(MAX(order_number), 0) FROM orders WHERE created_at >= ?"
)


def resolve_db_path() -> Path:
    override = os.environ.get(DB_PATH_ENV)
    return Path(override) if override else DEFAULT_DB_PATH


def _utc_timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _local_day_start(moment: datetime) -> datetime:
    local_midnight = moment.astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return local_midnight.astimezone(UTC)


def _row_to_order(row: sqlite3.Row) -> schemas.Order:
    return schemas.Order(
        id=UUID(row["id"]),
        order_number=row["order_number"],
        status=schemas.OrderStatus(row["status"]),
        customer_name=row["customer_name"],
        items=[
            schemas.OrderLineView.model_validate(item)
            for item in json.loads(row["items"])
        ],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class OrderStore:
    """All database access goes through this class: one connection,
    one lock, so FastAPI's threadpool never shares a cursor unsafely."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else resolve_db_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            self._path, check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_ORDERS)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def insert_order(
        self,
        *,
        items: list[schemas.OrderLineView],
        customer_name: str | None,
        now: datetime,
    ) -> schemas.Order:
        order_id = uuid4()
        created_at = _utc_timestamp(now)
        day_start = _utc_timestamp(_local_day_start(now))
        items_json = json.dumps(
            [item.model_dump(mode="json", by_alias=True) for item in items],
            ensure_ascii=False,
        )
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                (max_today,) = self._conn.execute(
                    _MAX_TODAY_NUMBER, (day_start,)
                ).fetchone()
                order_number = max_today + 1
                self._conn.execute(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(order_id),
                        order_number,
                        customer_name,
                        schemas.OrderStatus.placed.value,
                        items_json,
                        created_at,
                        created_at,
                    ),
                )
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return schemas.Order(
            id=order_id,
            order_number=order_number,
            status=schemas.OrderStatus.placed,
            customer_name=customer_name,
            items=items,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(created_at),
        )

    def get_order(self, order_id: UUID) -> schemas.Order | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM orders WHERE id = ?", (str(order_id),)
            ).fetchone()
        return _row_to_order(row) if row is not None else None

    def update_status(
        self, order_id: UUID, status: schemas.OrderStatus, now: datetime
    ) -> schemas.Order | None:
        target = schemas.OrderStatus(status)
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                (target.value, _utc_timestamp(now), str(order_id)),
            )
            if cursor.rowcount == 0:
                return None
            row = self._conn.execute(
                "SELECT * FROM orders WHERE id = ?", (str(order_id),)
            ).fetchone()
        return _row_to_order(row)

    def list_orders(
        self, statuses: list[schemas.OrderStatus] | None = None
    ) -> list[schemas.Order]:
        query = "SELECT * FROM orders"
        parameters: tuple[str, ...] = ()
        if statuses is not None:
            values = [schemas.OrderStatus(status).value for status in statuses]
            placeholders = ", ".join("?" for _ in values)
            query += f" WHERE status IN ({placeholders})"
            parameters = tuple(values)
        query += " ORDER BY created_at DESC, id DESC"
        with self._lock:
            rows = self._conn.execute(query, parameters).fetchall()
        return [_row_to_order(row) for row in rows]
