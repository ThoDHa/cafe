"""Generate menu/menu.json from the recipes repository plus the ordering
enrichment config.

Invoked as `uv run generate-menu` (see the pyproject scripts and the
Makefile generate-menu target). The shared stdlib parser in
menu/menu_source.py reads the recipes repository's cafe.md; the checked-in
menu/ordering-overrides.json supplies version, orderRules, categories, and
modifierGroups plus the ordering-only item enrichment the recipes cannot
express (ids, display names, menu copy, images, per-item modifier rules).
Drinks added to recipes appear with sensible defaults and no code or
config change. The result is validated against menu.schema.json before
the canonical serialization is written.
"""

import argparse
import json
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECIPES = REPO_ROOT.parent / "recipes" / "cafe.md"
DEFAULT_OVERRIDES = REPO_ROOT / "menu" / "ordering-overrides.json"
DEFAULT_OUTPUT = REPO_ROOT / "menu" / "menu.json"
SCHEMA_FILENAME = "menu.schema.json"

sys.path.insert(0, str(REPO_ROOT / "menu"))

import menu_source  # noqa: E402

CONFIG_BLOCK_KEYS = ("version", "orderRules", "categories", "modifierGroups")


class MenuGenerationError(Exception):
    """Raised when the recipes and config cannot become a valid menu document."""


def build_document(recipes_text: str, config: dict) -> dict:
    missing = [key for key in CONFIG_BLOCK_KEYS if key not in config]
    if missing:
        raise MenuGenerationError(
            f"the overrides config is missing {', '.join(map(repr, missing))}"
        )
    try:
        items = menu_source.build_ordering_items(recipes_text, config)
    except menu_source.OrderingConfigError as exc:
        raise MenuGenerationError(f"ordering overrides are invalid: {exc}") from exc
    return {
        "version": config["version"],
        "orderRules": config["orderRules"],
        "categories": config["categories"],
        "modifierGroups": config["modifierGroups"],
        "items": items,
    }


def serialize_document(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def validate_document(document: dict, schema: dict) -> None:
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=str)
    if errors:
        details = "\n".join(
            f"  {_describe_validation_error(document, error)}" for error in errors
        )
        raise MenuGenerationError(
            f"generated menu fails {SCHEMA_FILENAME} validation:\n{details}"
        )


def generate(
    recipes_path: Path,
    overrides_path: Path,
    out_path: Path,
    schema_path: Path | None = None,
) -> dict:
    try:
        recipes_text = recipes_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MenuGenerationError(
            f"cannot read the recipes file {recipes_path}: {exc}; pass --recipes "
            "with the path to cafe.md from a checkout of the recipes repository"
        ) from exc
    try:
        config = json.loads(overrides_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MenuGenerationError(
            f"cannot read the overrides config {overrides_path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise MenuGenerationError(
            f"the overrides config {overrides_path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(config, dict):
        raise MenuGenerationError(
            f"the overrides config {overrides_path} must be a JSON object, "
            f"got {type(config).__name__}"
        )
    document = build_document(recipes_text, config)
    if schema_path is None:
        schema_path = overrides_path.parent / SCHEMA_FILENAME
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MenuGenerationError(f"cannot read menu schema {schema_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MenuGenerationError(
            f"menu schema {schema_path} is not valid JSON: {exc}"
        ) from exc
    validate_document(document, schema)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(serialize_document(document), encoding="utf-8")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the orderable menu JSON from the recipes repository"
    )
    parser.add_argument(
        "--recipes", type=Path, default=DEFAULT_RECIPES, help="source cafe.md path"
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=DEFAULT_OVERRIDES,
        help="ordering enrichment config path",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUTPUT, help="output menu.json path"
    )
    args = parser.parse_args(argv)
    try:
        generate(args.recipes, args.overrides, args.out)
    except MenuGenerationError as exc:
        print(f"generate-menu: error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {args.out}")
    return 0


def _describe_validation_error(document: dict, error) -> str:
    path = list(error.path)
    location = ""
    for segment in path:
        if isinstance(segment, int):
            location += f"[{segment}]"
        elif location:
            location += f".{segment}"
        else:
            location = str(segment)
    if len(path) >= 2 and path[0] == "items" and isinstance(path[1], int):
        item = document["items"][path[1]]
        location = f"item {item.get('id')!r} ({location})"
    return f"{location or 'document'}: {error.message}"


if __name__ == "__main__":
    raise SystemExit(main())
