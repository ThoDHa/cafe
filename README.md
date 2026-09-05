# Cafe Ông Thọ Ordering System

A locally run ordering system for the home cafe behind the [recipes](../recipes) repository. Guests browse the drink menu and order from their own device; a barista works a live queue and moves drinks from placed to making to done; order status flows back to the guest in real time.

The requirements live in the [PRD](PRD.md). The decided solution (architecture, data, API, verification, packaging, build plan) lives in the [design document](DESIGN.md).

**Status:** requirements and design complete, pre-build. When built, the API documents itself with Swagger UI at `/docs` and ReDoc at `/redoc`, generated from the same schema that produces the web app's TypeScript types.

## Product at a Glance

- One web application, two surfaces: guest ordering and a barista queue at a dedicated path
- Drinks only: the menus live in [`menu/`](menu/); the five drink sections of the recipes menu (Cà Phê, Mát-cha, Trà, Giải Khát, Kem) with per-drink customization (temperature, milk, sweetener, sweetness, cold foam on iced, notes, quantity); `menu.json` is generated from the recipes repository plus [`menu/ordering-overrides.json`](menu/ordering-overrides.json) via `make menu`, and hand-editing is prohibited; no prices, matching the source menu
- Live both ways: new orders reach the barista without refresh, ready status reaches the guest without refresh, with notifications in both directions
- Per-device order history with one-tap reorder
- Orders persist across restarts; the system runs with one command, plain or containerized
- Public menus site at [thodha.github.io/cafe](https://thodha.github.io/cafe/): the drinks menu is generated from the [recipes](../recipes) repository at deploy time, with the kitchen and bar pages alongside

## Public Menus Site

The menus are publicly browsable at [thodha.github.io/cafe](https://thodha.github.io/cafe/), independent of the home ordering system:

- **Drinks menu, the homepage** (`/cafe/` and `/cafe/menu.html`): generated at deploy time by [`site/generate.py`](site/generate.py), which pulls drinks from `cafe.md` in the public [recipes repository](https://github.com/ThoDHa/recipes) and renders them through the templates in [`site/templates/`](site/templates/). The four drink sections print in the order Cà Phê, Trà, Mát-cha, Giải Khát, then Kem; each category's blurb in `cafe.md` appears as its section note. A drink added to recipes appears at the next deployment with no change here; a drink-like section the generator cannot place fails the build loudly instead of being dropped.
- **Compact menu** (`/cafe/menu/compact.html`): a one-page print reference with the same items, keeping Vietnamese and English names, nóng/đá tags, the category blurbs, and each drink's description, set small, muted, and italic so the dense three-column page still fits its print budget.
- **Kitchen and bar menus** (`kitchen.html`, `bar.html`): the hand-authored pages in [`menu/`](menu/), republished alongside.
- **Print budgets enforced at build time**: the generator renders every page with weasyprint and steps the print font size down (16px to an 11px floor) until the menu, kitchen, and bar pages fit two printed pages on A4 and Letter, and the compact page fits one. A page that cannot fit fails the build instead of shipping an overflowing printout.

Deploying: a push to `main` (or a manual workflow dispatch) runs [`.github/workflows/menu-pages.yml`](.github/workflows/menu-pages.yml), which runs the generator's tests, regenerates the site from the latest recipes, and publishes it to this repository's GitHub Pages.

Working locally: `make site` regenerates `site/public/` from the sibling `../recipes` checkout (both `make site` and `make test-site` run under `uv` with weasyprint; pass `--no-fit-pages` to skip the print-budget pass).
