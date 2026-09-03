# Product Design: Cafe Ông Thọ Ordering System

Version 1.0 · 2026-09-03 · Status: decided, pre-build

Companion to the [PRD](PRD.md): every functional requirement there (FR-1 through FR-11) traces to a design element here. Decisions were made fresh against the requirements and the host environment (Python 3.14 with `uv`, Node 24, Docker 29 with Compose v5).

## 1. Decision Record

| # | Decision | Alternatives rejected |
|---|----------|----------------------|
| D1 | Python 3.14 server on FastAPI | Flask: validation, SSE structure, and schema docs become hand-rolled; Node: rejected by user preference for Python despite the single-language appeal |
| D2 | Orders in SQLite via stdlib `sqlite3`, WAL mode | JSON file: scans on read, corruption risk under concurrent writes; third-party ORMs: no query complexity exists to justify them |
| D3 | Server-Sent Events for liveness | WebSocket: bidirectional power unused, own reconnect protocol; polling: makes FR-6 alerts latency-bound |
| D4 | Contract types generated: FastAPI's OpenAPI schema feeds `openapi-typescript` for the web app | Hand-written pydantic plus TS types in parallel: drift caught only by humans |
| D5 | Single container: Python image serving API and built web bundle, one volume | Multi-service compose: router and extra containers buy scaling a household never needs |
| D6 | One React (Vite, TypeScript) web app; guest surface at `/`, barista at `/barista` (lazy-loaded) | Two SPAs: duplicate toolchains, tokens, proxy configs; `/orders` as the barista path: reads as guest order history |
| D7 | `menu.json` plus JSON Schema at the repo root's `menu/` directory, consumed by server (validated in pytest) and web (mock data) | Parsing `cafe.md` programmatically: recipe-oriented markdown needs per-drink heuristics; burying the menu in one side's code: the other side can't consume it |
| D8 | Verification: pytest plus httpx on the server, vitest plus Testing Library on the web, TDD throughout, manual two-browser checklist at integration | Skips or post-hoc testing: prohibited; a single framework across languages: does not exist meaningfully |
| D9 | API documentation is the live OpenAPI schema: FastAPI serves Swagger UI at `/docs` and ReDoc at `/redoc`, generated from the same pydantic models that drive type generation | Hand-written `API.md`: drifts from the code the moment a field changes; external collections (Postman): a second artifact to maintain and no generation story |

## 2. System Architecture

One Python process and one web bundle, composed in a flat repository:

```
cafe/
├── PRD.md  README.md  DESIGN.md  Makefile  Dockerfile  compose.yaml
├── menu/
│   ├── menu.json            # the orderable menu (hand-curated, schema-validated)
│   ├── menu.schema.json     # JSON Schema for menu.json
│   └── assets/              # drink photos, optional, served at /images/menu/
├── server/                  # uv-managed Python project (FastAPI)
│   ├── app/
│   │   ├── main.py          # app assembly, static serving, SPA fallback
│   │   ├── schemas.py       # pydantic models: the contract source of truth
│   │   ├── orders.py        # order routes and lifecycle service
│   │   ├── events.py        # SSE hub: per-client queues, broadcast, heartbeat
│   │   └── db.py            # sqlite3 access layer behind a small interface
│   └── tests/
└── web/                     # npm project (React 19, Vite, TypeScript)
    └── src/
        ├── api/             # generated schema types, client interface, mock client
        ├── views/           ├── ordering/ (menu, customizer, cart, status, history)
        │                    └── barista/ (queue board, lazy route)
        ├── state/           # cart reducer, status store, orders store, history
        ├── design/tokens.css
        └── notifications.ts
```

**Process model:** one uvicorn worker (documented constraint; SSE fanout is in-process, and household scale needs no more). Dev: uvicorn on port 8000, Vite on 5173 proxying `/api`, `/events`, `/images` to 8000. Production and container: FastAPI serves the built web bundle at `/` and `/barista` with SPA fallback, one origin on port 8000.

