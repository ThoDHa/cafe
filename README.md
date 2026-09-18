# Cafe Ông Thọ Menus

Two generation pipelines with one shared recipes-parsing core, both fed by the private [recipes](../recipes) repository: the public menus site at [thodha.github.io/cafe](https://thodha.github.io/cafe/) and the ordering menu document (`menu/menu.json`) that captures the drinks with their customization rules. The site is static browsing only; the ordering menu is a generated data artifact.

The requirements live in two PRDs: the menus system (the pipelines in this repository) in [MENUS_REQUIREMENTS.md](MENUS_REQUIREMENTS.md), and the ordering application (guest ordering surface plus barista queue surface, built on the menu document) in [ORDERING_REQUIREMENTS.md](ORDERING_REQUIREMENTS.md). The menus design decisions are recorded in [MENUS_DESIGN.md](MENUS_DESIGN.md). The ordering application is not built yet; this repository currently carries the two generation pipelines.

## Ordering Menu

`menu/menu.json` is generated, never hand-edited: `make menu` runs [`menu/menu_generator.py`](menu/menu_generator.py), which reads `cafe.md` from the sibling `../recipes` checkout, applies the checked-in enrichment config [`menu/ordering-overrides.json`](menu/ordering-overrides.json) (version, orderRules, categories, modifierGroups, plus per-drink overrides for what recipes cannot express: ids, display names, menu copy, images, modifier rules), validates the result against [`menu/menu.schema.json`](menu/menu.schema.json), and writes the canonical artifact. The parsing core in [`menu/menu_source.py`](menu/menu_source.py) is shared with the site generator, so the two derivations cannot diverge. A drink added to recipes appears in the menu with sensible defaults and no code or config change.

`make test-menu` validates the committed artifact: schema conformance, referential integrity of modifier groups, temperature coverage, image path conventions, and a regeneration round trip proving `menu.json` matches its sources byte for byte. The staleness guard in [`site/test_menu_staleness.py`](site/test_menu_staleness.py) runs the same round trip in the Pages workflow, where the recipes checkout is guaranteed to exist.

## Public Menus Site

The menus and the pantry shopping list are publicly browsable at [thodha.github.io/cafe](https://thodha.github.io/cafe/), independent of the home ordering system:

- **Drinks menu, the homepage** (`/cafe/` and `/cafe/menu.html`): generated at deploy time by [`site/generate.py`](site/generate.py), which pulls drinks from `cafe.md` in the private [recipes repository](https://github.com/ThoDHa/recipes), checked out with the `RECIPES_TOKEN` secret, and renders them through the templates in [`site/templates/`](site/templates/). The four drink sections print in the order Cà Phê, Trà, Mát-cha, Giải Khát, then Kem; each category's blurb in `cafe.md` appears as its section note. The homepage menu carries no prices; priced views live one click away under the Giá family (the priced menu and the cost-reference prices). A drink added to recipes appears at the next deployment with no change here; a drink-like section the generator cannot place fails the build loudly instead of being dropped.
- **Compact menu** (`/cafe/menu/compact.html`): a one-page print reference with the same items, keeping Vietnamese and English names, nóng/đá tags, the category blurbs, and each drink's description, set small, muted, and italic so the dense three-column page still fits its print budget. Like the homepage menu it carries no prices.
- **Priced menu** (`/cafe/prices/menu.html`): the drinks menu layout with one selling price right-justified on every drink's name line outside the Kem cold-foam section, generated at deploy time by joining `cafe_costs.xlsx` in the recipes repository onto the cafe.md drinks through [`site/generate.py`](site/generate.py). Each price is the workbook's Menu Price (the suggested retail) exactly as the workbook evaluates it, and the Kem cold-foam builds show no price. A workbook row that matches no menu drink, or a drink with no workbook row, fails the deploy loudly naming every unmatched drink in both directions; this loud join covers the whole Giá family, so one unmatched drink blocks the priced menu and the cost-reference pair together. A workbook edit reprices the page at the next deploy with no code change here.
- **Cost-reference prices** (`/cafe/prices.html` and `/cafe/prices/compact.html`): the drinks with a cost-plus-SRP cluster right-justified on every drink's name line, generated at deploy time through the same join (workbook parsing in [`site/pricing_source.py`](site/pricing_source.py)). Every drink outside the Kem cold-foam section is priced individually, Bạc Xỉu included: it is priced in its own place when cafe.md defines the drink natively, and the curated Bạc Xỉu line is inserted right after House Latte when cafe.md describes it only as a variation; each drink's name line shows the cost to make and the suggested retail price exactly as the workbook evaluates them, so both numbers are always the workbook's own current figures. The cost is a planning estimate and the suggested retail is the suggested retail per the cost workbook; this repository hardcodes no pricing rule. Join failures follow the priced menu's loud-join rule above.
- **Bar menu** (`bar.html`): generated at deploy time from `cocktails.md` in the recipes repository through the same shared parsing core as the drinks menu; the template families become the COCKTAILS section, with the curated descriptions in [`site/menu-overrides.json`](site/menu-overrides.json). A cocktail template family added to recipes appears at the next deployment with no change here.
- **Kitchen menu** (`kitchen.html`): generated at deploy time from the recipes repository like the bar menu: the "Available Recipes" index in `README.md` places each dish in its section, the dish files back every link and anchor, and the curated Vietnamese names, variant merges, and descriptions live in [`site/menu-overrides.json`](site/menu-overrides.json). A dish added to the index appears at the next deployment with no change here; an index group the generator cannot place fails the build loudly.
- **Pantry list** (`pantry.html`): generated at deploy time from `cafe_pantry.md` in the recipes repository through the same shared parsing core; the three buying groups become sections under curated Vietnamese section titles held in the site's generator code (not the overrides file), and each item's quantity or buy spec rides the subtitle slot. A pantry item added to the pantry file appears at the next deployment with no change here, and a buying group the list adds later falls back to its English section title.
- **Print budgets enforced at build time**: the generator renders every page with weasyprint and steps the print font size down (16px to an 11px floor) until the menu, priced menu, kitchen, pantry, and prices pages fit two printed pages on A4 and Letter, and the bar, compact, and prices-compact pages fit one. A page that cannot fit fails the build instead of shipping an overflowing printout. The rendered PDFs answer to the same budgets, and a PDF over its page budget fails the build the same way.
- **Print-ready PDFs** (`menu.pdf`, `menu/compact.pdf`, `prices/menu.pdf`, `bar.pdf`, `kitchen.pdf`, `pantry.pdf`, `prices.pdf`, `prices/compact.pdf`): the same build pass renders each menu to a PDF next to its HTML. The PDFs are the print path: their `@page` bottom margin box carries the brand line "CAFE ÔNG THỌ · nhà làm · made in house" on every page, including pages 1 and 2 of the drinks, priced menu, kitchen, and prices menus, pinned inside the bottom margin band like a printed footer. A browser print preview cannot pin a footer to every page, so printing a menu means opening its PDF and printing that; each HTML page carries a screen-only "PDF View" link to its PDF, and printing the HTML page itself keeps the single in-flow footer at the content end.

## Repository Layout

```
cafe/
├── MENUS_REQUIREMENTS.md    # the menus system's requirements
├── MENUS_DESIGN.md          # the menus system's decision record and design
├── ORDERING_REQUIREMENTS.md # the ordering application's requirements
├── Makefile                 # menu, test-menu, site, test-site, verify-print-chrome
├── .github/workflows/menu-pages.yml   # generates the menus site from recipes, deploys Pages
├── menu/
│   ├── menu_source.py       # shared stdlib parsing core for recipes cafe.md, cocktails.md, the kitchen index, and cafe_pantry.md (site + ordering menu)
│   ├── menu_generator.py    # ordering menu generator: recipes cafe.md + ordering-overrides.json -> menu.json
│   ├── ordering-overrides.json # ordering enrichment: version, orderRules, categories, modifierGroups, per-drink overrides keyed by recipes name
│   ├── menu.json            # the orderable menu (generated via make menu, schema-validated)
│   ├── menu.schema.json     # JSON Schema for menu.json
│   ├── test_menu.py         # artifact validation suite
│   ├── test_menu_generation.py # generation suite
│   └── assets/              # drink photos, optional
└── site/                    # public menus site
    ├── generate.py          # stdlib generator: parses recipes cafe.md, cocktails.md, the kitchen index, and cafe_pantry.md, renders templates
    ├── test_generate.py     # parser, render, and site-assembly tests
    ├── menu-overrides.json  # site curation: per-page bar/kitchen overrides keyed by recipes names
    ├── templates/           # full drinks page (menu.html), one-page compact, priced pages, bar page, kitchen page
    └── public/              # generated artifact, gitignored, deployed by the workflow
```

## Deploying

A push to `main` (or a manual workflow dispatch) runs [`.github/workflows/menu-pages.yml`](.github/workflows/menu-pages.yml), which runs the generator's tests, regenerates the site from the latest recipes, and publishes it to this repository's GitHub Pages. The recipes checkout authenticates with the `RECIPES_TOKEN` repository secret, a fine-grained PAT scoped to `ThoDHa/recipes` with Contents: read-only; a missing, expired, or out-of-scope PAT fails that checkout with the same Not Found error, because GitHub reports a repository the token cannot see as nonexistent.

## Working Locally

- `make menu` regenerates `menu/menu.json` from the sibling `../recipes` checkout (`uv run --with jsonschema`)
- `make test-menu` runs the menu artifact and generation suites (`uv run --with pytest`)
- `make site` regenerates `site/public/` from the sibling `../recipes` checkout (runs under `uv` with weasyprint and openpyxl; pass `--no-fit-pages` to skip the print-budget pass and the print PDFs)
- `make test-site` runs the site suite (`uv run --with pytest`, weasyprint and openpyxl)
- `make verify-print-chrome` prints every built page in the pinned Chrome for Testing shell with JavaScript off and fails if any page overflows its print budget on Letter or A4
