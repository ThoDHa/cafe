# PRD: Cafe Ông Thọ Menus

Version 1.0 · 2026-09-17 · Status: requirements, submitted for review

## 1. Overview

The home cafe behind the private `recipes` repository (sibling checkout) publishes its menus two ways from one shared parsing core: an ordering menu document (`menu/menu.json`) that captures the drinks with their customization rules as generated data, and a public static menus site at `thodha.github.io/cafe` carrying the drinks, priced, bar, kitchen, and pantry pages. Everything is generated from the recipes: a drink added to `cafe.md` appears everywhere at the next generation with no code or config change, and anything a generator cannot place fails the build loudly instead of shipping silently wrong.

**Problem:** Menus maintained by hand drift from the recipes as they evolve, printed menus overflow their paper, and prices tracked in a cost workbook drift from the menu copy.

**Product shape:** Two generation pipelines in one repository: `make menu` derives the ordering menu document, and a GitHub Actions deploy regenerates the public site from the recipes on every push to `main`. Static output only; no server, no runtime. The ordering menu document is this system's handoff artifact: the ordering system (its own PRD, [ORDERING_REQUIREMENTS.md](ORDERING_REQUIREMENTS.md)) is built on it.

## 2. Users

| User | Device | Needs |
|------|--------|-------|
| Public visitor | Any device, the menus site at `thodha.github.io/cafe` | Browse the drinks, priced, bar, kitchen, and pantry menus read-only at a public URL, and print them within their paper budgets |
| Maintainer | Dev machine with the sibling recipes checkout | Regenerate the ordering menu and the site from current recipes, curate display copy through checked-in overrides configs, and see any drift or unmatched join fail loudly |
| Ordering system | The ordering application, as a consumer of the data | A schema-validated menu document carrying the drinks, their customization rules, and stable item ids, generated from the same recipes as the public site |

## 3. Goals and Non-Goals

**Goals:**

- Ordering menu generated from the recipes: `menu/menu.json` is derived, schema-validated data, never hand-edited
- Public menus site generated at deploy time: every page reflects the recipes repository at the moment of deployment, with no manual publication step
- Print discipline enforced at build time: every page fits its printed page budget on A4 and Letter, or the build fails
- Print-ready PDFs with the brand footer pinned to every printed page, as the canonical print path
- Loud failures everywhere: unmapped recipe sections, stale artifacts, and unmatched pricing joins fail builds naming the offending items, never silently omitting them
- Each pipeline runs with one command locally, with automated tests gating both

**Non-Goals:**

- The ordering runtime (server, cart, live status, notifications): that system has its own PRD; this system delivers the menu document it consumes
- Hand-editing `menu.json` or hand-authoring menu pages: both are generated artifacts
- Pricing rules in this repository: prices are the cost workbook's own figures, joined and printed verbatim, and never enter the ordering menu document
- Authentication, analytics, i18n, cloud services beyond GitHub Pages

## 4. Menu Scope and Customization Model

Source of truth: the recipes repository's `cafe.md` (the five drink sections plus the cold-foam builds), enriched for ordering by the checked-in `menu/ordering-overrides.json`. The config carries version, orderRules, categories, and modifierGroups, plus per-drink overrides keyed by recipes drink name for what recipes cannot express: ordering ids, display names, menu copy, images, and modifier rules. `menu/menu.json` is generated from the two on demand (`make menu`); hand-editing `menu.json` is prohibited. A drink added to recipes appears in the menu with sensible defaults (slug id, no image, sweetness plus cold foam when iced; the kem builds carry none) and no code or config change.

Each menu item carries: Vietnamese name, English description, hot/iced availability derived from the recipes prose (config overrides where the prose cannot prove it), its allowed customization dimensions, and an optional photo reference. Item photos do not exist yet; they will be added gradually over time, and the menu must accommodate them without schema or layout changes.

The ordering menu's scope is the drinks of `cafe.md` alone. The bar menu, kitchen menu, and pantry list are public-site pages generated from their own recipes sources; they never enter the ordering menu document.

**Customization model (frozen for v1, consumed verbatim by the ordering system):**

| Dimension | Rules |
|-----------|-------|
| Temperature | Limited to the item's offered options (hot, iced, or both) |
| Milk | Options vary per item and per temperature where `../recipes/cafe.md` varies them (example: Matcha Sữa hot is whole or oat; iced adds cream and half-and-half builds) |
| Sweetener type | Condensed milk or turbinado syrup, where the recipe offers a choice |
| Sweetness level | Standard scale (full, 75%, 50%, 25%, none) |
| Cold foam | Offered only when temperature is iced; any of the foam builds |
| Notes | Free text, capped at 200 characters |
| Quantity | 1 to 10 per line |

## 5. Requirements

