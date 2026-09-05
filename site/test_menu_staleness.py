"""Staleness guards for the committed ordering menu and its web copy.

Regenerates menu/menu.json from the recipes checkout plus the checked-in
menu/ordering-overrides.json through the shared parsing core and fails
loudly when the committed artifact differs, so the sources and the
artifact cannot drift. The web dev/test fallback copy of the same
document, web/src/views/ordering/lib/menuData.ts, is held to the
committed menu.json the same way. Lives beside the site tests because the
Pages workflow's test step is where the sibling recipes checkout is
guaranteed to exist; RECIPES_CAFE points at the recipes file there, as
for the site tests.
"""

import json
import os
import sys
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
RECIPES_CAFE = Path(
    os.environ.get("RECIPES_CAFE", REPO_ROOT.parent / "recipes" / "cafe.md")
)
MENU_DIR = REPO_ROOT / "menu"
MENUDATA_TS = (
    REPO_ROOT / "web" / "src" / "views" / "ordering" / "lib" / "menuData.ts"
)
MENUDATA_EXPORT = "export const menuDocument"

sys.path.insert(0, str(MENU_DIR))

import menu_source  # noqa: E402

BLOCK_KEYS = ("version", "orderRules", "categories", "modifierGroups")
ITEM_FIELDS = (
    "name",
    "nameVi",
    "description",
    "categoryId",
    "temperatures",
    "modifierGroupIds",
    "imagePath",
)


def rebuilt_document() -> dict:
    config = json.loads((MENU_DIR / "ordering-overrides.json").read_text(encoding="utf-8"))
    return {
        "version": config["version"],
        "orderRules": config["orderRules"],
        "categories": config["categories"],
        "modifierGroups": config["modifierGroups"],
        "items": menu_source.build_ordering_items(
            RECIPES_CAFE.read_text(encoding="utf-8"), config
        ),
    }


def differences(expected: dict, actual: dict) -> list[str]:
    problems: list[str] = []
    for key in BLOCK_KEYS:
        if actual.get(key) != expected[key]:
            problems.append(f"{key} differs from the expected document")
    expected_items = {item["id"]: item for item in expected.get("items", [])}
    actual_items = {item["id"]: item for item in actual["items"]}
    added = sorted(set(actual_items) - set(expected_items))
    removed = sorted(set(expected_items) - set(actual_items))
    if added:
        problems.append(f"items the expected document lacks: {added}")
    if removed:
        problems.append(f"items only the expected document defines: {removed}")
    for item_id in sorted(set(expected_items) & set(actual_items)):
        for field in ITEM_FIELDS:
            if expected_items[item_id].get(field) != actual_items[item_id].get(field):
                problems.append(
                    f"item {item_id!r} field {field!r}: expected "
                    f"{expected_items[item_id].get(field)!r} != actual "
                    f"{actual_items[item_id].get(field)!r}"
                )
    if [item["id"] for item in expected.get("items", [])] != [
        item["id"] for item in actual["items"]
    ]:
        problems.append("item order differs from the expected document order")
    return problems


def test_committed_menu_matches_recipes_plus_overrides() -> None:
    committed = json.loads((MENU_DIR / "menu.json").read_text(encoding="utf-8"))
    rebuilt = rebuilt_document()
    problems = differences(rebuilt, committed)
    assert problems == [], (
        "menu/menu.json is stale against the recipes and "
        "menu/ordering-overrides.json; regenerate with `make menu`:\n"
        + "\n".join(f"  - {problem}" for problem in problems)
    )


def parse_menudata_literal(text: str) -> dict:
    """Parse the menuDocument object literal out of menuData.ts as JSON.

    The file's header comment and typed export prefix are TS, so slice
    from the first `{` after the `export const menuDocument` marker to
    its matching close brace (brace counting that skips string
    literals), then require the slice to be strict JSON: menuData.ts
    must keep its object literal double-quoted with no trailing commas.
    """
    marker_at = text.index(MENUDATA_EXPORT)
    start = text.index("{", text.index("=", marker_at))
    depth = 0
    index = start
    in_string = False
    quote = ""
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                in_string = False
        elif char in "\"'`":
            in_string = True
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                literal = text[start : index + 1]
                try:
                    return json.loads(literal)
                except json.JSONDecodeError as error:
                    raise AssertionError(
                        f"{MENUDATA_TS.relative_to(REPO_ROOT)}: the "
                        "menuDocument object literal is not strict JSON "
                        f"(double-quoted keys, no trailing commas): {error}"
                    ) from error
        index += 1
    raise AssertionError(
        f"{MENUDATA_TS.relative_to(REPO_ROOT)}: no closing brace after "
        f"'{MENUDATA_EXPORT}'"
    )


def with_type_defaults(document: dict) -> dict:
    """Fill the fields menu.json omits but the web type requires.

    The generated MenuDocument type makes imagePath, defaultOptionId and
    defaultByTemperature non-optional nullables, so menuData.ts spells
    them out as nulls; apply the same defaults to both sides before
    comparing.
    """
    filled = json.loads(json.dumps(document))
    for group in filled.get("modifierGroups", []):
        group.setdefault("defaultOptionId", None)
        group.setdefault("defaultByTemperature", None)
    for item in filled.get("items", []):
        item.setdefault("imagePath", None)
    return filled


def test_menudata_matches_committed_menu() -> None:
    committed = json.loads((MENU_DIR / "menu.json").read_text(encoding="utf-8"))
    copied = parse_menudata_literal(MENUDATA_TS.read_text(encoding="utf-8"))
    problems = differences(
        with_type_defaults(committed), with_type_defaults(copied)
    )
    assert problems == [], (
        f"{MENUDATA_TS.relative_to(REPO_ROOT)} is stale against "
        "menu/menu.json; regenerate its exported menuDocument object "
        "literal from menu/menu.json (strict JSON, absent imagePath and "
        "defaultOptionId/defaultByTemperature written as null):\n"
        + "\n".join(f"  - {problem}" for problem in problems)
    )
