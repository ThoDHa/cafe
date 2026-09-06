"""Tests for the public menu site generator.

Run: uv run --with pytest pytest site/ -q
"""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
RECIPES_CAFE = Path(
    os.environ.get("RECIPES_CAFE", REPO_ROOT.parent / "recipes" / "cafe.md")
)
COCKTAILS_MD = RECIPES_CAFE.parent / "cocktails.md"
MENU_JSON = REPO_ROOT / "menu" / "menu.json"

sys.path.insert(0, str(SITE_DIR))

import generate  # noqa: E402

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

    def test_render_contains_temperature_pills(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        page = generate.render_menu_page(menu)
        assert 'class="tag nong"' in page
        assert 'class="tag da"' in page

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
            "class=\"section-note\"",
            "bản rút gọn",
        ]:
            assert needle in page, f"missing {needle!r}"


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

    def test_render_escapes_item_text(self):
        kitchen = real_kitchen_menu()
        kitchen.sections[0].items[0].description = "<script>alert(1)</script>"
        page = generate.render_kitchen_page(kitchen)
        assert "<script>alert" not in page


class TestPrintFit:
    PAGE = "<html><head><title>x</title></head><body><p>menu</p></body></html>"

    def _fake_counts(self, monkeypatch, fits_at):
        def fake(page_html, base_url=None, papers=generate.PAPER_SIZES):
            root = 16.0
            match = re.search(r"font-size: ([\d.]+)px", page_html)
            if match:
                root = float(match.group(1))
            pages = 2 if root <= fits_at else 3
            return {size: pages for size in papers}

        monkeypatch.setattr(generate, "render_page_counts", fake)

    def test_fit_returns_largest_size_that_fits(self, monkeypatch):
        self._fake_counts(monkeypatch, fits_at=14.0)
        fitted, root = generate.fit_print_root(self.PAGE, label="menu.html")
        assert root == 14.0
        assert 'font-size: 14px' in fitted

    def test_fit_skips_injection_when_default_fits(self, monkeypatch):
        self._fake_counts(monkeypatch, fits_at=16.0)
        fitted, root = generate.fit_print_root(self.PAGE, label="menu.html")
        assert root is None
        assert generate.PRINT_FIT_STYLE_ID not in fitted

    def test_fit_replaces_stale_injection(self, monkeypatch):
        self._fake_counts(monkeypatch, fits_at=14.0)
        pre_injected = generate.inject_print_root(self.PAGE, 12.0)
        fitted, root = generate.fit_print_root(pre_injected, label="menu.html")
        assert root == 14.0
        assert fitted.count(generate.PRINT_FIT_STYLE_ID) == 1
        assert 'font-size: 14px' in fitted

    def test_fit_fails_loudly_below_floor(self, monkeypatch):
        self._fake_counts(monkeypatch, fits_at=0.0)
        try:
            generate.fit_print_root(self.PAGE, label="menu.html")
        except generate.PrintFitError as exc:
            assert "floor" in str(exc)
        else:
            raise AssertionError("expected PrintFitError")

    def test_fit_honors_finer_step_for_compact_page(self, monkeypatch):
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
        )
        assert root == 13.75
        assert "font-size: 13.75px" in fitted

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
        for page in ("menu.html", "kitchen.html"):
            counts = generate.render_page_counts((out / page).read_text())
            for size, count in counts.items():
                assert count <= 2, (page, size, count)
        bar_counts = generate.render_page_counts((out / "bar.html").read_text())
        for size, count in bar_counts.items():
            assert count == 1, ("bar.html", size, count)
        counts = generate.render_page_counts((out / "menu" / "compact.html").read_text())
        for size, count in counts.items():
            assert count == 1, ("menu/compact.html", size, count)


