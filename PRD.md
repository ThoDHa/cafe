# PRD: Cafe Ông Thọ Ordering System

Version 1.0 · 2026-09-03 · Status: approved plan, pre-build

## 1. Overview

A locally run ordering system for the home cafe behind the `recipes` repository (sibling directory). Guests browse the drink menu and order from their own device; a barista screen shows a live queue and moves drinks from placed to making to done; order status flows back to the guest in real time. The system runs either as npm workspaces on a machine with Node 24, or as a single Docker container with volume-backed persistence.

**Problem:** Verbal ordering at a home cafe: no queue visibility for the person making drinks, no status visibility for guests waiting.

**Solution:** One React app serving two views (guest ordering at `/`, barista queue at `/barista`) plus one Express server, sharing a typed contract, with Server-Sent Events for liveness and SQLite for durability.

## 2. Users

| User | Device | Needs |
|------|--------|-------|
| Guest | Personal phone, ordering view at `/` | Browse menu, customize and place an order, learn when the drink is ready, reorder past drinks |
| Barista | Counter tablet or laptop, queue view at `/barista` | See new orders the moment they arrive, work the queue in order, mark drinks done or cancel |

No authentication anywhere: this is a trusted household network. The guest's device is the guest's identity (see order history, section 5.8).

## 3. Goals and Non-Goals

**Goals:**

- Full drink ordering flow with per-drink customization faithful to the recipes
- Live two-screen operation: orders appear on the barista board without refresh; status changes appear on the guest's screen without refresh
- Notifications in both directions (new order to barista, ready to guest)
- Per-device order history with one-tap reorder
- Persistence across restarts (Node mode) and across container replacement (Docker mode)
- One command to start everything, in both modes

**Non-Goals (v1):**

- Pricing and payments: the source menu publishes no prices, so v1 carries none
- Kitchen food (`kitchen.html`) and cocktails (`bar.html`): drinks only, per the five sections of `menu.html`
- Authentication, multiple baristas with order claiming, or cloud deployment
- Push notifications beyond the live tab (requires VAPID and a push server; meaningless locally)

## 4. Menu Scope and Data

Source of truth: `../recipes`. Extraction is hand-curated from `menu.html` (the customer-facing item list) cross-checked against `cafe.md` (composition rules), producing `shared/data/menu.json` consumed by server and web.

**Coverage:** every item in the five sections, Cà Phê, Mát-cha, Trà, Giải Khát, Kem, with Vietnamese names, English descriptions, and hot/iced availability from the nóng/đá tags. The Kem section's cold foams appear both as standalone drinks and as modifier options on other drinks.

**Customization model (per drink, frozen for v1):**

| Dimension | Rules |
|-----------|-------|
| Temperature | Limited to the item's offered options (hot, iced, or both) |
| Milk | Options vary per item and per temperature where `cafe.md` varies them (example: Matcha Sữa hot is whole or oat; iced adds cream and half-and-half builds) |
| Sweetener type | Condensed milk or turbinado syrup, where the recipe offers a choice |
| Sweetness level | Standard scale (full, 75%, 50%, 25%, none) |
| Cold foam | Offered only when temperature is iced; any of the foam builds |
| Notes | Free text, capped at 200 characters |
| Quantity | 1 to 10 per line |

**Photos:** every item carries an optional `imagePath` pointing at `/images/menu/<itemId>.<ext>`; files live in `shared/assets/menu/`, served statically by the server. No photos exist today; the customer app renders a styled on-brand placeholder (initial letter on the cream/cobalt token background) when the field is absent. Adding a photo is one file drop plus one JSON line, with no layout shift either way.

**Data quality:** automated validation asserts referential integrity (every referenced modifier group exists, every item has at least one temperature, valid defaults, `imagePath` matches the path convention when present), backed by manual spot checks of three representative drinks against `cafe.md`.

## 5. Functional Requirements

### 5.1 Menu Browsing (Guest)

The ordering view renders the five sections from `menu.json`, mobile-first, usable at 360 pixels wide, with the ported design identity (cream/cobalt palette, Bungee display, Lora names, Be Vietnam Pro body, nóng/đá pill tags). Item cards show photo or placeholder.

### 5.2 Drink Customizer (Guest)

Tapping an item opens a customizer limited to that item's rules: temperature choices from the item's offered set, foam groups only on iced, milk and sweetener groups filtered to the item's allowance. Identical drinks with different customizations are distinct cart lines; each line stores the full selection snapshot.

### 5.3 Cart and Order Placement (Guest)

Cart supports quantity adjustment and line removal. Submission produces a contract-shaped payload; the server assigns a daily-reset order number (short, callable across the counter) shown on the confirmation screen.

### 5.4 Live Status (Guest)

