# PRD: Cafe Ông Thọ Ordering System

Version 2.0 · 2026-09-03 · Status: requirements, pending solution review

## 1. Overview

A locally run ordering system for the home cafe behind the `recipes` repository (sibling directory). Guests browse the drink menu and order from their own device; a barista works a live queue and moves drinks from placed to making to done; order status flows back to the guest in real time.

**Problem:** Verbal ordering at a home cafe: no queue visibility for the person making drinks, no status visibility for guests waiting.

**Product shape:** One web application with two surfaces: a guest ordering surface and a barista queue surface at a dedicated path (suggested `/barista`; final path is an open decision). One server process. Everything runs on the local network with no external services.

## 2. Users

| User | Device | Needs |
|------|--------|-------|
| Guest | Personal phone, ordering surface | Browse menu, customize and place an order, learn when the drink is ready, reorder past drinks |
| Barista | Phone or tablet, queue surface | See new orders the moment they arrive, work the queue in order, mark drinks done or cancel |

No authentication: this is a trusted household network. The guest's device is the guest's identity (FR-8).

## 3. Goals and Non-Goals

**Goals:**

- Full drink ordering flow with per-drink customization faithful to the recipes
- Live two-screen operation: orders appear on the barista surface without refresh; status changes appear on the guest's screen without refresh
- Notifications in both directions (new order to barista, ready to guest)
- Per-device order history with one-tap reorder
- Orders persist across restarts and across container replacement
- The whole system starts with one command, in both a plain and a containerized mode

**Non-Goals:**

- Pricing and payments: the source menu publishes no prices, so v1 carries none
- Kitchen food (`kitchen.html`) and cocktails (`bar.html`): drinks only
- Authentication, multi-staff order claiming, cloud deployment
- Push notifications that reach a closed browser tab
- Order editing after placement, i18n

## 4. Menu Scope and Customization

Source of truth: `../recipes`. The orderable set is the five drink sections of `menu.html` (Cà Phê, Mát-cha, Trà, Giải Khát, Kem) with per-drink rules from `cafe.md`. The Kem section's cold foams appear both as standalone drinks and as modifiers on other drinks.

Each menu item carries: Vietnamese name, English description, hot/iced availability from the nóng/đá tags, its allowed customization dimensions, and an optional photo reference. Item photos do not exist yet; they will be added gradually over time, and the menu must accommodate them without schema or layout changes.

**Customization model (frozen for v1):**

| Dimension | Rules |
|-----------|-------|
| Temperature | Limited to the item's offered options (hot, iced, or both) |
| Milk | Options vary per item and per temperature where `cafe.md` varies them (example: Matcha Sữa hot is whole or oat; iced adds cream and half-and-half builds) |
| Sweetener type | Condensed milk or turbinado syrup, where the recipe offers a choice |
| Sweetness level | Standard scale (full, 75%, 50%, 25%, none) |
| Cold foam | Offered only when temperature is iced; any of the foam builds |
| Notes | Free text, capped at 200 characters |
| Quantity | 1 to 10 per line |

## 5. Functional Requirements

**FR-1 Menu browsing.** The ordering surface renders the five sections from menu data, mobile-first and usable at 360 pixels wide, with the visual identity of the existing `menu.html` (cream and cobalt palette, Bungee display, Lora names, Be Vietnam Pro body, nóng/đá pill tags). Item cards show the photo when present and a styled on-brand placeholder when absent; adding photos later must not shift layout.

**FR-2 Drink customizer.** Tapping an item opens a customizer limited to that item's rules: temperature choices from the item's offered set, cold foam only on iced, milk and sweetener groups filtered to the item's allowance. Identical drinks with different customizations are distinct cart lines; each line stores the full selection snapshot.

**FR-3 Cart and placement.** The cart supports quantity adjustment and line removal. Placing an order shows a confirmation with a short, callable order number that resets daily.

**FR-4 Live status.** After placing, the guest sees the order's status (placed, making, ready) change without refresh. If the connection drops, the view heals to the true state after reconnection; stale screens are not acceptable.

**FR-5 Queue board.** The barista surface shows three lanes: New, Making, Done. It is used on a phone or tablet in hand, so it is mobile-first like the ordering surface, with lanes arranged responsively (stacking on narrow screens, side by side where room allows). Order cards show number, customer name if given, elapsed time since placement, and per-line detail with temperature, modifiers spelled out by name, and notes. Actions: start, complete (including a direct placed-to-done fast path), and cancel (placed only). The Done lane shows recent completions so finished drinks are cleared knowingly.

**FR-6 Notifications.** New orders alert the barista (visual flash, optional sound, and an OS-level notification when the surface is not visible). Guests may opt in, from an explicit gesture, to a ready notification (notification plus sound) when their order completes. Notification permission is never requested on page load. Denied permission must degrade silently to the in-page experience.

**FR-7 Order lifecycle and validation.** Statuses: `placed`, `in_progress`, `completed`, `cancelled`. Legal transitions: placed to in_progress, in_progress to completed, placed to completed, placed to cancelled. All other transitions are rejected. Order creation validates every line against the menu (item exists, temperature offered, selections allowed, quantity in bounds) and rejects invalid submissions with a specific error message.

**FR-8 Guest order history.** Each guest device keeps its placed orders: id, number, timestamp, and full item lines, capped at a bounded count. A history view lists them newest first with live status. One-tap reorder loads a past order into the cart, skipping lines whose items no longer exist on the current menu. There is no barista-side history browsing.

**FR-9 Persistence.** Orders survive a server restart. In containerized operation, orders survive container replacement via durable storage external to the container.

**FR-10 Single application, two surfaces.** One web application serves the guest surface at the root and the barista surface at a dedicated path. The guest path must not download the barista surface's code.

**FR-11 Operation.** In plain mode, one command starts the whole system. In containerized mode, `docker compose up --build` from a clean checkout starts the whole system. Both modes serve everything from one origin on the local network.

## 6. Verification Requirements

- All order logic (validation, transitions, numbering, history, reorder) is covered by automated tests, written before the implementation they verify
- The menu data passes automated integrity checks (every referenced option exists, every item has at least one temperature, photo references match the agreed convention)
- The live flows are verified end to end across two real browsers: order placed on the guest surface appears on the barista surface within 2 seconds without refresh, status changes reflect on both surfaces, and both restart-persistence guarantees hold

## 7. Open Decisions (next: solution review)

The requirements above are settled; everything below is deliberately undecided and will be chosen in the solution review before building:

1. Backend language and framework
2. Storage engine for orders
3. Realtime delivery mechanism and its reconnection guarantees
4. Frontend stack and repo layout (monorepo shape, shared contract packaging)
5. Path for the barista surface (`/barista` suggested; `/orders` reads as guest history)
6. API design: endpoints, error shapes, event payloads, contract documentation
7. Menu data authoring format and validation tooling
8. Build sequencing: checkpoints, parallelization, mock strategy
9. Container packaging: image strategy, compose topology, data volume
10. Notification mechanism within the constraints of FR-6
11. Test frameworks and the shape of the end-to-end verification
