"""Unit tests for menu/generate_menudata.py, the menuData.ts generator.

Runs the generator against small synthetic menu documents to pin the
normalization (explicit nulls for the fields the web MenuDocument type
requires, present values untouched, idempotent), the round-trip reparse
guard, the strict-JSON literal emission, and the CLI's success and
failure paths. The committed-artifact drift guards live in
site/test_menu_staleness.py; this file only exercises generator
behavior.
"""

import json
import sys
from pathlib import Path

import pytest

SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
MENU_DIR = REPO_ROOT / "menu"

sys.path.insert(0, str(MENU_DIR))

import generate_menudata  # noqa: E402


def synthetic_document() -> dict:
    return {
        "version": 1,
        "orderRules": {"notesMaxLength": 200, "minQuantity": 1, "maxQuantity": 10},
        "categories": [{"id": "kem", "nameVi": "Kem", "name": "Cold Foams"}],
        "modifierGroups": [
            {
                "id": "sweetness",
                "dimension": "sweetness_level",
                "name": "Sweetness",
                "required": True,
                "options": [
                    {"id": "full", "name": "Full sweetness", "temperatures": ["hot", "iced"]}
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
        "items": [
            {
                "id": "kem-sua",
                "name": "Base Foam",
                "nameVi": "Kem Sữa",
                "description": "Cream and milk frothed thick, a touch of vanilla.",
                "categoryId": "kem",
                "temperatures": ["iced"],
                "modifierGroupIds": [],
            }
        ],
    }


def rendered_literal(text: str) -> str:
    """Slice the object literal out of a rendered menuData.ts text:
    everything between the typed export prefix and the trailing ';' newline."""
    assert text.startswith(generate_menudata.HEADER)
    assert text.endswith(";\n")
    return text[len(generate_menudata.HEADER) : -2]


def test_normalization_writes_type_required_nulls() -> None:
    document = synthetic_document()
    normalized = generate_menudata.normalize(document)
    assert normalized["items"][0]["imagePath"] is None
    assert normalized["modifierGroups"][1]["defaultOptionId"] is None
    assert normalized["modifierGroups"][1]["defaultByTemperature"] is None


def test_normalization_never_touches_present_values() -> None:
    document = synthetic_document()
    document["items"][0]["imagePath"] = "/images/menu/kem-sua.jpg"
    document["modifierGroups"][1]["defaultByTemperature"] = {"iced": "foam-base"}
    normalized = generate_menudata.normalize(document)
    assert normalized["items"][0]["imagePath"] == "/images/menu/kem-sua.jpg"
    assert normalized["modifierGroups"][1]["defaultByTemperature"] == {"iced": "foam-base"}
    assert normalized["modifierGroups"][0]["defaultOptionId"] == "full"


def test_normalization_is_idempotent() -> None:
    document = generate_menudata.normalize(synthetic_document())
    assert generate_menudata.normalize(document) == document


def test_render_round_trips_to_the_normalized_document() -> None:
    normalized = generate_menudata.normalize(synthetic_document())
    reparsed = json.loads(rendered_literal(generate_menudata.render(synthetic_document())))
    assert reparsed == normalized


def test_render_emits_a_strict_json_literal_with_the_typed_export() -> None:
    text = generate_menudata.render(synthetic_document())
    assert text.startswith(generate_menudata.HEADER)
    assert text.endswith("};\n")
    assert "Kem Sữa" in text
    # json.loads rejects trailing commas and single-quoted keys, so a
    # clean parse is the strictness proof.
    assert isinstance(json.loads(rendered_literal(text)), dict)


def test_render_requires_the_document_collections() -> None:
    with pytest.raises(generate_menudata.MenuDataGenerationError, match="missing 'items'"):
        generate_menudata.render({"modifierGroups": []})


def test_cli_main_writes_the_document_and_returns_zero(tmp_path, capsys) -> None:
    menu_path = tmp_path / "menu.json"
    menu_path.write_text(json.dumps(synthetic_document(), ensure_ascii=False), encoding="utf-8")
    out_path = tmp_path / "menuData.ts"
    assert generate_menudata.main(["--menu", str(menu_path), "--out", str(out_path)]) == 0
    text = out_path.read_text(encoding="utf-8")
    assert text == generate_menudata.render(json.loads(menu_path.read_text(encoding="utf-8")))
    assert f"wrote {out_path}" in capsys.readouterr().out


def test_cli_main_reports_a_missing_menu_and_writes_nothing(tmp_path, capsys) -> None:
    out_path = tmp_path / "menuData.ts"
    exit_code = generate_menudata.main(
        ["--menu", str(tmp_path / "absent" / "menu.json"), "--out", str(out_path)]
    )
    assert exit_code == 1
    assert "cannot read" in capsys.readouterr().err
    assert not out_path.exists()


def test_cli_main_reports_invalid_json_and_writes_nothing(tmp_path, capsys) -> None:
    menu_path = tmp_path / "menu.json"
    menu_path.write_text("{not json", encoding="utf-8")
    out_path = tmp_path / "menuData.ts"
    assert generate_menudata.main(["--menu", str(menu_path), "--out", str(out_path)]) == 1
    assert "not valid JSON" in capsys.readouterr().err
    assert not out_path.exists()


def test_cli_main_reports_a_non_object_menu_and_writes_nothing(tmp_path, capsys) -> None:
    menu_path = tmp_path / "menu.json"
    menu_path.write_text("[]", encoding="utf-8")
    out_path = tmp_path / "menuData.ts"
    assert generate_menudata.main(["--menu", str(menu_path), "--out", str(out_path)]) == 1
    assert "must be a JSON object" in capsys.readouterr().err
    assert not out_path.exists()
