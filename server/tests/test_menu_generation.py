"""Generation suite for the derived menu document.

Unit tests run the generator against small inline recipes and overrides
fixtures to pin the derivation rules (temperatures, Vietnamese names,
default modifier groups, override precedence, block passthrough, canonical
serialization); integration tests regenerate the real menu from the
sibling recipes checkout plus the checked-in overrides config and compare
against the committed menu/menu.json, so the sources and the artifact
cannot drift.
"""

import json
import re
import shutil
import textwrap
from pathlib import Path

import pytest

from app.menu_generator import (
    MenuGenerationError,
    build_document,
    generate,
    main,
    serialize_document,
)

MENU_DIR = Path(__file__).resolve().parents[2] / "menu"
MENU_JSON = MENU_DIR / "menu.json"
MENU_SCHEMA = MENU_DIR / "menu.schema.json"
DEFAULT_RECIPES = Path(__file__).resolve().parents[2].parent / "recipes" / "cafe.md"
DEFAULT_OVERRIDES = MENU_DIR / "ordering-overrides.json"

SWEETNESS_SCALE = ["full", "75", "50", "25", "none"]

ITEM_KEYS = [
    "id",
    "name",
    "nameVi",
    "description",
    "categoryId",
    "temperatures",
    "modifierGroupIds",
]

RECIPES_FIXTURE = textwrap.dedent(
    """
    # Cafe Fixture

    ## Coffee

    ### Vietnamese Iced Coffee

    #### Cà Phê Sữa Đá

    The classic: strong coffee stirred into condensed milk.

    Served hot or iced.

    - 1 batch Coffee Concentrate
    - 25g condensed milk

    #### Instructions

    1. Stir.

    ### Shakerato

    Iced only: coffee shaken with syrup until frothy.

    - 1 batch Coffee Concentrate
    - Ice

    ### Cortado

    A short, balanced cut of coffee and milk.

    - 60g Coffee Concentrate
    - 60g whole milk

    ## Cold Foams

    ### Foam Matrix

    | Build | Flavor Component | Prep |
    |---|---|---|
    | [Base](#base-foam) | None | Combine and froth |
    | [Salted](#salted-cold-foam) | 5g saline | Combine and froth |

    ### Base Foam

    Sweet cream cold foam.

    - 30g heavy whipping cream
    - 15g milk

    ### Foam Builds

    #### Salted Cold Foam

    Sweet cream cold foam with a pinch of salt.

    - 5g saline solution
    """
)

DESCRIPTION_LESS_RECIPES = textwrap.dedent(
    """
    # Cafe Fixture

    ## Refreshers

    ### Cocoa

    Served hot or iced.

    - 8g cocoa powder
    """
)


def overrides_config(items: dict | None = None) -> dict:
    return {
        "version": 1,
        "orderRules": {"notesMaxLength": 200, "minQuantity": 1, "maxQuantity": 10},
        "categories": [
            {"id": "ca-phe", "nameVi": "Cà Phê", "name": "Coffee"},
            {"id": "kem", "nameVi": "Kem", "name": "Cold Foams"},
        ],
        "modifierGroups": [
            {
                "id": "sweetness",
                "dimension": "sweetness_level",
                "name": "Sweetness",
                "required": True,
                "options": [
                    {"id": option_id, "name": option_id, "temperatures": ["hot", "iced"]}
                    for option_id in SWEETNESS_SCALE
                ],
                "defaultOptionId": "full",
            },
            {
                "id": "cold-foam",
                "dimension": "cold_foam",
                "name": "Cold foam",
                "required": False,
                "options": [
                    {"id": "foam-base", "name": "Base Foam", "temperatures": ["iced"]}
                ],
            },
        ],
        "defaults": {
            "modifierGroups": {
                "base": ["sweetness"],
                "icedOnly": ["cold-foam"],
                "byCategory": {"kem": []},
            }
        },
        "items": items or {},
    }


def items_by_id(document: dict) -> dict:
    return {item["id"]: item for item in document["items"]}


def build_fixture_document(items: dict | None = None, recipes: str = RECIPES_FIXTURE) -> dict:
    return build_document(recipes, overrides_config(items))


