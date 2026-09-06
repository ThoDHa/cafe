#!/usr/bin/env python3
"""Generate the public menus site from the recipes repository.

The drinks menu is generated from recipes/cafe.md through the shared
parsing core in menu/menu_source.py: the four drink sections plus the
cold-foam builds map onto the five menu sections, and items are derived
entirely from the file, so a drink added to recipes appears on the next
deploy with no generator change. The bar menu is generated the same way
from recipes/cocktails.md: the template families become the COCKTAILS
section, with curated copy in site/menu-overrides.json. The kitchen menu
is generated from the recipes README index over the dish files, with the
same overrides file holding the curated names, merges, and copy. This
module keeps only the site's own concerns: section blurbs, templates,
rendering, and the print-budget fit.

Usage: uv run --with weasyprint python site/generate.py [--recipes PATH] [--out DIR]

The build also enforces print budgets: weasyprint renders each page and the
print root font size steps down until the drinks and kitchen pages fit two
A4 and Letter pages and the compact and bar pages fit one, failing the build
if the 11px floor cannot satisfy the budget. Pass --no-fit-pages to skip this
pass (used by fast artifact tests). The published pages also reference the
shared beforeprint scaler (menu/assets/print-fit.js), which refines the
fitted root for the visitor's browser at print time; without JavaScript the
build-injected fit applies unchanged.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = Path(__file__).resolve().parent
MENU_DIR = REPO_ROOT / "menu"
DEFAULT_RECIPES = REPO_ROOT.parent / "recipes" / "cafe.md"
DEFAULT_OUT = SITE_DIR / "public"
TEMPLATES_DIR = SITE_DIR / "templates"
MENU_SOURCE_DIR = MENU_DIR
DEFAULT_OVERRIDES = SITE_DIR / "menu-overrides.json"

sys.path.insert(0, str(MENU_DIR))

import menu_source  # noqa: E402
from menu_source import (  # noqa: E402,F401
    HEADING_RE,
    Item,
    KitchenMenu,
    SECTION_MAP,
    TEMPERATURE_OVERRIDES,
    UnmappedSectionError,
    VIETNAMESE_NAME_OVERRIDES,
    build_bar_items,
    build_kitchen_menu,
    strip_markdown,
)

PRINT_PAGE_BUDGET = 2
COMPACT_PAGE_BUDGET = 1
# Bar prints as one page by user directive (2026-09-05 review); it fits the
# default 16px root already, so this budget only guards against drift.
BAR_PAGE_BUDGET = 1
PRINT_ROOT_DEFAULT = 16.0
PRINT_ROOT_FLOOR = 11.0
PRINT_ROOT_STEP = 1.0
# The compact page spends its slack on spacing, so its fit runs close to the
# page edge; a finer step keeps a drift below the integer root from falling a
# whole pixel and reopening a dead band at the bottom of the page.
COMPACT_PRINT_ROOT_STEP = 0.25
PAPER_SIZES = ("a4", "letter")
PRINT_FIT_SEARCH_SIZE = "letter"
PRINT_FIT_STYLE_ID = "print-fit"
PRINT_SCALER_ASSET_NAME = "print-fit.js"


def _scaler_config(budget: int, page_margins_mm: list[float]) -> dict:
    return {
        "budget": budget,
        "cap": int(PRINT_ROOT_DEFAULT),
        "paper": "letter",
        "pageMarginsMm": page_margins_mm,
    }


# Print-time scaler configuration per published page: the page budget and
# root cap mirrored from the build fit, plus the @page margins (top, bottom)
# in mm each page declares for itself. All four pages share the same
# template @page rule (0.6cm sides and top, 1.2cm bottom = 6/12mm), so the
# browser-side fit models the declared band for every copy. Letter is the
# binding paper for every page; A4 is taller and keeps its geometric
# remainder.
PRINT_SCALER_CONFIGS = {
    "menu.html": _scaler_config(PRINT_PAGE_BUDGET, [6, 12]),
    "menu/compact.html": _scaler_config(COMPACT_PAGE_BUDGET, [6, 12]),
    "kitchen.html": _scaler_config(PRINT_PAGE_BUDGET, [6, 12]),
    "bar.html": _scaler_config(BAR_PAGE_BUDGET, [6, 12]),
}


class PrintFitError(Exception):
    """Raised when a page cannot fit the print page budget at or above the floor size."""


@dataclass
class Section:
    id: str
    title_vi: str
    title_en: str
    items: list[Item] = field(default_factory=list)
    note: str | None = None
    show_pills: bool = True


@dataclass
class Menu:
    sections: list[Section]

    def by_id(self, section_id: str) -> Section:
        for section in self.sections:
            if section.id == section_id:
                return section
        raise KeyError(section_id)

    def temperature_map(self) -> dict[str, list[str]]:
        return {
            item.name_en: item.temperatures
            for section in self.sections
            for item in section.items
        }

    def vietnamese_map(self) -> dict[str, str | None]:
        return {
            item.name_en: item.name_vi
            for section in self.sections
            for item in section.items
        }


def parse_section_note(lines: list[str]) -> str | None:
    paragraphs: list[str] = []
    for line in lines:
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 3:
            break
        if line.strip() and not line.lstrip().startswith(("- ", "|")):
            paragraphs.append(line.strip())
    if not paragraphs:
        return None
    cleaned = strip_markdown("\n".join(paragraphs))
    return cleaned or None


def source_title_by_section_id() -> dict[str, str]:
    titles = {spec[0]: source_title for source_title, spec in SECTION_MAP.items()}
    kem_id, _, _ = menu_source.KEM_SECTION
    titles[kem_id] = "Cold Foams"
    return titles


def parse_menu(text: str) -> Menu:
    source_menu = menu_source.parse_menu(text)
    top_sections = menu_source.split_top_sections(text)
    titles = source_title_by_section_id()
    kem_id = menu_source.KEM_SECTION[0]
    sections = []
    for source_section in source_menu.sections:
        note = None
        if source_section.id != kem_id:
            note = parse_section_note(top_sections.get(titles[source_section.id], []))
        sections.append(
            Section(
                id=source_section.id,
                title_vi=source_section.title_vi,
                title_en=source_section.title_en,
                items=source_section.items,
                note=note,
                show_pills=source_section.id != kem_id,
            )
        )
    return Menu(sections=sections)


def render_pills(temperatures: list[str]) -> str:
    pills = []
    if "hot" in temperatures:
        pills.append('<span class="tag nong">nóng</span>')
    if "iced" in temperatures:
        pills.append('<span class="tag da">đá</span>')
    return f'<span class="tags">{"".join(pills)}</span>'


def item_lead(item: Item) -> str:
    return item.name_vi or item.name_en


def shows_english_subtitle(item: Item) -> bool:
    return bool(
        item.name_vi and item.name_en and item.name_en.lower() != item.name_vi.lower()
    )


def render_item(item: Item, show_pills: bool) -> str:
    line = f'<span class="item-name">{html.escape(item_lead(item))}</span>'
    if show_pills:
        line += render_pills(item.temperatures)
    parts = [f'<div class="item">', f'  <div class="item-line">{line}</div>']
    if shows_english_subtitle(item):
        parts.append(f'  <p class="item-vi">{html.escape(item.name_en)}</p>')
    if item.description:
        parts.append(f'  <p class="item-desc">{html.escape(item.description)}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def render_section(section: Section, item_renderer=None) -> str:
    if item_renderer is None:

        def item_renderer(item: Item) -> str:
            return render_item(item, section.show_pills)

    items = "\n".join(item_renderer(item) for item in section.items)
    parts = [
        "  <section>",
        '    <div class="section-head">',
        f"      <h2>{html.escape(section.title_vi.upper())}</h2>",
        f'      <span class="section-en">{html.escape(section.title_en)}</span>',
        "    </div>",
    ]
    if section.note:
        parts.append(f'    <p class="section-note">{html.escape(section.note)}</p>')
    parts.extend(
        [
            '    <div class="items">',
            items,
            "    </div>",
            "  </section>",
        ]
    )
    return "\n".join(parts)


def render_menu_page(menu: Menu) -> str:
    template = (TEMPLATES_DIR / "menu.html").read_text()
    sections_html = "\n".join(render_section(section) for section in menu.sections)
    return template.replace("<!--SECTIONS-->", sections_html)


def render_compact_page(menu: Menu) -> str:
    template = (TEMPLATES_DIR / "compact.html").read_text()
    sections_html = "\n".join(render_section(section) for section in menu.sections)
    return template.replace("<!--SECTIONS-->", sections_html)


def load_site_overrides(path: Path = DEFAULT_OVERRIDES) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"missing {path}; the generated pages need their overrides config"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {path}: {exc}") from exc


def render_bar_page(items: list[Item]) -> str:
    """Render the bar page with the design reference's exact item formatting.

    The bar chrome carries the drinks markup vocabulary minus the pills;
    the indentation mirrors the former hand page (recoverable from git
    history) so the generated body stays byte-identical to it.
    """

    def render_bar_item(item: Item) -> str:
        parts = [
            '      <div class="item">',
            '        <div class="item-line">',
            f'          <span class="item-name">{html.escape(item_lead(item))}</span>',
            "        </div>",
        ]
        if shows_english_subtitle(item):
            parts.append(f'        <p class="item-vi">{html.escape(item.name_en)}</p>')
        if item.description:
            parts.append(
                f'        <p class="item-desc">{html.escape(item.description)}</p>'
            )
        parts.append("      </div>")
        return "\n".join(parts)

    template = (TEMPLATES_DIR / "bar.html").read_text()
    items_html = "\n".join(render_bar_item(item) for item in items)
    return template.replace("<!--ITEMS-->", items_html)


def render_kitchen_page(kitchen: KitchenMenu) -> str:
    """Render the kitchen page with the design reference's exact formatting.

    Kitchen items lead with their display name and carry an optional
    subtitle; sections are separated by the phin-drip divider, all bytes
    mirroring the former hand page.
    """

    def render_kitchen_item(item: Item) -> str:
        parts = [
            '      <div class="item">',
            '        <div class="item-line">',
            f'          <span class="item-name">{html.escape(item.name_en)}</span>',
            "        </div>",
        ]
        if item.name_vi:
            parts.append(f'        <p class="item-vi">{html.escape(item.name_vi)}</p>')
        if item.description:
            parts.append(
                f'        <p class="item-desc">{html.escape(item.description)}</p>'
            )
        parts.append("      </div>")
        return "\n".join(parts)

    template = (TEMPLATES_DIR / "kitchen.html").read_text()
    drip = (
        "\n\n"
        '  <div class="drip" aria-hidden="true">'
        "<span></span><span></span><span></span></div>\n\n"
    )
    sections_html = drip.join(
        render_section(section, render_kitchen_item) for section in kitchen.sections
    )
    return template.replace("<!--SECTIONS-->", sections_html)


def inject_print_root(page_html: str, root_px: float) -> str:
    style = (
        f'<style id="{PRINT_FIT_STYLE_ID}">'
        f"@media print {{ html {{ font-size: {root_px:g}px; }} }}"
        f"</style>"
    )
    marker = f'id="{PRINT_FIT_STYLE_ID}"'
    if marker in page_html:
        pattern = re.compile(
            rf'<style id="{PRINT_FIT_STYLE_ID}">.*?</style>', re.S
        )
        return pattern.sub(style, page_html)
    return page_html.replace("</head>", f"  {style}\n</head>", 1)


def inject_print_scaler(page_html: str, page_name: str) -> str:
    prefix = "../" if "/" in page_name else ""
    payload = json.dumps(PRINT_SCALER_CONFIGS[page_name], separators=(",", ":"))
    # The attribute is single-quoted: escape &, <, > and single quotes so a
    # future config cannot break out, while today's constants stay
    # byte-identical (they carry none of those characters; the browser
    # decodes entities, so JSON.parse still sees the raw payload). Plain
    # html.escape(quote=True) would also rewrite the payload's double
    # quotes and change the built pages.
    payload = html.escape(payload, quote=False).replace("'", "&#x27;")
    tag = (
        f'<script defer src="{prefix}assets/{PRINT_SCALER_ASSET_NAME}" '
        f"data-print-fit='{payload}'></script>"
    )
    return page_html.replace("</body>", f"  {tag}\n</body>", 1)


def render_page_counts(
    page_html: str, base_url: Path | None = None, papers: tuple[str, ...] = PAPER_SIZES
) -> dict[str, int]:
    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise RuntimeError(
            "print fitting requires weasyprint; run the generator via "
            "'uv run --with weasyprint python site/generate.py'"
        ) from exc
    counts: dict[str, int] = {}
    for size in papers:
        document = HTML(
            string=page_html, base_url=str(base_url or TEMPLATES_DIR)
        ).render(stylesheets=[CSS(string=f"@page {{ size: {size}; }}")])
        counts[size] = len(document.pages)
    return counts


def fit_print_root(
    page_html: str,
    label: str,
    max_pages: int = PRINT_PAGE_BUDGET,
    step: float = PRINT_ROOT_STEP,
) -> tuple[str, float | None]:
    if not (step > 0):
        raise ValueError(f"fit_print_root needs a positive step; got {step}")
    marker = f'id="{PRINT_FIT_STYLE_ID}"'
    had_marker = marker in page_html
    root = PRINT_ROOT_DEFAULT
    while True:
        if root == PRINT_ROOT_DEFAULT and not had_marker:
            candidate = page_html
        else:
            candidate = inject_print_root(page_html, root)
        search_counts = render_page_counts(
            candidate, papers=(PRINT_FIT_SEARCH_SIZE,)
        )
        if search_counts[PRINT_FIT_SEARCH_SIZE] <= max_pages:
            full_counts = render_page_counts(candidate)
            if all(count <= max_pages for count in full_counts.values()):
                if not had_marker and root == PRINT_ROOT_DEFAULT:
                    return page_html, None
                return candidate, root
        if root <= PRINT_ROOT_FLOOR:
            raise PrintFitError(
                f"{label} needs more than {max_pages} printed pages even at the "
                f"{PRINT_ROOT_FLOOR:g}px floor (measured {search_counts} on "
                f"{PRINT_FIT_SEARCH_SIZE}); remove items or raise the page budget"
            )
        root = round(root - step, 2)


def build_site(
    recipes_path: Path,
    out_dir: Path,
    fit_pages: bool = True,
    overrides: dict | None = None,
) -> Menu:
    recipes_text = recipes_path.read_text()
    menu = parse_menu(recipes_text)
    if overrides is None:
        overrides = load_site_overrides()
    cocktails_path = recipes_path.parent / "cocktails.md"
    if not cocktails_path.is_file():
        raise RuntimeError(
            f"missing {cocktails_path}; the bar page is generated from it"
        )
    bar_items = build_bar_items(cocktails_path.read_text(), overrides)
    print(f"bar: {len(bar_items)} families from {cocktails_path.name}")
    readme_path = recipes_path.parent / "README.md"
    if not readme_path.is_file():
        raise RuntimeError(
            f"missing {readme_path}; the kitchen page is generated from it"
        )

    def load_recipe(name: str) -> str:
        return (recipes_path.parent / name).read_text()

    kitchen_menu = build_kitchen_menu(readme_path.read_text(), load_recipe, overrides)
    print(
        f"kitchen: {sum(len(s.items) for s in kitchen_menu.sections)} dishes "
        f"from {readme_path.name}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    scaler_asset = MENU_SOURCE_DIR.joinpath("assets", PRINT_SCALER_ASSET_NAME)
    if not scaler_asset.is_file():
        raise RuntimeError(
            f"missing {scaler_asset}; the published pages reference it "
            "for print-time scaling"
        )
    fitted: list[tuple[str, float | None]] = []
    menu_page = render_menu_page(menu)
    if fit_pages:
        menu_page, menu_root = fit_print_root(menu_page, label="menu.html")
        fitted.append(("index.html", menu_root))
    menu_page = inject_print_scaler(menu_page, "menu.html")
    (out_dir / "index.html").write_text(menu_page)
    (out_dir / "menu.html").write_text(menu_page)
    compact_page = render_compact_page(menu)
    if fit_pages:
        compact_page, compact_root = fit_print_root(
            compact_page,
            label="menu/compact.html",
            max_pages=COMPACT_PAGE_BUDGET,
            step=COMPACT_PRINT_ROOT_STEP,
        )
        fitted.append(("menu/compact.html", compact_root))
    compact_page = inject_print_scaler(compact_page, "menu/compact.html")
    (out_dir / "menu").mkdir(exist_ok=True)
    (out_dir / "menu" / "compact.html").write_text(compact_page)
    bar_page = render_bar_page(bar_items)
    if fit_pages:
        bar_page, bar_root = fit_print_root(
            bar_page, label="bar.html", max_pages=BAR_PAGE_BUDGET
        )
        fitted.append(("bar.html", bar_root))
    bar_page = inject_print_scaler(bar_page, "bar.html")
    (out_dir / "bar.html").write_text(bar_page)
    kitchen_page = render_kitchen_page(kitchen_menu)
    if fit_pages:
        kitchen_page, kitchen_root = fit_print_root(
            kitchen_page, label="kitchen.html", max_pages=PRINT_PAGE_BUDGET
        )
        fitted.append(("kitchen.html", kitchen_root))
    kitchen_page = inject_print_scaler(kitchen_page, "kitchen.html")
    (out_dir / "kitchen.html").write_text(kitchen_page)
    assets_out = out_dir / "assets"
    assets_out.mkdir(exist_ok=True)
    for asset in MENU_SOURCE_DIR.joinpath("assets").iterdir():
        if asset.is_file() and asset.name != ".gitkeep":
            shutil.copyfile(asset, assets_out / asset.name)
    for label, root in fitted:
        if root is None:
            print(f"print fit: {label} fits at the default 16px root")
        else:
            print(f"print fit: {label} fitted at a {root:g}px root")
    return menu


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recipes", type=Path, default=DEFAULT_RECIPES, help="path to cafe.md"
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="output directory"
    )
    parser.add_argument(
        "--no-fit-pages",
        action="store_true",
        help="skip the print-budget fitting pass",
    )
    args = parser.parse_args()
    menu = build_site(args.recipes, args.out, fit_pages=not args.no_fit_pages)
    counts = {s.id: len(s.items) for s in menu.sections}
    total = sum(counts.values())
    print(f"site generated in {args.out}: {total} items " + str(counts))


if __name__ == "__main__":
    main()
