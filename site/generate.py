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
if the 11px floor cannot satisfy the budget. The same pass renders each menu
to a print-ready PDF next to its HTML (menu.pdf, menu/compact.pdf, bar.pdf,
kitchen.pdf): the PDF carries the brand line in an @page bottom margin box
on every page, which browsers cannot do in their print preview, so the PDF
is the print path. Pass --no-fit-pages to skip this pass (used by fast
artifact tests). The build-injected fit always applies: every browser
print uses the same fitted margin root, with no print-time scripting.
Each injected fit carries a per-page headroom margin
(PRINT_HEADROOM_STEPS) below the largest root weasyprint fits, calibrated
against Chrome for Testing 153 to absorb the measured
weasyprint-versus-Chrome fragmentation drift near the page edge, and
make verify-print-chrome re-verifies the shipped roots against the
pinned Chrome shell with JavaScript off on both A4 and Letter.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = Path(__file__).resolve().parent
MENU_DIR = REPO_ROOT / "menu"
DEFAULT_RECIPES = REPO_ROOT.parent / "recipes" / "cafe.md"
DEFAULT_OUT = SITE_DIR / "public"
TEMPLATES_DIR = SITE_DIR / "templates"
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
# The print PDF of each page answers to the same page budget as the HTML
# print: the fit pass guarantees it at the fitted root, and the render gate
# below fails the build loudly if the artifact ever drifts over budget.
PDF_PAGE_BUDGETS = {
    "menu.pdf": PRINT_PAGE_BUDGET,
    "menu/compact.pdf": COMPACT_PAGE_BUDGET,
    "bar.pdf": BAR_PAGE_BUDGET,
    "kitchen.pdf": PRINT_PAGE_BUDGET,
}
PRINT_ROOT_DEFAULT = 16.0
PRINT_ROOT_FLOOR = 11.0
PRINT_ROOT_STEP = 1.0
# The compact page spends its slack on spacing, so its fit runs close to the
# page edge; a finer step keeps a drift below the integer root from falling a
# whole pixel and reopening a dead band at the bottom of the page.
COMPACT_PRINT_ROOT_STEP = 0.25
# Per-page headroom, in full steps of the page's own step size: the injected
# root ships this many steps below the largest root weasyprint fits, so a
# no-JavaScript browser print stays inside the budget the gate verified.
# Calibrated against the pinned Chrome for Testing 153 shell by
# make verify-print-chrome, whose measurement is the source of truth: Chrome's
# print fragmentation drifts from weasyprint near the page edge by one
# whole-px step on menu, bar, and kitchen (bar 16→15, kitchen 14→13) but by
# two 0.25-steps on compact (13.75→13.25; one step there ships a 2-page
# no-JS Letter print over compact's 1-page budget). Raise a page's entry if
# the sensor ever measures a wider divergence there.
PRINT_HEADROOM_STEPS = {
    "menu.html": 1,
    "menu/compact.html": 2,
    "bar.html": 1,
    "kitchen.html": 1,
}
PAPER_SIZES = ("a4", "letter")
PRINT_FIT_SEARCH_SIZE = "letter"
PRINT_FIT_STYLE_ID = "print-fit"
# The print PDF is rendered on A4 sheets: the standing margin rule for the
# published menus is measured on A4, and weasyprint pins the page size so
# the artifact does not depend on a viewer default.
PDF_PAPER = "a4"
# The printed brand line lives in the page's own bottom margin band; the
# in-flow footer is hidden so the last page does not carry the line twice.
PDF_ONLY_STYLESHEET = """
footer { display: none; }
/* The PDFs print on white stock (user direction 2026-09-07): every
   page-level surface the HTML print CSS paints cream is neutralized to
   white here, so this sheet reaches the PDF artifacts only and the HTML
   print preview keeps the cream design. The header rule also recolors the
   plaque's cream inset ring, which would otherwise survive as a warm band
   on the white plaque. Ink (text, seal, borders, pills, the margin-box
   brand line) is left untouched. The !important flags are a weasyprint 69
   requirement, not emphasis: it applies render()-passed author stylesheets
   BEFORE the page's own <style> sheets, so equal-specificity declarations
   from this sheet lose; important declarations win the cascade instead. */
html, body { background: #fff !important; }
.card, header { background: #fff !important; }
header { box-shadow: inset 0 0 0 4px #fff, inset 0 0 0 5px #1F3564 !important; }
@page {
  @bottom-center {
    content: "CAFE ÔNG THỌ · nhà làm · made in house";
    font-family: 'Be Vietnam Pro', 'Segoe UI', system-ui, sans-serif;
    font-size: 0.88rem;
    color: #56513F;
  }
}
"""


