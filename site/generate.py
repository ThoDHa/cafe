#!/usr/bin/env python3
"""Generate the public menus site from the recipes repository.

The drinks menu is generated from recipes/cafe.md through the shared
parsing core in menu/menu_source.py: the four drink sections plus the
cold-foam builds map onto the five menu sections, and items are derived
entirely from the file, so a drink added to recipes appears on the next
deploy with no generator change. This module keeps only the site's own
concerns: section blurbs, templates, rendering, and the print-budget fit.

Usage: uv run --with weasyprint python site/generate.py [--recipes PATH] [--out DIR]

The build also enforces print budgets: weasyprint renders each page and the
print root font size steps down until the drinks, kitchen, and bar pages fit
two A4 and Letter pages and the compact page fits one, failing the build if
the 11px floor cannot satisfy the budget. Pass --no-fit-pages to skip this
pass (used by fast artifact tests).
"""

from __future__ import annotations

import argparse
import html
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

sys.path.insert(0, str(MENU_DIR))

import menu_source  # noqa: E402
from menu_source import (  # noqa: E402,F401
    HEADING_RE,
    Item,
    SECTION_MAP,
    TEMPERATURE_OVERRIDES,
    UnmappedSectionError,
    VIETNAMESE_NAME_OVERRIDES,
    strip_markdown,
)

PRINT_PAGE_BUDGET = 2
COMPACT_PAGE_BUDGET = 1
PRINT_ROOT_DEFAULT = 16.0
PRINT_ROOT_FLOOR = 11.0
PRINT_ROOT_STEP = 1.0
PAPER_SIZES = ("a4", "letter")
PRINT_FIT_SEARCH_SIZE = "letter"
PRINT_FIT_STYLE_ID = "print-fit"


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


def render_item(item: Item, show_pills: bool, compact: bool = False) -> str:
    lead = item.name_vi or item.name_en
    line = f'<span class="item-name">{html.escape(lead)}</span>'
    if show_pills:
        line += render_pills(item.temperatures)
    parts = [f'<div class="item">', f'  <div class="item-line">{line}</div>']
    if item.name_vi and item.name_en and item.name_en.lower() != item.name_vi.lower():
        parts.append(f'  <p class="item-vi">{html.escape(item.name_en)}</p>')
    if not compact and item.description:
        parts.append(f'  <p class="item-desc">{html.escape(item.description)}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def render_section(section: Section, compact: bool = False) -> str:
    items = "\n".join(
        render_item(item, section.show_pills, compact) for item in section.items
    )
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
    sections_html = "\n".join(
        render_section(section, compact=True) for section in menu.sections
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
    page_html: str, label: str, max_pages: int = PRINT_PAGE_BUDGET
) -> tuple[str, float | None]:
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
        root = round(root - PRINT_ROOT_STEP, 2)


def build_site(
    recipes_path: Path, out_dir: Path, fit_pages: bool = True
) -> Menu:
    menu = parse_menu(recipes_path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    fitted: list[tuple[str, float | None]] = []
    menu_page = render_menu_page(menu)
    if fit_pages:
        menu_page, menu_root = fit_print_root(menu_page, label="menu.html")
        fitted.append(("index.html", menu_root))
    (out_dir / "index.html").write_text(menu_page)
    (out_dir / "menu.html").write_text(menu_page)
    compact_page = render_compact_page(menu)
    if fit_pages:
        compact_page, compact_root = fit_print_root(
            compact_page,
            label="menu/compact.html",
            max_pages=COMPACT_PAGE_BUDGET,
        )
        fitted.append(("menu/compact.html", compact_root))
    (out_dir / "menu").mkdir(exist_ok=True)
    (out_dir / "menu" / "compact.html").write_text(compact_page)
    for page in ("kitchen.html", "bar.html"):
        page_html = (MENU_SOURCE_DIR / page).read_text()
        if fit_pages:
            page_html, page_root = fit_print_root(page_html, label=page)
            fitted.append((page, page_root))
        (out_dir / page).write_text(page_html)
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
