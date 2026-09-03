# Cafe Ông Thọ Ordering System

A locally run ordering system for the home cafe behind the [recipes](../recipes) repository. Guests browse the drink menu and order from their own device; a barista screen shows a live queue and moves drinks from placed to making to done. Order status flows back to the guest in real time.

The full requirements, decisions, and roadmap live in the [PRD](PRD.md).

**Status:** planned, pre-build. The roadmap below tracks the six checkpoints; nothing has been implemented yet, so the run commands in [Running](#running) are the target interface, not working commands.

## Architecture

npm workspaces monorepo, Node 24, TypeScript everywhere:

| Component | Package | Role |
|-----------|---------|------|
| API server | `server` | Express 5, port 3001: REST endpoints, Server-Sent Events hub (`order:new`, `order:status`), better-sqlite3 persistence (WAL mode) |
| Web app | `web` | React 19 plus Vite, port 5173, one app with two routes: `/` for guest ordering (menu browsing, customizer, cart, live status) and `/barista` for the queue board (New, Making, Done, actions, alerts), lazy-loaded so guests never download queue code |
| Contract | `shared` | TypeScript types and `menu.json` consumed verbatim by server and web; the single seam both build against |

The app reuses the visual identity of the existing `recipes/menu.html` (cream and cobalt palette, Bungee, Lora, and Be Vietnam Pro type stack).

### Notifications

Two directions, both riding the existing SSE events with no server changes:

- Barista, drinks coming in: flash highlight plus chime on the board; when the tab is hidden, a browser notification with the order number
- Guest, drink ready: an opt-in "notify me when ready" on the confirmation screen (the same gesture grants Notification permission); completion fires a browser notification plus chime, with the in-page live status always as the baseline

Notifications use the Notification API from the live page rather than push infrastructure: a push server and VAPID keys add nothing to a locally run system, with the known tradeoff that notifications arrive while the ordering tab is open.

### Order History

Each guest device keeps its own order history in localStorage: past orders listed newest first with live status, and any entry reorders into the cart with one tap (lines for drinks no longer on the menu are skipped gracefully). No accounts, no server-side identity: the device is the guest.

## Menu Scope

Drinks only, extracted from the recipes repository: the five sections of `menu.html` (Cà Phê, Mát-cha, Trà, Giải Khát, Kem) with modifier rules from `cafe.md`. Cocktails (`bar.html`) and kitchen food (`kitchen.html`) are out of scope for v1.

Customization model per drink: temperature (hot or iced, where offered), milk, sweetener type, sweetness level, cold foam (iced drinks only), notes, and quantity. The source menu lists no prices, so v1 carries none.

Each menu item has an optional photo: files drop into `shared/assets/menu/` and are served at `/images/menu/<file>`, with the item's `imagePath` pointing at the public URL. Photos are absent today; the UI shows a styled placeholder per item until they arrive, one drink at a time.

## Roadmap

| Checkpoint | Scope | Status |
|------------|-------|--------|
| CAFE-1-1 | Monorepo scaffold, shared contract types, `menu.json` extraction, `API.md` specification | Ready |
| CAFE-1-2 | Backend: endpoints, order lifecycle with validated transitions, SSE hub, SQLite store | Ready |
| CAFE-1-3 | Customer ordering view (`/`): browsing, customizer, cart, order placement, live status (mocked API) | Ready |
| CAFE-1-4 | Barista queue view (`/barista`): queue board, actions, alerting (mocked API and event feed) | Ready |
| CAFE-1-5 | Integration: real clients, dev proxying, same-origin production serving, run scripts, end-to-end verification | Ready |
| CAFE-1-6 | Docker: multi-stage image, compose service, volume-backed SQLite persistence | Ready |

CAFE-1-1 blocks everything. CAFE-1-2 through CAFE-1-4 build against the contract in parallel with disjoint territories (the two views own separate route modules and state), then CAFE-1-5 wires them together and CAFE-1-6 packages the result.

## Running

Target interface once the corresponding checkpoints land:

```bash
# Development (CAFE-1-5): server on 3001, web app on 5173 (both routes)
npm install
npm run dev

# Production (CAFE-1-5): single origin on 3001 serving the app (both routes) and the API
npm run build
npm start

# Containerized (CAFE-1-6): full system, order data on a named volume
docker compose up --build
```

## Key Decisions

- Node and Express over Python: one language lets the shared contract types serve all packages unchanged
- One web app with route-split views over two SPAs: one build, one set of design tokens, one proxy config; the barista route lazy-loads so guests only fetch ordering code
- `/barista` over `/orders` for the queue route: `/orders` reads as guest order history to the people holding the phones
- Server-Sent Events over WebSocket: all pushes are server-to-client; EventSource reconnects natively and clients refetch state on reconnect to heal gaps
- SQLite over a JSON file: queryable by status, durable via WAL; a JSON store behind the same interface is the documented fallback
- No prices in v1: the source menu publishes none, and invented numbers would face guests
- Single container over one per component: the server already serves the built app same-origin, so one image and one volume cover it
- Debian slim over Alpine: better-sqlite3 ships glibc prebuilds; musl builds add fragility for marginal size savings