# The one copy of the print rules shared by every built page, defined
# empirically as the rules byte-identical across all four templates after
# 8520df6. Templates carry a /*SHARED_PRINT:<key>*/ marker exactly where
# each entry's rules stood, and injection substitutes the entry verbatim
# (indentation included), so the built pages stay byte-identical to the
# pre-injection build. Rules any page treats differently (`.card` padding,
# `.drip`/`footer nav`/`footer a`/`.own-page`, the per-page type scales)
# remain in the templates.
SHARED_PRINT_RULES = {
    "page": "  @page { margin: 0.6cm; margin-bottom: 1.2cm; }",
    "base": "    html, body { background: var(--sua); padding: 0; }",
    # overflow: hidden keeps .section-head monolithic for print fragmentation
    # (css-break): Blink otherwise emits a pushed head's h2 text run in the
    # previous fragmentainer when its glyphs' ink crosses the page edge, which
    # prints tall Vietnamese diacritic ink into the A4 bottom margin band.
    # Proven against Blink via chrome-headless-shell 1228. Removal condition:
    # overflow: hidden clips silently if fallback font metrics ever exceed
    # the 1.25 line box, so A4 print output must be re-verified before
    # removing the workaround.
    "keep": (
        "    section, .item { break-inside: avoid; }\n"
        "    .section-head { overflow: hidden; break-after: avoid; }"
    ),
    "color": (
        "    .seal, .tag {\n"
        "      print-color-adjust: exact;\n"
        "      -webkit-print-color-adjust: exact;\n"
        "    }"
    ),
    "header": (
        "    header { padding: 0.8rem 1rem 1rem; }\n"
        "    h1 { font-size: 1.9rem; }\n"
        "    .seal { width: 2.2rem; height: 2.2rem; margin-top: 0.5rem; }\n"
        "    .eyebrow { margin-bottom: 0.4rem; }\n"
        "    .tagline { margin-top: 0.5rem; }"
    ),
    "footer": "    footer { margin-top: 1rem; padding-top: 0.5rem; }",
    # The PDF View link is a screen-only affordance: the PDF is the print
    # path, so printing the HTML page must never show the link.
    "pdf-link": "    .pdf-link { display: none; }",
}

# An unterminated /*SHARED_PRINT marker leaves the whole template remainder
# as error context; the bound keeps one typo from flooding the build log
# with the rest of the file.
UNTERMINATED_MARKER_CONTEXT_LIMIT = 120


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
    """Render the temperature pills as two fixed slots, nóng then đá.

    An absent temperature leaves a reserved placeholder slot built like
    its real pill (same text, padding, and border) so the box keeps the
    pill's width; the template's .tag.slot rule paints it nothing. Both
    pill columns therefore hold their x positions on every item.
    """

    def slot(css_class: str, label: str, present: bool) -> str:
        if present:
            return f'<span class="tag {css_class}">{label}</span>'
        return (
            f'<span class="tag slot {css_class}" aria-hidden="true">'
            f"{label}</span>"
        )

    return (
        '<span class="tags">'
        + slot("nong", "nóng", "hot" in temperatures)
        + slot("da", "đá", "iced" in temperatures)
        + "</span>"
    )


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