def test_derived_drink_needs_no_config_entry() -> None:
    document = build_fixture_document()
    item = items_by_id(document)["vietnamese-iced-coffee"]
    assert item["name"] == "Vietnamese Iced Coffee"
    assert item["nameVi"] == "Cà Phê Sữa Đá"
    assert item["description"] == (
        "The classic: strong coffee stirred into condensed milk."
    )
    assert item["categoryId"] == "ca-phe"
    assert item["temperatures"] == ["hot", "iced"]
    assert item["modifierGroupIds"] == ["sweetness", "cold-foam"]


def test_iced_derivation_gains_cold_foam_while_hot_does_not() -> None:
    document = build_fixture_document()
    items = items_by_id(document)
    assert items["shakerato"]["temperatures"] == ["iced"]
    assert items["shakerato"]["modifierGroupIds"] == ["sweetness", "cold-foam"]
    assert items["cortado"]["temperatures"] == ["hot"]
    assert items["cortado"]["modifierGroupIds"] == ["sweetness"]


def test_foam_items_default_to_no_modifier_groups() -> None:
    document = build_fixture_document()
    kem = [item for item in document["items"] if item["categoryId"] == "kem"]
    assert [item["id"] for item in kem] == ["base-foam", "salted-cold-foam"]
    assert all(item["modifierGroupIds"] == [] for item in kem)
    assert all(item["temperatures"] == ["iced"] for item in kem)


def test_overrides_replace_the_derived_fields() -> None:
    document = build_fixture_document(
        {
            "Vietnamese Iced Coffee": {
                "id": "sua-da",
                "name": "Sữa Đá",
                "nameVi": "Sữa Đá",
                "description": "Menu copy for the house classic.",
                "modifierGroupIds": ["sweetness"],
            }
        }
    )
    item = items_by_id(document)["sua-da"]
    assert item["name"] == "Sữa Đá"
    assert item["nameVi"] == "Sữa Đá"
    assert item["description"] == "Menu copy for the house classic."
    assert item["modifierGroupIds"] == ["sweetness"]
    assert "vietnamese-iced-coffee" not in items_by_id(document)


def test_image_path_override_becomes_an_optional_field() -> None:
    document = build_fixture_document({"Cortado": {"imagePath": "/images/menu/cortado.jpg"}})
    assert items_by_id(document)["cortado"]["imagePath"] == "/images/menu/cortado.jpg"


def test_temperature_override_corrects_the_derivation_and_canonicalizes_order() -> None:
    document = build_fixture_document({"Cortado": {"temperatures": ["iced", "hot"]}})
    assert items_by_id(document)["cortado"]["temperatures"] == ["hot", "iced"]


def test_unknown_override_key_fails_loudly() -> None:
    with pytest.raises(MenuGenerationError, match=r"'Cortado'.*unknown keys.*'bogus'"):
        build_fixture_document({"Cortado": {"bogus": True}})


def test_override_for_a_drink_not_in_the_recipes_fails_loudly() -> None:
    with pytest.raises(MenuGenerationError, match="'Retired Drink'"):
        build_fixture_document({"Retired Drink": {"id": "retired-drink"}})


def test_drink_without_description_or_override_fails_loudly() -> None:
    with pytest.raises(MenuGenerationError, match="no description"):
        build_fixture_document(recipes=DESCRIPTION_LESS_RECIPES)


def test_duplicate_resolved_ids_fail_loudly() -> None:
    with pytest.raises(MenuGenerationError, match="both resolve to.*'cortado'"):
        build_fixture_document({"Shakerato": {"id": "cortado"}})


def test_unknown_modifier_group_reference_fails_loudly() -> None:
    with pytest.raises(MenuGenerationError, match="'mystery'"):
        build_fixture_document({"Cortado": {"modifierGroupIds": ["mystery"]}})


def test_invalid_temperature_values_fail_loudly() -> None:
    with pytest.raises(MenuGenerationError, match=r"Cortado.*temperatures.*'warm'"):
        build_fixture_document({"Cortado": {"temperatures": ["warm"]}})


