"""Tests for the cost workbook parser.

Run: uv run --with pytest --with openpyxl --with weasyprint==70.0 pytest site/test_pricing_source.py -q
"""

import os
import sys
from pathlib import Path

import openpyxl
import pytest

SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
RECIPES_CAFE = Path(
    os.environ.get("RECIPES_CAFE", REPO_ROOT.parent / "recipes" / "cafe.md")
)
CAFE_COSTS_XLSX = RECIPES_CAFE.parent / "cafe_costs.xlsx"

sys.path.insert(0, str(SITE_DIR))

import pricing_source  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "menu"))

import menu_source  # noqa: E402

# Spot values are pinned to one millionth: the evaluator must agree with the
# hand-derived arithmetic to full displayed-cents precision and far beyond.
COST_ABS_TOLERANCE = 1e-6


def read_rows_by_name() -> dict[str, pricing_source.DrinkCost]:
    return {
        row.name: row for row in pricing_source.read_drink_costs(CAFE_COSTS_XLSX)
    }


def read_readme_value(coordinate: str) -> float:
    """Return one numeric Read Me cell from the real workbook.

    The pricing parameter is read at test time because the workbook is
    owner-curated live data: pinning its value in the suite would break on
    every legitimate workbook edit.
    """

    workbook = openpyxl.load_workbook(CAFE_COSTS_XLSX)
    return float(workbook["Read Me"][coordinate].value)


def write_synthetic_workbook(
    path: Path, cost_formula: str, multiplier: float = 2.0
) -> Path:
    """Write a minimal workbook mirroring the real sheet shape.

    The Drinks C2 cell carries ``cost_formula``; D2 prices it through the
    Read Me B12 multiplier exactly like the real workbook. Bases D5 and
    Ingredients E2 give every drink formula a two-link resolution chain
    through other formula cells.
    """

    workbook = openpyxl.Workbook()
    readme = workbook.active
    readme.title = "Read Me"
    readme["B12"] = multiplier
    ingredients = workbook.create_sheet("Ingredients")
    ingredients["A2"] = "Turbinado Sugar"
    ingredients["C2"] = 8.49
    ingredients["D2"] = 1814
    ingredients["E2"] = "=C2/D2"
    bases = workbook.create_sheet("Bases")
    bases["A5"] = "Turbinado Syrup (25g dose)"
    bases["D5"] = "=Ingredients!E2/10"
    drinks = workbook.create_sheet("Drinks")
    drinks["A2"] = "Test Drink"
    drinks["C2"] = cost_formula
    drinks["D2"] = "=C2*'Read Me'!$B$12"
    workbook.save(path)
    return path


class TestReadDrinkCosts:
    def test_read_drink_costs_returns_all_rows_from_workbook(self):
        rows = pricing_source.read_drink_costs(CAFE_COSTS_XLSX)

        # The expected count derives from the Drinks sheet at test time:
        # the owner adds rows as live data (29 grew to 32 mid-build), so
        # pinning a count would break on every legitimate edit.
        workbook = openpyxl.load_workbook(CAFE_COSTS_XLSX)
        sheet = workbook[pricing_source.DRINKS_SHEET]
        sheet_row_count = sum(
            1
            for row in range(pricing_source.FIRST_DATA_ROW, sheet.max_row + 1)
            if sheet[f"{pricing_source.DRINK_NAME_COLUMN}{row}"].value is not None
        )
        assert len(rows) == sheet_row_count
        assert len(rows) > 0

    def test_read_drink_costs_preserves_workbook_row_order(self):
        rows = pricing_source.read_drink_costs(CAFE_COSTS_XLSX)

        # The expected order derives from the Drinks sheet at test time:
        # the owner reorders and renames rows as live data, so pinning
        # names would break on every legitimate edit.
        workbook = openpyxl.load_workbook(CAFE_COSTS_XLSX)
        sheet = workbook[pricing_source.DRINKS_SHEET]
        sheet_names = [
            sheet[f"{pricing_source.DRINK_NAME_COLUMN}{row}"].value
            for row in range(
                pricing_source.FIRST_DATA_ROW, sheet.max_row + 1
            )
            if sheet[f"{pricing_source.DRINK_NAME_COLUMN}{row}"].value
            is not None
        ]
        assert [row.name for row in rows] == sheet_names

    def test_black_coffee_cost_matches_hand_derived_concentrate_cost(self):
        black_coffee = read_rows_by_name()["Black Coffee"]

        assert black_coffee.cost == pytest.approx(
            20 * 18.99 / 1134, abs=COST_ABS_TOLERANCE
        )

    def test_black_coffee_suggested_matches_workbook_markup_pricing(self):
        # The workbook's Menu Price relationship is owner-curated: during
        # development it moved from cost x Read Me B12 to cost + Read Me
        # B13. The markup value is read live; a future structural change
        # to the D-column formulas must update this pin's shape.
        markup = read_readme_value("B13")

        black_coffee = read_rows_by_name()["Black Coffee"]

        assert black_coffee.suggested == pytest.approx(
            20 * 18.99 / 1134 + markup, abs=COST_ABS_TOLERANCE
        )

    def test_house_latte_cost_matches_hand_derived_build(self):
        house_latte = read_rows_by_name()["House Latte"]

        # 1 batch concentrate + 25g syrup dose + 150g whole milk, straight
        # from the workbook's Bases D2, Bases D5, and Ingredients E3 chains.
        expected = (
            20 * 18.99 / 1134
            + (100 * 8.49 / 1814) / 250 * 25
            + 150 * 5.99 / 7570
        )
        assert house_latte.cost == pytest.approx(expected, abs=COST_ABS_TOLERANCE)

    def test_house_latte_suggested_matches_workbook_markup_pricing(self):
        markup = read_readme_value("B13")

        house_latte = read_rows_by_name()["House Latte"]

        expected = (
            20 * 18.99 / 1134
            + (100 * 8.49 / 1814) / 250 * 25
            + 150 * 5.99 / 7570
        ) + markup
        assert house_latte.suggested == pytest.approx(
            expected, abs=COST_ABS_TOLERANCE
        )

    def test_hot_tea_cost_matches_hand_derived_tea_weight(self):
        hot_tea = read_rows_by_name()["Hot Tea"]

        assert hot_tea.cost == pytest.approx(
            4 * 14.99 / 454, abs=COST_ABS_TOLERANCE
        )


