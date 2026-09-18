"""Staleness guard for the committed ordering menu.

Regenerates menu/menu.json from the recipes checkout plus the checked-in
menu/ordering-overrides.json through the shared parsing core and fails
loudly when the committed artifact differs, so the sources and the
artifact cannot drift. Lives beside the site tests because the
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