- **Ordering menu generation.** `make menu` derives `menu/menu.json` from `cafe.md` plus `menu/ordering-overrides.json` through the shared stdlib parser in `menu/menu_source.py`, validates the result against `menu/menu.schema.json`, and writes the canonical serialization. Generation fails loudly on unknown override keys, overrides naming drinks absent from the recipes, duplicate resolved ids, unknown modifier-group references, invalid temperatures, and drinks with no derivable description, each error naming the offending item.
- **Ordering menu integrity.** The committed artifact passes automated checks: JSON Schema conformance; every modifier group reference resolves; every required group carries exactly one default mechanism valid for every temperature the item offers; cold foam attaches only to iced items; sweetness groups use the standard scale; image paths follow the `/images/menu/<itemId>.<ext>` convention with the file present in `menu/assets/`; orderRules freeze the section 4 bounds. A staleness test regenerates the document from the recipes plus the overrides config and asserts it matches the committed artifact, so the sources and the artifact cannot drift.
- **Public drinks menu, the homepage.** The deploy generates the drinks menu from `cafe.md` and publishes it as the homepage (`index.html` and `menu.html`). Sections render in the order Cà Phê, Trà, Mát-cha, Giải Khát, then Kem, each category's blurb paragraph appearing as its section note, in the house visual identity (cream and cobalt palette, Bungee display, Lora names, Be Vietnam Pro body, nóng/đá pill tags). The homepage pair carries no prices, and the generated pages carry no ordering artifacts (data attributes or embedded JSON). A drink-like section the generator cannot place fails the build loudly.
- **Compact menu.** A one-page print reference (`menu/compact.html`) with the same items, keeping Vietnamese and English names, nóng/đá tags, the category blurbs, and each drink's description, set small, muted, and italic so the dense three-column page fits its print budget. It carries no prices.
- **Priced menu.** The drinks menu layout with one selling price right-justified on every drink's name line outside the Kem cold-foam section (`prices/menu.html`), generated by joining the recipes repository's `cafe_costs.xlsx` onto the `cafe.md` drinks. Each price is the workbook's Menu Price exactly as the workbook evaluates it, and the Kem cold-foam builds show no price. A workbook row matching no menu drink, or a drink with no workbook row, fails the deploy loudly naming every unmatched item in both directions; one unmatched item blocks the whole priced family together.
- **Cost-reference prices.** The drinks with a cost-plus-SRP cluster right-justified on every drink's name line (`prices.html` and `prices/compact.html`), through the same join. Every drink outside the Kem cold-foam section is priced individually, Bạc Xỉu included: it is priced in its own place when `cafe.md` defines the drink natively, and the curated line is inserted right after House Latte when `cafe.md` describes it only as a variation. Both figures are the workbook's own current evaluations; this repository hardcodes no pricing rule.
- **Bar menu.** The deploy generates `bar.html` from `cocktails.md` in the recipes repository through the same shared parsing core; the template families become the COCKTAILS section, with curated descriptions in `site/menu-overrides.json`. A cocktail template family added to recipes appears at the next deployment with no change here.
- **Kitchen menu.** The deploy generates `kitchen.html` from the recipes repository: the "Available Recipes" index in its `README.md` places each dish in its section, the dish files back every link and anchor, and curated Vietnamese names, variant merges, and descriptions live in `site/menu-overrides.json`. A dish added to the index appears at the next deployment with no change here; an index group the generator cannot place fails the build loudly.
- **Pantry list.** The deploy generates `pantry.html` from `cafe_pantry.md` through the same shared parsing core: the three buying groups become sections under curated Vietnamese section titles held in the generator code, and each item's quantity or buy spec rides the subtitle slot. A pantry item added to the pantry file appears at the next deployment with no change here; a buying group the list adds later falls back to its English section title.
- **Print budgets.** The build renders every page with weasyprint and steps the print font size down (16px to an 11px floor, whichever still fits) so the menu, priced menu, kitchen, pantry, and prices pages fit two printed A4 and Letter pages and the bar, compact, and prices-compact pages fit one. A page that cannot fit fails the build loudly, and the rendered PDFs answer to the same budgets. A no-JavaScript browser print verification re-proves the budgets on both papers.
- **Print-ready PDFs.** The same build pass renders each menu to a PDF next to its HTML (`menu.pdf`, `menu/compact.pdf`, `prices/menu.pdf`, `bar.pdf`, `kitchen.pdf`, `pantry.pdf`, `prices.pdf`, `prices/compact.pdf`). The PDFs are the print path: their `@page` bottom margin box carries the brand line "CAFE ÔNG THỌ · nhà làm · made in house" on every page, pinned inside the bottom margin band like a printed footer, which a browser print preview cannot do. Each HTML page carries a screen-only "PDF View" link to its PDF, and printing the HTML page itself keeps the single in-flow footer at the content end.
- **Site deployment.** A push to `main` (or a manual workflow dispatch) runs the generator's tests, regenerates the site from the latest recipes, and publishes it to this repository's GitHub Pages. The recipes checkout authenticates with the `RECIPES_TOKEN` repository secret, a fine-grained PAT scoped to `ThoDHa/recipes` with Contents: read-only; a missing, expired, or out-of-scope PAT fails that checkout loudly.
- **Local operation.** `make menu` and `make test-menu` run the ordering menu pipeline and its suites; `make site`, `make test-site`, and `make verify-print-chrome` run the site pipeline, its suites, and the browser print verification. Both pipelines need only `uv` and the sibling recipes checkout.

## 6. Verification Requirements

- The ordering menu suites cover the derivation rules (temperatures, Vietnamese names, default modifier groups, override precedence, canonical serialization), every loud-failure path of generation, and the integrity checks and byte-identical staleness round trip
- The site suites cover the parsers, the rendered pages, site assembly, the print budgets, the loud pricing joins, and the no-ordering-artifacts rule
- The staleness guard runs in the deploy workflow where the recipes checkout is guaranteed to exist, failing the deploy on any drift between the committed artifacts and their sources
- Deployment is verified end to end: a push to `main` publishes the current menus with the drinks menu as the homepage, every page reachable, every page within its print budget

## 7. Open Decisions

None. The requirements above are settled; the decisions and rejected alternatives are recorded in the [menus design document](MENUS_DESIGN.md).
