# Product Design: Cafe Ông Thọ Ordering System

Version 1.1 · 2026-09-04 · Status: decided, pre-build

Companion to the [PRD](PRD.md): every functional requirement there (FR-1 through FR-12) traces to a design element here. Decisions were made fresh against the requirements and the host environment (Python 3.14 with `uv`, Node 24, Docker 29 with Compose v5).

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
| D10 | Menus site on this repository's own GitHub Pages (`thodha.github.io/cafe`): a workflow checks out the public `ThoDHa/recipes` repository, generates the drinks menu from `cafe.md` via the stdlib generator and templates in `site/`, ships `kitchen.html` and `bar.html` as-is, and deploys on every push to `main`; the repository is public to use Pages | Hosting on the recipes repo's Pages: cross-repo pushes need a PAT secret and the URLs live under `/recipes/`; publishing hand-authored pages only: the public menu drifts from the recipes as they evolve; generating from `menu.json`: couples the public site to the ordering pipeline, which must track the recipes instead |

## 2. System Architecture

One Python process and one web bundle, composed in a flat repository:

```
cafe/
├── PRD.md  README.md  DESIGN.md  Makefile  Dockerfile  compose.yaml
├── .github/workflows/menu-pages.yml   # generates the menus site from recipes, deploys Pages (D10)
├── menu/
│   ├── menu.html            # enriched single source: data attributes plus embedded JSON
│   ├── kitchen.html         # public kitchen menu, shipped as-is
│   ├── bar.html             # public bar menu, shipped as-is
│   ├── menu.json            # the orderable menu (generated via make menu, schema-validated)
│   ├── menu.schema.json     # JSON Schema for menu.json
│   └── assets/              # drink photos, optional, served at /images/menu/
├── site/                    # public menus site (D10)
│   ├── generate.py          # stdlib generator: parses recipes cafe.md, renders templates
│   ├── test_generate.py     # parser, render, and site-assembly tests
│   ├── templates/           # drinks page template (menu.html design) and static index
│   └── public/              # generated artifact, gitignored, deployed by the workflow
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

**Public menus site (D10, FR-12):** the site at `thodha.github.io/cafe` is generated by the deploy, independent of the home server. The workflow checks out both repositories, and `site/generate.py` (stdlib only) parses `recipes/cafe.md`: the four drink sections map to Cà Phê, Mát-cha, Trà, and Giải Khát, and the cold-foam builds become Kem. Items are derived entirely from the file, so a drink added to recipes appears at the next deploy with no generator change; only menu-shape knowledge recipes cannot express (section titles, ten Vietnamese names, the Hot Tea temperature the prose cannot prove, three foam descriptions) lives in the generator's configuration. An unrecognized drink-like section raises `UnmappedSectionError` and fails the build loudly. Temperatures derive conservatively from explicit cues ("iced only", "hot or iced", paired Hot/Iced blocks, ice ingredients excluding ice cream), with a test cross-checking every derived temperature against `menu.json`. The drinks page renders through a template ported from `menu/menu.html` (same CSS and chrome) with all ordering artifacts stripped; `kitchen.html`, `bar.html`, a static index linking the three menus, and `assets/` ship alongside. The repository is public, which Pages on the free plan requires; a secret scan preceded the visibility change.

**Contract flow:** pydantic models in `schemas.py` define every request and response shape. A generation step exports `openapi.json` and runs `openapi-typescript` into `web/src/api/schema.d.ts`; the web client codes only against generated types, so drift is a compile error. The same schema renders the interactive documentation at `/docs` and `/redoc` (D9).

## 3. Data Design

### 3.1 Menu (`menu/menu.json`)

`menu/menu.html` is the single source of truth, enriched to be machine-readable: each category section carries `data-category-id`, each item div carries `data-id` and, when applicable, `data-modifier-groups` (space-separated group ids) and `data-temperatures` (explicit hot/iced values overriding tag derivation, used by the Kem cold foams whose iced service is visually implicit), and the page embeds one `<script type="application/json" id="cafe-menu-data">` block carrying `version`, `orderRules`, `categories` (the five drink sections), and `modifierGroups`. `menu/menu.json` is a generated artifact: the server's `generate-menu` console script (wired like the existing `export-openapi` entry in `server/pyproject.toml`, stdlib HTML parsing plus jsonschema validation against `menu/menu.schema.json`) derives it from `menu.html` on demand via the root `make menu` target; hand-editing `menu.json` is prohibited. Items carry `id`, `name` (English), `nameVi`, `description`, `categoryId`, `temperatures` (from nóng/đá tags), `modifierGroupIds`, and optional `imagePath` (`/images/menu/<itemId>.<ext>`, files in `menu/assets/`, absent means placeholder). Modifier groups encode the PRD's frozen customization model; per-item rules live in the embedded data (example: Matcha Sữa milk options differ hot versus iced; cold foam attaches only to iced). pytest validates `menu.json` against `menu.schema.json`: referential integrity of modifier groups, non-empty temperatures, valid defaults, path convention on `imagePath`. A round-trip test regenerates the menu from `menu.html` and asserts it matches the committed `menu.json`, so the two cannot drift.

**Deferred:** runtime auto-sync from GitHub. When wanted, the server will poll `https://raw.githubusercontent.com/ThoDHa/cafe/main/menu/menu.html` with conditional GET (ETag) on an interval, regenerate and validate, hot-swap, and broadcast a refresh over the existing SSE event hub; deferred because generation on demand is sufficient for now.

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

