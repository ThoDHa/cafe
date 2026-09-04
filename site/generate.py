#!/usr/bin/env python3
"""Generate the public menus site from the recipes repository.

The drinks menu is generated from recipes/cafe.md: the four drink sections
plus the cold-foam builds map onto the five menu sections, and items are
derived entirely from the file, so a drink added to recipes appears on the
next deploy with no generator change. Only menu-shape knowledge that recipes
cannot express (section titles, Vietnamese names recipes omit, a temperature
the prose cannot prove) lives in the configuration below.

Usage: python3 site/generate.py [--recipes PATH] [--out DIR]
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = Path(__file__).resolve().parent
DEFAULT_RECIPES = REPO_ROOT.parent / "recipes" / "cafe.md"
DEFAULT_OUT = SITE_DIR / "public"
TEMPLATES_DIR = SITE_DIR / "templates"
MENU_SOURCE_DIR = REPO_ROOT / "menu"

SECTION_MAP = {
    "Coffee": ("ca-phe", "Cà Phê", "Coffee"),
    "Matcha": ("mat-cha", "Mát-cha", "Matcha"),
    "Tea": ("tra", "Trà", "Tea"),
    "Refreshers": ("giai-khat", "Giải Khát", "Refreshers"),
}
KEM_SECTION = ("kem", "Kem", "Cold Foams")

KNOWN_NON_DRINK_SECTIONS = {
    "Table of Contents",
    "Drink Matrix",
    "Pantry Staples",
    "Bases",
    "Cold Foams",
    "Presentation",
    "Drink Construction Rules",
    "Notes",
}

VIETNAMESE_NAME_OVERRIDES = {
    "Cinnamon Oat Shakerato": "Cà Phê Lắc",
    "Dirty Matcha": "Matcha Cà Phê",
    "Hot Tea": "Trà",
    "Lemon Tea": "Trà Chanh",
    "Milk Tea": "Trà Sữa",
    "Gongfu Tea": "Trà Công Phu",
    "Cocoa": "Cacao Sữa",
    "Strawberry Milk": "Sữa Dâu",
    "Strawberry Soda": "Soda Dâu",
    "Strawberry Limeade": "Soda Dâu Chanh",
}

TEMPERATURE_OVERRIDES = {
    "Hot Tea": ["hot", "iced"],
}

FOAM_VIETNAMESE_NAMES = {
    "Base": "Kem Sữa",
    "Salted": "Kem Muối",
    "Strawberry": "Kem Dâu",
    "Cocoa": "Kem Cacao",
    "Matcha": "Kem Matcha",
    "Tea": "Kem Trà",
    "Cheese": "Kem Phô Mai",
    "Yogurt": "Kem Sữa Chua",
}

FOAM_DESCRIPTION_FALLBACKS = {
    "Base": "Cream and milk frothed thick, spooned over the drink.",
    "Cocoa": "Cocoa and turbinado whisked to a paste, folded into the base foam.",
    "Matcha": "Matcha whisked hot until hydrated, folded into the base foam.",
}

STRUCTURAL_HEADINGS = {
    "Instructions",
    "Notes",
    "Uses",
    "Straight Serve",
    "Hot",
    "Iced",
    "Variations",
    "Strawberry Variation",
    "Dirty Version",
}

SERVE_CUE_PARAGRAPHS = {
    "served hot or iced",
    "hot or iced",
    "served iced",
    "served hot",
}

HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
ICE_WORD_RE = re.compile(r"\bice\b", re.IGNORECASE)


class UnmappedSectionError(Exception):
    """Raised when cafe.md contains a drink-like section the menu cannot place."""


@dataclass
class Item:
    name_en: str
    name_vi: str | None
    description: str | None
    temperatures: list[str]


@dataclass
class Section:
    id: str
    title_vi: str
    title_en: str
    items: list[Item] = field(default_factory=list)
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


def split_top_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 2:
            current = match.group(2).strip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def split_drinks(lines: list[str]) -> list[tuple[str, list[str]]]:
    drinks: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_lines: list[str] = []
    for line in lines:
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 3:
            if current_name is not None:
                drinks.append((current_name, current_lines))
            current_name = match.group(2).strip()
            current_lines = []
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        drinks.append((current_name, current_lines))
    return drinks


def blocks(lines: list[str]) -> list[tuple[str, str]]:
    """Group lines into (kind, text) blocks: heading, list, table, or paragraph."""
    result: list[tuple[str, str]] = []
    buffer: list[str] = []
    kind: str | None = None

    def flush() -> None:
        nonlocal buffer, kind
        if buffer and kind:
            result.append((kind, "\n".join(buffer).strip()))
        buffer = []
        kind = None

    for line in lines:
        match = HEADING_RE.match(line)
        if match:
            flush()
            result.append(("heading", match.group(2).strip()))
        elif line.lstrip().startswith("- "):
            if kind != "list":
                flush()
                kind = "list"
            buffer.append(line.strip())
        elif line.lstrip().startswith("|"):
            if kind != "table":
                flush()
                kind = "table"
            buffer.append(line.strip())
        elif not line.strip():
            flush()
        else:
            if kind != "paragraph":
                flush()
                kind = "paragraph"
            buffer.append(line.strip())
    flush()
    return result


def strip_markdown(text: str) -> str:
    text = LINK_RE.sub(r"\1", text)
    text = BOLD_RE.sub(r"\1", text)
    text = ITALIC_RE.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def is_serve_cue(paragraph: str) -> bool:
    return strip_markdown(paragraph).rstrip(".").strip().lower() in SERVE_CUE_PARAGRAPHS


def first_paragraph_after_name(drink_blocks: list[tuple[str, str]]) -> str | None:
    seen_name_heading = False
    for kind, text in drink_blocks:
        if kind == "heading":
            if not seen_name_heading and text not in STRUCTURAL_HEADINGS:
                seen_name_heading = True
                continue
            continue
        if kind == "paragraph":
            if is_serve_cue(text):
                continue
            cleaned = strip_markdown(text)
            cleaned = re.sub(r"^Iced only:\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"^Hot only:\s*", "", cleaned, flags=re.IGNORECASE)
            return cleaned or None
        break
    return None


def vietnamese_name(drink_blocks: list[tuple[str, str]]) -> str | None:
    for kind, text in drink_blocks:
        if kind == "heading":
            if text in STRUCTURAL_HEADINGS:
                return None
            return text
        return None
    return None


def derive_temperatures(name_en: str, drink_blocks: list[tuple[str, str]]) -> list[str]:
    if name_en in TEMPERATURE_OVERRIDES:
        return list(TEMPERATURE_OVERRIDES[name_en])
    full_text = "\n".join(text for _, text in drink_blocks).lower()
    if "iced only" in full_text:
        return ["iced"]
    if "hot or iced" in full_text:
        return ["hot", "iced"]
    if "**hot:**" in full_text and "**iced:**" in full_text:
        return ["hot", "iced"]
    for kind, text in drink_blocks:
        if kind == "list":
            for line in text.splitlines():
                if ICE_WORD_RE.search(line) and "ice cream" not in line.lower():
                    return ["iced"]
    if "served iced" in full_text:
        return ["iced"]
    return ["hot"]


def parse_drink_section(lines: list[str]) -> list[Item]:
    items: list[Item] = []
    for name_en, drink_lines in split_drinks(lines):
        drink_blocks = blocks(drink_lines)
        name_vi = VIETNAMESE_NAME_OVERRIDES.get(name_en) or vietnamese_name(drink_blocks)
        items.append(
            Item(
                name_en=name_en,
                name_vi=name_vi,
                description=first_paragraph_after_name(drink_blocks),
                temperatures=derive_temperatures(name_en, drink_blocks),
            )
        )
    return items


def parse_foam_matrix(lines: list[str]) -> list[str]:
    builds: list[str] = []
    in_matrix = False
    for line in lines:
        if line.startswith("### "):
            in_matrix = line.strip() == "### Foam Matrix"
            continue
        if in_matrix and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if not cells or set(cells[0]) <= {"-", " ", ":"}:
                continue
            link = re.match(r"\[([^\]]+)\]", cells[0])
            if link:
                build = link.group(1).strip()
                if build.lower() not in {"build"} and build not in builds:
                    builds.append(build)
    return builds


def foam_description(build: str, section_lines: list[str]) -> str | None:
    headings = ["Base Foam"] if build == "Base" else [f"{build} Cold Foam"]
    section_blocks = blocks(section_lines)
    for index, (kind, text) in enumerate(section_blocks):
        if kind == "heading" and text in headings:
            for block_kind, block_text in section_blocks[index + 1:]:
                if block_kind == "heading":
                    break
                if block_kind == "paragraph" and not is_serve_cue(block_text):
                    return strip_markdown(block_text)
            break
    return FOAM_DESCRIPTION_FALLBACKS.get(build)


def parse_foam_section(lines: list[str]) -> list[Item]:
    items: list[Item] = []
    for build in parse_foam_matrix(lines):
        name_en = "Base Foam" if build == "Base" else f"{build} Cold Foam"
        items.append(
            Item(
                name_en=name_en,
                name_vi=FOAM_VIETNAMESE_NAMES.get(build),
                description=foam_description(build, lines),
                temperatures=["iced"],
            )
        )
    return items


def parse_menu(text: str) -> Menu:
    top_sections = split_top_sections(text)
    mapped: dict[str, Section] = {}
    for source_title, lines in top_sections.items():
        if source_title in SECTION_MAP:
            section_id, title_vi, title_en = SECTION_MAP[source_title]
            mapped[section_id] = Section(
                id=section_id, title_vi=title_vi, title_en=title_en,
                items=parse_drink_section(lines),
            )
        elif source_title not in KNOWN_NON_DRINK_SECTIONS:
            raise UnmappedSectionError(
                f"recipes section {source_title!r} is not mapped to a menu section; "
                f"add it to SECTION_MAP or KNOWN_NON_DRINK_SECTIONS in site/generate.py"
            )
    kem_id, kem_vi, kem_en = KEM_SECTION
    foam_lines = top_sections.get("Cold Foams", [])
    if "Cold Foams" in top_sections:
        mapped[kem_id] = Section(
            id=kem_id, title_vi=kem_vi, title_en=kem_en,
            items=parse_foam_section(foam_lines),
            show_pills=False,
        )
    order = [spec[0] for spec in SECTION_MAP.values()] + [kem_id]
    return Menu(sections=[mapped[section_id] for section_id in order if section_id in mapped])


def render_pills(temperatures: list[str]) -> str:
    pills = []
    if "hot" in temperatures:
        pills.append('<span class="tag nong">nóng</span>')
    if "iced" in temperatures:
        pills.append('<span class="tag da">đá</span>')
    return f'<span class="tags">{"".join(pills)}</span>'


def render_item(item: Item, show_pills: bool) -> str:
    lead = item.name_vi or item.name_en
    line = f'<span class="item-name">{html.escape(lead)}</span>'
    if show_pills:
        line += render_pills(item.temperatures)
    parts = [f'<div class="item">', f'  <div class="item-line">{line}</div>']
    if item.name_vi and item.name_en and item.name_en.lower() != item.name_vi.lower():
        parts.append(f'  <p class="item-vi">{html.escape(item.name_en)}</p>')
    if item.description:
        parts.append(f'  <p class="item-desc">{html.escape(item.description)}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def render_section(section: Section) -> str:
    items = "\n".join(render_item(item, section.show_pills) for item in section.items)
    return "\n".join(
        [
            "  <section>",
            '    <div class="section-head">',
            f"      <h2>{html.escape(section.title_vi.upper())}</h2>",
            f'      <span class="section-en">{html.escape(section.title_en)}</span>',
            "    </div>",
            '    <div class="items">',
            items,
            "    </div>",
            "  </section>",
        ]
    )


def render_menu_page(menu: Menu) -> str:
    template = (TEMPLATES_DIR / "menu.html").read_text()
    sections_html = "\n".join(render_section(section) for section in menu.sections)
    return template.replace("<!--SECTIONS-->", sections_html)


def build_site(recipes_path: Path, out_dir: Path) -> None:
    menu = parse_menu(recipes_path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "menu.html").write_text(render_menu_page(menu))
    shutil.copyfile(TEMPLATES_DIR / "index.html", out_dir / "index.html")
    for page in ("kitchen.html", "bar.html"):
        shutil.copyfile(MENU_SOURCE_DIR / page, out_dir / page)
    assets_out = out_dir / "assets"
    assets_out.mkdir(exist_ok=True)
    for asset in MENU_SOURCE_DIR.joinpath("assets").iterdir():
        if asset.is_file() and asset.name != ".gitkeep":
            shutil.copyfile(asset, assets_out / asset.name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recipes", type=Path, default=DEFAULT_RECIPES, help="path to cafe.md"
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="output directory"
    )
    args = parser.parse_args()
    build_site(args.recipes, args.out)
    counts = {s.id: len(s.items) for s in parse_menu(args.recipes.read_text()).sections}
    total = sum(counts.values())
    print(f"site generated in {args.out}: {total} items " + str(counts))


if __name__ == "__main__":
    main()
