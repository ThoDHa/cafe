"""Export the OpenAPI schema for the web type-generation pipeline.

Invoked as `uv run export-openapi` (see pyproject scripts and the
Makefile contract target); writes web/openapi.json, which
openapi-typescript compiles into web/src/api/schema.d.ts.
"""

import argparse
import json
from pathlib import Path

from app.main import app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "web" / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the OpenAPI schema to disk")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
