# PRD: Cafe Ông Thọ Ordering System

Version 1.0 · 2026-09-17 · Status: requirements, submitted for review

## 1. Overview

A locally run ordering application for the home cafe: guests browse the drink menu and order from their own device; a barista works a live queue and moves drinks from placed to making to done; order status flows back to the guest in real time.

The menu this application serves comes from the menus system ([MENUS_REQUIREMENTS.md](MENUS_REQUIREMENTS.md)): `menu/menu.json`, generated from the recipes repository, carrying the drinks, their customization rules, and stable item ids. This system owns the ordering runtime only; menu generation and the public menus site are out of scope here.

**Problem:** Verbal ordering at a home cafe: no queue visibility for the person making drinks, no status visibility for guests waiting.

**Product shape:** One web application with two surfaces: a guest ordering surface and a barista queue surface at a dedicated path (suggested `/barista`; final path is an open decision). One server process. Everything runs on the local network with no external services.

## 2. Users

| User | Device | Needs |
|------|--------|-------|
| Guest | Personal phone, the ordering surface | Browse the drink menu, customize and place an order, learn when the drink is ready, reorder past drinks |
| Barista | Phone or tablet, the queue surface | See new orders the moment they arrive, work the queue in order, mark drinks done or cancel |

No authentication: this is a trusted household network. The guest's device is the guest's identity.

## 3. Goals and Non-Goals

**Goals:**

- Full drink ordering flow with per-drink customization faithful to the menu document's frozen rules
- Live two-screen operation: orders appear on the barista surface without refresh; status changes appear on the guest's screen without refresh
- Notifications in both directions (new order to barista, ready to guest)
- Per-device order history with one-tap reorder
- Orders persist across restarts and across container replacement
- The whole system starts with one command, in both a plain and a containerized mode

**Non-Goals:**

- Menu generation and the public menus site: the menus system owns both; this system consumes `menu/menu.json` as data
- Pricing and payments: the source menu publishes no prices, so ordering carries none
- Ordering bar cocktails and kitchen food: ordering covers drinks only, matching the menu document's scope
- Authentication, multi-staff order claiming, cloud deployment, push notifications that reach a closed browser tab, order editing after placement, i18n

## 4. Menu Dependency

The application serves exactly the document the menus system generates: `menu/menu.json`, validated against `menu/menu.schema.json`, with the customization model frozen there (temperature, milk, sweetener type, sweetness level, cold foam on iced, notes capped at 200 characters, quantity 1 to 10 per line). This system never re-derives, re-curates, or extends the menu; a drink added to the recipes repository appears on the ordering surface when the document regenerates, with no change here. Menu item photos arrive as `imagePath` references with files in `menu/assets/`; absent photos render an on-brand placeholder, and adding photos later must not shift layout.

## 5. Requirements

- **Menu browsing.** The ordering surface renders the five sections from the menu data, mobile-first and usable at 360 pixels wide, in the house visual identity shared with the public site. Item cards show the photo when present and a styled on-brand placeholder when absent.
- **Drink customizer.** Tapping an item opens a customizer limited to that item's rules: temperature choices from the item's offered set, cold foam only on iced, milk and sweetener groups filtered to the item's allowance. Identical drinks with different customizations are distinct cart lines; each line stores the full selection snapshot.
- **Cart and placement.** The cart supports quantity adjustment and line removal. Placing an order shows a confirmation with a short, callable order number that resets daily.
- **Live status.** After placing, the guest sees the order's status (placed, making, ready) change without refresh. If the connection drops, the view heals to the true state after reconnection; stale screens are not acceptable.
- **Queue board.** The barista surface shows three lanes: New, Making, Done. It is used on a phone or tablet in hand, so it is mobile-first like the ordering surface, with lanes arranged responsively (stacking on narrow screens, side by side where room allows). Order cards show number, customer name if given, elapsed time since placement, and per-line detail with temperature, modifiers spelled out by name, and notes. Actions: start, complete (including a direct placed-to-done fast path), and cancel (placed only). The Done lane shows recent completions so finished drinks are cleared knowingly.
- **Notifications.** New orders alert the barista (visual flash, optional sound, and an OS-level notification when the surface is not visible). Guests may opt in, from an explicit gesture, to a ready notification (notification plus sound) when their order completes. Notification permission is never requested on page load. Denied permission must degrade silently to the in-page experience.
- **Order lifecycle and validation.** Statuses: `placed`, `in_progress`, `completed`, `cancelled`. Legal transitions: placed to in_progress, in_progress to completed, placed to completed, placed to cancelled. All other transitions are rejected. Order creation validates every line against the menu (item exists, temperature offered, selections allowed, quantity in bounds) and rejects invalid submissions with a specific error message.
- **Guest order history.** Each guest device keeps its placed orders: id, number, timestamp, and full item lines, capped at a bounded count. A history view lists them newest first with live status. One-tap reorder loads a past order into the cart, skipping lines whose items no longer exist on the current menu. There is no barista-side history browsing.
- **Persistence.** Orders survive a server restart. In containerized operation, orders survive container replacement via durable storage external to the container.
- **Single application, two surfaces.** One web application serves the guest surface at the root and the barista surface at a dedicated path. The guest path must not download the barista surface's code.
- **Operation.** In plain mode, one command starts the whole system (server plus web build). In containerized mode, `docker compose up --build` from a clean checkout starts the whole system. Both modes serve everything from one origin on the local network.

## 6. Verification Requirements

- All ordering logic (validation, transitions, numbering, history, reorder) is covered by automated tests, written before the implementation they verify
- The live flows are verified end to end across two real browsers: an order placed on the guest surface appears on the barista surface within 2 seconds without refresh, status changes reflect on both surfaces, and both restart-persistence guarantees hold

## 7. Open Decisions

Backend language and framework, storage engine for orders, realtime delivery mechanism and its reconnection guarantees, frontend stack and repo layout, the barista surface's path, the ordering API's design and contract documentation, the application's container packaging, the notification mechanism within its constraints, and the test frameworks and the shape of the end-to-end verification. All are settled in the solution review, with choices and rejected alternatives recorded in a design document.