class TestBuildSite:
    def _build(self, tmp_path):
        out = tmp_path / "public"
        generate.build_site(recipes_path=RECIPES_CAFE, out_dir=out, fit_pages=False)
        return out

    def test_build_site_writes_full_artifact(self, tmp_path):
        out = self._build(tmp_path)
        expected = [
            "index.html",
            "menu.html",
            "menu/compact.html",
            "kitchen.html",
            "bar.html",
        ]
        for name in expected:
            assert (out / name).is_file(), f"missing {name}"
        assert (out / "index.html").read_text() == (out / "menu.html").read_text()
        for page in ("kitchen.html", "bar.html"):
            assert "CAFE ÔNG THỌ" in (out / page).read_text()

    def test_homepage_is_the_full_menu(self, tmp_path):
        out = self._build(tmp_path)
        homepage = (out / "index.html").read_text()
        assert ">CÀ PHÊ<" in homepage
        assert ">GIẢI KHÁT<" in homepage
        assert 'class="tag nong"' in homepage

    def test_build_site_copies_assets(self, tmp_path):
        out = self._build(tmp_path)
        asset_source = REPO_ROOT / "menu" / "assets"
        if any(asset_source.iterdir()):
            copied = {p.name for p in (out / "assets").iterdir()}
            expected = {
                p.name for p in asset_source.iterdir() if p.name != ".gitkeep"
            }
            assert copied == expected


PUBLISHED_PAGES = (
    "index.html",
    "menu.html",
    "menu/compact.html",
    "kitchen.html",
    "bar.html",
)


def read_scaler_config(page_html: str) -> dict:
    match = re.search(r"data-print-fit='([^']+)'", page_html)
    assert match, "page carries no scaler configuration"
    return json.loads(match.group(1))


class TestPrintScaler:
    def _build(self, tmp_path):
        out = tmp_path / "public"
        generate.build_site(recipes_path=RECIPES_CAFE, out_dir=out, fit_pages=False)
        return out

    def test_scaler_script_is_referenced_by_every_published_page(self, tmp_path):
        out = self._build(tmp_path)
        expected_src = {
            "index.html": "assets/print-fit.js",
            "menu.html": "assets/print-fit.js",
            "kitchen.html": "assets/print-fit.js",
            "bar.html": "assets/print-fit.js",
            "menu/compact.html": "../assets/print-fit.js",
        }
        for name, src in expected_src.items():
            page = (out / name).read_text()
            assert f'<script defer src="{src}"' in page, name
            config = read_scaler_config(page)
            assert config["cap"] == 16, name
            assert config["paper"] == "letter", name

    def test_compact_and_bar_budget_is_one_page_and_others_are_two(self, tmp_path):
        out = self._build(tmp_path)
        for name in ("menu/compact.html", "bar.html"):
            config = read_scaler_config((out / name).read_text())
            assert config["budget"] == 1, name
        assert read_scaler_config((out / "menu" / "compact.html").read_text())[
            "pageMarginsMm"
        ] == [6, 12]
        for name in ("index.html", "menu.html", "kitchen.html"):
            config = read_scaler_config((out / name).read_text())
            assert config["budget"] == 2, name
        assert read_scaler_config((out / "menu.html").read_text())[
            "pageMarginsMm"
        ] == [6, 12]
        for name in ("kitchen.html", "bar.html"):
            assert read_scaler_config((out / name).read_text())[
                "pageMarginsMm"
            ] == [6, 12], name

    def test_scaler_asset_is_published_into_assets(self, tmp_path):
        out = self._build(tmp_path)
        published = out / "assets" / generate.PRINT_SCALER_ASSET_NAME
        source = REPO_ROOT / "menu" / "assets" / generate.PRINT_SCALER_ASSET_NAME
        assert published.is_file()
        assert published.read_bytes() == source.read_bytes()

    def test_missing_scaler_asset_fails_the_build(self, tmp_path, monkeypatch):
        menu_dir = tmp_path / "menu"
        (menu_dir / "assets").mkdir(parents=True)
        page = "<html><head><title>x</title></head><body><p>menu</p></body></html>"
        for name in ("kitchen.html", "bar.html"):
            (menu_dir / name).write_text(page)
        monkeypatch.setattr(generate, "MENU_SOURCE_DIR", menu_dir)
        try:
            generate.build_site(
                recipes_path=RECIPES_CAFE, out_dir=tmp_path / "public", fit_pages=False
            )
        except RuntimeError as exc:
            assert generate.PRINT_SCALER_ASSET_NAME in str(exc)
        else:
            raise AssertionError("expected the build to fail without the scaler asset")