def items_open_tag(item_count: int, columns: int) -> str:
    """Open the section's .items grid with its explicit row count.

    The grid fills column-major (grid-auto-flow: column), which needs an
    explicit row count: with R = ceil(items/columns) rows, items of equal
    rank share one grid row, so partner columns line up item to item. The
    style attribute is emitted per section because the count is data, not
    design.
    """

    rows = math.ceil(item_count / columns)
    return f'<div class="items" style="grid-template-rows: repeat({rows}, auto)">'


def render_section(
    section: Section,
    item_renderer=None,
    columns: int = 2,
    css_class: str | None = None,
) -> str:
    if item_renderer is None:

        def item_renderer(item: Item) -> str:
            return render_item(item, section.show_pills)

    items = "\n".join(item_renderer(item) for item in section.items)
    opening = (
        "  <section>"
        if css_class is None
        else f'  <section class="{html.escape(css_class)}">'
    )
    parts = [
        opening,
        '    <div class="section-head">',
        f"      <h2>{html.escape(section.title_vi.upper())}</h2>",
        f'      <span class="section-en">{html.escape(section.title_en)}</span>',
        "    </div>",
    ]
    if section.note:
        parts.append(f'    <p class="section-note">{html.escape(section.note)}</p>')
    parts.extend(
        [
            f"    {items_open_tag(len(section.items), columns)}",
            items,
            "    </div>",
            "  </section>",
        ]
    )
    return "\n".join(parts)


def inject_shared_print_css(page_html: str, template_name: str) -> str:
    """Substitute the template's shared-print markers with the shared rules.

    A marker that names no SHARED_PRINT_RULES entry would silently drop
    shared print CSS from the built page (the leftover text is a legal CSS
    comment), so an unresolved marker fails the build instead.
    """

    for key, css in SHARED_PRINT_RULES.items():
        page_html = page_html.replace(f"/*SHARED_PRINT:{key}*/", css)
    start = page_html.find("/*SHARED_PRINT")
    if start != -1:
        end = page_html.find("*/", start)
        if end == -1:
            newline = page_html.find("\n", start)
            stop = start + UNTERMINATED_MARKER_CONTEXT_LIMIT
            if newline != -1:
                stop = min(stop, newline)
            leftover = page_html[start:stop]
        else:
            leftover = page_html[start : end + 2]
        raise RuntimeError(
            f"{template_name}: unresolved shared print CSS marker "
            f"{leftover!r}; markers must name a SHARED_PRINT_RULES entry"
        )
    return page_html


def read_template(name: str) -> str:
    """Read a page template with the shared print CSS injected."""

    return inject_shared_print_css(
        (TEMPLATES_DIR / name).read_text(), template_name=name
    )


# The drinks page's second printed sheet opens with Mát-cha: the menu
# render alone tags that section with .own-page (print-only break-before
# in the template), so page 1 = Cà Phê + Trà and page 2 = Mát-cha + the
# rest. The compact and kitchen renders share render_section and never
# pass the class.
MENU_PAGE_BREAK_SECTION_ID = "mat-cha"
OWN_PAGE_CSS_CLASS = "own-page"


def render_menu_page(menu: Menu) -> str:
    template = read_template("menu.html")
    sections_html = "\n".join(
        render_section(
            section,
            css_class=(
                OWN_PAGE_CSS_CLASS
                if section.id == MENU_PAGE_BREAK_SECTION_ID
                else None
            ),
        )
        for section in menu.sections
    )
    return template.replace("<!--SECTIONS-->", sections_html)


def render_compact_page(menu: Menu) -> str:
    template = read_template("compact.html")
    sections_html = "\n".join(
        render_section(section, columns=3) for section in menu.sections
    )
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

    template = read_template("bar.html")
    items_html = "\n".join(render_bar_item(item) for item in items)
    template = template.replace(
        '<div class="items">', items_open_tag(len(items), columns=2)
    )
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

    template = read_template("kitchen.html")
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


