# Menus Design: Cafe Ông Thọ

Version 1.0 · 2026-09-17 · Status: decided; the implementation this documents already ships

Companion to the menus PRD ([MENUS_REQUIREMENTS.md](MENUS_REQUIREMENTS.md)): every requirement there traces to a design element here. Decisions were made against the requirements and the host environment (Python 3.14 with `uv`; weasyprint pinned at 70.0 for the print pass). This document records the system as decided, including one decision made and later superseded during the build (the browser print scaler, D6).

## 1. Decision Record

| # | Decision | Alternatives rejected |
|---|----------|----------------------|
| D1 | One shared stdlib parsing core, `menu/menu_source.py`, powers both derivations (the ordering menu and every site page family) | Two parsers, one per pipeline: the derivations drift apart silently; the site parsing `menu.json` instead: couples the public site to the ordering artifact, which lacks section blurbs and site copy, and makes the site lag the recipes |
| D2 | Enrichment lives in checked-in overrides configs (`menu/ordering-overrides.json` for ordering, `site/menu-overrides.json` for the site), keyed by recipes names; the recipes files stay the sole source of the items themselves | Copying or forking recipes content into this repository: drifts immediately; burying curation in generator code for everything: makes routine copy edits code changes (only truly structural fallbacks, like the pantry's Vietnamese section titles, live in code) |
| D3 | `menu/menu.json` is a generated artifact: schema-validated on generation, integrity-checked and round-trip checked in tests, hand-editing prohibited | Hand-maintained JSON: the menu drifts from the recipes; no schema: invalid documents surface downstream instead of at generation |
| D4 | Conservative derivation from explicit prose cues (temperature from "iced only", "hot or iced", paired Hot/Iced blocks, ice ingredients excluding ice cream), with per-item overrides where prose cannot prove a fact, and `UnmappedSectionError` failing the build on unrecognized drink-like sections | Optimistic derivation: wrong temperatures ship; silent omission of unmapped sections: drinks vanish without a trace |
| D5 | The site builds at deploy time on every push to `main`: a GitHub Actions workflow checks out this repository plus the private `ThoDHa/recipes` (authenticated with the `RECIPES_TOKEN` fine-grained PAT, Contents: read-only), runs the suites, generates, and publishes to this repository's own GitHub Pages (`thodha.github.io/cafe`); the repository is public to use Pages; the generated `site/public/` is gitignored | Hosting on the recipes repo's Pages: cross-repo pushes need a PAT and the URLs live under `/recipes/`; committing generated pages: the published site can drift from the last build; hand-authored pages: the public menu drifts from the recipes as they evolve |
| D6 | Print budgets enforced at build time: every page is rendered with weasyprint and the print root font size steps down from 16px to an 11px floor until the page fits its budget; the fitted root is injected into the built HTML, and the same gate renders the print PDFs. Superseded in build history: a runtime browser print scaler (`print-fit.js`) was added and later removed (2026-09-08); the build-injected root replaced it, re-verified on A4 and Letter by `make verify-print-chrome` with JavaScript off | No budgets: printouts overflow their paper; runtime scaling in the browser: a script that runs only sometimes and cannot gate CI; PDF-only budgets: the HTML print path goes unguarded |
| D7 | The PDFs are the print path: each menu renders to a PDF beside its HTML with the brand line pinned in the `@page` bottom margin box on every sheet; HTML pages keep the in-flow footer at the content end and link their PDF with a screen-only "PDF View" link | Browser print preview as the print path: no browser pins a footer to every printed page |
| D8 | Priced pages join the recipes cost workbook (`cafe_costs.xlsx`, parsed by `site/pricing_source.py`) onto the drinks loudly: any unmatched row or drink fails the deploy naming every item in both directions, and one unmatched item blocks the whole priced family | Hardcoding prices: drifts from the workbook on every edit; silently skipping unmatched items: prices go missing or stale without a signal |
| D9 | The site's generated pages carry no ordering artifacts: no data attributes, no embedded JSON, no pills or controls the public visitor cannot use | Sharing rendering wholesale with an ordering surface: leaks contract data into public static pages |

## 2. System Architecture

Two generation pipelines over one parsing core, composed in a flat repository:

```
cafe/
├── MENUS_REQUIREMENTS.md    ORDERING_REQUIREMENTS.md  README.md  Makefile
├── .github/workflows/menu-pages.yml   # runs the suites, builds the site, deploys Pages (D5)
├── menu/
│   ├── menu_source.py       # shared stdlib parsing core: cafe.md, cocktails.md, the kitchen index, cafe_pantry.md (D1)
│   ├── menu_generator.py    # ordering menu generator: cafe.md + ordering-overrides.json -> menu.json
│   ├── ordering-overrides.json # ordering enrichment: version, orderRules, categories, modifierGroups, per-drink overrides (D2)
│   ├── menu.json            # generated artifact, schema-validated (D3)
│   ├── menu.schema.json     # JSON Schema for menu.json
│   ├── test_menu.py         # artifact integrity suite
│   ├── test_menu_generation.py # generation and derivation suite
│   └── assets/              # optional drink photos, served by the ordering system at /images/menu/
└── site/                    # public menus site
    ├── generate.py          # stdlib generator: parses the recipes sources, joins the workbook, fits print budgets, renders PDFs
    ├── pricing_source.py    # cost workbook parser feeding the priced pages (D8)
    ├── menu-overrides.json  # site curation: bar and kitchen copy keyed by recipes names (D2)
    ├── templates/           # drinks homepage, compact, priced trio, bar, kitchen, pantry
    ├── test_generate.py     # parser, render, join, budget, and assembly suites
    ├── test_menu_staleness.py # menu.json round-trip guard, run where the recipes checkout exists (D3)
    ├── verify_no_js_print.py  # pinned Chrome for Testing print sensor for the built pages (D6)
    └── public/              # generated output, gitignored, deployed by the workflow
```

**Ordering menu pipeline.** `make menu` runs `menu/menu_generator.py`: read `../recipes/cafe.md`, apply `menu/ordering-overrides.json`, derive items through the shared core (D1, D4), validate against `menu.schema.json`, write the canonical serialization (D3).

**Site pipeline.** `make site` (and the deploy workflow) runs `site/generate.py`: parse the four recipes sources through the same core, join the cost workbook for the priced family (D8), render the eight pages through the templates, fit every page to its print budget and render its PDF (D6, D7), and write `site/public/`. Both pipelines are stdlib-only apart from weasyprint (pinned 70.0) and openpyxl for the workbook, run under `uv`.

## 3. Data Design

### 3.1 Ordering menu (`menu/menu.json`)

The document carries `version`, `orderRules`, `categories` (the five drink sections: Cà Phê, Trà, Mát-cha, Giải Khát, Kem), `modifierGroups`, and `items`. Items carry `id` (stable slug; kem builds take `kem-` prefixed ids), `name` (English), `nameVi`, `description`, `categoryId`, `temperatures`, `modifierGroupIds`, and optional `imagePath` (`/images/menu/<itemId>.<ext>`, file in `menu/assets/`). Required modifier groups carry exactly one default mechanism (`defaultOptionId` or `defaultByTemperature`) valid at every temperature the item offers; optional groups carry none.

Generation fails loudly, naming the item, on: unknown override keys, overrides naming drinks absent from the recipes, duplicate resolved ids, unknown modifier-group references, invalid temperatures, and drinks with no derivable description (D4). `make menu` writes nothing on failure.

### 3.2 Curation configs

`menu/ordering-overrides.json` owns everything ordering that recipes cannot express: orderRules (the frozen bounds: notes 200 characters, quantity 1 to 10), the categories and modifier groups, and per-drink overrides (ids, display names, menu copy, images, modifier rules) keyed by recipes drink name. `site/menu-overrides.json` owns site copy: curated descriptions for bar families and kitchen dishes, Vietnamese names and variant merges for the kitchen, and section ordering. Both are checked in; neither is generated.

## 4. Site Generation Design

Six families, nine HTML pages (the drinks render ships twice as `index.html` and `menu.html`), eight print PDFs, all rendered through `site/templates/` with the house identity (cream and cobalt palette, Bungee display, Lora names, Be Vietnam Pro body, nóng/đá pill tags):

| Family | Pages | Source | Notes |
|--------|-------|--------|-------|
| Drinks homepage | `index.html`, `menu.html` | `cafe.md` | Same render, two filenames; section order Cà Phê, Trà, Mát-cha, Giải Khát, Kem; blurbs become section notes; no prices; no ordering artifacts (D9) |
| Compact | `menu/compact.html` | `cafe.md` | One-page dense three-column print reference; descriptions set small, muted, italic |
| Priced | `prices/menu.html`, `prices.html`, `prices/compact.html` | `cafe.md` + `cafe_costs.xlsx` | Selling price right-justified on the name line; the cost-reference pair shows cost plus SRP; Kem builds unpriced; loud join (D8) |
| Bar | `bar.html` | `cocktails.md` | Template families become the COCKTAILS section; curated copy from the overrides config |
| Kitchen | `kitchen.html` | recipes README index over the dish files | Curated names, merges, and ordering from the overrides config |
| Pantry | `pantry.html` | `cafe_pantry.md` | Buying groups become sections under Vietnamese titles held in generator code; quantities ride the subtitle slot |

A drink, cocktail family, dish, or pantry item added to its recipes source appears at the next deploy with no change here; an unplaceable section fails the build (D4). Every page links back to the drinks menu and carries the screen-only PDF View link to its PDF (D7).

## 5. Print and PDF Design

Budgets: menu, priced menu, kitchen, pantry, and prices pages fit two printed A4 and Letter pages; bar, compact, and prices-compact fit one. The build renders each page with weasyprint and steps the print root font size down from 16px to an 11px floor until the page fits both papers; a page that cannot fit fails the build (D6). The fitted root is injected into the shipped HTML so a browser print of the HTML matches the verified fit, and `site/verify_no_js_print.py` re-proves it in the pinned Chrome for Testing shell with JavaScript off, on both papers, as the conservative worst case.

The same pass renders each page to a PDF at its fitted root, gated by the same budgets. The PDFs' `@page` bottom margin box carries the brand line "CAFE ÔNG THỌ · nhà làm · made in house" on every sheet, pinned inside the reserved bottom margin band; the HTML pages keep the single in-flow footer at the content end (D7).

## 6. Deployment

A push to `main` (or a manual dispatch) runs `.github/workflows/menu-pages.yml`: check out this repository and `ThoDHa/recipes` (with the `RECIPES_TOKEN` secret), run the site suites including the staleness guard (which needs the recipes checkout), build `site/public/`, and publish to GitHub Pages with `build_type: workflow`. The drinks menu is the homepage. A missing, expired, or out-of-scope PAT fails the recipes checkout with the same Not Found error, because GitHub reports a repository the token cannot see as nonexistent; the failure is loud at the checkout step (D5).

## 7. Verification Design

- `menu/test_menu_generation.py`: derivation rules against inline fixtures (temperatures, Vietnamese names, default groups, override precedence, kem id derivation, canonical serialization), every loud-failure path, the CLI, and byte-identical regeneration against the committed artifact and the sibling recipes checkout
- `menu/test_menu.py`: artifact integrity: schema conformance, group referential integrity, default-mechanism and temperature coverage, cold foam on iced only, the standard sweetness scale, image path conventions with files present, frozen orderRules, and spot checks (Matcha Sữa milk variance, iced-only Cà Phê Lắc, standalone kem builds)
- `site/test_generate.py`: parsers, rendered pages and chrome needles, the loud pricing joins in both directions, print budgets and PDF artifacts for every page, site assembly and link integrity, and the no-ordering-artifacts rule
- `site/test_menu_staleness.py`: the menu.json round trip, run in the workflow where the recipes checkout is guaranteed to exist
- `make verify-print-chrome`: the no-JavaScript browser print sensor over a fresh build
- Deployment verified end to end: the drinks menu is the homepage, every page reachable, every page within budget on both papers

## 8. Local Operation

| Command | Runs |
|---------|------|
| `make menu` | Regenerate `menu/menu.json` (uv, jsonschema) |
| `make test-menu` | The two menu suites (uv, pytest, jsonschema) |
| `make site` | Build `site/public/` (uv, weasyprint, openpyxl; `--no-fit-pages` skips the budget pass and PDFs) |
| `make test-site` | The site suites (uv, pytest, weasyprint, openpyxl) |
| `make verify-print-chrome` | The browser print sensor (adds playwright and pypdf) |

Both pipelines need only `uv` and the sibling `../recipes` checkout.

## 9. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Recipes prose cannot prove a temperature, or a new section appears in `cafe.md` | Medium | Conservative cue-based derivation with per-item overrides, the temperature cross-checks in the suites, and `UnmappedSectionError` failing the build on unmapped sections (D4) |
| The committed `menu.json` drifts from the recipes or the overrides config | Medium | The staleness suite regenerates from sources and asserts byte equality, running in CI where the checkout exists (D3) |
| The cost workbook and `cafe.md` drift apart | Medium | The loud join fails the deploy naming every unmatched item in both directions (D8) |
| A page outgrows its print budget as content grows | Medium | The build-time fit fails loudly at 16px through the 11px floor; beyond the floor the page must be restructured, and the build says so |
| weasyprint rendering changes across versions | Medium | weasyprint pinned at 70.0 in the Makefile and workflow; the print suites gate any bump |
| The PAT expires or loses scope silently | Low | The checkout fails loudly with the documented Not Found signature; the README documents the required PAT shape |
| Ordering display drifts from the recipes | Medium | One shared parsing core (D1) with the site's own suites cross-checking the same derivations |