**Contract flow:** pydantic models in `schemas.py` define every request and response shape. A generation step exports `openapi.json` and runs `openapi-typescript` into `web/src/api/schema.d.ts`; the web client codes only against generated types, so drift is a compile error. The same schema renders the interactive documentation at `/docs` and `/redoc` (D9).

## 3. Data Design

### 3.1 Menu (`menu/menu.json`)

Five categories from `recipes/menu.html`; items carry `id`, `name` (English), `nameVi`, `description`, `categoryId`, `temperatures` (from nóng/đá tags), `modifierGroupIds`, and optional `imagePath` (`/images/menu/<itemId>.<ext>`, files in `menu/assets/`, absent means placeholder). Modifier groups encode the PRD's frozen customization model; per-item rules come from `cafe.md` (example: Matcha Sữa milk options differ hot versus iced; cold foam attaches only to iced). pytest validates `menu.json` against `menu.schema.json`: referential integrity of modifier groups, non-empty temperatures, valid defaults, path convention on `imagePath`.

### 3.2 Orders (SQLite)

Single `orders` table: `id` (uuid text, primary key), `order_number` (int), `customer_name` (nullable text), `status` (text), `items` (JSON text: full line snapshots), `created_at`, `updated_at` (ISO 8601). WAL mode; file at `server/data/cafe.db`, overridable via `CAFE_DB_PATH` (the container mounts a volume there). No item-level SQL exists, so normalization buys nothing.

**Lifecycle** (FR-7): `placed → in_progress → completed`, `placed → completed` (fast path), `placed → cancelled`; everything else rejected 422. Daily numbering: `SELECT MAX(order_number)` over today's orders inside the insert transaction.

## 4. API Design

| Method | Path | Purpose |
|--------|------|---------|
| GET | /api/menu | The validated menu document |
| POST | /api/orders | Place an order; assigns the daily number; broadcasts `order:new` |
| GET | /api/orders?status=active | Active orders, newest first (barista snapshot) |
| GET | /api/orders/{id} | One order (guest status, reconnect refetch) |
| PATCH | /api/orders/{id}/status | Validated transition; broadcasts `order:status` |
| GET | /api/events | SSE stream: `order:new`, `order:status`, heartbeat every 25 seconds |
| GET | /images/menu/{file} | Static drink photos |

Errors: 422 `{ "error": string, "details": [string] }` for validation and transition rejections (FR-7), 404 for unknown order ids. Order creation validates each line against the live menu: item exists, temperature offered, selections within the item's allowed groups, quantity 1 to 10, notes at most 200 characters.

**Documentation (D9):** the API documents itself. Every pydantic model and route carries descriptions and response examples, so FastAPI serves an always-current Swagger UI at `/docs` and ReDoc at `/redoc` from the same OpenAPI schema that generates the web app's TypeScript types: one source of truth for humans, docs readers, and the compiler alike. OpenAPI metadata (title, description, version) is set in app assembly.

## 5. Web App Design

**Ordering view (`/`)**: category sections (mobile-first, 360 pixels usable, FR-1), photo-or-placeholder cards, customizer sheet enforcing per-item rules (FR-2), cart drawer with per-line snapshots and quantity bounds (FR-3), confirmation with the daily number, live status view with refetch-on-reconnect healing (FR-4), device history (localStorage, cap 50, newest first, one-tap reorder that skips retired items, FR-8), and the opt-in ready notification (FR-6).

**Barista view (`/barista`, lazy-loaded so `/` never downloads it, FR-10)**: three lanes (New, Making, Done) stacking on narrow screens (FR-5 handheld), cards with number, name, elapsed time derived from timestamps, and lines with modifiers spelled out via menu lookup; start, complete, and cancel actions; flash plus chime on new orders and an OS notification when the tab is hidden (FR-6).

**Client interface:** both views consume a typed `ApiClient` interface (menu, orders, transitions, event subscription) with a mock implementation used during view development and as the permanent test double; the real fetch and EventSource implementation lands at integration, making integration a swap.

