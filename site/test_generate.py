"""Tests for the public menu site generator.

Run: uv run --with pytest pytest site/ -q
"""

import sys
import textwrap
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SITE_DIR.parent
RECIPES_CAFE = REPO_ROOT.parent / "recipes" / "cafe.md"
MENU_JSON = REPO_ROOT / "menu" / "menu.json"

sys.path.insert(0, str(SITE_DIR))

import generate  # noqa: E402

FIXTURE = textwrap.dedent(
    """
    # Cafe Fixture

    ## Coffee

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


class TestRealRecipesFile:
    def test_real_file_exists(self):
        assert RECIPES_CAFE.is_file(), "sibling recipes checkout missing"

    def test_real_section_minimum_counts(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        counts = {s.id: len(s.items) for s in menu.sections}
        minimums = {
            "ca-phe": 10,
            "mat-cha": 8,
            "tra": 4,
            "giai-khat": 6,
            "kem": 8,
        }
        assert set(counts) == set(minimums)
        for section_id, minimum in minimums.items():
            assert counts[section_id] >= minimum, (section_id, counts[section_id])

    def test_real_spot_temperatures(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        temps = menu.temperature_map()
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
            "Sữa Đá",
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

    def test_render_escapes_item_text(self):
        menu = generate.parse_menu(RECIPES_CAFE.read_text())
        menu.by_id("ca-phe").items[0].description = "<script>alert(1)</script>"
        page = generate.render_menu_page(menu)
        assert "<script>alert" not in page


class TestBuildSite:
    def test_build_site_writes_full_artifact(self, tmp_path):
        out = tmp_path / "public"
        generate.build_site(recipes_path=RECIPES_CAFE, out_dir=out)
        expected = ["index.html", "menu.html", "kitchen.html", "bar.html"]
        for name in expected:
            assert (out / name).is_file(), f"missing {name}"
        assert (out / "kitchen.html").read_text() == (
            REPO_ROOT / "menu" / "kitchen.html"
        ).read_text()

    def test_build_site_copies_assets(self, tmp_path):
        out = tmp_path / "public"
        generate.build_site(recipes_path=RECIPES_CAFE, out_dir=out)
        asset_source = REPO_ROOT / "menu" / "assets"
        if any(asset_source.iterdir()):
            copied = {p.name for p in (out / "assets").iterdir()}
            expected = {
                p.name for p in asset_source.iterdir() if p.name != ".gitkeep"
            }
            assert copied == expected