class TestFormulaEvaluation:
    def test_b12_multiplier_edit_reprices_suggested_at_next_read(self, tmp_path):
        path = write_synthetic_workbook(
            tmp_path / "costs.xlsx", cost_formula="=Ingredients!E2*100"
        )

        before = pricing_source.read_drink_costs(path)[0]
        assert before.cost == pytest.approx(
            (8.49 / 1814) * 100, abs=COST_ABS_TOLERANCE
        )
        assert before.suggested == pytest.approx(
            (8.49 / 1814) * 100 * 2.0, abs=COST_ABS_TOLERANCE
        )

        workbook = openpyxl.load_workbook(path)
        workbook["Read Me"]["B12"] = 3.5
        workbook.save(path)

        after = pricing_source.read_drink_costs(path)[0]
        assert after.suggested == pytest.approx(
            (8.49 / 1814) * 100 * 3.5, abs=COST_ABS_TOLERANCE
        )

    def test_formula_chain_resolves_through_nested_cells(self, tmp_path):
        path = write_synthetic_workbook(
            tmp_path / "costs.xlsx", cost_formula="=Bases!D5*2"
        )

        (row,) = pricing_source.read_drink_costs(path)

        assert row.cost == pytest.approx(
            (8.49 / 1814 / 10) * 2, abs=COST_ABS_TOLERANCE
        )

    def test_function_call_formula_fails_naming_cell_and_formula(self, tmp_path):
        path = write_synthetic_workbook(
            tmp_path / "costs.xlsx", cost_formula="=SUM(A1:A2)"
        )

        with pytest.raises(pricing_source.FormulaError) as excinfo:
            pricing_source.read_drink_costs(path)

        message = str(excinfo.value)
        assert "Drinks!C2" in message
        assert "=SUM(A1:A2)" in message

    def test_bare_word_formula_fails_naming_cell_and_formula(self, tmp_path):
        path = write_synthetic_workbook(
            tmp_path / "costs.xlsx", cost_formula="=Bogus+1"
        )

        with pytest.raises(pricing_source.FormulaError) as excinfo:
            pricing_source.read_drink_costs(path)

        message = str(excinfo.value)
        assert "Drinks!C2" in message
        assert "=Bogus+1" in message

    def test_self_reference_fails_naming_the_cyclic_cell(self, tmp_path):
        path = write_synthetic_workbook(
            tmp_path / "costs.xlsx", cost_formula="=C2+1"
        )

        with pytest.raises(pricing_source.FormulaError) as excinfo:
            pricing_source.read_drink_costs(path)

        message = str(excinfo.value)
        assert "Drinks!C2" in message
        assert "cycle" in message.lower()

    def test_reference_to_empty_cell_fails_naming_the_reference(self, tmp_path):
        path = write_synthetic_workbook(
            tmp_path / "costs.xlsx", cost_formula="=Z99*2"
        )

        with pytest.raises(pricing_source.FormulaError) as excinfo:
            pricing_source.read_drink_costs(path)

        assert "Z99" in str(excinfo.value)


class TestContractSurface:
    def test_price_aliases_match_contract(self):
        assert pricing_source.PRICE_ALIASES == {
            "Pour Over": "Pour Over Coffee",
            "Vietnamese Coffee": "Vietnamese Iced Coffee",
        }

    def test_bac_xiu_item_matches_contract(self):
        item = pricing_source.BAC_XIU

        assert isinstance(item, menu_source.Item)
        assert item.name_en == "Bạc Xỉu"
        assert item.name_vi == "Cà Phê Bạc Xỉu"
        assert item.description == (
            "The classic milkier white coffee: the House Latte built on "
            "condensed milk instead of syrup."
        )
        assert item.temperatures == ["hot", "iced"]

    def test_bac_xiu_anchor_matches_contract(self):
        assert pricing_source.BAC_XIU_ANCHOR == "House Latte"

    def test_default_costs_derives_from_sibling_recipes_checkout(self):
        assert pricing_source.DEFAULT_COSTS == (
            REPO_ROOT.parent / "recipes" / "cafe_costs.xlsx"
        )


class TestLazyOpenpyxlImport:
    def test_missing_openpyxl_raises_runtime_error_naming_uv_incantation(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setitem(sys.modules, "openpyxl", None)
        path = write_synthetic_workbook(
            tmp_path / "costs.xlsx", cost_formula="=Ingredients!E2"
        )

        with pytest.raises(RuntimeError) as excinfo:
            pricing_source.read_drink_costs(path)

        assert "uv run --with openpyxl python site/generate.py" in str(
            excinfo.value
        )