NODE_SCENARIOS = """
const assert = require("assert");
const solver = require(process.argv[1]);
const pxPerMm = solver.MM_TO_PX;

const compact = solver.geometry({ paper: "letter", pageMarginsMm: [6, 12] });
assert.ok(Math.abs(compact.capacity - (279.4 - 18) * pxPerMm) < 1e-6);
assert.ok(Math.abs(compact.areaWidth - (215.9 - 12) * pxPerMm) < 1e-6);
const kitchenBar = solver.geometry({ paper: "letter", pageMarginsMm: [12.7, 12.7] });
assert.ok(Math.abs(kitchenBar.capacity - (279.4 - 25.4) * pxPerMm) < 1e-6);
assert.equal(solver.geometry({ paper: "a4", pageMarginsMm: [6, 12] }), null);
assert.equal(solver.geometry({ paper: "letter", pageMarginsMm: [6] }), null);

const flat = solver.flattenMedia(
  "@media print { a } @media screen { b } @media (min-width: 0) { c }"
);
assert.ok(flat.includes("@media all"));
assert.ok(flat.includes("@media not all"));
assert.ok(flat.includes("@media (min-width: 0)"));

function linearLayout(sumAt16, lead, tail) {
  return (root) => {
    const flow = (sumAt16 * root) / 16;
    return {
      blocks: [{ h: flow, breakBefore: false }],
      pageLead: lead,
      pageTail: tail,
      total: lead + tail + flow
    };
  };
}

const capacity = 988;

// clamps at the cap when every candidate fits
assert.equal(
  solver.solveRoot(linearLayout(100, 10, 10), { start: 14.25, cap: 16, budget: 1, capacity }),
  16
);
// clamps a start above the cap back into range
assert.equal(
  solver.solveRoot(linearLayout(100, 10, 10), { start: 19, cap: 16, budget: 1, capacity }),
  16
);
// degrades to null when even the floor cannot satisfy the budget
assert.equal(
  solver.solveRoot(linearLayout(100000, 10, 10), { start: 14.25, cap: 16, budget: 1, capacity }),
  null
);

// walk-down then refinement lands on the largest full-page fill
const refined = solver.solveRoot(linearLayout(1100, 10, 10), {
  start: 16, cap: 16, budget: 1, capacity
});
assert.equal(refined, 13.9);

// forced page breaks split the packing into separate pages
assert.equal(
  solver.estimatePageCount(
    [{ h: 400, breakBefore: false }, { h: 480, breakBefore: true }],
    10, 10, 1000, 0.01
  ),
  2
);
assert.equal(
  solver.estimatePageCount(
    [{ h: 400, breakBefore: false }, { h: 480, breakBefore: false }],
    10, 10, 1000, 0.01
  ),
  1
);
// blocks taller than a page fragment like the engines render them
assert.equal(
  solver.estimatePageCount([{ h: 2000, breakBefore: false }], 10, 10, 1000, 0.01),
  3
);

// boundary margins: with margins folded into block heights, the tail
// margin counts against the same page's capacity (the measureIn model's
// boundary case)
assert.equal(
  solver.estimatePageCount([{ h: 940 }], 10, 100, 988, 0.01),
  2
);
assert.equal(
  solver.estimatePageCount([{ h: 860 }], 10, 100, 988, 0.01),
  1
);

// a two-page budget keeps a layout the one-page budget must refuse
const twoPages = solver.solveRoot(linearLayout(1100, 10, 10), {
  start: 16, cap: 16, budget: 2, capacity
});
assert.equal(twoPages, 16);
"""


class TestPrintScalerSolverNode:
    @pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
    def test_pure_solver_passes_node_smoke_scenarios(self):
        asset = REPO_ROOT / "menu" / "assets" / generate.PRINT_SCALER_ASSET_NAME
        assert asset.is_file()
        result = subprocess.run(
            ["node", "-e", NODE_SCENARIOS, str(asset)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