**Design tokens:** the `menu/menu.html` palette and type stack ported verbatim to `design/tokens.css` (cream and cobalt, Bungee, Lora, Be Vietnam Pro, nóng/đá pill styles), one token set for both views.

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
| Public menus site | push to `main` (or workflow dispatch) | GitHub Actions checks out cafe plus recipes, `site/generate.py` builds `site/public/`, Pages deploys it at `thodha.github.io/cafe` (D10, FR-12); static pages only, no server, no ordering |

A root Makefile glues the two toolchains (`dev`, `test`, `build`, `start`); stdlib sqlite3 means no native modules anywhere in the image.

## 8. Build Plan

The menu leads the plan: generation lands in CP-1 and publication in CP-2, before any app surface. Checkpoints 4 and 5 are parallel-ready with disjoint territories (separate route modules and state).

| Order | Checkpoint | Scope | Verified by |
|-------|------------|-------|-------------|
| 1 | CP-1 Contract | Scaffold (uv and npm projects, Makefile stub), `menu/` with schema and extracted `menu.json`, pydantic schemas with descriptions and examples, OpenAPI to TS generation pipeline | Menu validation pytest green; generated types compile; `/docs` renders with documented models and examples |
| 2 | CP-2 Menu Pages | `site/` generator, templates and tests; `.github/workflows/menu-pages.yml`; Pages enabled (`build_type: workflow`), repository public | Site test suite green; push to `main` deploys; all three menus reachable at `thodha.github.io/cafe` and the drinks menu carries no ordering artifacts |
| 3 | CP-3 Server | db layer, order service, routes, SSE hub, static images | Full pytest suite green (TDD) |
| 4 | CP-4 Ordering view | Scaffold and tokens, client interface and mock, cart, customizer, status, history, notifications, views | vitest suite green (TDD) |
| 5 | CP-5 Barista view | `/barista` route module, orders store, board, alerting | vitest suite green (TDD) |
| 6 | CP-6 Integration | Real client, Vite proxy, production serving with SPA fallback, Makefile targets, README accuracy, two-browser checklist | Checklist passes line by line |
| 7 | CP-7 Container | Dockerfile, compose.yaml, volume, .dockerignore | Clean-checkout `up --build`, down/up persistence, layer inspection, image size recorded |

## 9. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Python 3.14 wheel availability for the FastAPI stack | Medium | Verify at CP-1; fallback is pinning the runtime to 3.13 or 3.12 via `uv python` with no design change |
| Single-worker SSE constraint forgotten during scaling attempts | Low | Documented in the process model; the design explicitly trades multi-worker fanout (would need a shared bus) for household simplicity |
| Generated-types pipeline friction | Low | Generation runs inside the web build; hand-augmentation, if ever needed, lives in a wrapper module, never in generated files |
| Menu extraction mismatches `menu/menu.html` | Medium | Schema validation plus three manual spot checks (temperature-dependent milk, iced-only drink, foam-as-drink) at CP-1 |
| Vite proxy or CORS misconfiguration | Low | Dev is same-origin through the proxy; production is same-origin by construction |
| GitHub Pages workflow fails or the site is left disabled | Low | Deployment runs on every push to `main`, so a failure is visible in Actions immediately; the repo is public, so Pages carries no plan dependency |
| Recipes prose cannot prove a temperature, or a new section appears in `cafe.md` | Medium | Conservative cue-based derivation with per-item overrides, a test cross-checking all derived temperatures against `menu.json`, and `UnmappedSectionError` failing the build on unmapped sections instead of silent omission |
| Two menu derivations drift (public site from recipes, ordering `menu.html` enriched by hand) | Medium | Accepted by decision D10; the temperature cross-check test catches drift at the derivation layer, and the public page carries no ordering data |