**Notifications:** Notification API from the live page, permission requested only from explicit gestures (the guest's post-order opt-in; a control near the barista chime toggle), Web Audio chime, silent degradation on denial.

**Design tokens:** the `menu.html` palette and type stack ported verbatim to `design/tokens.css` (cream and cobalt, Bungee, Lora, Be Vietnam Pro, nóng/đá pill styles), one token set for both views.

## 6. Verification Design

- Server (pytest, httpx): validation matrix (each 422 path with its specific message), every legal and illegal transition, daily numbering at the midnight boundary, SSE delivery of both event types with heartbeat, order persistence across database reopen, menu schema validation
- Web (vitest, Testing Library): cart reducer, customizer constraint derivation (foam hidden when hot, temperature filtering), payload building against generated types, status and orders stores including reconnect snapshot replacement, history round trip and reorder skipping, notification gating (hidden versus visible, granted versus denied)
- End to end (integration checkpoint): two real browsers, orders visible on the barista surface within 2 seconds, status changes reflected both directions, cancel path, simultaneous orders, restart and container-replacement persistence
- TDD throughout: failing tests precede implementation; no test is skipped to reach green

## 7. Packaging and Operations

| Mode | How | Shape |
|------|-----|-------|
| Development | `make dev` | uvicorn (8000) plus Vite (5173) with same-origin proxying |
| Production | `make build && make start` | FastAPI serves the built bundle and API on one origin (8000) |
| Container | `docker compose up --build` | Multi-stage `python:3.14-slim` image (uv install, web build in a node stage), non-root runtime, volume at `CAFE_DB_PATH`, `restart: unless-stopped` |

A root Makefile glues the two toolchains (`dev`, `test`, `build`, `start`); stdlib sqlite3 means no native modules anywhere in the image.

## 8. Build Plan

Contract-first checkpoints; 3 and 4 are parallel-ready with disjoint territories (separate route modules and state).

| Order | Checkpoint | Scope | Verified by |
|-------|------------|-------|-------------|
| 1 | CP-1 Contract | Scaffold (uv and npm projects, Makefile stub), `menu/` with schema and extracted `menu.json`, pydantic schemas with descriptions and examples, OpenAPI to TS generation pipeline | Menu validation pytest green; generated types compile; `/docs` renders with documented models and examples |
| 2 | CP-2 Server | db layer, order service, routes, SSE hub, static images | Full pytest suite green (TDD) |
| 3 | CP-3 Ordering view | Scaffold and tokens, client interface and mock, cart, customizer, status, history, notifications, views | vitest suite green (TDD) |
| 4 | CP-4 Barista view | `/barista` route module, orders store, board, alerting | vitest suite green (TDD) |
| 5 | CP-5 Integration | Real client, Vite proxy, production serving with SPA fallback, Makefile targets, README accuracy, two-browser checklist | Checklist passes line by line |
| 6 | CP-6 Container | Dockerfile, compose.yaml, volume, .dockerignore | Clean-checkout `up --build`, down/up persistence, layer inspection, image size recorded |

## 9. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Python 3.14 wheel availability for the FastAPI stack | Medium | Verify at CP-1; fallback is pinning the runtime to 3.13 or 3.12 via `uv python` with no design change |
| Single-worker SSE constraint forgotten during scaling attempts | Low | Documented in the process model; the design explicitly trades multi-worker fanout (would need a shared bus) for household simplicity |
| Generated-types pipeline friction | Low | Generation runs inside the web build; hand-augmentation, if ever needed, lives in a wrapper module, never in generated files |
| Menu extraction mismatches the recipes | Medium | Schema validation plus three manual spot checks (temperature-dependent milk, iced-only drink, foam-as-drink) at CP-1 |
| Vite proxy or CORS misconfiguration | Low | Dev is same-origin through the proxy; production is same-origin by construction |
