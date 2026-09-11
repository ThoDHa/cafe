"""Tests for the public menu site generator.

Run: uv run --with pytest pytest site/ -q
"""

import ast
import os
import re
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
RECIPES_CAFE = Path(
    os.environ.get("RECIPES_CAFE", REPO_ROOT.parent / "recipes" / "cafe.md")
)
COCKTAILS_MD = RECIPES_CAFE.parent / "cocktails.md"
CAFE_PANTRY_MD = RECIPES_CAFE.parent / "cafe_pantry.md"
CAFE_COSTS_XLSX = RECIPES_CAFE.parent / "cafe_costs.xlsx"
MENU_JSON = REPO_ROOT / "menu" / "menu.json"

sys.path.insert(0, str(SITE_DIR))

import generate  # noqa: E402

import pricing_source  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "menu"))

import menu_source  # noqa: E402

FIXTURE = textwrap.dedent(
    """
    # Cafe Fixture

    ## Coffee

    Sweet, milky, shaken: the classics, hot or iced.

    ### Vietnamese Iced Coffee

    #### Cà Phê Sữa Đá

    The classic: strong coffee stirred into condensed milk. Served hot or iced.

    - 1 batch Coffee Concentrate
    - 25g condensed milk

    #### Instructions

    1. Stir.

    ### Cortado

    A 1:1 preparation of coffee and milk.

    - 60g Coffee Concentrate
    - 60g whole milk

    ### Coffee Affogato

    Hot coffee poured over vanilla ice cream.

    - 1 batch Coffee Concentrate, hot
    - 90-120g vanilla ice cream

    ### Shakerato

    Iced only: coffee shaken with syrup until frothy.

    - 1 batch Coffee Concentrate
    - Ice

    ## Refreshers

    Strawberry and lime sodas, a milk limeade, strawberry milk, and cocoa.

    ### Cocoa

    Served hot or iced.

    - 8g cocoa powder
    - 150g milk

    ### Strawberry Milk

    Cheong stirred into cold milk. Served iced.

    - 45g Strawberry Cheong
    - 240g cold whole milk

    ### Milk Limeade

    Lime pressed into condensed milk over crushed ice.

    - 60g fresh lime juice
    - 150g crushed ice

    ### Pour Over Style

    A standalone drink brewed two ways.

    **Hot:**

    - 18g coffee

    **Iced:**

    - 20g coffee
    - 120g clean ice

    ## Cold Foams

    Cold foam, spooned over the finished drink.

    ### Foam Matrix

    | Build | Flavor Component | Prep |
    |---|---|---|
    | [Base](#base-foam) | None | Combine and froth |
    | [Salted](#salted-cold-foam) | 5g saline | Combine and froth |

    ### Base Foam

    - 30g heavy whipping cream
    - 15g milk

    ### Foam Builds

    Every build is the Base Foam with the components listed below.

    #### Salted Cold Foam

    The base foam sharpened with a dash of salt.

    - 5g saline solution
    """
)


def parsed_fixture():
    return generate.parse_menu(FIXTURE)