def test_config_block_fields_pass_through_verbatim() -> None:
    config = overrides_config()
    document = build_document(RECIPES_FIXTURE, config)
    assert document["version"] == config["version"]
    assert document["orderRules"] == config["orderRules"]
    assert document["categories"] == config["categories"]
    assert document["modifierGroups"] == config["modifierGroups"]


def test_missing_config_block_field_raises() -> None:
    config = overrides_config()
    del config["modifierGroups"]
    with pytest.raises(MenuGenerationError, match="missing.*'modifierGroups'"):
        build_document(RECIPES_FIXTURE, config)


def test_serialization_is_canonical() -> None:
    document = build_fixture_document()
    text = serialize_document(document)
    assert re.findall(r'^  "(\w+)":', text, re.MULTILINE) == [
        "version",
        "orderRules",
        "categories",
        "modifierGroups",
        "items",
    ]
    assert list(document["items"][0]) == ITEM_KEYS
    assert text == json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    assert text.endswith("}\n")


def test_schema_violation_raises_and_writes_nothing(tmp_path) -> None:
    recipes_path = tmp_path / "cafe.md"
    recipes_path.write_text(RECIPES_FIXTURE, encoding="utf-8")
    overrides_path = tmp_path / "ordering-overrides.json"
    config = overrides_config()
    config["version"] = 0
    overrides_path.write_text(json.dumps(config), encoding="utf-8")
    out_path = tmp_path / "menu.json"
    with pytest.raises(MenuGenerationError) as excinfo:
        generate(recipes_path, overrides_path, out_path, schema_path=MENU_SCHEMA)
    assert "validation" in str(excinfo.value)
    assert "version" in str(excinfo.value)
    assert not out_path.exists()


def test_cli_main_writes_the_document_and_returns_zero(tmp_path, capsys) -> None:
    recipes_path = tmp_path / "cafe.md"
    recipes_path.write_text(RECIPES_FIXTURE, encoding="utf-8")
    overrides_path = tmp_path / "ordering-overrides.json"
    overrides_path.write_text(json.dumps(overrides_config()), encoding="utf-8")
    shutil.copyfile(MENU_SCHEMA, tmp_path / "menu.schema.json")
    out_path = tmp_path / "menu.json"
    assert main(
        [
            "--recipes", str(recipes_path),
            "--overrides", str(overrides_path),
            "--out", str(out_path),
        ]
    ) == 0
    document = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(document["items"]) == 5
    assert f"wrote {out_path}" in capsys.readouterr().out


def test_cli_main_reports_a_missing_recipes_file_and_writes_nothing(tmp_path, capsys) -> None:
    out_path = tmp_path / "menu.json"
    assert main(["--recipes", str(tmp_path / "absent" / "cafe.md"), "--out", str(out_path)]) == 1
    assert "cannot read the recipes file" in capsys.readouterr().err
    assert not out_path.exists()


def test_generated_document_matches_the_committed_menu_json(tmp_path) -> None:
    out_path = tmp_path / "menu.json"
    generate(DEFAULT_RECIPES, DEFAULT_OVERRIDES, out_path)
    assert json.loads(out_path.read_text(encoding="utf-8")) == json.loads(
        MENU_JSON.read_text(encoding="utf-8")
    )


def test_generation_is_byte_identical_across_runs(tmp_path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    generate(DEFAULT_RECIPES, DEFAULT_OVERRIDES, first)
    generate(DEFAULT_RECIPES, DEFAULT_OVERRIDES, second)
    assert first.read_bytes() == second.read_bytes()


def test_real_menu_yields_36_items_across_5_categories(tmp_path) -> None:
    document = generate(DEFAULT_RECIPES, DEFAULT_OVERRIDES, tmp_path / "menu.json")
    assert len(document["items"]) == 36
    assert len(document["categories"]) == 5


def test_real_menu_tracks_the_recipes_drinks(tmp_path) -> None:
    document = generate(DEFAULT_RECIPES, DEFAULT_OVERRIDES, tmp_path / "menu.json")
    items = items_by_id(document)
    assert items["black-coffee"]["nameVi"] == "Cà Phê Đen"
    assert items["black-coffee"]["temperatures"] == ["hot", "iced"]
    assert items["black-coffee"]["modifierGroupIds"] == ["sweetness", "cold-foam"]
    assert "bac-xiu" not in items
