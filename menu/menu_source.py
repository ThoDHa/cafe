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
temperature (Hot Tea) the prose cannot prove. The ordering generator adds
ordering-only enrichment from its own checked-in config; the site adds
blurbs, print fitting, and rendering on top of the parsed menu.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

SECTION_MAP = {
    "Coffee": ("ca-phe", "Cà Phê", "Coffee"),
    "Tea": ("tra", "Trà", "Tea"),
    "Matcha": ("mat-cha", "Mát-cha", "Matcha"),
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
ORDERING_DEFAULT_GROUP_KEYS = frozenset({"base", "icedOnly", "byCategory"})


class UnmappedSectionError(Exception):
    """Raised when cafe.md contains a drink-like section the menu cannot place."""


class OrderingConfigError(Exception):
    """Raised when the ordering enrichment config contradicts the recipes."""


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
                f"add it to SECTION_MAP or KNOWN_NON_DRINK_SECTIONS in menu/menu_source.py"
            )
    kem_id, kem_vi, kem_en = KEM_SECTION
    foam_lines = top_sections.get("Cold Foams", [])
    if "Cold Foams" in top_sections:
        mapped[kem_id] = Section(
            id=kem_id, title_vi=kem_vi, title_en=kem_en,
            items=parse_foam_section(foam_lines),
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
            item_id = override.get("id") or slugify(drink.name_en)
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