def _load_weasyprint() -> tuple[type, type]:
    try:
        from weasyprint import CSS, HTML
    except ImportError as exc:
        raise RuntimeError(
            "print fitting requires weasyprint; run the generator via "
            "'uv run --with weasyprint python site/generate.py'"
        ) from exc
    return CSS, HTML


def render_page_counts(
    page_html: str, base_url: Path | None = None, papers: tuple[str, ...] = PAPER_SIZES
) -> dict[str, int]:
    CSS, HTML = _load_weasyprint()
    counts: dict[str, int] = {}
    for size in papers:
        document = HTML(
            string=page_html, base_url=str(base_url or TEMPLATES_DIR)
        ).render(stylesheets=[CSS(string=f"@page {{ size: {size}; }}")])
        counts[size] = len(document.pages)
    return counts


def write_print_pdf(
    page_html: str, out_path: Path, label: str, max_pages: int
) -> int:
    """Render a page's print-ready PDF artifact and enforce its page budget.

    The page renders with the PDF-only stylesheet applied on top of its own
    print CSS: the in-flow footer is hidden and the brand line is painted
    into the @page bottom margin band of every sheet. The rendered page
    count is checked against ``max_pages`` (the page's print budget) before
    anything is written, so a budget violation fails the build loudly and
    leaves no artifact behind. Returns the rendered page count.
    """

    CSS, HTML = _load_weasyprint()
    document = HTML(
        string=page_html, base_url=str(TEMPLATES_DIR)
    ).render(
        stylesheets=[
            CSS(string=f"@page {{ size: {PDF_PAPER}; }}"),
            CSS(string=PDF_ONLY_STYLESHEET),
        ]
    )
    count = len(document.pages)
    if count > max_pages:
        raise PrintFitError(
            f"{label} renders a {count}-page print PDF on {PDF_PAPER}, over "
            f"its {max_pages}-page budget; remove items or raise the page budget"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.write_pdf(str(out_path))
    print(
        f"print pdf: {label} on {PDF_PAPER} sheets: {count} pages "
        f"(budget {max_pages})"
    )
    return count


def fit_print_root(
    page_html: str,
    label: str,
    max_pages: int = PRINT_PAGE_BUDGET,
    step: float = PRINT_ROOT_STEP,
    headroom_steps: int = 1,
) -> tuple[str, float]:
    """Fit a page's print root under its page budget, with headroom margin.

    Walks down from ``PRINT_ROOT_DEFAULT`` by ``step`` to the floor, accepts
    the first root where the letter search fits and both papers verify, then
    ships ``headroom_steps`` full steps of ``step`` below that root instead,
    clamped at the floor, so the injected fit also holds in a no-JavaScript
    browser whose fragmentation drifts from weasyprint near the page edge.
    Per-page calibration lives in ``PRINT_HEADROOM_STEPS``, which
    ``build_site`` feeds in here. The accepted root is re-verified on both
    papers before returning, except when the floor clamp lands the margin on
    the root the walk just verified: the margin candidate is then
    byte-identical to the verified one, so the held counts gate it. A
    pathological non-monotonic failure keeps stepping down to the floor,
    where a loud warning prints and the floor root ships without its
    headroom margin. Raises ``ValueError`` for a headroom below one step and
    ``PrintFitError`` when even the floor cannot satisfy the budget.
    """

    if not (step > 0):
        raise ValueError(f"fit_print_root needs a positive step; got {step}")
    if not (headroom_steps >= 1):
        raise ValueError(
            f"fit_print_root needs a headroom of at least 1 step; got "
            f"{headroom_steps}"
        )
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
                accepted = max(
                    round(root - headroom_steps * step, 2),
                    PRINT_ROOT_FLOOR,
                )
                clamped_at_floor = root - headroom_steps * step < PRINT_ROOT_FLOOR
                if clamped_at_floor:
                    print(
                        f"print fit: WARNING {label} clamps at the "
                        f"{PRINT_ROOT_FLOOR:g}px floor: the "
                        f"{headroom_steps}-step headroom margin is "
                        "exhausted; make verify-print-chrome must clear "
                        "this root"
                    )
                # The clamp landing accepted == root re-renders the exact
                # candidate the walk just verified on both papers; gate it
                # on the counts already held. Real margin roots re-verify.
                if clamped_at_floor and accepted == root:
                    margin_counts = full_counts
                else:
                    margin_counts = None
                while True:
                    if margin_counts is None:
                        candidate = inject_print_root(page_html, accepted)
                        margin_counts = render_page_counts(candidate)
                    if all(
                        count <= max_pages for count in margin_counts.values()
                    ):
                        return candidate, accepted
                    if accepted <= PRINT_ROOT_FLOOR:
                        raise PrintFitError(
                            f"{label} needs more than {max_pages} printed pages even at the "
                            f"{PRINT_ROOT_FLOOR:g}px floor (measured {margin_counts} on "
                            f"{', '.join(PAPER_SIZES)}); remove items or raise the page budget"
                        )
                    margin_counts = None
                    accepted = round(accepted - step, 2)
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
    fitted: list[tuple[str, float]] = []
    menu_page = render_menu_page(menu)
    if fit_pages:
        menu_page, menu_root = fit_print_root(
            menu_page,
            label="menu.html",
            headroom_steps=PRINT_HEADROOM_STEPS["menu.html"],
        )
        fitted.append(("index.html", menu_root))
    (out_dir / "index.html").write_text(menu_page)
    (out_dir / "menu.html").write_text(menu_page)
    compact_page = render_compact_page(menu)
    if fit_pages:
        compact_page, compact_root = fit_print_root(
            compact_page,
            label="menu/compact.html",
            max_pages=COMPACT_PAGE_BUDGET,
            step=COMPACT_PRINT_ROOT_STEP,
            headroom_steps=PRINT_HEADROOM_STEPS["menu/compact.html"],
        )
        fitted.append(("menu/compact.html", compact_root))
    (out_dir / "menu").mkdir(exist_ok=True)
    (out_dir / "menu" / "compact.html").write_text(compact_page)
    bar_page = render_bar_page(bar_items)
    if fit_pages:
        bar_page, bar_root = fit_print_root(
            bar_page,
            label="bar.html",
            max_pages=BAR_PAGE_BUDGET,
            headroom_steps=PRINT_HEADROOM_STEPS["bar.html"],
        )
        fitted.append(("bar.html", bar_root))
    (out_dir / "bar.html").write_text(bar_page)
    kitchen_page = render_kitchen_page(kitchen_menu)
    if fit_pages:
        kitchen_page, kitchen_root = fit_print_root(
            kitchen_page,
            label="kitchen.html",
            max_pages=PRINT_PAGE_BUDGET,
            headroom_steps=PRINT_HEADROOM_STEPS["kitchen.html"],
        )
        fitted.append(("kitchen.html", kitchen_root))
    (out_dir / "kitchen.html").write_text(kitchen_page)
    if fit_pages:
        # The PDF artifact renders from the final built HTML (the
        # fit-injected root included), so it paginates exactly like the
        # published page. --no-fit-pages skips it:
        # without the fit pass the unfitted roots legitimately overflow the
        # budgets and the gate would fail by design.
        for pdf_name, page_html in (
            ("menu.pdf", menu_page),
            ("menu/compact.pdf", compact_page),
            ("bar.pdf", bar_page),
            ("kitchen.pdf", kitchen_page),
        ):
            write_print_pdf(
                page_html,
                out_dir / pdf_name,
                label=pdf_name,
                max_pages=PDF_PAGE_BUDGETS[pdf_name],
            )
    for label, root in fitted:
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
        help="skip the print-budget fitting pass and the print PDF artifacts",
    )
    args = parser.parse_args()
    menu = build_site(args.recipes, args.out, fit_pages=not args.no_fit_pages)
    counts = {s.id: len(s.items) for s in menu.sections}
    total = sum(counts.values())
    print(f"site generated in {args.out}: {total} items " + str(counts))


if __name__ == "__main__":
    main()
