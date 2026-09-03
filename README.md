# Cafe Ông Thọ Ordering System

A locally run ordering system for the home cafe behind the [recipes](../recipes) repository. Guests browse the drink menu and order from their own device; a barista works a live queue and moves drinks from placed to making to done; order status flows back to the guest in real time.

The requirements live in the [PRD](PRD.md). The decided solution (architecture, data, API, verification, packaging, build plan) lives in the [design document](DESIGN.md).

**Status:** requirements and design complete, pre-build. When built, the API documents itself with Swagger UI at `/docs` and ReDoc at `/redoc`, generated from the same schema that produces the web app's TypeScript types.

## Product at a Glance

- One web application, two surfaces: guest ordering and a barista queue at a dedicated path
- Drinks only: the five sections of the recipes menu (Cà Phê, Mát-cha, Trà, Giải Khát, Kem) with per-drink customization (temperature, milk, sweetener, sweetness, cold foam on iced, notes, quantity); no prices, matching the source menu
- Live both ways: new orders reach the barista without refresh, ready status reaches the guest without refresh, with notifications in both directions
- Per-device order history with one-tap reorder
- Orders persist across restarts; the system runs with one command, plain or containerized