After placing, the guest sees their order's status (placed, making, ready) updating live without refresh. Reconnects heal by refetch: on every SSE (re)connection the client refetches state, so missed events never leave a stale screen.

### 5.5 Queue Board (Barista, `/barista`)

Three lanes, New, Making, Done: order cards show number, customer name if given, elapsed time since placement (ticking locally, derived from timestamps), and per-line detail with temperature, modifier selections spelled out via menu lookup, and notes. Actions: start (placed to making), complete (making or placed to done), cancel (placed only). The Done lane shows recent completions so finished drinks are cleared knowingly. The route is lazy-loaded, so the guest path never downloads queue code.

### 5.6 Notifications

| Direction | Trigger | Behavior |
|-----------|---------|----------|
| To barista | New order | Flash highlight plus optional chime (toggle, default on); when the tab is hidden, additionally a browser notification with order number and item count |
| To guest | Order completes | Browser notification plus soft chime, only if the guest opted in |

Permission handling: Notification permission is requested only from explicit gestures (the guest's "notify me when ready" button on the confirmation screen; a control near the barista chime toggle), never on page load. Denial degrades silently to the in-page experience. Notifications use the Notification API from the live page; the accepted tradeoff is that they arrive while the app's tab is open.

### 5.7 Order Lifecycle and Validation

Statuses: `placed`, `in_progress`, `completed`, `cancelled`. Legal transitions: placed to in_progress, in_progress to completed, placed to completed (fast path), placed to cancelled. Everything else is rejected with 422. Order creation validates every line against the menu (item exists, temperature offered, selections allowed, quantity in bounds) and rejects invalid payloads with 422 and a specific message.

### 5.8 Order History (Guest device)

Each guest device keeps its placed orders in localStorage: id, number, timestamp, and full item lines, capped at the 50 most recent. A history view lists them newest first with live status resolved from the server by order id. One-tap reorder loads a past order's lines into the cart, skipping any line whose item no longer exists on the current menu. No server-side history browsing exists for the barista.

### 5.9 Persistence

Orders live in SQLite (better-sqlite3, WAL mode): a single `orders` table with items as a JSON column. Restarting the server loses nothing. In Docker mode the database file sits on a named volume, so replacing the container loses nothing.

### 5.10 Run Modes

| Mode | Commands | Shape |
|------|----------|-------|
| Development | `npm install`, `npm run dev` | Server on 3001, web app on 5173 (both routes served by one Vite dev server), `/api` and `/images` proxied same-origin |
| Production | `npm run build`, `npm start` | Express serves the built SPA bundle on one origin (3001); `/` renders the ordering view, `/barista` the queue view, with SPA fallback routing |
| Container | `docker compose up --build` | Single multi-stage image (Debian slim, non-root), named volume at the SQLite path, `restart: unless-stopped` |

## 6. API Contract Summary

Full specification lands as `API.md` in the first checkpoint; the shape agreed here:

| Method | Path | Purpose |
|--------|------|---------|
| GET | /api/menu | Categories, items, modifier groups |
| POST | /api/orders | Place an order; assigns number; broadcasts `order:new` |
| GET | /api/orders?status=active | Active orders for the board |
| GET | /api/orders/:id | One order: status view and reconnect refetch |
| PATCH | /api/orders/:id/status | Validated transition; broadcasts `order:status` |
| GET | /api/events | SSE: `order:new`, `order:status`, heartbeats every 25 seconds |

Errors: 422 with `{ error, details? }` for validation and transition rejections, 404 for unknown orders, 400 for malformed JSON, 500 generic for the rest (no stack traces in responses). Static routes: `/images/menu/<file>` serves `shared/assets/menu/`.

## 7. Architecture

npm workspaces, Node 24, TypeScript strict throughout:

- `shared`: contract types and `menu.json`; imported verbatim by server and web; validation tests live here
- `server`: Express 5, layered as routes, order service (lifecycle, daily numbering), db (better-sqlite3 behind an interface), SSE hub (client registry, broadcast, heartbeat pruning), zod validation middleware
- `web`: React 19 plus Vite, one app with route-split views: `/` (menu, customizer, cart, status, history) and lazily loaded `/barista` (queue board, alerting); api client interfaces with mocks (used in dev slices and as permanent test doubles), cart reducer, status and orders stores, notifications module, order-history module; a single `design/tokens.css` serves both views

The web app codes against client interfaces; the real fetch/EventSource implementations arrive at integration, making integration a swap rather than a rewrite.

## 8. Decisions

| # | Decision | Alternatives rejected |
|---|----------|----------------------|
| 1 | Node 24, Express 5, TypeScript backend | Python FastAPI: two languages, duplicated contract types, no local-run benefit |
| 2 | SSE over WebSocket | All pushes are server-to-client; EventSource reconnects natively; WebSocket adds a protocol for nothing used |
| 3 | better-sqlite3, orders as JSON column | JSON file store: hand-rolled scans, corruption risk (kept as documented fallback behind the db interface); normalized tables: no item-level queries exist |
| 4 | npm workspaces monorepo | Separate repos: local import friction; single package: one build config forced across three toolchains |
| 5 | No prices in v1 | Inventing prices: fabricated data facing guests |
| 6 | Hand-curated menu.json over parsing `cafe.md` | Parser needs per-recipe heuristics for roughly 40 drinks and breaks on style drift |
| 7 | Frozen v1 modifier vocabulary | Free-form component builder: pushes recipe authoring onto guests |
| 8 | Interface-backed mock clients | MSW: intercepts a network layer this phase never exercises |
| 9 | Same-origin static serving in production | Three origins with CORS: configuration and SSE surface for no benefit |
| 10 | Refetch-on-reconnect reconciliation | Last-Event-ID replay: server event buffering with retention policy, overkill locally |
| 11 | Notification API from live page, opt-in gestures | Push API: VAPID keys and a push server, meaningless locally; prompts on load: throttled, hostile |
| 12 | Device-local history, localStorage, cap 50 | Server-side session history: identity state for what the device already remembers; barista browsing: explicitly out per user |
| 13 | Single Docker container over per-component | The server already serves everything same-origin; splitting adds containers and a router for nothing |
| 14 | Debian slim over Alpine | better-sqlite3 ships glibc prebuilds; musl adds build fragility for marginal size savings |
| 15 | Daily order numbers via MAX-today in insert transaction | Global sequence: unfriendly numbers; counter row: second source of truth |
| 16 | One web app, route-split views (`/`, lazy `/barista`) | Two SPAs (original plan): duplicated design tokens, two builds and proxy configs, extra workspace; `/orders` as the route name: reads as guest order history to guests |

## 9. Roadmap

Contract-first checkpoint order; 2 through 4 are parallel-ready with disjoint territories.

| Order | Checkpoint | Scope | Verified by |
|-------|------------|-------|-------------|
| 1 | CAFE-1-1 Contract | Monorepo scaffold (three workspaces: `shared`, `server`, `web`), git init, shared types, menu.json extraction, API.md | Types compile; menu validation suite; three-drink spot check |
| 2 | CAFE-1-2 Backend | Routes, order service, db layer, SSE hub, static images | supertest integration suite (validation, transitions, SSE delivery, restart persistence) |
| 3 | CAFE-1-3 Customer ordering view | Web scaffold and tokens, client interface and mock, cart and customizer logic, views with live status, photos-or-placeholder, ready notifications, history and reorder | vitest unit and component suites against mocks |
| 4 | CAFE-1-4 Barista queue view | `/barista` route module, orders store, board view with alerting and hidden-tab notifications | vitest unit and component suites against mock feed |
| 5 | CAFE-1-5 Integration | Real clients, dev proxying, production serving with SPA fallback, root scripts, README accuracy, end-to-end checklist | Two-browser checklist: live delivery both directions, cancel path, simultaneous orders, restart persistence |
| 6 | CAFE-1-6 Docker | Dockerfile, compose, volume, .dockerignore | Clean-checkout compose run, down/up persistence, layer inspection, image size recorded |

Testing stance: TDD throughout (failing tests first each unit); the view suites run against mocks, the server suite against the real app with in-memory SQLite, and checkpoint 5 adds the manual two-screen checklist as final verification. No test may be skipped to reach green.

## 10. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Menu extraction mismatches recipes | Medium | Item-for-item from `menu.html`, per-drink rules from `cafe.md`, validation suite, three-drink spot check |
| SSE clients miss events during reconnect | Medium | Refetch-on-(re)connect reconciliation, 25-second heartbeats to prune dead connections |
| Modifier scope creep | Medium | Vocabulary frozen in the contract; additions are future work, not mid-build changes |
| Notification autoplay or permission quirks | Medium | Audio context resumes on first gesture; permission anchored to explicit opt-ins; visual channels remain the baseline |
| better-sqlite3 native build failure on host | Low | Prebuilds cover the target; JSON store fallback behind the db interface |
| Dev proxy or CORS misconfiguration | Low | Dev uses Vite proxying (same-origin from the browser's view); production is same-origin by construction |
| Image size bloat in Docker | Low | Multi-stage with explicit copy lists; size checked and recorded at checkpoint 6 |

## 11. Future Work (explicitly deferred)

- Pricing: schema extension plus display, if the owner ever publishes prices
- Push notifications for closed tabs (service worker plus VAPID)
- Kitchen food and cocktail ordering (`kitchen.html`, `bar.html`)
- Multi-barista claiming, order editing after placement, i18n toggle
- GitHub issue mirroring of checkpoints if GitHub-native tracking becomes wanted