class TestParserSections:
    def test_drink_sections_are_mapped_in_menu_order(self):
        menu = parsed_fixture()
        assert [s.id for s in menu.sections] == [
            "ca-phe",
            "giai-khat",
            "kem",
        ]

    def test_fixture_sections_carry_titles(self):
        menu = parsed_fixture()
        ca_phe = menu.by_id("ca-phe")
        assert ca_phe.title_vi == "Cà Phê"
        assert ca_phe.title_en == "Coffee"

    def test_section_titles_use_accented_forms(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        assert menu.by_id("mat-cha").title_vi == "Mát-cha"
        assert menu.by_id("tra").title_vi == "Trà"
        assert menu.by_id("giai-khat").title_vi == "Giải Khát"
        assert menu.by_id("kem").title_en == "Cold Foams"

    def test_foams_section_under_both_titles_fails_loudly(self):
        text = FIXTURE + textwrap.dedent(
            """
            ## Foams

            Creamy foam caps for any drink.

            ### Stray Foam

            - 30g heavy whipping cream
            """
        )
        with pytest.raises(menu_source.UnmappedSectionError) as excinfo:
            menu_source.parse_menu(text)
        message = str(excinfo.value)
        assert "Foams" in message
        assert "Cold Foams" in message
        assert "exactly one" in message

    def test_category_blurb_is_parsed_from_fixture(self):
        menu = parsed_fixture()
        assert menu.by_id("ca-phe").note == (
            "Sweet, milky, shaken: the classics, hot or iced."
        )
        assert menu.by_id("giai-khat").note == (
            "Strawberry and lime sodas, a milk limeade, strawberry milk, and cocoa."
        )

    def test_blurb_is_not_mistaken_for_an_item_description(self):
        menu = parsed_fixture()
        first = menu.by_id("ca-phe").items[0]
        assert first.description.startswith("The classic: strong coffee")


class TestParserItems:
    def test_vietnamese_name_taken_from_following_heading(self):
        menu = parsed_fixture()
        item = menu.by_id("ca-phe").items[0]
        assert item.name_en == "Vietnamese Iced Coffee"
        assert item.name_vi == "Cà Phê Sữa Đá"

    def test_structural_heading_is_not_a_vietnamese_name(self):
        menu = parsed_fixture()
        cortado = next(i for i in menu.by_id("ca-phe").items if i.name_en == "Cortado")
        assert cortado.name_vi is None

    def test_description_is_first_paragraph_with_links_stripped(self):
        menu = parsed_fixture()
        item = menu.by_id("ca-phe").items[0]
        assert item.description.startswith("The classic: strong coffee")
        assert "[" not in item.description and "](" not in item.description

    def test_standalone_serve_cue_paragraph_is_skipped_for_description(self):
        menu = parsed_fixture()
        cocoa = next(i for i in menu.by_id("giai-khat").items if i.name_en == "Cocoa")
        assert cocoa.description is None

    def test_iced_only_prefix_is_stripped_from_description(self):
        menu = parsed_fixture()
        shakerato = next(
            i for i in menu.by_id("ca-phe").items if i.name_en == "Shakerato"
        )
        assert shakerato.description is not None
        assert not shakerato.description.lower().startswith("iced only")


class TestTemperatures:
    def test_hot_or_iced_phrase_yields_both(self):
        menu = parsed_fixture()
        item = menu.by_id("ca-phe").items[0]
        assert item.temperatures == ["hot", "iced"]

    def test_default_is_hot(self):
        menu = parsed_fixture()
        cortado = next(i for i in menu.by_id("ca-phe").items if i.name_en == "Cortado")
        assert cortado.temperatures == ["hot"]

    def test_ice_cream_ingredient_does_not_imply_iced(self):
        menu = parsed_fixture()
        affogato = next(
            i for i in menu.by_id("ca-phe").items if i.name_en == "Coffee Affogato"
        )
        assert affogato.temperatures == ["hot"]

    def test_iced_only_phrase_yields_iced(self):
        menu = parsed_fixture()
        shakerato = next(
            i for i in menu.by_id("ca-phe").items if i.name_en == "Shakerato"
        )
        assert shakerato.temperatures == ["iced"]

    def test_served_iced_phrase_yields_iced(self):
        menu = parsed_fixture()
        strawberry_milk = next(
            i for i in menu.by_id("giai-khat").items if i.name_en == "Strawberry Milk"
        )
        assert strawberry_milk.temperatures == ["iced"]

    def test_crushed_ice_ingredient_yields_iced(self):
        menu = parsed_fixture()
        limeade = next(
            i for i in menu.by_id("giai-khat").items if i.name_en == "Milk Limeade"
        )
        assert limeade.temperatures == ["iced"]

    def test_paired_hot_and_iced_blocks_yield_both(self):
        menu = parsed_fixture()
        pour_over = next(
            i for i in menu.by_id("giai-khat").items if i.name_en == "Pour Over Style"
        )
        assert pour_over.temperatures == ["hot", "iced"]


class TestFoams:
    def test_foam_builds_become_kem_items(self):
        menu = parsed_fixture()
        kem = menu.by_id("kem")
        assert [i.name_en for i in kem.items] == ["Base Foam", "Salted Cold Foam"]

    def test_foams_have_configured_vietnamese_names(self):
        menu = parsed_fixture()
        base = menu.by_id("kem").items[0]
        assert base.name_vi == "Kem Sữa"

    def test_foams_are_iced(self):
        menu = parsed_fixture()
        assert all(i.temperatures == ["iced"] for i in menu.by_id("kem").items)

    def test_foam_description_from_recipe_paragraph(self):
        menu = parsed_fixture()
        salted = menu.by_id("kem").items[1]
        assert salted.description == "The base foam sharpened with a dash of salt."

    def test_foam_description_falls_back_to_config(self):
        menu = parsed_fixture()
        base = menu.by_id("kem").items[0]
        assert base.description is not None


class TestOverrides:
    def test_vietnamese_name_override_applies(self):
        menu = parsed_fixture()
        assert generate.VIETNAMESE_NAME_OVERRIDES.get("Cortado") is None
        assert generate.TEMPERATURE_OVERRIDES.get("Hot Tea") == ["hot", "iced"]


class TestGenericPickup:
    def test_new_drink_in_known_section_is_picked_up(self):
        new_drink = textwrap.dedent(
            """
            ### Brand New Drink Never Seen Before

            #### Đồ Uống Mới

            A drink added to recipes after the generator was written.

            - something potable
            - [Ice](#ice)

            """
        ).lstrip("\n")
        fixture = FIXTURE.replace("## Refreshers", new_drink + "## Refreshers")
        menu = generate.parse_menu(fixture)
        names = [i.name_en for i in menu.by_id("ca-phe").items]
        assert "Brand New Drink Never Seen Before" in names
        new_item = next(i for i in menu.by_id("ca-phe").items if "Brand New" in i.name_en)
        assert new_item.name_vi == "Đồ Uống Mới"
        assert new_item.temperatures == ["iced"]

    def test_unmapped_new_section_fails_loudly(self):
        fixture = FIXTURE + textwrap.dedent(
            """
            ## Smoothies

            ### Blended Fruit

            - fruit
            """
        )
        try:
            generate.parse_menu(fixture)
        except generate.UnmappedSectionError as exc:
            assert "Smoothies" in str(exc)
        else:
            raise AssertionError("expected UnmappedSectionError")

    def test_known_non_drink_sections_do_not_fail(self):
        menu = parsed_fixture()
        target_ids = {spec[0] for spec in generate.SECTION_MAP.values()} | {"kem"}
        assert all(s.id in target_ids for s in menu.sections)


COCKTAILS_FIXTURE = textwrap.dedent(
    """
    # Cocktails

    Cocktail templates built from the modular drink system.

    ## Mule

    A flexible highball built from spirit, ginger beer, and lime.

    - 60g spirit (2 fl oz)
    - 120g ginger beer (4 fl oz)
    - [Angostura Bitters](cafe.md#angostura-bitters), optional

    ### Instructions

    1. Fill a mug with ice.

    ## Highball

    - 60g spirit (2 fl oz)
    - 120-150g mixer (4-5 fl oz)

    ### Instructions

    1. Fill a highball glass with ice.

    ## Old Fashioned

    Built from spirit, [Turbinado Simple Syrup](cafe.md#turbinado-simple-syrup), and bitters.

    - 60g spirit (2 fl oz)
    - 2-3 dashes bitters

    ### Instructions

    1. Stir until chilled.

    ---

    ## Construction Rules

    **Spirit + ginger beer + lime → [Mule](#mule)**
    """
)


def parsed_cocktails_fixture():
    return menu_source.parse_cocktails(COCKTAILS_FIXTURE)


class TestCocktailParser:
    def test_families_are_extracted_in_file_order(self):
        families = parsed_cocktails_fixture()
        assert [i.name_en for i in families] == ["Mule", "Highball", "Old Fashioned"]

    def test_intro_paragraph_is_not_a_family(self):
        families = parsed_cocktails_fixture()
        names = [i.name_en for i in families]
        assert "Cocktails" not in names
        assert all(
            "modular drink system" not in (i.description or "") for i in families
        )

    def test_description_is_first_paragraph_of_the_family(self):
        mule = parsed_cocktails_fixture()[0]
        assert mule.description == (
            "A flexible highball built from spirit, ginger beer, and lime."
        )

    def test_description_links_are_stripped(self):
        old_fashioned = parsed_cocktails_fixture()[2]
        assert old_fashioned.description == (
            "Built from spirit, Turbinado Simple Syrup, and bitters."
        )

    def test_family_without_description_yields_none(self):
        highball = parsed_cocktails_fixture()[1]
        assert highball.description is None

    def test_instructions_heading_is_not_a_description(self):
        for family in parsed_cocktails_fixture():
            assert family.description != "Instructions"

    def test_construction_rules_is_never_a_family(self):
        names = [i.name_en for i in parsed_cocktails_fixture()]
        assert "Construction Rules" not in names

    def test_families_carry_no_temperature_or_vietnamese_machinery(self):
        for family in parsed_cocktails_fixture():
            assert family.temperatures == []
            assert family.name_vi is None

    def test_new_family_is_picked_up_without_registration(self):
        new_family = textwrap.dedent(
            """
            ## Brand New Template Never Seen Before

            A template added to recipes after the generator was written.

            - 60g something

            ### Instructions

            1. Combine.

            """
        ).lstrip("\n")
        fixture = COCKTAILS_FIXTURE.replace("## Highball", new_family + "## Highball")
        families = menu_source.parse_cocktails(fixture)
        names = [i.name_en for i in families]
        assert "Brand New Template Never Seen Before" in names
        new_item = next(i for i in families if "Brand New" in i.name_en)
        assert new_item.description == (
            "A template added to recipes after the generator was written."
        )


BAR_OVERRIDES = {
    "version": 1,
    "bar": {
        "items": {
            "Mule": {"description": "Ginger beer, fresh lime, optional Angostura."}
        }
    },
}


class TestBarOverrides:
    def test_description_override_replaces_recipes_prose(self):
        items = menu_source.build_bar_items(COCKTAILS_FIXTURE, BAR_OVERRIDES)
        assert items[0].description == "Ginger beer, fresh lime, optional Angostura."

    def test_unoverridden_family_keeps_recipes_prose(self):
        items = menu_source.build_bar_items(COCKTAILS_FIXTURE, BAR_OVERRIDES)
        assert items[2].description == (
            "Built from spirit, Turbinado Simple Syrup, and bitters."
        )

    def test_name_override_applies(self):
        config = {"bar": {"items": {"Mule": {"name": "Moscow Mule"}}}}
        items = menu_source.build_bar_items(COCKTAILS_FIXTURE, config)
        assert items[0].name_en == "Moscow Mule"

    def test_unknown_override_key_fails_loudly(self):
        config = {"bar": {"items": {"Mule": {"temperatures": ["iced"]}}}}
        try:
            menu_source.build_bar_items(COCKTAILS_FIXTURE, config)
        except menu_source.SiteOverridesError as exc:
            assert "temperatures" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")

    def test_override_naming_unknown_family_fails_loudly(self):
        config = {"bar": {"items": {"Margarita": {"description": "not on the recipes"}}}}
        try:
            menu_source.build_bar_items(COCKTAILS_FIXTURE, config)
        except menu_source.SiteOverridesError as exc:
            assert "Margarita" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")

    def test_config_without_bar_object_fails_loudly(self):
        try:
            menu_source.build_bar_items(COCKTAILS_FIXTURE, {})
        except menu_source.SiteOverridesError as exc:
            assert "bar" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")


KITCHEN_README_FIXTURE = textwrap.dedent(
    """
    # My Recipe Collection

    ## Quick References

    ### [Produce Guide](produce.md) - How to pick, ripen, and store produce

    ---

    ## Available Recipes

    ### Appetizers

    - [Charcuterie Nachos](charcuterie_nachos.md) - Salt and vinegar chips under molten Brie
    - [Cured Salmon Sashimi](cured_salmon_sashimi.md) - Lightly cured salmon, sliced thin

    ### Main Dishes

    - [Chicken Wings](chicken_wings.md) - Dry brined roasted wings
    - [Cajun Shrimp Pasta](cajun_shrimp_pasta.md) - Assembly dish: pasta with Cajun sauce:
      - [Lobster Bisque Pasta Sauce](lobster_bisque_pasta_sauce.md) - Rich Cajun sauce
    - [Bacon Over Congee](bacon_over_congee.md)
    - [Ragu](ragu.md) - Vietnamese style ragu

    ### Side Dishes

    - [Roasted Garlic Potatoes](side_dishes.md#roasted-garlic-potatoes)
    - [Oven Roasted Asparagus](side_dishes.md#oven-roasted-asparagus)
    - [Pan Cooked Asparagus](side_dishes.md#pan-cooked-asparagus)

    ### Drinks

    - [Coffee](cafe.md#coffee) - Sweet, milky, shaken

    ### Cocktails

    - [Mule](cocktails.md#mule) - Generic mule template

    ### Sauces & Toppings

    - [Nước Chấm](sauces.md#nước-chấm-nước-mắm-pha) - The foundational Vietnamese fish sauce dip

    ### Desserts

    - [Cookies](cookies.md) - Modular cookie system
    """
)

KITCHEN_FILE_FIXTURES = {
    "charcuterie_nachos.md": (
        "# Charcuterie Nachos\n"
        "\n"
        "Crisp chips are layered with Brie.\n"
        "\n"
        "---\n"
        "\n"
        "## Ingredients\n"
        "\n"
        "- chips\n"
    ),
    "cured_salmon_sashimi.md": (
        "# Cured Salmon Sashimi\n"
        "\n"
        "*Salmon cured, wiped clean, and sliced.*\n"
        "\n"
        "## Ingredients\n"
        "\n"
        "- salmon\n"
    ),
    "chicken_wings.md": (
        "# Chicken Wings\n"
        "\n"
        "Juicy wings with crackling skin.\n"
        "\n"
        "## Ingredients\n"
    ),
    "cajun_shrimp_pasta.md": "# Cajun Shrimp Pasta\n\nAn assembly dish.\n\n## Ingredients\n",
    "steak.md": "# Steak\n\nA ribeye.\n\n## Ingredients\n",
    "bacon_over_congee.md": (
        "# Bacon Over Congee\n"
        "\n"
        "Fish-sauce-glazed bacon over rice congee.\n"
        "\n"
        "## Ingredients\n"
    ),
    "ragu.md": "# Ragu\n\nA deeply savory sauce.\n\n## Ingredients\n",
    "side_dishes.md": (
        "# Vegetables\n"
        "\n"
        "## Potatoes\n"
        "\n"
        "### Roasted Garlic Potatoes\n"
        "\n"
        "#### Ingredients\n"
        "\n"
        "- potatoes\n"
        "\n"
        "## Asparagus\n"
        "\n"
        "### Oven Roasted Asparagus\n"
        "\n"
        "#### Ingredients\n"
        "\n"
        "- asparagus\n"
        "\n"
        "### Pan Cooked Asparagus\n"
        "\n"
        "#### Ingredients\n"
        "\n"
        "- asparagus\n"
    ),
    "sauces.md": (
        "# Sauces & Toppings\n"
        "\n"
        "## Sauces\n"
        "\n"
        "### Nước Chấm (Nước Mắm Pha)\n"
        "\n"
        "#### Ingredients\n"
        "\n"
        "- fish sauce\n"
    ),
    "cookies.md": "# Cookies\n\nThe cookie system.\n\n## Base Dough\n",
}


def kitchen_file_loader(name):
    try:
        return KITCHEN_FILE_FIXTURES[name]
    except KeyError:
        raise KeyError(f"no fixture recipe file {name!r}") from None


KITCHEN_OVERRIDES_FIXTURE = {
    "kitchen": {
        "items": {
            "Chicken Wings": {"name": "Cánh Gà", "nameVi": "Chicken Wings"},
            "Ragu": {"nameVi": "Ra-gu"},
            "Charcuterie Nachos": {
                "description": "Salt and vinegar chips under molten Brie."
            },
        },
        "merges": {
            "Asparagus": {
                "sources": ["Oven Roasted Asparagus", "Pan Cooked Asparagus"],
                "description": "Roasted or pan-cooked, bright and snappy.",
            }
        },
        "sections": {"sot": {"note": "Made in house. Ask for pairings."}},
    }
}


def parsed_kitchen_fixture():
    return menu_source.build_kitchen_menu(
        KITCHEN_README_FIXTURE, kitchen_file_loader, KITCHEN_OVERRIDES_FIXTURE
    )


class TestKitchenIndex:
    def test_groups_become_sections_in_readme_order(self):
        kitchen = parsed_kitchen_fixture()
        assert [s.id for s in kitchen.sections] == [
            "khai-vi",
            "mon-chinh",
            "mon-phu",
            "sot",
            "trang-mieng",
        ]

    def test_drinks_cocktails_and_quick_reference_groups_are_skipped(self):
        kitchen = parsed_kitchen_fixture()
        ids = {s.id for s in kitchen.sections}
        assert {"drinks", "cocktails", "quick-references"}.isdisjoint(ids)
        for section in kitchen.sections:
            names = [i.name_en for i in section.items]
            assert "Coffee" not in names
            assert "Mule" not in names
            assert "Produce Guide" not in names

    def test_bullets_become_entries_with_link_text_names(self):
        kitchen = menu_source.build_kitchen_menu(
            KITCHEN_README_FIXTURE, kitchen_file_loader, {"kitchen": {}}
        )
        mains = kitchen.sections[1]
        assert [i.name_en for i in mains.items] == [
            "Chicken Wings",
            "Cajun Shrimp Pasta",
            "Bacon Over Congee",
            "Ragu",
        ]

    def test_nested_bullets_are_not_entries(self):
        kitchen = parsed_kitchen_fixture()
        names = [i.name_en for s in kitchen.sections for i in s.items]
        assert "Lobster Bisque Pasta Sauce" not in names

    def test_stray_heading_ends_the_current_group(self):
        readme = KITCHEN_README_FIXTURE.replace(
            "- [Cookies](cookies.md) - Modular cookie system",
            "- [Cookies](cookies.md) - Modular cookie system\n\n"
            "#### Variants\n\n- [Orphan Dish](orphan.md) - Never placed",
        )
        kitchen = menu_source.build_kitchen_menu(
            readme, kitchen_file_loader, {"kitchen": {}}
        )
        desserts = kitchen.sections[-1]
        assert [i.name_en for i in desserts.items] == ["Cookies"]

    def test_bullet_separator_variants_and_annotations(self):
        readme = KITCHEN_README_FIXTURE.replace(
            "- [Bacon Over Congee](bacon_over_congee.md)",
            "- [Bacon Over Congee](bacon_over_congee.md) – Fish sauce glazed bacon\n"
            "- [Steak](steak.md) (annotation only)",
        )
        kitchen = menu_source.build_kitchen_menu(
            readme, kitchen_file_loader, {"kitchen": {}}
        )
        mains = kitchen.sections[1]
        by_name = {i.name_en: i for i in mains.items}
        assert by_name["Bacon Over Congee"].description == "Fish sauce glazed bacon"
        # the parenthetical annotation is not a description; the chain falls
        # through to the dish file's intro paragraph
        assert by_name["Steak"].description == "A ribeye."

    def test_unknown_group_fails_loudly(self):
        readme = KITCHEN_README_FIXTURE.replace(
            "### Desserts", "### Smoothies\n\n- [Blended Fruit](blended.md)\n\n### Desserts"
        )
        try:
            menu_source.build_kitchen_menu(
                readme, kitchen_file_loader, KITCHEN_OVERRIDES_FIXTURE
            )
        except menu_source.KitchenIndexError as exc:
            assert "Smoothies" in str(exc)
        else:
            raise AssertionError("expected KitchenIndexError")


class TestDishIntro:
    def test_plain_intro_paragraph_is_extracted(self):
        intro = menu_source.dish_intro(KITCHEN_FILE_FIXTURES["charcuterie_nachos.md"])
        assert intro == "Crisp chips are layered with Brie."

    def test_italic_intro_is_stripped(self):
        intro = menu_source.dish_intro(KITCHEN_FILE_FIXTURES["cured_salmon_sashimi.md"])
        assert intro == "Salmon cured, wiped clean, and sliced."
        assert "*" not in intro

    def test_file_without_intro_yields_none(self):
        assert menu_source.dish_intro("# Title\n\n## Ingredients\n\n- x\n") is None


class TestGitHubSlugs:
    def test_diacritics_survive_the_slug(self):
        assert menu_source.github_slug("Nước Chấm (Nước Mắm Pha)") == (
            "nước-chấm-nước-mắm-pha"
        )

    def test_duplicate_headings_get_suffix_ids(self):
        text = "### Sauce\n\n### Sauce\n\n### Sauce\n"
        ids = menu_source.github_heading_ids(text)
        assert ids == {"sauce", "sauce-1", "sauce-2"}


class TestBuildKitchenMenu:
    def test_merged_item_replaces_its_sources(self):
        kitchen = parsed_kitchen_fixture()
        sides = kitchen.sections[2]
        names = [i.name_en for i in sides.items]
        assert names == ["Roasted Garlic Potatoes", "Asparagus"]
        asparagus = sides.items[1]
        assert asparagus.description == "Roasted or pan-cooked, bright and snappy."

    def test_name_and_namevi_overrides_preserve_lead_and_subtitle(self):
        kitchen = parsed_kitchen_fixture()
        mains = kitchen.sections[1]
        wings = mains.items[0]
        assert wings.name_en == "Cánh Gà"
        assert wings.name_vi == "Chicken Wings"
        ragu = mains.items[3]
        assert ragu.name_en == "Ragu"
        assert ragu.name_vi == "Ra-gu"

    def test_description_chain_one_liner_then_intro(self):
        kitchen = parsed_kitchen_fixture()
        mains = kitchen.sections[1]
        wings = mains.items[0]
        assert wings.description == "Dry brined roasted wings"
        congee = mains.items[2]
        assert congee.description == "Fish-sauce-glazed bacon over rice congee."

    def test_section_note_applies_to_its_section_only(self):
        kitchen = parsed_kitchen_fixture()
        by_id = {s.id: s for s in kitchen.sections}
        assert by_id["sot"].note == "Made in house. Ask for pairings."
        assert by_id["khai-vi"].note is None
        assert by_id["mon-chinh"].note is None

    def test_unknown_item_override_key_fails_loudly(self):
        config = {"kitchen": {"items": {"Ragu": {"temperatures": ["hot"]}}}}
        try:
            menu_source.build_kitchen_menu(
                KITCHEN_README_FIXTURE, kitchen_file_loader, config
            )
        except menu_source.SiteOverridesError as exc:
            assert "temperatures" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")

    def test_stale_override_name_fails_loudly(self):
        config = {"kitchen": {"items": {"Milk Tea": {"description": "gone"}}}}
        try:
            menu_source.build_kitchen_menu(
                KITCHEN_README_FIXTURE, kitchen_file_loader, config
            )
        except menu_source.SiteOverridesError as exc:
            assert "Milk Tea" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")

    def test_merge_with_unknown_source_fails_loudly(self):
        config = {
            "kitchen": {
                "merges": {
                    "Asparagus": {
                        "sources": ["Grilled Asparagus"],
                    }
                }
            }
        }
        try:
            menu_source.build_kitchen_menu(
                KITCHEN_README_FIXTURE, kitchen_file_loader, config
            )
        except menu_source.SiteOverridesError as exc:
            assert "Grilled Asparagus" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")

    def test_merge_key_colliding_with_a_bullet_name_fails_loudly(self):
        config = {
            "kitchen": {
                "merges": {
                    "Ragu": {"sources": ["Oven Roasted Asparagus"]},
                }
            }
        }
        try:
            menu_source.build_kitchen_menu(
                KITCHEN_README_FIXTURE, kitchen_file_loader, config
            )
        except menu_source.SiteOverridesError as exc:
            assert "Ragu" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")

    def test_unknown_section_override_id_fails_loudly(self):
        config = {"kitchen": {"sections": {"soup": {"note": "hot"}}}}
        try:
            menu_source.build_kitchen_menu(
                KITCHEN_README_FIXTURE, kitchen_file_loader, config
            )
        except menu_source.SiteOverridesError as exc:
            assert "soup" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")

    def test_order_list_must_be_a_permutation_of_the_sections_items(self):
        config = {
            "kitchen": {
                "order": {"mon-chinh": ["Ragu", "Chicken Wings", "Ghost Dish"]},
            }
        }
        try:
            menu_source.build_kitchen_menu(
                KITCHEN_README_FIXTURE, kitchen_file_loader, config
            )
        except menu_source.SiteOverridesError as exc:
            assert "Ghost Dish" in str(exc)
        else:
            raise AssertionError("expected SiteOverridesError")

    def test_order_list_reorders_the_section(self):
        config = {
            "kitchen": {
                "order": {"mon-chinh": ["Ragu", "Bacon Over Congee", "Cajun Shrimp Pasta", "Chicken Wings"]},
            }
        }
        kitchen = menu_source.build_kitchen_menu(
            KITCHEN_README_FIXTURE, kitchen_file_loader, config
        )
        mains = kitchen.sections[1]
        assert [i.name_en for i in mains.items] == [
            "Ragu",
            "Bacon Over Congee",
            "Cajun Shrimp Pasta",
            "Chicken Wings",
        ]

    def test_missing_recipe_file_fails_loudly(self):
        readme = KITCHEN_README_FIXTURE.replace(
            "## Desserts", "## Desserts"
        ).replace("[Cookies](cookies.md)", "[Cookies](missing_file.md)")
        try:
            menu_source.build_kitchen_menu(
                readme, kitchen_file_loader, KITCHEN_OVERRIDES_FIXTURE
            )
        except menu_source.KitchenIndexError as exc:
            assert "missing_file.md" in str(exc)
        else:
            raise AssertionError("expected KitchenIndexError")

    def test_missing_anchor_fails_loudly(self):
        readme = KITCHEN_README_FIXTURE.replace(
            "side_dishes.md#roasted-garlic-potatoes", "side_dishes.md#ghost-potatoes"
        )
        try:
            menu_source.build_kitchen_menu(
                readme, kitchen_file_loader, KITCHEN_OVERRIDES_FIXTURE
            )
        except menu_source.KitchenIndexError as exc:
            assert "ghost-potatoes" in str(exc)
        else:
            raise AssertionError("expected KitchenIndexError")


class TestRealRecipesFile:
    def test_real_file_exists(self):
        assert RECIPES_CAFE.is_file(), "sibling recipes checkout missing"

    def test_real_section_minimum_counts(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        counts = {s.id: len(s.items) for s in menu.sections}
        minimums = {
            "ca-phe": 10,
            "tra": 4,
            "mat-cha": 8,
            "giai-khat": 6,
            "kem": 8,
        }
        assert set(counts) == set(minimums)
        for section_id, minimum in minimums.items():
            assert counts[section_id] >= minimum, (section_id, counts[section_id])

    def test_renamed_foams_section_maps_to_kem(self):
        # The recipes renamed the Cold Foams section to Foams and added
        # the hot egg builds; the Kem section must keep mapping either
        # heading and carry the foam builds it drives.
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        kem = menu.by_id("kem")
        names = {item.name_en for item in kem.items}
        assert "Base Foam" in names
        assert any("Egg" in name for name in names), names

    def test_real_section_order_is_tra_before_mat_cha(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        assert [s.id for s in menu.sections] == [
            "ca-phe",
            "tra",
            "mat-cha",
            "giai-khat",
            "kem",
        ]

    def test_real_spot_temperatures(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        temps = menu.temperature_map()
        assert temps["Black Coffee"] == ["hot", "iced"]
        assert temps["Coffee Tonic"] == ["iced"]
        assert temps["Gongfu Tea"] == ["hot"]
        assert temps["Pour Over Coffee"] == ["hot", "iced"]
        assert temps["Milk Tea"] == ["iced"]
        assert temps["Hot Tea"] == ["hot", "iced"]
        assert temps["Coffee Affogato"] == ["hot"]
        assert temps["Cinnamon Oat Shakerato"] == ["iced"]

    def test_real_temperatures_match_menu_json_ground_truth(self):
        import json

        ground_truth = {}
        data = json.loads(MENU_JSON.read_text())
        for item in data["items"]:
            ground_truth[item["name"]] = item["temperatures"]
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        alias = {
            "Coffee Affogato": "Affogato",
            "Strawberry Matcha": "Strawberry Matcha Latte",
            "Lemon Tea": "Fresh Lemon Tea",
            "Strawberry Soda": "Strawberry Fizz",
            "Lime Soda": "Lime Fizz",
            "Milk Limeade": "Condensed Milk Limeade",
            "Hot Tea": "Tea",
            "Pour Over Coffee": "Pour Over",
            "Vietnamese Coffee": "Vietnamese Iced Coffee",
        }
        mismatched = []
        for name_en, temps in menu.temperature_map().items():
            key = alias.get(name_en, name_en)
            if key in ground_truth and ground_truth[key] != temps:
                mismatched.append((name_en, temps, ground_truth[key]))
        assert mismatched == []

    def test_real_vietnamese_names_from_overrides_and_recipes(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        vi = menu.vietnamese_map()
        assert vi["Cinnamon Oat Shakerato"] == "Cà Phê Lắc"
        assert vi["Dirty Matcha"] == "Matcha Cà Phê"
        assert vi["Hot Tea"] == "Trà"
        assert vi["Milk Tea"] == "Trà Sữa"
        assert vi["Gongfu Tea"] == "Trà Công Phu"
        assert vi["Cocoa"] == "Cacao Sữa"
        assert vi["Strawberry Matcha"] == "Matcha Dâu"
        assert vi["Milk Limeade"] == "Chanh Sữa Dầm"

    def test_real_category_blurbs_parsed_for_all_drink_sections(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        expected = {
            "ca-phe": "Sweet, milky, shaken, layered, sparkling, or brewed by the cup: coffee every way.",
            "tra": "Milky tea, fresh lemon tea, or a straight cup brewed by the leaf.",
            "mat-cha": "Whisked matcha as lattes, milk floats, sodas, and tonics, plus the coffee-style undertow and affogato parallels.",
            "giai-khat": "Strawberry and lime sodas, a milk limeade, strawberry milk, and cocoa.",
        }
        assert {s.id: s.note for s in menu.sections if s.note} == expected


class TestRealCocktailsFile:
    def test_real_file_exists(self):
        assert COCKTAILS_MD.is_file(), "cocktails.md missing beside the recipes cafe.md"

    def test_real_family_minimum_count(self):
        families = menu_source.parse_cocktails(COCKTAILS_MD.read_text())
        assert len(families) >= 7, len(families)

    def test_real_spot_family_names(self):
        names = [i.name_en for i in menu_source.parse_cocktails(COCKTAILS_MD.read_text())]
        for name in [
            "Mule",
            "Collins",
            "Highball",
            "Old Fashioned",
            "Sour",
            "Daiquiri",
            "Sidecar",
        ]:
            assert name in names

    def test_real_construction_rules_is_not_a_family(self):
        names = [i.name_en for i in menu_source.parse_cocktails(COCKTAILS_MD.read_text())]
        assert "Construction Rules" not in names

    def test_real_families_have_descriptions(self):
        families = menu_source.parse_cocktails(COCKTAILS_MD.read_text())
        missing = [i.name_en for i in families if not i.description]
        assert missing == []


KITCHEN_README_MD = RECIPES_CAFE.parent / "README.md"
KITCHEN_RECIPES_ROOT = RECIPES_CAFE.parent


def real_kitchen_loader(name):
    return (KITCHEN_RECIPES_ROOT / name).read_text()


def real_kitchen_menu():
    return menu_source.build_kitchen_menu(
        KITCHEN_README_MD.read_text(),
        real_kitchen_loader,
        generate.load_site_overrides(),
    )


class TestRealKitchenFile:
    def test_real_readme_and_dish_files_exist(self):
        assert KITCHEN_README_MD.is_file(), "README.md missing beside recipes cafe.md"
        for name in [
            "charcuterie_nachos.md",
            "steak.md",
            "side_dishes.md",
            "sauces.md",
            "cookies.md",
        ]:
            assert (KITCHEN_RECIPES_ROOT / name).is_file(), name

    def test_real_section_ids_and_order(self):
        kitchen = real_kitchen_menu()
        assert [s.id for s in kitchen.sections] == [
            "khai-vi",
            "mon-chinh",
            "mon-phu",
            "sot",
            "trang-mieng",
        ]

    def test_real_section_minimum_counts(self):
        kitchen = real_kitchen_menu()
        counts = {s.id: len(s.items) for s in kitchen.sections}
        minimums = {
            "khai-vi": 3,
            "mon-chinh": 14,
            "mon-phu": 9,
            "sot": 17,
            "trang-mieng": 1,
        }
        assert set(counts) == set(minimums)
        for section_id, minimum in minimums.items():
            assert counts[section_id] >= minimum, (section_id, counts[section_id])

    def test_real_hand_display_names_are_all_present(self):
        kitchen = real_kitchen_menu()
        names = {i.name_en for s in kitchen.sections for i in s.items}
        for name in [
            "Charcuterie Nachos",
            "Cured Salmon Sashimi",
            "Cured Salmon Bagel",
            "Steak",
            "Lamb Rib Chops",
            "Cánh Gà",
            "Shrimp Scampi",
            "Cajun Shrimp Pasta",
            "Crawfish",
            "Pan Seared Salmon",
            "Salmon Sushi Bake",
            "Carne Asada",
            "Ragu",
            "Beefaroni",
            "Cháo Ba Chỉ",
            "Braised Beef",
            "Smash Burgers",
            "Roasted Garlic Potatoes",
            "Confit Garlic Mashed Potatoes",
            "Mushrooms",
            "Asparagus",
            "Broccolini",
            "Brussels Sprouts",
            "Simple Crisp Slaw",
            "Texas Caviar",
            "Corn Casserole",
            "Nước Chấm",
            "Nước Mắm Gừng",
            "Muối Tiêu Chanh Ớt",
            "Nam Jim Jaew",
            "Chimichurri",
            "Creamy Steak Sauce",
            "Soy-Mirin Brown Butter",
            "Mushroom Pan Sauce",
            "Creamy Garlic Sauce",
            "Lemon Caper Butter",
            "Soy Ginger Sauce",
            "Soy Garlic Sauce",
            "Asian Style Tzatziki",
            "Burger Sauce",
            "Nacho Cheese Sauce",
            "Pico de Gallo",
            "Simple Guacamole",
            "Cookies",
        ]:
            assert name in names, name

    def test_real_merged_variant_names_are_absent(self):
        kitchen = real_kitchen_menu()
        names = {i.name_en for s in kitchen.sections for i in s.items}
        for gone in [
            "Oven Roasted Asparagus",
            "Pan Cooked Asparagus",
            "Oven Roasted Broccolini",
            "Pan Cooked Broccolini",
        ]:
            assert gone not in names, gone

    def test_real_vietnamese_lead_and_subtitle_cases(self):
        kitchen = real_kitchen_menu()
        items = {i.name_en: i for s in kitchen.sections for i in s.items}
        assert items["Cánh Gà"].name_vi == "Chicken Wings"
        assert items["Cháo Ba Chỉ"].name_vi == "Bacon Over Congee"
        assert items["Ragu"].name_vi == "Ra-gu"
        assert items["Steak"].name_vi is None

    def test_real_sauce_note_applies_only_to_sot(self):
        kitchen = real_kitchen_menu()
        by_id = {s.id: s for s in kitchen.sections}
        assert by_id["sot"].note == "Made in house. Ask for pairings."
        for section_id in ("khai-vi", "mon-chinh", "mon-phu", "trang-mieng"):
            assert by_id[section_id].note is None

    def test_real_curated_item_order_holds(self):
        kitchen = real_kitchen_menu()
        by_id = {s.id: s for s in kitchen.sections}
        sot_names = [i.name_en for i in by_id["sot"].items]
        assert sot_names[0] == "Nước Chấm"
        assert sot_names[-2:] == ["Pico de Gallo", "Simple Guacamole"]
        phu_names = [i.name_en for i in by_id["mon-phu"].items]
        assert phu_names.index("Brussels Sprouts") < phu_names.index("Simple Crisp Slaw")
        mains_names = [i.name_en for i in by_id["mon-chinh"].items]
        assert mains_names[:2] == ["Steak", "Lamb Rib Chops"]

    def test_real_curated_descriptions(self):
        kitchen = real_kitchen_menu()
        items = {i.name_en: i for s in kitchen.sections for i in s.items}
        assert items["Nacho Cheese Sauce"].description == "Roux-based cheddar and Jack."
        assert items["Asparagus"].description == "Roasted or pan-cooked, bright and snappy."
        assert items["Cookies"].description == (
            "Baked from the house dough: chocolate chip, M&M, oatmeal, or oatmeal raisin."
        )
        assert items["Steak"].description == (
            "Reverse-seared ribeye basted in garlic brown butter."
        )


PANTRY_FIXTURE = textwrap.dedent(
    """
    # Cafe Pantry Fixture

    Everything to buy for the [Cafe Ong Tho](cafe.md) menu: quantities are
    per batch or per single serving, as marked.

    ## Fresh Dairy and Produce

    The cold case: buy these fresh each week.

    - Heavy whipping cream (pint carton): the backbone of every [cold foam](cafe.md#cold-foams)
    - Whole milk: the undertows and every milk tea
    - Turbinado sugar
      - the coarse golden cane sugar, not white sugar

    ## Make-Ahead Staples

    - [20% Saline Solution](cafe.md#20-saline-solution): 100g batch from 20g salt + 80g water

    Ice is assumed on hand: serving a drink over ice turns it into its iced version.
    """
)


def parsed_pantry_fixture():
    return menu_source.parse_pantry(PANTRY_FIXTURE)


class TestPantryParser:
    def test_sections_parse_in_file_order_with_slug_ids(self):
        pantry = parsed_pantry_fixture()
        assert [s.id for s in pantry.sections] == [
            "fresh-dairy-and-produce",
            "make-ahead-staples",
        ]

    def test_intro_is_parsed_with_links_stripped(self):
        pantry = parsed_pantry_fixture()
        assert pantry.intro == (
            "Everything to buy for the Cafe Ong Tho menu: quantities are "
            "per batch or per single serving, as marked."
        )
        assert "[" not in pantry.intro

    def test_column_zero_bullet_before_the_first_section_fails_loudly(self):
        stray = PANTRY_FIXTURE.replace(
            "## Fresh Dairy and Produce",
            "- Stray bulk flour bag\n\n## Fresh Dairy and Produce",
        )
        try:
            menu_source.parse_pantry(stray)
        except ValueError as exc:
            assert "Stray bulk flour bag" in str(exc)
            assert "##" in str(exc)
        else:
            raise AssertionError(
                "expected ValueError for a pantry bullet before the first section"
            )

    def test_indented_bullet_in_the_intro_zone_is_ignored(self):
        stray = PANTRY_FIXTURE.replace(
            "## Fresh Dairy and Produce",
            "  - a nested note before any section\n\n## Fresh Dairy and Produce",
        )
        pantry = menu_source.parse_pantry(stray)
        assert "a nested note before any section" not in pantry.intro

    def test_annotated_bullet_moves_the_parenthetical_to_the_subtitle(self):
        pantry = parsed_pantry_fixture()
        item = pantry.sections[0].items[0]
        assert item.name_en == "Heavy whipping cream"
        assert item.name_vi == "pint carton"
        assert item.description == "the backbone of every cold foam"

    def test_bullet_without_annotation_keeps_the_subtitle_none(self):
        pantry = parsed_pantry_fixture()
        item = pantry.sections[0].items[1]
        assert item.name_en == "Whole milk"
        assert item.name_vi is None
        assert item.description == "the undertows and every milk tea"

    def test_bullet_without_description_yields_none(self):
        pantry = parsed_pantry_fixture()
        item = pantry.sections[0].items[2]
        assert item.name_en == "Turbinado sugar"
        assert item.description is None

    def test_link_named_bullet_keeps_only_the_display_text(self):
        pantry = parsed_pantry_fixture()
        item = pantry.sections[1].items[0]
        assert item.name_en == "20% Saline Solution"
        assert item.description == "100g batch from 20g salt + 80g water"

    def test_section_note_is_parsed_from_leading_paragraph(self):
        pantry = parsed_pantry_fixture()
        assert pantry.sections[0].note == "The cold case: buy these fresh each week."
        assert pantry.sections[1].note is None

    def test_final_section_trailing_paragraph_becomes_the_outro(self):
        pantry = parsed_pantry_fixture()
        assert pantry.outro == (
            "Ice is assumed on hand: serving a drink over ice turns it into "
            "its iced version."
        )

    def test_indented_nested_bullet_is_not_an_item(self):
        pantry = parsed_pantry_fixture()
        names = [i.name_en for s in pantry.sections for i in s.items]
        assert "the coarse golden cane sugar, not white sugar" not in names
        assert len(pantry.sections[0].items) == 3

    def test_pantry_bullets_carry_no_temperatures(self):
        pantry = parsed_pantry_fixture()
        assert all(
            i.temperatures == [] for s in pantry.sections for i in s.items
        )

    def test_brand_new_section_is_picked_up_with_english_lead_and_no_label(self):
        new_group = textwrap.dedent(
            """
            ## Brand New Group Never Seen Before

            A group added to the pantry file after the generator was written.

            - Something new (one bag)

            """
        ).lstrip("\n")
        fixture = PANTRY_FIXTURE.replace(
            "## Make-Ahead Staples", new_group + "## Make-Ahead Staples"
        )
        pantry = menu_source.parse_pantry(fixture)
        new_section = pantry.sections[1]
        assert new_section.title_lead == "Brand New Group Never Seen Before"
        assert new_section.title_label is None
        assert new_section.items[0].name_en == "Something new"
        assert new_section.items[0].name_vi == "one bag"


class TestRealPantryFile:
    def test_real_file_exists(self):
        assert CAFE_PANTRY_MD.is_file(), "cafe_pantry.md missing beside recipes cafe.md"

    def test_real_sections_and_minimum_counts(self):
        pantry = menu_source.parse_pantry(CAFE_PANTRY_MD.read_text())
        assert [s.id for s in pantry.sections] == [
            "fresh-dairy-and-produce",
            "shelf-stable-pantry",
            "make-ahead-staples",
        ]
        minimums = {
            "fresh-dairy-and-produce": 9,
            "shelf-stable-pantry": 15,
            "make-ahead-staples": 7,
        }
        for section in pantry.sections:
            assert len(section.items) >= minimums[section.id], (
                section.id,
                len(section.items),
            )

    def test_real_curated_leads_with_english_labels(self):
        pantry = menu_source.parse_pantry(CAFE_PANTRY_MD.read_text())
        expected = {
            "fresh-dairy-and-produce": ("Sữa & Trái Cây", "Fresh Dairy and Produce"),
            "shelf-stable-pantry": ("Đồ Khô", "Shelf-Stable Pantry"),
            "make-ahead-staples": ("Làm Sẵn", "Make-Ahead Staples"),
        }
        for section in pantry.sections:
            lead, label = expected[section.id]
            assert section.title_lead == lead, section.id
            assert section.title_label == label, section.id

    def test_real_spot_items_annotation_note_intro_and_outro(self):
        pantry = menu_source.parse_pantry(CAFE_PANTRY_MD.read_text())
        by_name = {
            i.name_en: i for s in pantry.sections for i in s.items
        }
        assert by_name["Heavy whipping cream"].name_vi == "pint carton"
        make_ahead = pantry.sections[2]
        assert "Brew or mix these ahead" in make_ahead.note
        assert "Everything to buy" in pantry.intro
        assert "Ice is assumed on hand" in pantry.outro


class TestRender:
    def test_render_contains_sections_and_items(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        page = generate.render_menu_page(menu)
        for needle in [
            "CAFE ÔNG THỌ",
            ">CÀ PHÊ<",
            ">MÁT-CHA<",
            ">TRÀ<",
            ">GIẢI KHÁT<",
            ">KEM<",
            "Cà Phê Sữa",
            "Matcha Sữa",
            "Trà Sữa",
        ]:
            assert needle in page, f"missing {needle!r}"

    def test_render_places_pills_in_fixed_two_slot_order(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        page = generate.render_menu_page(menu)
        pill_items = sum(len(s.items) for s in menu.sections if s.show_pills)
        temperatures = {
            t: sum(
                1
                for s in menu.sections
                if s.show_pills
                for i in s.items
                if t in i.temperatures
            )
            for t in ("hot", "iced")
        }
        assert page.count('<span class="tag nong">') == temperatures["hot"]
        assert page.count('<span class="tag da">') == temperatures["iced"]
        assert 'class="tag nong"' in page, (
            "at least one real nóng pill must be present"
        )
        assert 'class="tag da"' in page, (
            "at least one real đá pill must be present"
        )
        assert (
            page.count('<span class="tag slot nong" aria-hidden="true">')
            == pill_items - temperatures["hot"]
        ), "an absent nóng pill must leave a reserved placeholder slot"
        assert (
            page.count('<span class="tag slot da" aria-hidden="true">')
            == pill_items - temperatures["iced"]
        ), "an absent đá pill must leave a reserved placeholder slot"
        openers = page.count('<span class="tags"><span class="tag nong">') + page.count(
            '<span class="tags"><span class="tag slot nong"'
        )
        assert openers == pill_items, (
            "every .tags container must open with the nóng slot: fixed order"
        )
        assert ".tag.slot { visibility: hidden; }" in page, (
            "reserved slots must paint nothing"
        )

    def test_price_renders_in_the_item_line_after_the_item_name(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        item = menu.by_id("ca-phe").items[0]
        rendered = generate.render_item(
            item,
            show_pills=True,
            price='<span class="price">'
            '<span class="price-menu">$2.00</span></span>',
        )
        line = re.search(
            r'<div class="item-line">(.*?)</div>', rendered, re.S
        ).group(1)
        assert line.index('class="item-name"') < line.index('class="price"'), (
            "the price must be the name row's right slot, after the item name"
        )
        assert 'class="tags"' not in line, (
            "the pills must never share the name row with the price"
        )

    def test_pills_render_in_the_subtitle_row_after_the_english_name(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        item = next(
            i
            for s in menu.sections
            if s.show_pills
            for i in s.items
            if generate.shows_english_subtitle(i)
        )
        rendered = generate.render_item(item, show_pills=True)
        line = re.search(
            r'<div class="item-line">(.*?)</div>', rendered, re.S
        ).group(1)
        assert 'class="tags"' not in line, "the pills must leave the name row"
        subline = re.search(
            r'<div class="item-subline">(.*?)</div>', rendered, re.S
        ).group(1)
        assert subline.index('class="item-vi"') < subline.index('class="tags"'), (
            "the subtitle row must lead with the English name and right-slot "
            "the pills"
        )

    def test_item_without_subtitle_right_justifies_pills_on_their_own_row(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        item = menu.by_id("ca-phe").items[0]
        item.name_vi = item.name_en
        rendered = generate.render_item(item, show_pills=True)
        assert 'class="item-vi"' not in rendered
        subline = re.search(
            r'<div class="item-subline">(.*?)</div>', rendered, re.S
        )
        assert subline, (
            "an item with pills but no English subtitle must still render "
            "the pill row"
        )
        assert subline.group(1).startswith('<span class="tags">'), (
            "a subtitle-less item's pill row must carry only the pills"
        )

    def test_subtitle_row_exists_when_only_the_subtitle_exists(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        item = next(
            i
            for s in menu.sections
            for i in s.items
            if generate.shows_english_subtitle(i)
        )
        rendered = generate.render_item(item, show_pills=False)
        subline = re.search(
            r'<div class="item-subline">(.*?)</div>', rendered, re.S
        )
        assert subline, "a subtitle with no pills still rides row 2"
        assert 'class="tags"' not in subline.group(1)

    def test_item_with_neither_subtitle_nor_pills_skips_the_subtitle_row(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        item = menu.by_id("ca-phe").items[0]
        item.name_vi = item.name_en
        rendered = generate.render_item(item, show_pills=False)
        assert 'class="item-subline"' not in rendered, (
            "row 2 must not exist when the item has no English subtitle "
            "and no pills"
        )

    def test_empty_price_leaves_the_name_row_right_slot_empty(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        item = menu.by_id("ca-phe").items[0]
        rendered = generate.render_item(item, show_pills=True, price="")
        assert 'class="price"' not in rendered, (
            "an empty price must render no price element: the customer "
            "pair's row 1 right slot stays empty"
        )

    def test_print_page_break_is_tagged_on_mat_cha_in_menu_render_only(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        menu_page = generate.render_menu_page(menu)
        tagged = re.findall(
            r'<section class="own-page">\s*<div class="section-head">\s*'
            r"<h2>([^<]+)</h2>",
            menu_page,
        )
        assert tagged == ["MÁT-CHA"], (
            f"the print page break must sit on exactly the Mát-cha section "
            f"of the menu render; found own-page on {tagged or 'no section'}"
        )
        assert 'class="own-page"' not in generate.render_compact_page(menu), (
            "the compact render must never carry the print page break"
        )
        assert (
            'class="own-page"' not in generate.render_kitchen_page(real_kitchen_menu())
        ), "the kitchen render must never carry the print page break"
        assert (
            'class="own-page"'
            not in generate.render_bar_page(
                menu_source.build_bar_items(
                    COCKTAILS_MD.read_text(), generate.load_site_overrides()
                )
            )
        ), "the bar render must never carry the print page break"
        assert (
            'class="own-page"' not in generate.render_pantry_page(real_pantry_menu())
        ), "the pantry render must never carry the print page break"

    def test_render_has_no_ordering_artifacts(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        page = generate.render_menu_page(menu)
        assert "data-id" not in page
        assert "data-category-id" not in page
        assert "data-temperatures" not in page
        assert "application/json" not in page
        assert "cafe-menu-data" not in page

    def test_render_contains_category_blurbs(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        page = generate.render_menu_page(menu)
        for blurb in [
            "Sweet, milky, shaken, layered, sparkling",
            "Milky tea, fresh lemon tea, or a straight cup",
            "Whisked matcha as lattes, milk floats",
            "Strawberry and lime sodas, a milk limeade",
        ]:
            assert blurb in page, f"missing blurb {blurb!r}"
        assert 'class="section-note"' in page

    def test_render_escapes_item_text(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        menu.by_id("ca-phe").items[0].description = "<script>alert(1)</script>"
        page = generate.render_menu_page(menu)
        assert "<script>alert" not in page


class TestCompactRender:
    def test_compact_shows_item_descriptions(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        page = generate.render_compact_page(menu)
        assert 'class="item-desc"' in page
        assert page.count('class="item-desc"') == sum(
            1 for s in menu.sections for i in s.items if i.description
        )

    def test_compact_shows_black_coffee_description(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        page = generate.render_compact_page(menu)
        black_coffee = next(
            i for i in menu.by_id("ca-phe").items if i.name_en == "Black Coffee"
        )
        assert black_coffee.description is not None
        assert black_coffee.description in page

    def test_compact_keeps_names_pills_and_blurbs(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        page = generate.render_compact_page(menu)
        for needle in [
            "CÀ PHÊ<",
            "TRÀ<",
            "MÁT-CHA<",
            "Trà Sữa",
            "Matcha Dâu",
            "Cà Phê Sữa",
            "class=\"tag nong\"",
            "class=\"tag da\"",
            "class=\"tag slot nong\"",
            "class=\"tag slot da\"",
            ".tag.slot { visibility: hidden; }",
            "class=\"section-note\"",
            "bản rút gọn",
        ]:
            assert needle in page, f"missing {needle!r}"


def print_css_of(page_html: str, name: str) -> str:
    marker = "@media print {"
    assert marker in page_html, f"{name}: carries no @media print block"
    return page_html.split(marker, 1)[1].split("</style>", 1)[0]


def read_workbook_rows() -> dict[str, pricing_source.DrinkCost]:
    return {
        row.name: row for row in pricing_source.read_drink_costs(CAFE_COSTS_XLSX)
    }


def menu_without_drink(name: str) -> generate.Menu:
    """Parse the real menu and drop one drink by its English name."""

    menu = generate.parse_menu(RECIPES_CAFE.read_text())
    return generate.Menu(
        sections=[
            replace(section, items=[i for i in section.items if i.name_en != name])
            for section in menu.sections
        ]
    )


def bac_xiu_menu_name() -> str | None:
    """The live menu's Bạc Xỉu drink name, matched by either curated name.

    The drink's English name is volatile (it has been "Bạc Xỉu" and is
    now "White Coffee"); its Vietnamese name and the curated item's
    names are the stable identity. Returns None when cafe.md defines no
    Bạc Xỉu drink, the world where the join inserts the curated item.
    """

    menu = generate.parse_menu(RECIPES_CAFE.read_text())
    return next(
        (
            item.name_en
            for s in menu.sections
            if s.id != "kem"
            for item in s.items
            if item.name_en in generate.BAC_XIU_ITEM_NAMES
            or item.name_vi in generate.BAC_XIU_ITEM_NAMES
        ),
        None,
    )


def synthetic_costs_for(menu: generate.Menu) -> list[pricing_source.DrinkCost]:
    """One $1/$2 row per non-Kem drink name of the given menu."""

    return [
        pricing_source.DrinkCost(name, 1.0, 2.0)
        for name in {
            item.name_en
            for s in menu.sections
            if s.id != "kem"
            for item in s.items
        }
    ]


def joined_prices() -> tuple[list[generate.Section], dict[str, pricing_source.DrinkCost]]:
    """Parse the real menu and join the real workbook rows, once per call."""
    menu = generate.parse_menu(RECIPES_CAFE.read_text())
    costs = list(read_workbook_rows().values())
    return generate.join_prices(menu, costs)


def price_cluster_text(row: pricing_source.DrinkCost) -> str:
    """Build the contract price-cluster bytes from one workbook row.

    The cluster shape is spelled out here rather than delegated to the
    renderer so the test pins the contract microformat, with the two
    dollar figures derived from the workbook at test time through the
    same half-up formatter as the pages.
    """

    return (
        '<span class="price">'
        f'<span class="price-cost">{generate.format_price(row.cost)}</span>'
        '<span class="price-sep">·</span>'
        f'<span class="price-menu">{generate.format_price(row.suggested)}</span>'
        "</span>"
    )


class TestPricesJoin:
    def test_join_prices_every_menu_drink_exactly_once(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        menu_drinks = {
            item.name_en
            for s in menu.sections
            if s.id != "kem"
            for item in s.items
        }
        sections, costs = joined_prices()
        assert [s.id for s in sections] == ["ca-phe", "tra", "mat-cha", "giai-khat"]
        priced_names = [
            item.name_en for s in sections for item in s.items
        ]
        assert set(priced_names) - menu_drinks <= {"Bạc Xỉu"}, (
            "the priced pages may add no drink beyond the menu's own, "
            "except the curated Bạc Xỉu insertion when cafe.md lacks it"
        )
        assert menu_drinks <= set(priced_names)
        assert len(priced_names) == len(set(priced_names)) == len(costs), (
            "every priced drink must be unique and carry exactly one "
            "workbook row: Bạc Xỉu must render once, priced, whether "
            "cafe.md defines it natively or the join inserts it"
        )
        expected_bac_xiu = bac_xiu_menu_name() or "Bạc Xỉu"
        assert priced_names.count(expected_bac_xiu) == 1
        assert expected_bac_xiu in costs

    def test_join_inserts_bac_xiu_when_the_menu_lacks_it(self):
        native = bac_xiu_menu_name()
        menu = (
            menu_without_drink(native)
            if native
            else generate.parse_menu(RECIPES_CAFE.read_text())
        )
        assert not any(
            item.name_en in generate.BAC_XIU_ITEM_NAMES
            or item.name_vi in generate.BAC_XIU_ITEM_NAMES
            for s in menu.sections
            for item in s.items
        ), "precondition: this menu defines no Bạc Xỉu drink of its own"
        costs = synthetic_costs_for(menu)
        costs.append(
            pricing_source.DrinkCost("Bạc Xỉu (House Latte variant)", 1.0, 2.0)
        )
        sections, costs_by_name = generate.join_prices(menu, costs)
        ca_phe_names = [item.name_en for item in sections[0].items]
        assert ca_phe_names.count(pricing_source.BAC_XIU.name_en) == 1
        assert ca_phe_names.index(pricing_source.BAC_XIU.name_en) == (
            ca_phe_names.index("House Latte") + 1
        )
        assert pricing_source.BAC_XIU.name_en in costs_by_name

    def test_native_bac_xiu_needs_no_anchor(self):
        menu = parsed_fixture()
        menu.by_id("ca-phe").items[0].name_en = "Bạc Xỉu"
        costs = synthetic_costs_for(menu)
        sections, costs_by_name = generate.join_prices(menu, costs)
        priced_names = [
            item.name_en for s in sections for item in s.items
        ]
        assert "House Latte" not in {
            item.name_en for s in menu.sections for item in s.items
        }, "precondition: this synthetic menu carries no anchor drink"
        assert priced_names.count("Bạc Xỉu") == 1
        assert "Bạc Xỉu" in costs_by_name

    def test_join_does_not_mutate_the_parsed_menu(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        before = [item.name_en for s in menu.sections for item in s.items]
        sections, costs = generate.join_prices(
            menu, list(read_workbook_rows().values())
        )
        after = [item.name_en for s in menu.sections for item in s.items]
        assert after == before, (
            "join_prices must build its own sections: the parsed menu feeds "
            "the unpriced pages too, which must stay insertion-free"
        )
        assert sections[0].items is not menu.by_id("ca-phe").items

    def test_join_fails_loudly_listing_both_unmatched_sets(
        self, monkeypatch, tmp_path
    ):
        rows = list(read_workbook_rows().values())
        mutated = [
            pricing_source.DrinkCost("Discontinued Elixir", row.cost, row.suggested)
            if row.name == "Cocoa"
            else row
            for row in rows
        ]
        monkeypatch.setattr(pricing_source, "read_drink_costs", lambda path: mutated)
        with pytest.raises(generate.PriceJoinError) as excinfo:
            generate.build_site(
                recipes_path=RECIPES_CAFE, out_dir=tmp_path / "public", fit_pages=False
            )
        message = str(excinfo.value)
        assert "Discontinued Elixir" in message, message
        assert "Cocoa" in message, message
        assert "workbook rows with no menu drink" in message
        assert "menu drinks with no workbook row" in message

    def test_unknown_workbook_row_fails_loudly_naming_it(
        self, monkeypatch, tmp_path
    ):
        rows = list(read_workbook_rows().values()) + [
            pricing_source.DrinkCost("Extra Workbook Row", 1.0, 2.0)
        ]
        monkeypatch.setattr(pricing_source, "read_drink_costs", lambda path: rows)
        with pytest.raises(generate.PriceJoinError) as excinfo:
            generate.build_site(
                recipes_path=RECIPES_CAFE, out_dir=tmp_path / "public", fit_pages=False
            )
        assert "Extra Workbook Row" in str(excinfo.value)

    def test_two_rows_mapping_to_one_drink_fail_loudly_naming_both(
        self, monkeypatch, tmp_path
    ):
        rows = list(read_workbook_rows().values()) + [
            pricing_source.DrinkCost("Pour Over Coffee", 1.0, 2.0)
        ]
        monkeypatch.setattr(pricing_source, "read_drink_costs", lambda path: rows)
        with pytest.raises(generate.PriceJoinError) as excinfo:
            generate.build_site(
                recipes_path=RECIPES_CAFE, out_dir=tmp_path / "public", fit_pages=False
            )
        message = str(excinfo.value)
        assert "Pour Over" in message
        assert "Pour Over Coffee" in message
        assert "both map to" in message

    def test_renamed_row_prices_the_drink_through_the_alias(self):
        menu = parsed_fixture()
        menu.by_id("ca-phe").items[1].name_en = "Bạc Xỉu"
        assert "Vietnamese Iced Coffee" in {
            item.name_en for s in menu.sections for item in s.items
        }, "precondition: this synthetic menu carries the renamed drink"
        costs = [
            pricing_source.DrinkCost(
                "Vietnamese Coffee" if row.name == "Vietnamese Iced Coffee" else row.name,
                row.cost,
                row.suggested,
            )
            for row in synthetic_costs_for(menu)
        ]
        _, costs_by_name = generate.join_prices(menu, costs)
        assert costs_by_name["Vietnamese Iced Coffee"].name == (
            "Vietnamese Coffee"
        )

    def test_identity_match_wins_when_a_drink_carries_the_row_name(self):
        menu = parsed_fixture()
        menu.by_id("ca-phe").items[0].name_en = "Vietnamese Coffee"
        menu.by_id("ca-phe").items[1].name_en = "Bạc Xỉu"
        costs = synthetic_costs_for(menu)
        _, costs_by_name = generate.join_prices(menu, costs)
        assert costs_by_name["Vietnamese Coffee"].name == "Vietnamese Coffee"

    def test_missing_bac_xiu_anchor_fails_loudly_naming_it(self):
        fixture_drinks = [
            item.name_en
            for s in parsed_fixture().sections
            if s.id != "kem"
            for item in s.items
        ]
        rows = [
            pricing_source.DrinkCost(name, 1.0, 2.0) for name in fixture_drinks
        ]
        rows.append(
            pricing_source.DrinkCost("Bạc Xỉu (House Latte variant)", 1.0, 2.0)
        )
        with pytest.raises(generate.PriceJoinError) as excinfo:
            generate.join_prices(parsed_fixture(), rows)
        assert "House Latte" in str(excinfo.value)

    def test_duplicate_bac_xiu_anchor_fails_loudly_naming_it(self):
        menu = parsed_fixture()
        ca_phe = menu.by_id("ca-phe")
        ca_phe.items[0].name_en = pricing_source.BAC_XIU_ANCHOR
        ca_phe.items[1].name_en = pricing_source.BAC_XIU_ANCHOR
        rows = synthetic_costs_for(menu)
        rows.append(
            pricing_source.DrinkCost("Bạc Xỉu (House Latte variant)", 1.0, 2.0)
        )
        with pytest.raises(generate.PriceJoinError) as excinfo:
            generate.join_prices(menu, rows)
        assert "House Latte" in str(excinfo.value)


class TestPricesRender:
    def test_format_price_rounds_a_half_cent_half_up(self):
        assert generate.format_price(1.005) == "$1.01"
        assert generate.format_price(1.015) == "$1.02"

    def test_both_priced_pages_carry_four_sections_of_priced_items(
        self, no_fit_build
    ):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        expected_items = sum(
            len(s.items) for s in menu.sections if s.id != "kem"
        )
        for name in ("prices.html", "prices/compact.html"):
            page = (no_fit_build / name).read_text()
            assert len(re.findall(r"<section[ >]", page)) == 4, name
            sections = re.findall(r"<section[ >].*?</section>", page, re.S)
            blocks = [
                block for section in sections for block in item_blocks(section)
            ]
            assert len(blocks) == expected_items, name
            for block in blocks:
                assert block.count('<span class="price">') == 1, (
                    f"{name}: every drink item shows exactly one price "
                    f"cluster; got {block[:120]!r}"
                )
            assert ">KEM<" not in page, name

    def test_black_coffee_item_carries_the_workbook_clusters(self, no_fit_build):
        _, costs = joined_prices()
        cluster = price_cluster_text(costs["Black Coffee"])
        for name in ("prices.html", "prices/compact.html"):
            page = (no_fit_build / name).read_text()
            block = item_block_for_name(page, "Black Coffee")
            assert cluster in block, name
            assert block.count('<span class="price">') == 1, name

    def test_bac_xiu_item_rides_its_own_workbook_row(self, no_fit_build):
        _, costs = joined_prices()
        cluster = price_cluster_text(costs[bac_xiu_menu_name() or "Bạc Xỉu"])
        page = (no_fit_build / "prices.html").read_text()
        name_at = page.index(">Cà Phê Bạc Xỉu<")
        block = item_block_for_name(page, "Cà Phê Bạc Xỉu")
        assert cluster in block
        assert block.index('<span class="price">') < block.index("</div>"), (
            "the price cluster must sit inside the item line, after the "
            "item name"
        )
        ca_phe_at = page.index(">CÀ PHÊ<")
        tra_at = page.index(">TRÀ<")
        assert ca_phe_at < name_at < tra_at, (
            "the Bạc Xỉu line must render inside Cà Phê, wherever cafe.md "
            "places the drink"
        )

    def test_pour_over_row_prices_the_pour_over_coffee_line(self, no_fit_build):
        _, costs = joined_prices()
        cluster = price_cluster_text(costs["Pour Over Coffee"])
        page = (no_fit_build / "prices.html").read_text()
        block = item_block_for_name(page, "Cà Phê Pha Tay")
        assert cluster in block

    def test_regular_prices_page_breaks_print_at_mat_cha_only(self):
        sections, costs = joined_prices()
        page = generate.render_prices_page(sections, costs)
        tagged = re.findall(
            r'<section class="own-page">\s*<div class="section-head">\s*'
            r"<h2>([^<]+)</h2>",
            page,
        )
        assert tagged == ["MÁT-CHA"]
        compact = generate.render_prices_compact_page(sections, costs)
        assert 'class="own-page"' not in compact

    def test_priced_pages_render_through_their_own_templates(self, no_fit_build):
        regular = (no_fit_build / "prices.html").read_text()
        compact = (no_fit_build / "prices/compact.html").read_text()
        assert "<title>Cafe Ông Thọ · Giá</title>" in regular
        assert "<title>Cafe Ông Thọ · Giá · In</title>" in compact
        assert 'href="prices.pdf">PDF View</a>' in regular
        assert 'href="compact.pdf">PDF View</a>' in compact
        priced_menu = (no_fit_build / "prices/menu.html").read_text()
        assert "<title>Cafe Ông Thọ · Bảng Giá</title>" in priced_menu
        assert 'href="menu.pdf">PDF View</a>' in priced_menu

    def test_price_sits_in_the_item_line_after_the_item_name(self, no_fit_build):
        for name in ("prices/menu.html", "prices.html", "prices/compact.html"):
            page = (no_fit_build / name).read_text()
            block = item_block_for_name(page, "Black Coffee")
            line = re.search(
                r'<div class="item-line">(.*?)</div>', block, re.S
            ).group(1)
            assert line.index('class="item-name"') < line.index('class="price"'), (
                f"{name}: the price must render inside the name row, after "
                "the item name"
            )
            assert 'class="tags"' not in line, (
                f"{name}: the pills must never share the name row with the "
                "price"
            )
            subline_at = block.index('class="item-subline"')
            desc_at = block.index('class="item-desc"')
            assert block.index("</div>") < subline_at < desc_at, (
                f"{name}: the subtitle row and description must follow the "
                "name row"
            )


class TestPricesMenuPage:
    """The priced customer menu: the drinks-menu layout, selling price only.

    Owner direction 2026-09-10: prices/menu.html carries the drink-menu
    layout with one selling price per non-Kem drink right-justified on the
    drink's name row; no cost figure, separator, or planning legend rides
    the page; the Kem cold-foam builds stay unpriced.
    """

    def test_priced_menu_page_exists_in_the_build(self, no_fit_build):
        assert (no_fit_build / "prices/menu.html").is_file()

    def test_priced_menu_carries_one_selling_price_per_non_kem_drink(
        self, no_fit_build
    ):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        kem_id = menu_source.KEM_SECTION[0]
        expected_total = sum(
            len(s.items) for s in menu.sections if s.id != kem_id
        )
        page = (no_fit_build / "prices/menu.html").read_text()
        counted = page.count('<span class="price">')
        assert counted == expected_total, (
            f"expected exactly one selling price per non-Kem drink "
            f"({expected_total}); counted {counted}"
        )
        sections = re.findall(r"<section[ >].*?</section>", page, re.S)
        assert len(sections) == len(menu.sections), "the Kem section renders too"
        for section in sections:
            blocks = item_blocks(section)
            if ">KEM<" in section:
                assert not any(
                    '<span class="price">' in block for block in blocks
                ), "the Kem section carries no price display"
                continue
            for block in blocks:
                assert block.count('<span class="price">') == 1, block[:120]

    def test_black_coffee_carries_the_workbook_selling_price(self, no_fit_build):
        _, costs = joined_prices()
        price = selling_price_text(costs["Black Coffee"])
        page = (no_fit_build / "prices/menu.html").read_text()
        block = item_block_for_name(page, "Black Coffee")
        assert price in block
        assert block.count('<span class="price">') == 1

    def test_priced_menu_carries_no_cost_figures_separators_or_legend(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        _, costs = joined_prices()
        page = generate.render_prices_menu_page(menu, costs)
        assert "price-cost" not in page
        assert "price-sep" not in page
        assert "giá vốn" not in page
        assert "ước tính để lập kế hoạch" not in page

    def test_priced_menu_breaks_print_at_mat_cha_only(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        _, costs = joined_prices()
        page = generate.render_prices_menu_page(menu, costs)
        tagged = re.findall(
            r'<section class="own-page">\s*<div class="section-head">\s*'
            r"<h2>([^<]+)</h2>",
            page,
        )
        assert tagged == ["MÁT-CHA"]

    def test_priced_menu_marks_itself_current_and_links_its_pdf(
        self, no_fit_build
    ):
        page = (no_fit_build / "prices/menu.html").read_text()
        assert '<a href="#" aria-current="page">Bảng Giá</a>' in page
        assert '<a class="pdf-link" href="menu.pdf">PDF View</a>' in page
        assert '<a href="../menu.html">Thực Đơn</a>' in page
        assert '<a href="prices.html">Giá</a>' in page


class TestPriceWeight:
    """The menu price figure reads at description weight, not heavier.

    Owner direction 2026-09-10: the price keeps its cobalt color and
    1.15em size but carries the same normal (400) weight as the item
    descriptions, on every page that renders a price.
    """

    WEIGHT_RULE = (
        ".price-menu { font-size: 1.15em; font-weight: normal; "
        "color: var(--cobalt); }"
    )

    def test_price_menu_weight_is_normal_on_every_priced_page(
        self, no_fit_build
    ):
        for name in ("prices/menu.html", "prices.html", "prices/compact.html"):
            page = (no_fit_build / name).read_text()
            assert self.WEIGHT_RULE in page, (
                f"{name}: the price figure must carry the normal (400) "
                "weight, matching the item descriptions"
            )
            assert (
                ".price-menu { font-size: 1.15em; font-weight: 600" not in page
            ), f"{name}: the heavy 600 price weight must be gone"

    def test_priced_item_text_is_escaped(self):
        sections, costs = joined_prices()
        sections[0].items[0].description = "<script>alert(1)</script>"
        page = generate.render_prices_page(sections, costs)
        assert "<script>alert" not in page


def selling_price_text(cost: pricing_source.DrinkCost) -> str:
    """Build the single selling-price span bytes from one workbook row.

    The span shape is spelled out here, like price_cluster_text, so the
    test pins the microformat while the dollar figure derives from the
    workbook at test time through the same half-up formatter as the
    prices pair.
    """

    return (
        '<span class="price">'
        f'<span class="price-menu">{generate.format_price(cost.suggested)}</span>'
        "</span>"
    )


def item_blocks(section_html: str) -> list[str]:
    """Split one rendered section into its .item element blocks.

    The lookahead keeps each block from one item's opening div to just
    before the next item (or the section close for the last one), so
    price markup can be counted per item element.
    """

    return re.findall(
        r'<div class="item">.*?(?=<div class="item">|</section>)',
        section_html,
        re.S,
    )


def item_block_for_name(page: str, name_en: str) -> str:
    """Return one built page's .item element block for a drink's English name.

    The English name leads the line when it is the display name and sits
    in the item-vi subtitle otherwise; the block runs from the item's
    opening div to just before the next item or the section close.
    """

    subtitle_at = page.find(f'class="item-vi">{name_en}<')
    anchor_at = (
        subtitle_at if subtitle_at != -1 else page.index(f">{name_en}<")
    )
    block_start = page.rindex('<div class="item">', 0, anchor_at)
    return item_blocks(page[block_start:])[0]


class TestCustomerPairUnpriced:
    """The customer-facing drinks pair renders with no prices at all.

    Owner direction 2026-09-10: the public menu guests see stays clean of
    prices; priced references remain one click away under the Giá family
    (the priced menu carries the selling price alone, the prices pair
    carries cost plus suggested retail). The needles scan the whole built
    page, so no price markup or price style rule can survive anywhere on
    it, the Kem section included.
    """

    def test_customer_pair_pages_carry_no_price_markup_anywhere(
        self, no_fit_build
    ):
        for name in ("menu.html", "index.html", "menu/compact.html"):
            page = (no_fit_build / name).read_text()
            assert '<span class="price' not in page, (
                f"{name}: the customer pair carries no price element"
            )
            assert "price-cost" not in page, name
            assert "price-sep" not in page, name
            assert "price-menu" not in page, name
            assert ".price {" not in page, (
                f"{name}: the price style rules die with the prices"
            )
            assert "giá vốn" not in page, name

    def test_kem_section_renders_its_builds_on_every_customer_page(
        self, no_fit_build
    ):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        leads = sorted(
            {generate.item_lead(item) for item in menu.by_id("kem").items}
        )
        for name in ("menu.html", "index.html", "menu/compact.html"):
            page = (no_fit_build / name).read_text()
            assert ">KEM<" in page, name
            for lead in leads:
                assert lead in page, (name, lead)

    def test_index_stays_byte_identical_to_menu_html(self, no_fit_build):
        assert (no_fit_build / "index.html").read_bytes() == (
            no_fit_build / "menu.html"
        ).read_bytes()


class TestBarRender:
    def _bar_items(self):
        return menu_source.build_bar_items(
            COCKTAILS_MD.read_text(), generate.load_site_overrides()
        )

    def test_render_contains_cocktails_head_and_families(self):
        page = generate.render_bar_page(self._bar_items())
        for needle in [">COCKTAILS<", ">Mule<", ">Old Fashioned<", ">Sidecar<"]:
            assert needle in page, f"missing {needle!r}"

    def test_render_carries_overridden_descriptions(self):
        page = generate.render_bar_page(self._bar_items())
        assert "Ginger beer, fresh lime, optional Angostura." in page

    def test_render_has_no_pills_or_ordering_artifacts(self):
        page = generate.render_bar_page(self._bar_items())
        assert '<span class="tag' not in page
        assert "data-id" not in page
        assert "data-temperatures" not in page
        assert "application/json" not in page

    def test_render_keeps_footer_links(self):
        page = generate.render_bar_page(self._bar_items())
        assert '<a href="menu.html">' in page
        assert '<a href="kitchen.html">' in page
        assert '<a href="pantry.html">' in page

    def test_print_hides_footer_links_paragraph(self):
        page = generate.render_bar_page(self._bar_items())
        print_block = print_css_of(page, "bar.html")
        assert "footer p + p { display: none; }" in print_block, (
            "the bar footer's second paragraph is only cross-page links; "
            "printed sheets have no use for them and the line tips the "
            "browser print onto a blank second sheet"
        )

    def test_render_escapes_item_text(self):
        items = self._bar_items()
        items[0].description = "<script>alert(1)</script>"
        page = generate.render_bar_page(items)
        assert "<script>alert" not in page


class TestKitchenRender:
    def _kitchen_page(self):
        return generate.render_kitchen_page(real_kitchen_menu())

    def test_render_contains_section_heads_and_items(self):
        page = self._kitchen_page()
        for needle in [
            ">KHAI VỊ<",
            ">MÓN CHÍNH<",
            ">MÓN PHỤ<",
            ">SỐT &amp; NƯỚC CHẤM<",
            ">TRÁNG MIỆNG<",
            ">Charcuterie Nachos<",
            ">Cánh Gà<",
            ">Cookies<",
        ]:
            assert needle in page, f"missing {needle!r}"

    def test_render_keeps_subtitle_markup(self):
        page = self._kitchen_page()
        canh_ga = page[page.index(">Cánh Gà<") : page.index(">Cánh Gà<") + 300]
        assert '<p class="item-vi">Chicken Wings</p>' in canh_ga
        ragu = page[page.index(">Ragu<") : page.index(">Ragu<") + 300]
        assert '<p class="item-vi">Ra-gu</p>' in ragu

    def test_render_carries_the_sauce_note_between_sections(self):
        page = self._kitchen_page()
        assert '<p class="section-note">Made in house. Ask for pairings.</p>' in page

    def test_render_has_four_drip_dividers_between_five_sections(self):
        page = self._kitchen_page()
        assert page.count('<div class="drip" aria-hidden="true">') == 4

    def test_render_has_no_pills_or_ordering_artifacts(self):
        page = self._kitchen_page()
        assert '<span class="tag' not in page
        assert "data-id" not in page
        assert "data-temperatures" not in page
        assert "application/json" not in page

    def test_render_keeps_footer_links(self):
        page = self._kitchen_page()
        assert '<a href="menu.html">' in page
        assert '<a href="bar.html">' in page
        assert '<a href="pantry.html">' in page

    def test_render_escapes_item_text(self):
        kitchen = real_kitchen_menu()
        kitchen.sections[0].items[0].description = "<script>alert(1)</script>"
        page = generate.render_kitchen_page(kitchen)
        assert "<script>alert" not in page


def real_pantry_menu():
    return menu_source.parse_pantry(CAFE_PANTRY_MD.read_text())


class TestPantryRender:
    def _pantry_page(self):
        return generate.render_pantry_page(real_pantry_menu())

    def test_render_contains_section_heads_items_intro_and_outro(self):
        page = self._pantry_page()
        for needle in [
            ">SỮA &amp; TRÁI CÂY<",
            ">ĐỒ KHÔ<",
            ">LÀM SẴN<",
            '<span class="section-en">Fresh Dairy and Produce</span>',
            '<span class="section-en">Shelf-Stable Pantry</span>',
            '<span class="section-en">Make-Ahead Staples</span>',
            ">Heavy whipping cream<",
            '<p class="item-vi">pint carton</p>',
            "Everything to buy",
            "Ice is assumed on hand",
            "Brew or mix these ahead of service",
        ]:
            assert needle in page, f"missing {needle!r}"

    def test_render_has_two_drip_dividers_between_three_sections(self):
        page = self._pantry_page()
        assert page.count('<div class="drip" aria-hidden="true">') == 2

    def test_render_has_no_pills_or_ordering_artifacts(self):
        page = self._pantry_page()
        assert '<span class="tag' not in page
        assert "data-id" not in page
        assert "data-temperatures" not in page
        assert "application/json" not in page

    def test_render_keeps_footer_links_and_pdf_view(self):
        page = self._pantry_page()
        for needle in [
            '<a href="menu.html">',
            '<a href="bar.html">',
            '<a href="kitchen.html">',
            '<a class="pdf-link" href="pantry.pdf">PDF View</a>',
        ]:
            assert needle in page, f"missing {needle!r}"

    def test_render_escapes_item_text(self):
        pantry = real_pantry_menu()
        pantry.sections[0].items[0].description = "<script>alert(1)</script>"
        page = generate.render_pantry_page(pantry)
        assert "<script>alert" not in page

    def test_unmapped_section_renders_english_lead_without_label(self):
        pantry = menu_source.PantryMenu(
            intro=None,
            outro=None,
            sections=[
                menu_source.PantrySection(
                    id="brand-new-group",
                    title_lead="Brand New Group",
                    title_label=None,
                    items=[menu_source.Item("Something new", None, None, [])],
                )
            ],
        )
        page = generate.render_pantry_page(pantry)
        assert ">BRAND NEW GROUP<" in page
        assert 'class="section-en"' not in page


class TestPrintFit:
    PAGE = "<html><head><title>x</title></head><body><p>menu</p></body></html>"

    def _counting_counts(self, monkeypatch, fits_at):
        calls = []

        def fake(page_html, base_url=None, papers=generate.PAPER_SIZES):
            root = 16.0
            match = re.search(r"font-size: ([\d.]+)px", page_html)
            if match:
                root = float(match.group(1))
            pages = 2 if root <= fits_at else 3
            calls.append((root, tuple(papers)))
            return {size: pages for size in papers}

        monkeypatch.setattr(generate, "render_page_counts", fake)
        return calls

    def _fake_counts(self, monkeypatch, fits_at):
        self._counting_counts(monkeypatch, fits_at)

    def test_fit_ships_the_given_headroom_steps_below_the_first_fit(self, monkeypatch):
        self._fake_counts(monkeypatch, fits_at=14.0)
        fitted, root = generate.fit_print_root(
            self.PAGE, label="menu.html", headroom_steps=1
        )
        assert root == 13.0
        assert 'font-size: 13px' in fitted
        fitted, root = generate.fit_print_root(
            self.PAGE, label="menu.html", headroom_steps=2
        )
        assert root == 12.0
        assert 'font-size: 12px' in fitted

    def test_fit_injects_margin_root_when_default_fits(self, monkeypatch):
        # The default-fits case still injects: the headroom margin is part of
        # the shipped fit, so the no-JS print keeps the margin even when the
        # page fits at the default root.
        self._fake_counts(monkeypatch, fits_at=16.0)
        fitted, root = generate.fit_print_root(
            self.PAGE, label="menu.html", headroom_steps=1
        )
        assert root == 15.0
        assert f'id="{generate.PRINT_FIT_STYLE_ID}"' in fitted
        assert 'font-size: 15px' in fitted

    def test_fit_reverifies_the_accepted_root_on_both_papers(self, monkeypatch):
        calls = self._counting_counts(monkeypatch, fits_at=14.0)
        generate.fit_print_root(self.PAGE, label="menu.html", headroom_steps=1)
        assert (14.0, (generate.PRINT_FIT_SEARCH_SIZE,)) in calls
        assert (13.0, generate.PAPER_SIZES) in calls

    def test_fit_skips_the_reverify_when_the_clamp_lands_on_the_verified_root(
        self, monkeypatch
    ):
        calls = self._counting_counts(
            monkeypatch, fits_at=generate.PRINT_ROOT_FLOOR
        )
        fitted, root = generate.fit_print_root(
            self.PAGE, label="menu.html", headroom_steps=1
        )
        assert root == generate.PRINT_ROOT_FLOOR
        assert "font-size: 11px" in fitted
        both_paper = [call for call in calls if call[1] == generate.PAPER_SIZES]
        assert both_paper == [(generate.PRINT_ROOT_FLOOR, generate.PAPER_SIZES)], (
            "a clamp landing on the root the walk just verified must not "
            "re-render that candidate: the single both-paper render is the "
            "outer verification itself, a second would be the redundant pair"
        )

    def test_fit_still_reverifies_a_real_margin_root_on_both_papers(
        self, monkeypatch
    ):
        calls = self._counting_counts(monkeypatch, fits_at=14.0)
        fitted, root = generate.fit_print_root(
            self.PAGE, label="menu.html", headroom_steps=1
        )
        assert root == 13.0
        assert "font-size: 13px" in fitted
        both_paper_roots = [
            call[0] for call in calls if call[1] == generate.PAPER_SIZES
        ]
        assert both_paper_roots == [14.0, 13.0], (
            "a real margin root (accepted < root) must still re-render and "
            "re-verify on both papers: one both-paper render at the verified "
            "root and one at the accepted margin root"
        )

    def test_fit_replaces_stale_injection(self, monkeypatch):
        self._fake_counts(monkeypatch, fits_at=14.0)
        pre_injected = generate.inject_print_root(self.PAGE, 12.0)
        fitted, root = generate.fit_print_root(
            pre_injected, label="menu.html", headroom_steps=1
        )
        assert root == 13.0
        assert fitted.count(generate.PRINT_FIT_STYLE_ID) == 1
        assert 'font-size: 13px' in fitted

    def test_fit_fails_loudly_below_floor(self, monkeypatch):
        self._fake_counts(monkeypatch, fits_at=0.0)
        try:
            generate.fit_print_root(self.PAGE, label="menu.html")
        except generate.PrintFitError as exc:
            assert "floor" in str(exc)
        else:
            raise AssertionError("expected PrintFitError")

    def test_fit_clamps_the_margin_at_the_floor_with_a_loud_warning(
        self, monkeypatch, capsys
    ):
        self._fake_counts(monkeypatch, fits_at=generate.PRINT_ROOT_FLOOR)
        fitted, root = generate.fit_print_root(
            self.PAGE, label="menu.html", headroom_steps=1
        )
        assert root == generate.PRINT_ROOT_FLOOR
        assert "font-size: 11px" in fitted
        captured = capsys.readouterr().out
        assert "print fit: WARNING" in captured
        assert "headroom" in captured

    def test_fit_steps_past_a_non_monotonic_reverify_failure(self, monkeypatch):
        def fake(page_html, base_url=None, papers=generate.PAPER_SIZES):
            root = 16.0
            match = re.search(r"font-size: ([\d.]+)px", page_html)
            if match:
                root = float(match.group(1))
            # 13 fits the letter search but pathologically fails the
            # both-paper re-verify; 12 fits everything.
            letter = 2 if root <= 14.0 and root != 13.0 else 3
            counts = {"letter": letter, "a4": 2}
            return {size: counts[size] for size in papers}

        monkeypatch.setattr(generate, "render_page_counts", fake)
        fitted, root = generate.fit_print_root(
            self.PAGE, label="menu.html", headroom_steps=1
        )
        assert root == 12.0
        assert 'font-size: 12px' in fitted

    def test_fit_raises_when_margin_stepping_hits_an_unfittable_floor(
        self, monkeypatch
    ):
        def fake(page_html, base_url=None, papers=generate.PAPER_SIZES):
            root = 16.0
            match = re.search(r"font-size: ([\d.]+)px", page_html)
            if match:
                root = float(match.group(1))
            # Only 14 verifies: every margin-stepped root below it overflows,
            # so the margin walk must run out at the floor instead of looping
            # forever.
            pages = 2 if root == 14.0 else 3
            return {size: pages for size in papers}

        monkeypatch.setattr(generate, "render_page_counts", fake)
        try:
            generate.fit_print_root(
                self.PAGE, label="menu.html", headroom_steps=1
            )
        except generate.PrintFitError as exc:
            assert "floor" in str(exc)
        else:
            raise AssertionError("expected PrintFitError")

    def test_fit_takes_the_compact_pages_calibrated_headroom_steps(self, monkeypatch):
        def fake(page_html, base_url=None, papers=generate.PAPER_SIZES):
            root = 16.0
            match = re.search(r"font-size: ([\d.]+)px", page_html)
            if match:
                root = float(match.group(1))
            pages = 1 if root <= 13.75 else 2
            return {size: pages for size in papers}

        monkeypatch.setattr(generate, "render_page_counts", fake)
        fitted, root = generate.fit_print_root(
            self.PAGE,
            label="menu/compact.html",
            max_pages=generate.COMPACT_PAGE_BUDGET,
            step=generate.COMPACT_PRINT_ROOT_STEP,
            headroom_steps=generate.PRINT_HEADROOM_STEPS["menu/compact.html"],
        )
        assert root == 13.25
        assert "font-size: 13.25px" in fitted

    def test_print_headroom_steps_carry_the_measured_calibration(self):
        assert set(generate.PRINT_HEADROOM_STEPS) == {
            "menu.html",
            "menu/compact.html",
            "prices/menu.html",
            "bar.html",
            "kitchen.html",
            "pantry.html",
            "prices.html",
            "prices/compact.html",
        }
        assert generate.PRINT_HEADROOM_STEPS["menu/compact.html"] == 2
        assert generate.PRINT_HEADROOM_STEPS["prices/compact.html"] == 3
        for name in (
            "menu.html",
            "prices/menu.html",
            "bar.html",
            "kitchen.html",
            "pantry.html",
            "prices.html",
        ):
            assert generate.PRINT_HEADROOM_STEPS[name] == 1, name

    def test_fit_rejects_a_headroom_below_one_step(self):
        for headroom_steps in (0, -1, float("nan")):
            try:
                generate.fit_print_root(
                    self.PAGE, label="x", headroom_steps=headroom_steps
                )
            except ValueError as exc:
                assert "headroom" in str(exc)
            else:
                raise AssertionError(
                    f"expected ValueError for headroom {headroom_steps!r}"
                )

    def test_fit_rejects_non_positive_step(self):
        for step in (0, -1, float("nan")):
            try:
                generate.fit_print_root(self.PAGE, label="x", step=step)
            except ValueError as exc:
                assert "step" in str(exc)
            else:
                raise AssertionError(f"expected ValueError for step {step!r}")

    def test_injection_only_affects_print(self):
        fitted = generate.inject_print_root(self.PAGE, 13.5)
        assert "@media print" in fitted
        assert "13.5px" in fitted


class TestPageBudget:
    def test_built_pages_satisfy_print_budgets(self, tmp_path):
        out = tmp_path / "public"
        generate.build_site(recipes_path=RECIPES_CAFE, out_dir=out)
        for page in ("menu.html", "kitchen.html", "pantry.html"):
            counts = generate.render_page_counts((out / page).read_text())
            for size, count in counts.items():
                assert count <= 2, (page, size, count)
        bar_counts = generate.render_page_counts((out / "bar.html").read_text())
        for size, count in bar_counts.items():
            assert count == 1, ("bar.html", size, count)
        counts = generate.render_page_counts((out / "menu" / "compact.html").read_text())
        for size, count in counts.items():
            assert count == 1, ("menu/compact.html", size, count)
        prices_counts = generate.render_page_counts((out / "prices.html").read_text())
        for size, count in prices_counts.items():
            assert count <= generate.PRICES_PAGE_BUDGET, ("prices.html", size, count)
        counts = generate.render_page_counts((out / "prices" / "compact.html").read_text())
        for size, count in counts.items():
            assert count == generate.PRICES_COMPACT_PAGE_BUDGET, (
                "prices/compact.html",
                size,
                count,
            )
        prices_menu_counts = generate.render_page_counts(
            (out / "prices" / "menu.html").read_text()
        )
        for size, count in prices_menu_counts.items():
            assert count <= generate.PRINT_PAGE_BUDGET, (
                "prices/menu.html",
                size,
                count,
            )

    def test_fit_build_writes_every_print_pdf_artifact(self, tmp_path):
        out = tmp_path / "public"
        generate.build_site(recipes_path=RECIPES_CAFE, out_dir=out)
        for name in generate.PDF_PAGE_BUDGETS:
            pdf = out / name
            assert pdf.is_file(), f"missing print PDF {name}"
            assert pdf.read_bytes().startswith(b"%PDF"), f"not a PDF: {name}"


class TestPrintPdf:
    PAGE = "<html><head><title>x</title></head><body><p>menu</p></body></html>"
    # Flowing paragraphs fragment across pages; a fixed-height box only
    # overflows its single page and clips, so it cannot trip the budget.
    TALL_PAGE = (
        "<html><head><title>x</title></head><body>"
        + "<p>line of menu content</p>" * 400
        + "</body></html>"
    )

    def test_write_print_pdf_renders_a_pdf_under_budget(self, tmp_path):
        target = tmp_path / "menu.pdf"
        count = generate.write_print_pdf(
            self.PAGE, target, label="menu.pdf", max_pages=2
        )
        assert count == 1
        assert target.is_file()
        assert target.read_bytes().startswith(b"%PDF")

    def test_write_print_pdf_fails_loudly_over_budget_without_artifact(self, tmp_path):
        target = tmp_path / "menu.pdf"
        try:
            generate.write_print_pdf(
                self.TALL_PAGE, target, label="menu.pdf", max_pages=1
            )
        except generate.PrintFitError as exc:
            assert "menu.pdf" in str(exc)
            assert "budget" in str(exc)
        else:
            raise AssertionError("expected PrintFitError over the page budget")
        assert not target.exists(), "a budget violation must leave no artifact"

    def test_pdf_page_budgets_mirror_the_print_budgets(self):
        assert generate.PDF_PAGE_BUDGETS == {
            "menu.pdf": generate.PRINT_PAGE_BUDGET,
            "menu/compact.pdf": generate.COMPACT_PAGE_BUDGET,
            "prices/menu.pdf": generate.PRINT_PAGE_BUDGET,
            "bar.pdf": generate.BAR_PAGE_BUDGET,
            "kitchen.pdf": generate.PRINT_PAGE_BUDGET,
            "pantry.pdf": generate.PANTRY_PAGE_BUDGET,
            "prices.pdf": generate.PRICES_PAGE_BUDGET,
            "prices/compact.pdf": generate.PRICES_COMPACT_PAGE_BUDGET,
        }

    def test_verify_script_page_budgets_mirror_the_generator_constants(self):
        import verify_no_js_print

        assert verify_no_js_print.PAGE_BUDGETS == {
            "menu.html": generate.PRINT_PAGE_BUDGET,
            "menu/compact.html": generate.COMPACT_PAGE_BUDGET,
            "prices/menu.html": generate.PRINT_PAGE_BUDGET,
            "bar.html": generate.BAR_PAGE_BUDGET,
            "kitchen.html": generate.PRINT_PAGE_BUDGET,
            "pantry.html": generate.PANTRY_PAGE_BUDGET,
            "prices.html": generate.PRICES_PAGE_BUDGET,
            "prices/compact.html": generate.PRICES_COMPACT_PAGE_BUDGET,
        }

    def test_pdf_only_stylesheet_hides_footer_and_carries_margin_box(self):
        css = generate.PDF_ONLY_STYLESHEET
        assert "footer { display: none; }" in css, (
            "the in-flow footer must be hidden in the PDF or the last page "
            "carries the brand line twice"
        )
        assert "@bottom-center" in css
        assert "CAFE ÔNG THỌ · nhà làm · made in house" in css
        assert "font-weight: 600" in css, (
            "the margin-box brand line must carry weight 600 so it reads "
            "thick on paper, matching the in-flow footer brand line"
        )
        assert "color: #1F3564" in css, (
            "the margin-box brand line must be cobalt, matching the plaque"
        )

    def test_pdf_only_stylesheet_paints_the_margin_box_double_rule(self):
        css = generate.PDF_ONLY_STYLESHEET
        assert "border-top: 2px solid #1F3564" in css, (
            "the @bottom-center margin box must carry the thick cobalt rule "
            "above the brand line on every sheet"
        )
        assert (
            "linear-gradient(to bottom, transparent 2px, #1F3564 2px)" in css
        ), (
            "the thin companion line must be a gradient strip: weasyprint 70 "
            "paints only the first inset box-shadow of a stack, so the "
            "plaque's shadow-ring pairing cannot produce a two-line rule"
        )
        assert "background-size: 100% 3px" in css, (
            "the companion strip must stay 3px tall: 2px transparent gap "
            "over the 1px cobalt line"
        )
        assert "width: 100%" in css, (
            "the margin box must stretch to the full content width so the "
            "rule spans the sheet like the HTML footer's rule spans the card"
        )

    def test_pdf_only_stylesheet_paints_the_page_white(self):
        css = generate.PDF_ONLY_STYLESHEET
        assert "html, body { background: #fff" in css, (
            "the PDFs print on white stock: the page background the HTML "
            "print CSS paints cream must be neutralized to white"
        )
        assert ".card, header { background: #fff" in css, (
            "the card and header plaque surfaces must be white in the PDF "
            "or they survive as cream panels on the white sheet"
        )
        assert "header { box-shadow: inset" in css, (
            "the header plaque's cream inset ring must be recolored or it "
            "survives as a warm band on the white plaque"
        )

    def test_pdf_only_stylesheet_paints_the_plaque_ring(self):
        css = generate.PDF_ONLY_STYLESHEET
        assert css.count("linear-gradient(#1F3564 0 0)") == 4, (
            "the PDF plaque ring must be four gradient strips: weasyprint "
            "70 paints only the first inset box-shadow of a stack, so the "
            "screen shadow ring cannot render on white stock"
        )
        assert (
            "background-position: left 0 top 2px, left 0 bottom 2px, "
            "left 2px top 0, right 2px top 0" in css
        ), (
            "the ring strips must sit at the 5px inset from the border's "
            "outer edge that the plaque vocabulary uses"
        )
        assert "background-size: 100% 1px, 100% 1px, 1px 100%, 1px 100%" in css, (
            "the ring strips must stay 1px thin"
        )

    def test_pdf_only_stylesheet_brands_continuation_sheets(self):
        css = generate.PDF_ONLY_STYLESHEET
        assert css.count("@top-center") == 2, (
            "the band needs the styled @top-center and the :first "
            "suppression, exactly two occurrences"
        )
        assert css.count(f'content: "{generate.BRAND_LINE}"') == 2, (
            "both margin boxes must carry the brand-line value; counting "
            "selectors alone cannot catch a content regressed to empty"
        )
        assert "@page :first" in css and "content: none" in css, (
            "first sheets carry the big plaque; the top band must be "
            "suppressed there or sheet 1 reads the brand twice"
        )
        assert "border-bottom: 1px solid #1F3564" in css, (
            "the band's rule sits below the text, on the content side of "
            "the top margin band, mirroring the footer band's content-side "
            "rule"
        )
        assert "font-size: 0.7rem" in css, (
            "the band text must be the small size: the 0.6cm top margin "
            "fits the band only well under the footer band's 0.88rem"
        )


class TestPrintPdfLink:
    """Needles pinning the screen-only PDF View link on the published pages.

    The page-backed needles share one build through the module-scoped
    `no_fit_build` fixture.
    """

    def test_every_published_page_links_its_print_pdf(self, no_fit_build):
        out = no_fit_build
        expected = {
            "index.html": "menu.pdf",
            "menu.html": "menu.pdf",
            "menu/compact.html": "compact.pdf",
            "prices/menu.html": "menu.pdf",
            "kitchen.html": "kitchen.pdf",
            "bar.html": "bar.pdf",
            "pantry.html": "pantry.pdf",
            "prices.html": "prices.pdf",
            "prices/compact.html": "compact.pdf",
        }
        for name, pdf in expected.items():
            page = (out / name).read_text()
            assert f'<a class="pdf-link" href="{pdf}">PDF View</a>' in page, name

    def test_print_pdf_link_is_hidden_from_the_browser_print_css(self, no_fit_build):
        out = no_fit_build
        for name in PUBLISHED_PAGES:
            page = (out / name).read_text()
            print_css = print_css_of(page, name)
            assert ".pdf-link { display: none; }" in print_css, (
                f"{name}: the PDF View link is not hidden in print; printing "
                "the HTML page must never show the link"
            )

    def test_pdf_only_footer_stays_out_of_the_published_pages(self, no_fit_build):
        out = no_fit_build
        for name in PUBLISHED_PAGES:
            page = (out / name).read_text()
            assert "@bottom-center" not in page, name
            assert "@top-center" not in page, (
                f"{name}: the continuation-sheet band belongs to the PDF "
                "stylesheet only; browsers cannot render margin boxes"
            )
            assert "footer { display: none" not in page, name


class TestBuildSite:
    def test_build_site_writes_full_artifact(self, no_fit_build):
        out = no_fit_build
        expected = [
            "index.html",
            "menu.html",
            "menu/compact.html",
            "prices/menu.html",
            "kitchen.html",
            "bar.html",
            "pantry.html",
            "prices.html",
            "prices/compact.html",
        ]
        for name in expected:
            assert (out / name).is_file(), f"missing {name}"
        assert (out / "index.html").read_text() == (out / "menu.html").read_text()
        for page in ("kitchen.html", "bar.html", "pantry.html"):
            assert "CAFE ÔNG THỌ" in (out / page).read_text()

    def test_homepage_is_the_full_menu(self, no_fit_build):
        out = no_fit_build
        homepage = (out / "index.html").read_text()
        assert ">CÀ PHÊ<" in homepage
        assert ">GIẢI KHÁT<" in homepage
        assert 'class="tag nong"' in homepage

    def test_no_fit_pages_build_writes_no_print_pdfs(self, no_fit_build):
        out = no_fit_build
        assert not list(out.rglob("*.pdf")), (
            "--no-fit-pages must stay the fast artifact path: the print PDFs "
            "belong to the fit pass, whose fitted roots are the only state "
            "the PDF page-budget gate is meaningful at"
        )

    def test_build_site_passes_each_page_its_calibrated_headroom(
        self, monkeypatch, tmp_path
    ):
        captured = {}

        def fake_fit(page_html, **kwargs):
            captured[kwargs["label"]] = kwargs["headroom_steps"]
            return generate.inject_print_root(page_html, 12.0), 12.0

        def fake_pdf(*args, **kwargs):
            pass

        monkeypatch.setattr(generate, "fit_print_root", fake_fit)
        monkeypatch.setattr(generate, "write_print_pdf", fake_pdf)
        generate.build_site(
            recipes_path=RECIPES_CAFE, out_dir=tmp_path / "public", fit_pages=True
        )
        assert captured == generate.PRINT_HEADROOM_STEPS


PUBLISHED_PAGES = (
    "index.html",
    "menu.html",
    "menu/compact.html",
    "prices/menu.html",
    "kitchen.html",
    "bar.html",
    "pantry.html",
    "prices.html",
    "prices/compact.html",
)

# The companion strip is 3px tall inside the padding box; the print
# padding-bottom must be at least this deep at every fitted root down to
# the floor, or the strip underpaints the content box.
STRIP_CLEARANCE_PX = 3
# A whole .section-head rule body, in print blocks and screen stylesheets.
SECTION_HEAD_RULE_RE = r"\.section-head \{[^}]*\}"


@pytest.fixture(scope="module")
def no_fit_build(tmp_path_factory) -> Path:
    """Build the site once on the --no-fit-pages fast path.

    Returns the public output directory; the page-backed needle classes
    read it read-only, so one build serves every test in the module.
    """
    out = tmp_path_factory.mktemp("no-fit-build") / "public"
    generate.build_site(recipes_path=RECIPES_CAFE, out_dir=out, fit_pages=False)
    return out


@pytest.fixture(scope="module")
def shared_print_pages(no_fit_build) -> dict[str, str]:
    """Return each published page's text from the one shared module build."""
    return {name: (no_fit_build / name).read_text() for name in PUBLISHED_PAGES}


class TestSharedPrintCss:
    """Needles pinning the shared print CSS shape injected by read_template.

    These guard the SITE-9 invariants directly: the shared rules verbatim on
    every built page, no fixed-position print CSS, and one common @page rule.
    A failure here names the broken invariant, instead of surfacing late as
    a print-budget overflow.

    The page-backed needles share one build through the module-scoped
    `shared_print_pages` fixture.
    """

    # The @page rule is injected above the @media print block: it is a
    # stylesheet-level rule and print-only by CSS definition (@page cannot
    # nest in @media screen), so its exactly-once count stays whole-page.
    # Every other shared rule lives inside the print block and is counted
    # there, so a future screen-media copy of a rule's text cannot trip
    # this needle.
    WHOLE_PAGE_COUNTED_RULES = frozenset({"page"})

    def _count_shared_rule(self, page_html: str, name: str, key: str, css: str) -> int:
        if key in self.WHOLE_PAGE_COUNTED_RULES:
            return page_html.count(css)
        return print_css_of(page_html, name).count(css)

    def test_every_built_page_carries_each_shared_print_rule(self, shared_print_pages):
        for name, page in shared_print_pages.items():
            for key, css in generate.SHARED_PRINT_RULES.items():
                count = self._count_shared_rule(page, name, key, css)
                assert count == 1, (
                    f"{name}: shared print rule {key!r} appears {count} times; "
                    "each shared rule must appear exactly once per page, or a "
                    "duplicated copy doubles the rule's effect (counted within "
                    "the page's print block; the @page rule is counted across "
                    "the whole page)"
                )

    def test_exactly_once_needle_counts_a_duplicated_shared_rule_in_the_print_block(
        self,
    ):
        rule = generate.SHARED_PRINT_RULES["keep"]
        page_html = (
            "<html><head><style>@media print {\n"
            f"{rule}\n{rule}\n"
            "}</style></head><body></body></html>"
        )
        count = self._count_shared_rule(page_html, "unit.html", "keep", rule)
        assert count == 2, (
            "expected the exactly-once needle to count a shared rule "
            f"duplicated inside the print block twice, counted {count}"
        )

    def test_every_built_page_keeps_section_head_monolithic_in_print(
        self, shared_print_pages
    ):
        for name, page in shared_print_pages.items():
            print_css = print_css_of(page, name)
            assert ".section-head { overflow: hidden; break-after: avoid; }" in print_css, (
                f"{name}: .section-head is not monolithic in print; without "
                "overflow: hidden Blink paints a pushed head's h2 glyphs as "
                "ghost ink past the A4 page-1 content edge into the bottom "
                "margin band"
            )

    def test_no_built_page_declares_fixed_position_print_css(self, shared_print_pages):
        for name, page in shared_print_pages.items():
            print_css = print_css_of(page, name)
            assert "position: fixed" not in print_css, (
                f"{name}: print CSS contains position: fixed; printed headers "
                "and footers must stay in the page flow"
            )

    def test_every_built_page_declares_the_same_page_rule(self, shared_print_pages):
        by_rules: dict[tuple[str, ...], list[str]] = {}
        for name, page in shared_print_pages.items():
            rules = re.findall(r"@page \{[^}]*\}", page)
            assert rules, f"{name}: declares no @page rule"
            by_rules.setdefault(tuple(rules), []).append(name)
        assert len(by_rules) == 1, f"pages declare divergent @page rules: {by_rules}"

    def test_inject_shared_print_css_substitutes_every_defined_rule(self):
        template = "\n".join(
            f"/*SHARED_PRINT:{key}*/" for key in generate.SHARED_PRINT_RULES
        )
        injected = generate.inject_shared_print_css(
            template, template_name="unit.html"
        )
        for key, css in generate.SHARED_PRINT_RULES.items():
            assert css in injected, f"shared print rule {key!r} not substituted"
        assert "SHARED_PRINT:" not in injected

    def test_unresolved_shared_print_marker_fails_loudly(self):
        template = "<style>\n  /*SHARED_PRINT:headder*/\n</style>"
        try:
            generate.inject_shared_print_css(template, template_name="menu.html")
        except RuntimeError as exc:
            assert "headder" in str(exc)
            assert "menu.html" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for an unresolved marker")

    def test_unresolved_shared_print_marker_with_asterisk_in_key_fails_loudly(self):
        template = "<style>\n  /*SHARED_PRINT:head*er*/\n</style>"
        try:
            generate.inject_shared_print_css(template, template_name="menu.html")
        except RuntimeError as exc:
            assert "head*er" in str(exc)
            assert "menu.html" in str(exc)
        else:
            raise AssertionError(
                "expected RuntimeError for a marker whose key contains an asterisk"
            )

    def test_unterminated_marker_context_is_bounded_to_the_limit_or_newline(self):
        limit = generate.UNTERMINATED_MARKER_CONTEXT_LIMIT
        prefix = "/*SHARED_PRINT:"

        def context_of(template: str) -> str:
            try:
                generate.inject_shared_print_css(template, template_name="menu.html")
            except RuntimeError as exc:
                match = re.search(r"marker (.*); markers must", str(exc), re.S)
                assert match, f"unexpected error message shape: {exc}"
                return ast.literal_eval(match.group(1))
            raise AssertionError("expected RuntimeError for an unresolved marker")

        unbounded = prefix + "x" * (limit * 3)
        bounded = context_of(f"<style>\n  {unbounded}\n</style>")
        assert len(bounded) <= limit, (
            f"the unterminated marker context ran {len(bounded)} chars, over "
            f"the {limit}-char bound: one typo must not flood the build log"
        )
        filler = max(limit - len(prefix) - 1, 1)
        before_newline = prefix + "y" * filler
        at_newline = context_of(f"<style>\n  {before_newline}\n  tail\n</style>")
        assert at_newline == before_newline, (
            "a newline inside the limit must end the context at the newline"
        )
        terminated = prefix + "z" * 150 + "*/"
        full = context_of(f"<style>\n  {terminated}\n</style>")
        assert full == terminated, (
            "a terminated marker keeps its full text as the error context"
        )


class TestSharedScreenCss:
    """Needles pinning the shared screen CSS injected by read_template.

    Mirrors TestSharedPrintCss for the screen vocabulary: the companion
    strips, the footer brand rule, the item text treatment, and the engine
    note are one copy in generate.py, substituted at /*SHARED_SCREEN:*/
    markers on every built page. Screen rules cascade into print, so the
    exactly-once counts are whole-page.
    """

    def test_every_built_page_carries_each_shared_screen_rule(
        self, shared_print_pages
    ):
        for name, page in shared_print_pages.items():
            for key, css in generate.SHARED_SCREEN_RULES.items():
                count = page.count(css)
                assert count == 1, (
                    f"{name}: shared screen rule {key!r} appears {count} "
                    "times; each shared screen rule must appear exactly once "
                    "per page, or a duplicated copy doubles the rule's effect"
                )

    def test_unresolved_shared_screen_marker_fails_loudly(self):
        template = "<style>\n  /*SHARED_SCREEN:headder*/\n</style>"
        try:
            generate.inject_shared_print_css(template, template_name="menu.html")
        except RuntimeError as exc:
            assert "headder" in str(exc)
            assert "menu.html" in str(exc)
        else:
            raise AssertionError(
                "expected RuntimeError for an unresolved SHARED_SCREEN marker"
            )

    def test_item_text_screen_rule_keeps_descriptions_at_normal_weight(
        self, shared_print_pages
    ):
        for name, page in shared_print_pages.items():
            assert ".item-vi { font-weight: 500; }" in page, (
                f"{name}: the item-vi subtitle must keep the 500 weight"
            )
            assert ".item-vi, .item-desc { font-weight: 500; }" not in page, (
                f"{name}: descriptions must not ride the 500-weight selector"
            )
            assert ".item-desc, .section-note { color: var(--ink); }" in page, (
                f"{name}: the description ink color treatment must stay"
            )

    def test_item_text_screen_rule_indents_descriptions_as_a_whole_block(
        self, shared_print_pages
    ):
        for name, page in shared_print_pages.items():
            assert ".item-desc { padding-left: 2ch; }" in page, (
                f"{name}: descriptions must carry the shared whole-block 2ch "
                "indent (the CSS reading of the owner's two-space indent)"
            )


class TestDrinksPrintItemGap:
    """Needles pinning SITE-42's widened print gutter on the drinks family.

    The five drinks-menu templates (six built pages, counting the index
    copy) widen their print-block `.items` column-gap one visible step
    (1.4 to 1.8rem on the two-column pages, 1.1 to 1.5rem on the compact
    twins) for legible printed columns. Bar, kitchen, and pantry sit
    outside the owner's request and keep their gaps, and every screen gap
    stays put: the widening is a print-path change only.
    """

    WIDENED_PRINT_GAPS = {
        "index.html": "1.8rem",
        "menu.html": "1.8rem",
        "menu/compact.html": "1.5rem",
        "prices.html": "1.8rem",
        "prices/compact.html": "1.5rem",
        "prices/menu.html": "1.8rem",
    }

    UNTOUCHED_PRINT_GAPS = {
        "bar.html": "1.6rem",
        "kitchen.html": "1.2rem",
        "pantry.html": "1.2rem",
    }

    SCREEN_GAPS = {
        "index.html": "2.5rem",
        "menu.html": "2.5rem",
        "menu/compact.html": "2rem",
        "prices.html": "2.5rem",
        "prices/compact.html": "2rem",
        "prices/menu.html": "2.5rem",
    }

    def _print_item_gap_of(self, page_html: str, name: str) -> str:
        match = re.search(
            r"\.items \{ column-gap: ([0-9.]+)rem", print_css_of(page_html, name)
        )
        assert match, f"{name}: the print block declares no .items column-gap"
        return f"{match.group(1)}rem"

    def test_drinks_pages_carry_the_widened_print_item_gap(self, shared_print_pages):
        for name, expected in self.WIDENED_PRINT_GAPS.items():
            gap = self._print_item_gap_of(shared_print_pages[name], name)
            assert gap == expected, (
                f"{name}: print .items column-gap is {gap}, expected the "
                f"widened {expected}"
            )

    def test_pages_outside_the_drinks_family_keep_their_print_item_gap(
        self, shared_print_pages
    ):
        for name, expected in self.UNTOUCHED_PRINT_GAPS.items():
            gap = self._print_item_gap_of(shared_print_pages[name], name)
            assert gap == expected, (
                f"{name}: print .items column-gap is {gap}; the widening "
                f"covers the drinks family only, expected {expected}"
            )

    def test_drinks_pages_keep_their_screen_item_gap(self, shared_print_pages):
        for name, expected in self.SCREEN_GAPS.items():
            screen_css = shared_print_pages[name].split("@media print {", 1)[0]
            pattern = rf"\.items \{{[^}}]*column-gap: {re.escape(expected)}"
            assert re.search(pattern, screen_css), (
                f"{name}: the screen .items column-gap {expected} must stay; "
                "the SITE-42 widening is print-only"
            )


class TestItemRowAnatomy:
    """Needles pinning SITE-46's two-row item anatomy on the drinks family.

    Row 1 (the .item-line) right-justifies the price with margin-left: auto
    and keeps white-space: nowrap so the figure cannot break under the
    name; row 2 (the .item-subline) is a full-width flex row leading with
    the English subtitle and right-justifying the pills through the
    established margin-left: auto vocabulary, so the cross-item pill
    column alignment and the reserved-slot mechanism carry over exactly.
    The screen rules cascade into print, so one copy carries both paths.
    """

    DRINKS_PAGES = (
        "index.html",
        "menu.html",
        "menu/compact.html",
        "prices.html",
        "prices/compact.html",
        "prices/menu.html",
    )

    PRICED_PAGES = ("prices.html", "prices/compact.html", "prices/menu.html")

    def test_every_drinks_page_rides_the_subtitle_row(self, no_fit_build):
        for name in self.DRINKS_PAGES:
            page = (no_fit_build / name).read_text()
            sublines = re.findall(
                r'<div class="item-subline">.*?</div>', page, re.S
            )
            assert sublines, f"{name}: no subtitle rows rendered"
            tags_total = page.count('<span class="tags">')
            assert tags_total, f"{name}: no pills rendered"
            assert sum(s.count('<span class="tags">') for s in sublines) == tags_total, (
                f"{name}: every .tags container must ride the subtitle row"
            )
            vi_total = page.count('class="item-vi"')
            assert vi_total, f"{name}: no English subtitles rendered"
            assert (
                sum(s.count('class="item-vi"') for s in sublines) == vi_total
            ), f"{name}: every English subtitle must ride the subtitle row"

    def test_name_row_right_justifies_the_price_without_wrapping(
        self, no_fit_build
    ):
        for name in self.PRICED_PAGES:
            page = (no_fit_build / name).read_text()
            rule = re.search(r"\.price \{[^}]*\}", page)
            assert rule, f"{name}: no .price rule"
            assert "margin-left: auto;" in rule.group(0), (
                f"{name}: the price must right-justify on the name row via "
                "margin-left: auto"
            )
            assert "white-space: nowrap;" in rule.group(0), (
                f"{name}: the price must carry white-space: nowrap so it "
                "cannot break under the item name"
            )

    def test_subtitle_row_is_a_flex_row_right_justifying_the_pills(
        self, no_fit_build
    ):
        for name in self.DRINKS_PAGES:
            page = (no_fit_build / name).read_text()
            subline_rule = re.search(r"\.item-subline \{[^}]*\}", page)
            assert subline_rule, f"{name}: no .item-subline rule"
            assert "display: flex;" in subline_rule.group(0), (
                f"{name}: the subtitle row must be a full-width flex row"
            )
            tags_rule = re.search(r"\.tags \{[^}]*\}", page)
            assert tags_rule, f"{name}: no .tags rule"
            assert "margin-left: auto;" in tags_rule.group(0), (
                f"{name}: the pills must right-justify on the subtitle row "
                "via the margin-left: auto vocabulary"
            )


class TestPlaqueDoubleRule:
    """Needles pinning the plaque-echo double rule on footers and section heads.

    SITE-38: a thick cobalt line paired with a thin cobalt companion rides
    every footer band and every section head, on all four pages, in screen
    view, browser print, and the PDF margin band. The companion line is a
    no-repeat 3px gradient strip inside the padding box because weasyprint
    70 paints only the first inset box-shadow of a stack, so the plaque's
    shadow-ring pairing cannot carry a two-line rule into the PDFs; browsers
    render the same strip identically, and the transparent gap shows the
    surface behind it, so the white PDF stock needs no recolor override.
    """

    SECTION_HEAD_GEOMETRY = (
        "background-image: linear-gradient(to top, transparent 2px, var(--cobalt) 2px);\n"
        "    background-position: left bottom;\n"
        "    background-size: 100% 3px;\n"
        "    background-repeat: no-repeat;"
    )
    FOOTER_GEOMETRY = (
        "background-image: linear-gradient(to bottom, transparent 2px, var(--cobalt) 2px);\n"
        "    background-position: left top;\n"
        "    background-size: 100% 3px;\n"
        "    background-repeat: no-repeat;"
    )

    def test_every_page_keeps_the_companion_strip_geometry(self, no_fit_build):
        for name in PUBLISHED_PAGES:
            page = (no_fit_build / name).read_text()
            assert self.SECTION_HEAD_GEOMETRY in page, (
                f"{name}: the section-head companion strip must be a 3px "
                "no-repeat strip anchored above the border: 2px gap, 1px line"
            )
            assert self.FOOTER_GEOMETRY in page, (
                f"{name}: the footer companion strip must be a 3px no-repeat "
                "strip anchored below the border: 2px gap, 1px line"
            )

    def test_every_page_brands_the_footer_line_cobalt_600(self, no_fit_build):
        for name in PUBLISHED_PAGES:
            page = (no_fit_build / name).read_text()
            assert 'class="footer-brand"' in page, (
                f"{name}: the footer brand line is untagged; the weight and "
                "color treatment needs its hook"
            )
            assert (
                ".footer-brand { color: var(--cobalt); font-weight: 600; }" in page
            ), f"{name}: the footer brand line must render cobalt at weight 600"

    def test_print_keeps_the_companion_strips_through_background_stripping(
        self, shared_print_pages
    ):
        for name, page in shared_print_pages.items():
            print_css = print_css_of(page, name)
            assert ".seal, .tag, .section-head, footer {" in print_css, (
                f"{name}: print's print-color-adjust: exact rule must cover "
                ".section-head and footer or a browser's default background "
                "stripping drops the gradient companion lines from prints"
            )

    def test_print_section_head_padding_clears_the_companion_strip(
        self, shared_print_pages
    ):
        for name, page in shared_print_pages.items():
            print_rules = re.findall(
                SECTION_HEAD_RULE_RE, print_css_of(page, name)
            )
            declared = [rule for rule in print_rules if "padding-bottom:" in rule]
            if declared:
                source = declared[-1]
            else:
                screen_css = page.split("@media print {", 1)[0]
                screen_declared = [
                    rule
                    for rule in re.findall(SECTION_HEAD_RULE_RE, screen_css)
                    if "padding-bottom:" in rule
                ]
                assert screen_declared, (
                    f"{name}: no .section-head padding-bottom in the print "
                    "block or the screen stylesheet; the companion strip "
                    "clearance has no guard"
                )
                source = screen_declared[-1]
            padding = re.search(r"padding-bottom: ([\d.]+)(px|rem)", source)
            assert padding is not None, (
                f"{name}: no .section-head padding-bottom guards the strip "
                "clearance"
            )
            value = float(padding[1])
            clearance = (
                value if padding[2] == "px" else value * generate.PRINT_ROOT_FLOOR
            )
            assert clearance >= STRIP_CLEARANCE_PX, (
                f"{name}: print .section-head padding-bottom {padding[0]} "
                f"underpaints the content box at the "
                f"{generate.PRINT_ROOT_FLOOR:g}px print floor; the 3px "
                f"companion strip needs {STRIP_CLEARANCE_PX}px of clearance"
            )


class TestPantryNavLinks:
    def test_every_published_page_links_the_pantry_page(self, no_fit_build):
        # The pantry page carries no self-link; its own footer links are
        # pinned by TestPantryRender.
        for name in PUBLISHED_PAGES:
            if name == "pantry.html":
                continue
            page = (no_fit_build / name).read_text()
            if name in ("menu/compact.html", "prices/compact.html", "prices/menu.html"):
                assert '<a href="../pantry.html">Đi Chợ</a>' in page, name
            else:
                assert 'href="pantry.html"' in page, name


class TestPricesNavLinks:
    def test_every_existing_page_links_the_cost_reference_pages(self, no_fit_build):
        # The cost-reference pages carry their own navs (the Giá entry is
        # aria-current there); every pre-existing page links them plainly.
        for name in ("index.html", "menu.html", "kitchen.html", "bar.html", "pantry.html"):
            page = (no_fit_build / name).read_text()
            assert '<a href="prices.html">Giá</a>' in page, name
        compact = (no_fit_build / "menu/compact.html").read_text()
        assert '<a href="../prices/compact.html">Giá</a>' in compact

    def test_every_page_links_the_priced_menu(self, no_fit_build):
        # The priced menu is linked from every published page under one
        # consistent label: the nav-carrying pages link it in their navs
        # and the bar, kitchen, and pantry pages (which carry no footer
        # nav element) link it in their footer paragraphs after Giá. The
        # priced menu's own nav marks it current.
        for name in (
            "index.html",
            "menu.html",
            "prices.html",
            "bar.html",
            "kitchen.html",
            "pantry.html",
        ):
            page = (no_fit_build / name).read_text()
            assert '<a href="prices/menu.html">Bảng Giá</a>' in page, name
        assert (
            '<a href="../prices/menu.html">Bảng Giá</a>'
            in (no_fit_build / "menu/compact.html").read_text()
        )
        # prices/menu.html sits beside prices/compact.html, so the link is
        # a same-directory sibling like that page's own PDF link.
        assert (
            '<a href="menu.html">Bảng Giá</a>'
            in (no_fit_build / "prices/compact.html").read_text()
        )
        priced_menu = (no_fit_build / "prices/menu.html").read_text()
        assert '<a href="#" aria-current="page">Bảng Giá</a>' in priced_menu

    def test_every_nav_carrying_page_marks_exactly_one_current_page(
        self, no_fit_build
    ):
        nav_pages = (
            "index.html",
            "menu.html",
            "menu/compact.html",
            "prices/menu.html",
            "prices.html",
            "prices/compact.html",
        )
        for name in PUBLISHED_PAGES:
            page = (no_fit_build / name).read_text()
            expected = 1 if name in nav_pages else 0
            assert page.count('aria-current="page"') == expected, name

