"""Validation suite for the shared menu document.

The menu is hand-curated from ../recipes (menu.html sections and names,
cafe.md per-drink rules), so these tests gate both structure and the
frozen customization model from the PRD.
"""

import json
import re
from functools import cache
from pathlib import Path

import jsonschema

MENU_DIR = Path(__file__).resolve().parents[2] / "menu"
ASSETS_DIR = MENU_DIR / "assets"

EXPECTED_CATEGORIES = [
    ("ca-phe", "Cà Phê", "Coffee"),
    ("mat-cha", "Mát-cha", "Matcha"),
    ("tra", "Trà", "Tea"),
    ("giai-khat", "Giải Khát", "Refreshers"),
    ("kem", "Kem", "Cold Foams"),
]

EXPECTED_ITEM_COUNTS = {
    "ca-phe": 10,
    "mat-cha": 8,
    "tra": 4,
    "giai-khat": 6,
    "kem": 8,
}

SWEETNESS_SCALE = ["full", "75", "50", "25", "none"]

IMAGE_PATH_PATTERN = re.compile(
    r"^/images/menu/(?P<stem>[a-z0-9-]+)\.(?:jpg|jpeg|png|webp|avif)$"
)

FROZEN_ORDER_RULES = {"notesMaxLength": 200, "minQuantity": 1, "maxQuantity": 10}


@cache
def menu() -> dict:
    return json.loads((MENU_DIR / "menu.json").read_text(encoding="utf-8"))


@cache
def schema() -> dict:
    return json.loads((MENU_DIR / "menu.schema.json").read_text(encoding="utf-8"))


def items_by_id() -> dict:
    return {item["id"]: item for item in menu()["items"]}


def groups_by_id() -> dict:
    return {group["id"]: group for group in menu()["modifierGroups"]}


def option_ids_at(group: dict, temperature: str) -> set[str]:
    return {
        option["id"]
        for option in group["options"]
        if temperature in option["temperatures"]
    }


def test_menu_validates_against_the_json_schema() -> None:
    validator = jsonschema.Draft202012Validator(schema())
    errors = sorted(validator.iter_errors(menu()), key=str)
    assert not errors, "\n".join(f"{list(error.path)}: {error.message}" for error in errors)


def test_menu_covers_the_five_recipe_sections() -> None:
    categories = menu()["categories"]
    assert [(c["id"], c["nameVi"], c["name"]) for c in categories] == [
        (category_id, name_vi, name) for category_id, name_vi, name in EXPECTED_CATEGORIES
    ]
    counts = {category_id: 0 for category_id, _, _ in EXPECTED_CATEGORIES}
    for item in menu()["items"]:
        counts[item["categoryId"]] += 1
    assert counts == EXPECTED_ITEM_COUNTS


def test_items_are_unique_and_fully_described() -> None:
    ids = [item["id"] for item in menu()["items"]]
    assert len(ids) == len(set(ids))
    category_ids = {c["id"] for c in menu()["categories"]}
    for item in menu()["items"]:
        assert item["name"] and item["nameVi"] and item["description"]
        assert item["categoryId"] in category_ids
        temperatures = item["temperatures"]
        assert temperatures, f"{item['id']} offers no temperature"
        assert set(temperatures) <= {"hot", "iced"}
        assert len(temperatures) == len(set(temperatures))


def test_modifier_group_references_resolve() -> None:
    group_ids = set(groups_by_id())
    for item in menu()["items"]:
        for group_id in item["modifierGroupIds"]:
            assert group_id in group_ids, f"{item['id']} references unknown group {group_id}"


def test_required_groups_have_valid_defaults_for_every_temperature() -> None:
    for group in menu()["modifierGroups"]:
        option_ids = {option["id"] for option in group["options"]}
        assert len(option_ids) == len(group["options"])
        default_option = group.get("defaultOptionId")
        defaults_by_temperature = group.get("defaultByTemperature", {})
        mechanisms = bool(default_option) + bool(defaults_by_temperature)
        if group["required"]:
            assert mechanisms == 1, f"group {group['id']} lacks exactly one default mechanism"
            if default_option:
                assert default_option in option_ids
            else:
                option_temperatures = {
                    temperature
                    for option in group["options"]
                    for temperature in option["temperatures"]
                }
                assert set(defaults_by_temperature) == option_temperatures, (
                    f"group {group['id']} defaults must cover {option_temperatures}"
                )
                for temperature, option_id in defaults_by_temperature.items():
                    assert option_id in option_ids_at(group, temperature)
        else:
            assert mechanisms == 0


def test_required_groups_cover_every_item_temperature() -> None:
    groups = groups_by_id()
    for item in menu()["items"]:
        for group_id in item["modifierGroupIds"]:
            group = groups[group_id]
            if not group["required"]:
                continue
            for temperature in item["temperatures"]:
                assert option_ids_at(group, temperature), (
                    f"{item['id']} at {temperature} leaves required group "
                    f"{group_id} without options"
                )


def test_cold_foam_attaches_only_to_iced_items() -> None:
    groups = groups_by_id()
    for item in menu()["items"]:
        referenced = [groups[gid] for gid in item["modifierGroupIds"]]
        foam_groups = [g for g in referenced if g["dimension"] == "cold_foam"]
        for group in foam_groups:
            assert "iced" in item["temperatures"], (
                f"{item['id']} is not iced-capable but offers {group['id']}"
            )
            for option in group["options"]:
                assert option["temperatures"] == ["iced"]


def test_sweetness_groups_use_the_standard_scale() -> None:
    for group in menu()["modifierGroups"]:
        if group["dimension"] != "sweetness_level":
            continue
        assert [option["id"] for option in group["options"]] == SWEETNESS_SCALE


def test_image_paths_follow_the_convention_and_files_exist() -> None:
    for item in menu()["items"]:
        image_path = item.get("imagePath")
        if image_path is None:
            continue
        match = IMAGE_PATH_PATTERN.match(image_path)
        assert match, f"{item['id']} has non-conventional imagePath {image_path}"
        assert match.group("stem") == item["id"]
        assert (ASSETS_DIR / Path(image_path).name).is_file()


def test_order_rules_freeze_the_prd_customization_bounds() -> None:
    assert menu()["orderRules"] == FROZEN_ORDER_RULES


def test_matcha_sua_milk_options_vary_by_temperature() -> None:
    group = groups_by_id()["milk-matcha-latte"]
    assert option_ids_at(group, "hot") == {"whole-milk", "oat-milk"}
    assert option_ids_at(group, "iced") == {
        "milk-plus-cream",
        "heavy-cream",
        "half-and-half",
        "oat-milk",
    }
    item = items_by_id()["matcha-sua"]
    assert set(item["modifierGroupIds"]) >= {"milk-matcha-latte", "sweetener-matcha"}


def test_ca_phe_lac_is_iced_only() -> None:
    item = items_by_id()["ca-phe-lac"]
    assert item["temperatures"] == ["iced"]
    assert "cold-foam" in item["modifierGroupIds"]


def test_kem_items_are_standalone_foam_builds() -> None:
    kem_ids = {item["id"] for item in menu()["items"] if item["categoryId"] == "kem"}
    assert kem_ids == {
        "kem-sua",
        "kem-muoi",
        "kem-matcha",
        "kem-pho-mai",
        "kem-dau",
        "kem-cacao",
        "kem-tra",
        "kem-sua-chua",
    }
    for item in menu()["items"]:
        if item["categoryId"] != "kem":
            continue
        assert item["temperatures"] == ["iced"]
        assert item["modifierGroupIds"] == []
