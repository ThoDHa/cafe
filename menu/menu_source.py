"""Shared recipes-parsing core for both menu generators.

site/generate.py (the public menus site) and server/app/menu_generator.py
(the ordering menu) both derive their drinks from the recipes repository's
cafe.md. This module holds everything that parsing has in common: drink
extraction from the markdown, the section mapping onto menu sections,
temperature derivation from the prose, and Vietnamese-name handling.
It stays stdlib-only so the site build can run it under
`uv run --with weasyprint` and nothing else.

Only menu-shape knowledge that recipes cannot express lives here as
configuration: section titles, Vietnamese names recipes omit, and the one
temperature (Hot Tea) the prose cannot prove. The Kem section's own note
paragraph is parsed here beside its items; the ordering generator adds
ordering-only enrichment from its own checked-in config; the site adds
the drinks sections' notes, print fitting, and rendering on top of the
parsed menu.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

SECTION_MAP = {
    "Coffee": ("ca-phe", "Cà Phê", "Coffee"),
    "Tea": ("tra", "Trà", "Tea"),
    "Matcha": ("mat-cha", "Mát-cha", "Matcha"),
    "Refreshers": ("giai-khat", "Giải Khát", "Refreshers"),
}
KEM_SECTION = ("kem", "Kem", "Cold Foams")
# The foam section's source heading in recipes cafe.md: the owner renamed
# it "Cold Foams" → "Foams", so both spellings register and the parse
# fails loudly when a file carries both at once. The Kem display title
# stays KEM_SECTION's.
KEM_SOURCE_TITLES = ("Foams", "Cold Foams")
CATEGORY_ID_PREFIXES = {"kem": "kem"}

KNOWN_NON_DRINK_SECTIONS = {
    "Table of Contents",
    "Drink Matrix",
    "Pantry Staples",
    "Bases",
    "Foams",
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

KNOWN_NON_COCKTAIL_SECTIONS = {
    "Construction Rules",
}

KITCHEN_SECTION_MAP = {
    "Appetizers": ("khai-vi", "Khai Vị", "Starters"),
    "Main Dishes": ("mon-chinh", "Món Chính", "Mains"),
    "Side Dishes": ("mon-phu", "Món Phụ", "Sides"),
    "Sauces & Toppings": ("sot", "Sốt & Nước Chấm", "Sauces"),
    "Desserts": ("trang-mieng", "Tráng Miệng", "Desserts"),
}

KNOWN_NON_KITCHEN_GROUPS = {
    "Quick References",
    "Drinks",
    "Cocktails",
}

KITCHEN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

KITCHEN_BULLET_RE = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\)\s*(.*)$")

KITCHEN_BULLET_DESC_RE = re.compile(r"[–—-]\s+(.+)")

KITCHEN_OVERRIDE_KEYS = frozenset({"name", "nameVi", "description"})

KITCHEN_MERGE_OVERRIDE_KEYS = frozenset({"sources", "nameVi", "description"})

KITCHEN_SECTION_OVERRIDE_KEYS = frozenset({"note"})

KITCHEN_CONFIG_KEYS = frozenset({"items", "merges", "sections", "order"})

# Pantry section leads: curated short Vietnamese display leads keyed by the
# recipes cafe_pantry.md `##` titles. An unmapped `##` section falls back to
# its English title as the lead and ships no label: a new pantry group
# appears on the page with no registration and no curated title, while a
# group whose title cannot yield an ASCII slug fails the build loudly via
# slugify.
PANTRY_SECTION_TITLES = {
    "Fresh Dairy and Produce": "Sữa & Trái Cây",
    "Shelf-Stable Pantry": "Đồ Khô",
    "Make-Ahead Staples": "Làm Sẵn",
}

# A trailing "(...)" on a pantry bullet's name is the buy spec ("Heavy
# whipping cream (pint carton)"); it moves to the item's subtitle slot.
PANTRY_ANNOTATION_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)$")

SERVE_CUE_PARAGRAPHS = {
    "served hot or iced",
    "hot or iced",
    "served iced",
    "served hot",
}

HOT = "hot"
ICED = "iced"
TEMPERATURE_ORDER = (HOT, ICED)

HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
ICE_WORD_RE = re.compile(r"\bice\b", re.IGNORECASE)

ORDERING_OVERRIDE_KEYS = frozenset(
    {"id", "name", "nameVi", "description", "imagePath", "temperatures", "modifierGroupIds"}
)
COCKTAIL_OVERRIDE_KEYS = frozenset({"name", "nameVi", "description"})
ORDERING_DEFAULT_GROUP_KEYS = frozenset({"base", "icedOnly", "byCategory"})


class UnmappedSectionError(Exception):
    """Raised when cafe.md contains a drink-like section the menu cannot place."""


class OrderingConfigError(Exception):
    """Raised when the ordering enrichment config contradicts the recipes."""


class SiteOverridesError(Exception):
    """Raised when the site overrides config contradicts the recipes."""


class KitchenIndexError(Exception):
    """Raised when the recipes README index cannot place a kitchen dish."""


@dataclass
class Item:
    name_en: str
    name_vi: str | None
    description: str | None
    temperatures: list[str]


@dataclass
class Section:
    """One drinks menu section.

    note carries the section's own first-paragraph blurb from the
    recipes; today only the Kem section's is parsed here, while the
    drinks sections' notes stay a site-side concern built on the same
    recipes paragraphs.
    """

    id: str
    title_vi: str
    title_en: str
    items: list[Item] = field(default_factory=list)
    note: str | None = None


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


def first_paragraph_note(lines: list[str]) -> str | None:
    """Read a section's note: the first paragraph under its heading,
    markdown-stripped the way item prose is handled.

    Only the first paragraph counts (the drinks sections' convention),
    so a section that opens with a table or a deeper heading, or whose
    first paragraph strips to nothing, yields None.
    """
    for kind, text in blocks(lines):
        if kind == "paragraph":
            return strip_markdown(text) or None
        return None
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


GITHUB_ANCHOR_NOISE_RE = re.compile(r"[^\w\s-]", re.UNICODE)


def heading_anchor(text: str) -> str:
    """GitHub-style anchor a markdown link uses for a heading: lowercased,
    punctuation dropped, whitespace runs collapsed to single hyphens."""
    slug = GITHUB_ANCHOR_NOISE_RE.sub("", text.strip().lower())
    return re.sub(r"\s+", "-", slug)


def parse_foam_matrix(lines: list[str]) -> list[tuple[str, str]]:
    """Read the Foam Matrix rows as (build, anchor) pairs.

    Each row links the build's own section heading by anchor, which is how
    the parse later finds that build's prose; a row whose first cell
    carries no link contributes no build.
    """
    builds: list[tuple[str, str]] = []
    seen: set[str] = set()
    in_matrix = False
    for line in lines:
        if line.startswith("### "):
            in_matrix = line.strip() == "### Foam Matrix"
            continue
        if in_matrix and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if not cells or set(cells[0]) <= {"-", " ", ":"}:
                continue
            link = re.match(r"\[([^\]]+)\]\(#([^)]+)\)", cells[0])
            if link:
                build = link.group(1).strip()
                if build.lower() not in {"build"} and build not in seen:
                    seen.add(build)
                    builds.append((build, link.group(2).strip()))
    return builds


def foam_anchor_map(section_lines: list[str]) -> dict[str, tuple[str, int]]:
    """Map each heading's GitHub anchor to its (text, occurrence): the
    anchor follows GitHub's document-order slug deduplication, the first
    occurrence of a slug keeping the bare anchor and later duplicates
    getting -1, -2, ... suffixes, while the occurrence counts prior
    headings of the same exact text, matching how foam_build_prose
    locates a heading, so a matrix row pointing at a suffixed anchor
    resolves its own heading instead of falling back to the legacy
    pattern."""
    slug_counts: dict[str, int] = {}
    text_counts: dict[str, int] = {}
    anchors: dict[str, tuple[str, int]] = {}
    for line in section_lines:
        match = HEADING_RE.match(line)
        if not match:
            continue
        text = match.group(2).strip()
        slug = heading_anchor(text)
        # A literal "Foo 1" heading beside a duplicated "Foo" slugs to
        # GitHub's suffixed "foo-1" and overwrites the duplicate's entry
        # in this map; GitHub's own anchor algorithm is ambiguous the
        # same way, so the collision is accepted as parity. Revisit if
        # GitHub's algorithm ever changes or the recipes file carries
        # such a heading pair.
        slug_prior = slug_counts.get(slug, 0)
        slug_counts[slug] = slug_prior + 1
        text_prior = text_counts.get(text, 0)
        text_counts[text] = text_prior + 1
        anchors[slug if slug_prior == 0 else f"{slug}-{slug_prior}"] = (
            text,
            text_prior,
        )
    return anchors


def foam_build_heading(
    build: str, anchor: str, anchors: dict[str, tuple[str, int]]
) -> tuple[str, int]:
    """Resolve a foam build to its own section heading.

    The matrix row anchors the build's real heading, looked up in the
    section's anchor map; otherwise the legacy "Base Foam" / "{build}
    Cold Foam" heading pattern applies, first occurrence.
    """
    resolved = anchors.get(anchor)
    if resolved is not None:
        return resolved
    return ("Base Foam" if build == "Base" else f"{build} Cold Foam"), 0


def foam_build_prose(
    section_lines: list[str], heading: str, occurrence: int = 0
) -> tuple[str | None, str | None]:
    """Read a foam build's (Vietnamese name, description) from under its
    own section heading.

    The Vietnamese name follows the drinks convention: a heading one level
    deeper than the build's own, before any structural heading ends the
    build; occurrence selects which same-text heading owns the scan when
    the section repeats a heading (GitHub suffixes the duplicates). The
    description is the first paragraph under the build's heading, joined
    from its wrapped source lines the way the drinks path reads a blocks()
    paragraph, and only the first paragraph counts. The scan stops at the
    first heading other than that deeper name heading, or at any heading
    at the build heading's level or shallower, so a build with no deeper
    name never inherits the next build's heading or prose.
    """
    name_vi: str | None = None
    description: str | None = None
    own_level: int | None = None
    seen_heading = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal description, paragraph
        lines, paragraph = paragraph, []
        if description is not None or not lines:
            return
        joined = strip_markdown(" ".join(lines))
        if joined and not is_serve_cue(joined):
            description = joined

    for line in section_lines:
        match = HEADING_RE.match(line)
        if match:
            flush_paragraph()
            level, text = len(match.group(1)), match.group(2).strip()
            if own_level is None:
                if text == heading:
                    if seen_heading == occurrence:
                        own_level = level
                    seen_heading += 1
                continue
            if level <= own_level:
                break
            if name_vi is None and text not in STRUCTURAL_HEADINGS:
                name_vi = text
                continue
            break
        if own_level is None:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(("- ", "|")):
            flush_paragraph()
        else:
            paragraph.append(stripped)
        if description is not None and name_vi is not None:
            break
    flush_paragraph()
    return name_vi, description


def parse_foam_section(lines: list[str]) -> list[Item]:
    items: list[Item] = []
    anchors = foam_anchor_map(lines)
    for build, anchor in parse_foam_matrix(lines):
        name_en = "Base Foam" if build == "Base" else f"{build} Cold Foam"
        heading, occurrence = foam_build_heading(build, anchor, anchors)
        name_vi, description = foam_build_prose(lines, heading, occurrence)
        items.append(
            Item(
                name_en=name_en,
                name_vi=name_vi or FOAM_VIETNAMESE_NAMES.get(build),
                description=description or FOAM_DESCRIPTION_FALLBACKS.get(build),
                temperatures=["iced"],
            )
        )
    return items


def parse_cocktails(text: str) -> list[Item]:
    """Extract the cocktail template families from recipes cocktails.md.

    Every top-level `##` heading is a family: the name is the heading and
    the first paragraph under it is the menu description, with the `###`
    instructions never contributing. The intro paragraph before the first
    `##` heading belongs to no family, and KNOWN_NON_COCKTAIL_SECTIONS
    registers the structural sections. A family the recipes add later is
    picked up with no registration.
    """
    families: list[Item] = []
    for title, lines in split_top_sections(text).items():
        if title in KNOWN_NON_COCKTAIL_SECTIONS:
            continue
        families.append(
            Item(
                name_en=title,
                name_vi=None,
                description=first_paragraph_after_name(blocks(lines)),
                temperatures=[],
            )
        )
    return families


def _bar_overrides(config: dict) -> dict:
    bar_config = config.get("bar")
    if not isinstance(bar_config, dict):
        raise SiteOverridesError(
            "the overrides config needs a 'bar' object with an 'items' mapping"
        )
    overrides = bar_config.get("items", {})
    if not isinstance(overrides, dict) or not all(
        isinstance(entry, dict) for entry in overrides.values()
    ):
        raise SiteOverridesError(
            "the overrides config 'bar.items' must be an object mapping "
            "cocktail family names to override objects"
        )
    for family_name, entry in overrides.items():
        unknown = set(entry) - COCKTAIL_OVERRIDE_KEYS
        if unknown:
            raise SiteOverridesError(
                f"the bar overrides entry for {family_name!r} has unknown keys "
                f"{sorted(unknown)}: expected only {sorted(COCKTAIL_OVERRIDE_KEYS)}"
            )
    return overrides


def build_bar_items(text: str, config: dict) -> list[Item]:
    """Build the bar menu items from the parsed cocktails plus the site
    overrides config.

    The config's 'bar.items' object keys families by their recipes name
    and may carry name, nameVi, and description; anything omitted falls
    back to what the recipes derivation yields, so a family added to
    recipes appears with its prose description and no config entry.
    Overrides naming families the recipes no longer define fail loudly.
    """
    overrides = _bar_overrides(config)
    families = parse_cocktails(text)
    defined = {family.name_en for family in families}
    unmatched = sorted(set(overrides) - defined)
    if unmatched:
        raise SiteOverridesError(
            "the bar overrides config names families the recipes do not "
            f"define: {unmatched}"
        )
    items: list[Item] = []
    for family in families:
        entry = overrides.get(family.name_en, {})
        items.append(
            Item(
                name_en=entry.get("name") or family.name_en,
                name_vi=entry.get("nameVi"),
                description=entry.get("description") or family.description,
                temperatures=[],
            )
        )
    return items


def _pantry_prose(lines: list[str]) -> str | None:
    """Join accumulated paragraph lines into one cleaned string, or None."""
    if not lines:
        return None
    return strip_markdown(" ".join(lines)) or None


def parse_pantry_item(bullet_text: str) -> Item:
    """Map one pantry bullet's text (after "- ") onto an Item.

    The text splits on the first ": ": the part before is the name and the
    part after, when the separator is found, is the description. A trailing
    parenthetical (PANTRY_ANNOTATION_RE) moves from the name into name_vi,
    the pages' subtitle slot, the same reuse the kitchen makes for English
    subtitles: "Heavy whipping cream (pint carton)" carries name_en "Heavy
    whipping cream" and name_vi "pint carton"; an empty annotation yields
    None. Both parts strip markdown, so the make-ahead bullets named by a
    link keep their display text and link-laden description prose lands
    clean. Temperatures are meaningless on a buying list and stay empty.
    """
    name_part, separator, description_part = bullet_text.partition(": ")
    name = strip_markdown(name_part)
    name_vi: str | None = None
    annotation = PANTRY_ANNOTATION_RE.match(name)
    if annotation and annotation.group(2).strip():
        name, name_vi = annotation.group(1), annotation.group(2).strip()
    return Item(
        name_en=name,
        name_vi=name_vi,
        description=strip_markdown(description_part) if separator else None,
        temperatures=[],
    )


@dataclass
class PantrySection:
    """One `##` buying group of the recipes cafe_pantry.md."""

    id: str
    title_lead: str
    title_label: str | None
    note: str | None = None
    items: list[Item] = field(default_factory=list)


@dataclass
class PantryMenu:
    intro: str | None
    outro: str | None
    sections: list[PantrySection] = field(default_factory=list)


def parse_pantry(text: str) -> PantryMenu:
    """Parse the recipes cafe_pantry.md shopping list into the pantry page.

    Every `##` heading becomes a section in file order and every column-0
    `- ` bullet under it becomes an Item. The section id is the slug of the
    source (English) title; a title in PANTRY_SECTION_TITLES renders its
    curated Vietnamese lead with the English title as the label, and any
    other `##` falls back to the English title as the lead with no label,
    so a pantry group the recipes add later is picked up with no
    registration. Paragraphs under a heading before its first bullet become
    the section's note; paragraphs before the first `##` (skipping the `# `
    document title) become the page intro, with a column-0 `- ` bullet in
    that zone rejected loudly instead, since bullets must live inside a
    `##` section; the final section's trailing paragraphs become the page
    outro, and any other section's trailing paragraphs fold into that
    section's note. Indented bullets are never items or copy, and table
    lines are skipped inside sections, though intro-zone table lines fold
    into the intro prose; deeper headings (###+) are structural and
    dropped while their content lines stay as paragraphs.
    split_top_sections is unsuitable here because it loses line
    indentation and merges nested bullets, so the lines are parsed
    directly instead.
    """
    intro_lines: list[str] = []
    sections: list[PantrySection] = []
    note_lines_by_section: list[list[str]] = []
    trailing_lines_by_section: list[list[str]] = []
    for line in text.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            if len(heading.group(1)) == 2:
                title = heading.group(2).strip()
                sections.append(
                    PantrySection(
                        id=slugify(title),
                        title_lead=PANTRY_SECTION_TITLES.get(title, title),
                        title_label=(
                            title if title in PANTRY_SECTION_TITLES else None
                        ),
                    )
                )
                note_lines_by_section.append([])
                trailing_lines_by_section.append([])
            continue
        if line.startswith("# "):
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if not sections:
            if line.startswith("- "):
                raise ValueError(
                    f"pantry bullet {stripped!r} appears before the first "
                    "`##` section; pantry bullets must live inside a `##` "
                    "section of cafe_pantry.md"
                )
            if stripped.startswith("- "):
                continue
            intro_lines.append(stripped)
            continue
        if line.startswith("- "):
            sections[-1].items.append(parse_pantry_item(line[2:]))
            continue
        if stripped.startswith("- ") or stripped.startswith("|"):
            continue
        if sections[-1].items:
            trailing_lines_by_section[-1].append(stripped)
        else:
            note_lines_by_section[-1].append(stripped)
    outro: str | None = None
    for index, section in enumerate(sections):
        if index == len(sections) - 1:
            outro = _pantry_prose(trailing_lines_by_section[index])
        else:
            note_lines_by_section[index].extend(trailing_lines_by_section[index])
        section.note = _pantry_prose(note_lines_by_section[index])
    return PantryMenu(
        intro=_pantry_prose(intro_lines),
        outro=outro,
        sections=sections,
    )


@dataclass
class KitchenEntry:
    """One top-level README bullet: a dish the kitchen menu can place."""

    name: str
    file: str
    anchor: str | None
    description: str | None


@dataclass
class KitchenIndexSection:
    id: str
    title_vi: str
    title_en: str
    entries: list[KitchenEntry]


@dataclass
class KitchenMenuSection:
    id: str
    title_vi: str
    title_en: str
    note: str | None
    items: list[Item] = field(default_factory=list)


@dataclass
class KitchenMenu:
    sections: list[KitchenMenuSection]


def github_slug(text: str) -> str:
    """Slug a heading the way recipes/build.py anchors them: unicode word
    characters survive, so README anchors like #nước-chấm-nước-mắm-pha
    resolve. The ASCII-folding slugify above is for identifiers, not
    anchors."""
    slug = re.sub(r"[^\w\s-]", "", text.strip().lower()).replace(" ", "-")
    return slug or "section"


def github_heading_ids(text: str) -> set[str]:
    """Every heading id recipes/build.py would assign: github_slug per
    heading, duplicates suffixed -1, -2, ... in document order."""
    counts: dict[str, int] = {}
    ids: set[str] = set()
    for line in text.splitlines():
        match = KITCHEN_HEADING_RE.match(line)
        if not match:
            continue
        slug = github_slug(match.group(2))
        seen = counts.get(slug, 0)
        counts[slug] = seen + 1
        ids.add(slug if seen == 0 else f"{slug}-{seen}")
    return ids


def dish_intro(text: str) -> str | None:
    """First paragraph under the H1 of a one-dish recipe file, markdown
    stripped; None when the file opens with a heading instead."""
    past_h1 = False
    for line in text.splitlines():
        match = KITCHEN_HEADING_RE.match(line)
        if match:
            if not past_h1 and len(match.group(1)) == 1:
                past_h1 = True
                continue
            break
        if not past_h1:
            continue
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue
        return strip_markdown(stripped) or None
    return None


def parse_kitchen_index(text: str) -> list[KitchenIndexSection]:
    """Walk the recipes README's Available Recipes index.

    A `###` group heading maps through KITCHEN_SECTION_MAP; groups in
    KNOWN_NON_KITCHEN_GROUPS (the drinks and cocktail indexes) are
    skipped, and anything else fails loudly. Within a mapped group every
    top-level bullet is one KitchenEntry keyed by its link text, with the
    one-liner after the link as its description; nested bullets are
    components, not dishes.
    """
    sections: list[KitchenIndexSection] = []
    in_available = False
    current: KitchenIndexSection | None = None
    for line in text.splitlines():
        heading = KITCHEN_HEADING_RE.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            if level == 2:
                in_available = title == "Available Recipes"
                current = None
            elif level == 3 and in_available:
                spec = KITCHEN_SECTION_MAP.get(title)
                if spec is None:
                    if title not in KNOWN_NON_KITCHEN_GROUPS:
                        raise KitchenIndexError(
                            f"recipes README group {title!r} is not mapped to a "
                            "kitchen section; add it to KITCHEN_SECTION_MAP or "
                            "KNOWN_NON_KITCHEN_GROUPS in menu/menu_source.py"
                        )
                    current = None
                else:
                    section_id, title_vi, title_en = spec
                    current = KitchenIndexSection(section_id, title_vi, title_en, [])
                    sections.append(current)
            else:
                # any other heading (levels 1 and 4-6, or a `###` outside
                # Available Recipes) ends the current group so bullets can
                # not silently attach to a stale section
                current = None
            continue
        if current is None:
            continue
        bullet = KITCHEN_BULLET_RE.match(line)
        if not bullet:
            continue
        name, target = bullet.group(1), bullet.group(2)
        # The remainder may hold the one-liner behind a -, –, or — separator,
        # or an annotation like Mushrooms' "(Oven Roasted, Pan Roasted, ...)",
        # which is not a description.
        desc_match = KITCHEN_BULLET_DESC_RE.match(bullet.group(3) or "")
        file, _, anchor = target.partition("#")
        current.entries.append(
            KitchenEntry(
                name=name,
                file=file,
                anchor=anchor or None,
                description=desc_match.group(1) if desc_match else None,
            )
        )
    return sections


def _kitchen_overrides(config: dict) -> dict:
    kitchen = config.get("kitchen")
    if not isinstance(kitchen, dict):
        raise SiteOverridesError("the overrides config needs a 'kitchen' object")
    unknown = set(kitchen) - KITCHEN_CONFIG_KEYS
    if unknown:
        raise SiteOverridesError(
            f"the overrides config 'kitchen' has unknown keys {sorted(unknown)}: "
            f"expected only {sorted(KITCHEN_CONFIG_KEYS)}"
        )
    items = kitchen.get("items", {})
    if not isinstance(items, dict) or not all(
        isinstance(entry, dict) for entry in items.values()
    ):
        raise SiteOverridesError(
            "the overrides config 'kitchen.items' must be an object mapping "
            "README dish names to override objects"
        )
    for name, entry in items.items():
        unknown = set(entry) - KITCHEN_OVERRIDE_KEYS
        if unknown:
            raise SiteOverridesError(
                f"the kitchen overrides entry for {name!r} has unknown keys "
                f"{sorted(unknown)}: expected only {sorted(KITCHEN_OVERRIDE_KEYS)}"
            )
    merges = kitchen.get("merges", {})
    if not isinstance(merges, dict) or not all(
        isinstance(entry, dict) for entry in merges.values()
    ):
        raise SiteOverridesError(
            "the overrides config 'kitchen.merges' must be an object mapping "
            "menu item names to merge objects"
        )
    for name, merge in merges.items():
        unknown = set(merge) - KITCHEN_MERGE_OVERRIDE_KEYS
        if unknown:
            raise SiteOverridesError(
                f"the kitchen merge for {name!r} has unknown keys {sorted(unknown)}: "
                f"expected only {sorted(KITCHEN_MERGE_OVERRIDE_KEYS)}"
            )
        sources = merge.get("sources")
        if (
            not isinstance(sources, list)
            or not sources
            or not all(isinstance(source, str) for source in sources)
        ):
            raise SiteOverridesError(
                f"the kitchen merge for {name!r} needs a non-empty 'sources' "
                "list of README dish names"
            )
    sections = kitchen.get("sections", {})
    if not isinstance(sections, dict) or not all(
        isinstance(entry, dict) for entry in sections.values()
    ):
        raise SiteOverridesError(
            "the overrides config 'kitchen.sections' must be an object mapping "
            "section ids to overrides"
        )
    for section_id, entry in sections.items():
        unknown = set(entry) - KITCHEN_SECTION_OVERRIDE_KEYS
        if unknown:
            raise SiteOverridesError(
                f"the kitchen section override for {section_id!r} has unknown "
                f"keys {sorted(unknown)}: expected only "
                f"{sorted(KITCHEN_SECTION_OVERRIDE_KEYS)}"
            )
    order = kitchen.get("order", {})
    if not isinstance(order, dict) or not all(
        isinstance(names, list) and all(isinstance(name, str) for name in names)
        for names in order.values()
    ):
        raise SiteOverridesError(
            "the overrides config 'kitchen.order' must be an object mapping "
            "section ids to item-name lists"
        )
    return {
        "items": items,
        "merges": merges,
        "sections": sections,
        "order": order,
    }


def _kitchen_entry_texts(
    entries: dict[str, tuple["KitchenIndexSection", "KitchenEntry"]],
    file_loader: Callable[[str], str],
) -> dict[str, str]:
    """Load and cache every referenced recipe file, failing loudly on the
    first missing one, and verify every #anchor against build.py's
    heading ids."""
    texts: dict[str, str] = {}
    for name, (_, entry) in entries.items():
        if entry.file not in texts:
            try:
                texts[entry.file] = file_loader(entry.file)
            except Exception as exc:
                raise KitchenIndexError(
                    f"recipe file {entry.file!r} referenced by {name!r} is "
                    f"missing or unreadable: {exc}"
                ) from exc
        if entry.anchor is not None and entry.anchor not in github_heading_ids(
            texts[entry.file]
        ):
            raise KitchenIndexError(
                f"anchor {entry.anchor!r} from {entry.name!r} not found in "
                f"{entry.file!r}"
            )
    return texts


def build_kitchen_menu(
    readme_text: str, file_loader: Callable[[str], str], config: dict
) -> KitchenMenu:
    """Build the kitchen menu from the recipes README index, the dish
    files behind it, and the site overrides config.

    Every top-level README bullet in a mapped group becomes an item: the
    display name defaults to the link text, and the description chain is
    the override, then the README one-liner, then the dish file's intro
    paragraph, then none. A merge (e.g. Asparagus from its oven and pan
    variants) replaces its source bullets with one item placed at the
    first source. Every referenced file and #anchor is verified against
    the recipes tree using build.py's GitHub-slug anchors. Overrides
    naming dishes or sections the README does not define, merges whose
    sources are missing or span sections, and order lists that are not a
    permutation of their section's items all fail loudly.

    Kitchen items reuse Item with repurposed fields: name_en carries the
    display (lead) name as rendered, name_vi the optional subtitle (the
    English name under a Vietnamese lead, or a gloss like Ra-gu), and
    temperatures stays empty.
    """
    kitchen = _kitchen_overrides(config)
    index = parse_kitchen_index(readme_text)

    entries: dict[str, tuple[KitchenIndexSection, KitchenEntry]] = {}
    for section in index:
        for entry in section.entries:
            if entry.name in entries:
                raise KitchenIndexError(
                    f"recipes README lists {entry.name!r} twice; dish names "
                    "must be unique"
                )
            entries[entry.name] = (section, entry)

    stale = sorted(set(kitchen["items"]) - set(entries))
    if stale:
        raise SiteOverridesError(
            "the kitchen overrides config names dishes the README does not "
            f"define: {stale}"
        )
    for menu_name, merge in kitchen["merges"].items():
        if menu_name in entries:
            raise SiteOverridesError(
                f"the kitchen merge {menu_name!r} collides with a README dish "
                "of the same name"
            )
        unknown_sources = [
            source for source in merge["sources"] if source not in entries
        ]
        if unknown_sources:
            raise SiteOverridesError(
                f"the kitchen merge {menu_name!r} sources dishes the README "
                f"does not define: {unknown_sources}"
            )
        spanned = sorted({entries[source][0].id for source in merge["sources"]})
        if len(spanned) > 1:
            raise SiteOverridesError(
                f"the kitchen merge {menu_name!r} spans sections {spanned}"
            )
    unknown_notes = sorted(set(kitchen["sections"]) - {s.id for s in index})
    if unknown_notes:
        raise SiteOverridesError(
            "the kitchen overrides config keys sections the README does not "
            f"define: {unknown_notes}"
        )
    unknown_order = sorted(set(kitchen["order"]) - {s.id for s in index})
    if unknown_order:
        raise SiteOverridesError(
            "the kitchen overrides config orders sections the README does "
            f"not define: {unknown_order}"
        )
    consumed: dict[str, str] = {}
    for menu_name, merge in kitchen["merges"].items():
        for source in merge["sources"]:
            if source in consumed:
                raise SiteOverridesError(
                    f"the kitchen merges {consumed[source]!r} and {menu_name!r} "
                    f"both consume {source!r}"
                )
            consumed[source] = menu_name

    texts = _kitchen_entry_texts(entries, file_loader)

    sections: list[KitchenMenuSection] = []
    for index_section in index:
        items: list[Item] = []
        merge_seen: set[str] = set()
        for entry in index_section.entries:
            menu_name = consumed.get(entry.name)
            if menu_name is not None:
                if menu_name in merge_seen:
                    continue
                merge_seen.add(menu_name)
                merge = kitchen["merges"][menu_name]
                items.append(
                    Item(
                        name_en=menu_name,
                        name_vi=merge.get("nameVi"),
                        description=merge.get("description"),
                        temperatures=[],
                    )
                )
                continue
            override = kitchen["items"].get(entry.name, {})
            description = override.get("description") or entry.description
            if description is None and entry.anchor is None:
                description = dish_intro(texts[entry.file])
            items.append(
                Item(
                    name_en=override.get("name") or entry.name,
                    name_vi=override.get("nameVi"),
                    description=description,
                    temperatures=[],
                )
            )
        duplicates = sorted(
            {
                name
                for name in {item.name_en for item in items}
                if [item.name_en for item in items].count(name) > 1
            }
        )
        if duplicates:
            raise SiteOverridesError(
                f"the kitchen section {index_section.id!r} resolves duplicate "
                f"item names {duplicates}"
            )
        note = kitchen["sections"].get(index_section.id, {}).get("note")
        sections.append(
            KitchenMenuSection(
                id=index_section.id,
                title_vi=index_section.title_vi,
                title_en=index_section.title_en,
                note=note,
                items=items,
            )
        )

    for section_id, order in kitchen["order"].items():
        section = next(s for s in sections if s.id == section_id)
        final_names = [item.name_en for item in section.items]
        if sorted(order) != sorted(final_names):
            raise SiteOverridesError(
                f"the kitchen order for {section_id!r} must be a permutation "
                f"of the section's items {final_names}; got {order}"
            )
        by_name = {item.name_en: item for item in section.items}
        section.items[:] = [by_name[name] for name in order]

    return KitchenMenu(sections=sections)


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
                f"add it to SECTION_MAP or KNOWN_NON_DRINK_SECTIONS in menu/menu_source.py"
            )
    kem_id, kem_vi, kem_en = KEM_SECTION
    kem_titles_present = [
        title for title in KEM_SOURCE_TITLES if title in top_sections
    ]
    if len(kem_titles_present) > 1:
        raise UnmappedSectionError(
            f"recipes carries foam sections under both "
            f"{kem_titles_present[0]!r} and {kem_titles_present[1]!r}; "
            "exactly one foam section is expected"
        )
    if kem_titles_present:
        kem_lines = top_sections[kem_titles_present[0]]
        mapped[kem_id] = Section(
            id=kem_id, title_vi=kem_vi, title_en=kem_en,
            items=parse_foam_section(kem_lines),
            note=first_paragraph_note(kem_lines),
        )
    order = [spec[0] for spec in SECTION_MAP.values()] + [kem_id]
    return Menu(sections=[mapped[section_id] for section_id in order if section_id in mapped])


def slugify(text: str) -> str:
    """ASCII slug from a display name: diacritics folded, runs of
    non-alphanumerics collapsed to single dashes, matching the schema's
    identifier pattern."""
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(char for char in folded if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    if not slug:
        raise OrderingConfigError(f"cannot derive an identifier slug from {text!r}")
    return slug


def _ordering_defaults(config: dict) -> dict[str, list[str]]:
    defaults = config.get("defaults", {})
    if not isinstance(defaults, dict):
        raise OrderingConfigError("the overrides config 'defaults' must be an object")
    modifier_defaults = defaults.get("modifierGroups", {})
    unknown = set(modifier_defaults) - ORDERING_DEFAULT_GROUP_KEYS
    if unknown:
        raise OrderingConfigError(
            "the overrides config 'defaults.modifierGroups' has unknown keys "
            f"{sorted(unknown)}: expected only {sorted(ORDERING_DEFAULT_GROUP_KEYS)}"
        )
    return {
        "base": list(modifier_defaults.get("base", ["sweetness"])),
        "icedOnly": list(modifier_defaults.get("icedOnly", ["cold-foam"])),
        "byCategory": {
            category_id: list(group_ids)
            for category_id, group_ids in modifier_defaults.get("byCategory", {}).items()
        },
    }


def _ordering_overrides(config: dict) -> dict[str, dict]:
    overrides = config.get("items", {})
    if not isinstance(overrides, dict) or not all(
        isinstance(entry, dict) for entry in overrides.values()
    ):
        raise OrderingConfigError(
            "the overrides config 'items' must be an object mapping recipes "
            "drink names to override objects"
        )
    for drink_name, entry in overrides.items():
        unknown = set(entry) - ORDERING_OVERRIDE_KEYS
        if unknown:
            raise OrderingConfigError(
                f"the overrides entry for {drink_name!r} has unknown keys "
                f"{sorted(unknown)}: expected only {sorted(ORDERING_OVERRIDE_KEYS)}"
            )
    return overrides


def _canonical_temperatures(source: str, values: list[str]) -> list[str]:
    unknown = [value for value in values if value not in TEMPERATURE_ORDER]
    if unknown or not values:
        raise OrderingConfigError(
            f"{source} carries temperatures {values}: expected only "
            f"{HOT!r} or {ICED!r}, at least one"
        )
    return [temperature for temperature in TEMPERATURE_ORDER if temperature in values]


def _default_item_id(section: Section, drink: Item) -> str:
    """Derive the id for a drink whose overrides config carries none.

    A kem build must keep the kem-* convention its consumers and asset
    paths expect even when the recipes carry no Vietnamese name for it,
    so categories listed in CATEGORY_ID_PREFIXES prefix the English-name
    slug; every other category keeps the plain slug.
    """
    slug = slugify(drink.name_en)
    prefix = CATEGORY_ID_PREFIXES.get(section.id)
    return f"{prefix}-{slug}" if prefix else slug


def build_ordering_items(recipes_text: str, config: dict) -> list[dict]:
    """Build the orderable menu items from the parsed recipes plus the
    ordering enrichment config.

    The config's "items" object keys drinks by their recipes name and may
    carry id, name, nameVi, description, imagePath, temperatures, and
    modifierGroupIds; anything omitted falls back to what the recipes
    derivation yields, so a drink added to recipes orderably appears with
    a slug id, no image, and the default modifier groups (sweetness, plus
    cold foam when iced; the kem builds carry none). The config's
    "modifierGroups" must cover every referenced group id. Overrides naming
    drinks the recipes no longer define fail loudly, as does any drink left
    without a description.
    """
    menu = parse_menu(recipes_text)
    overrides = _ordering_overrides(config)
    defaults = _ordering_defaults(config)
    known_group_ids = {
        group.get("id") for group in config.get("modifierGroups", []) if isinstance(group, dict)
    }
    items: list[dict] = []
    seen_ids: set[str] = set()
    defined_drinks: set[str] = set()
    for section in menu.sections:
        for drink in section.items:
            defined_drinks.add(drink.name_en)
            override = overrides.get(drink.name_en, {})
            item_id = override.get("id") or _default_item_id(section, drink)
            if item_id in seen_ids:
                raise OrderingConfigError(
                    f"items {drink.name_en!r} and an earlier drink both resolve to "
                    f"the id {item_id!r}"
                )
            seen_ids.add(item_id)
            temperatures = (
                _canonical_temperatures(drink.name_en, list(override["temperatures"]))
                if "temperatures" in override
                else list(drink.temperatures)
            )
            if "modifierGroupIds" in override:
                group_ids = list(override["modifierGroupIds"])
            elif section.id in defaults["byCategory"]:
                group_ids = list(defaults["byCategory"][section.id])
            else:
                group_ids = list(defaults["base"]) + [
                    group_id
                    for group_id in defaults["icedOnly"]
                    if ICED in temperatures
                ]
            unknown_groups = [gid for gid in group_ids if gid not in known_group_ids]
            if unknown_groups:
                raise OrderingConfigError(
                    f"item {item_id!r} references modifier groups {unknown_groups} "
                    "that the overrides config does not define"
                )
            name = override.get("name") or drink.name_en
            name_vi = override.get("nameVi") or drink.name_vi or name
            description = override.get("description") or drink.description
            if not description:
                raise OrderingConfigError(
                    f"item {item_id!r} ({name_vi}) has no description: the recipes "
                    "prose yields none and the overrides config carries no override"
                )
            entry = {
                "id": item_id,
                "name": name,
                "nameVi": name_vi,
                "description": description,
                "categoryId": section.id,
                "temperatures": temperatures,
                "modifierGroupIds": group_ids,
            }
            if "imagePath" in override:
                entry["imagePath"] = override["imagePath"]
            items.append(entry)
    unmatched = sorted(set(overrides) - defined_drinks)
    if unmatched:
        raise OrderingConfigError(
            f"the overrides config keys drinks the recipes do not define: {unmatched}"
        )
    return items
