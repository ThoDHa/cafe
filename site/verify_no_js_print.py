#!/usr/bin/env python3
"""Verify the built menus print inside budget in Chrome with JavaScript off.

The build gate fits pages with weasyprint only, so the universal print
promise ("the build-injected fit always applies; no print-time scripting
exists") is checked here, against a real browser: this sensor prints every
built page in the pinned Chrome for Testing shell with a
java_script_enabled=False context (the conservative worst case), waits for
the page's load event plus
document.fonts.ready, and renders each page to PDF twice, on Letter and on
explicit 8.27in x 11.69in A4. Page counts are checked against each page's
print budget; any overflow is reported and the exit code is non-zero.

Usage:
    uv run --with playwright --with pypdf python site/verify_no_js_print.py \
        [--out DIR] [--recipes PATH] [--chrome PATH]

With --out the script consumes an existing build directory; without it the
script builds the site first (that mode also needs weasyprint). The browser
defaults to
~/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell
and can be overridden with --chrome or the PRINT_CHROME_BIN environment
variable. The make wrapper is `make verify-print-chrome`.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
import tempfile
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent
DEFAULT_CHROME = (
    Path.home()
    / ".cache"
    / "ms-playwright"
    / "chromium_headless_shell-1243"
    / "chrome-headless-shell-linux64"
    / "chrome-headless-shell"
)
A4_PDF_OPTIONS = {"width": "8.27in", "height": "11.69in"}
PAPER_PDF_OPTIONS = {
    "letter": {"format": "Letter"},
    "a4": A4_PDF_OPTIONS,
}

sys.path.insert(0, str(SITE_DIR))

import generate  # noqa: E402

DEFAULT_RECIPES = generate.DEFAULT_RECIPES

# The four published pages and their print budgets, mirrored from the
# generator's own budget constants so a budget change propagates here.
PAGE_BUDGETS = {
    "menu.html": generate.PRINT_PAGE_BUDGET,
    "menu/compact.html": generate.COMPACT_PAGE_BUDGET,
    "bar.html": generate.BAR_PAGE_BUDGET,
    "kitchen.html": generate.PRINT_PAGE_BUDGET,
}


def shipped_root(page_html: str, page_name: str) -> float:
    """Read the build-injected print root back out of a built page.

    Raises RuntimeError when the page carries no print-fit injection, which
    means the build was made with the fit pass disabled and cannot be
    verified against the shipped roots.
    """

    match = re.search(
        rf'<style id="{generate.PRINT_FIT_STYLE_ID}">'
        rf".*?font-size: ([\d.]+)px.*?</style>",
        page_html,
        re.S,
    )
    if match is None:
        raise RuntimeError(
            f"{page_name} carries no injected print-fit root; rebuild with "
            "the fit pass enabled (make site)"
        )
    return float(match.group(1))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="existing build directory to verify (default: build fresh)",
    )
    parser.add_argument(
        "--recipes",
        type=Path,
        default=DEFAULT_RECIPES,
        help="path to cafe.md, used only when building fresh",
    )
    parser.add_argument(
        "--chrome",
        type=Path,
        default=Path(os.environ.get("PRINT_CHROME_BIN", DEFAULT_CHROME)),
        help="path to the pinned chrome-headless-shell binary",
    )
    return parser.parse_args()


@contextlib.contextmanager
def resolve_build(args: argparse.Namespace):
    """Yield the build directory to verify, building fresh when no --out.

    A fresh build lands in a temporary directory removed when verification
    ends; an explicit --out is only ever read.
    """

    if args.out is not None:
        missing = [
            name
            for name in PAGE_BUDGETS
            if not (args.out / name).is_file()
        ]
        if missing:
            raise RuntimeError(
                f"{args.out} is missing built pages: {', '.join(missing)}; "
                "run make site first"
            )
        yield args.out
        return
    with tempfile.TemporaryDirectory(prefix="cafe-no-js-verify-") as tmp:
        generate.build_site(recipes_path=args.recipes, out_dir=Path(tmp))
        yield Path(tmp)


def _pdf_page_count(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def verify_page(page, build_dir: Path, page_name: str) -> list[str]:
    """Print one built page on both papers and return its overflow failures.

    Each failure string names the page, the paper, the rendered page count,
    the budget, and the shipped root, so a red run is actionable on its own.
    """

    page_html = (build_dir / page_name).read_text()
    root = shipped_root(page_html, page_name)
    budget = PAGE_BUDGETS[page_name]
    page.goto(
        (build_dir / page_name).resolve().as_uri(),
        wait_until="load",
    )
    page.evaluate("document.fonts.ready")
    failures: list[str] = []
    for paper, options in PAPER_PDF_OPTIONS.items():
        pdf = page.pdf(print_background=True, **options)
        count = _pdf_page_count(pdf)
        print(
            f"no-js print: {page_name} on {paper} at a {root:g}px root: "
            f"{count} pages (budget {budget})"
            + ("" if count <= budget else " OVER BUDGET")
        )
        if count > budget:
            failures.append(
                f"{page_name} prints {count} pages on {paper} over its "
                f"{budget}-page budget at the {root:g}px injected root"
            )
    return failures


def main() -> None:
    args = parse_args()
    if not args.chrome.is_file():
        raise RuntimeError(
            f"pinned Chrome shell not found at {args.chrome}; install it or "
            "point --chrome / PRINT_CHROME_BIN at the binary"
        )
    failures: list[str] = []
    from playwright.sync_api import sync_playwright

    with resolve_build(args) as build_dir, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(args.chrome))
        try:
            with contextlib.closing(
                browser.new_context(java_script_enabled=False)
            ) as context:
                page = context.new_page()
                for page_name in PAGE_BUDGETS:
                    failures.extend(verify_page(page, build_dir, page_name))
        finally:
            browser.close()
    if failures:
        for failure in failures:
            print(f"no-js print: FAILED {failure}")
        raise SystemExit(1)
    print(
        "no-js print: all "
        f"{len(PAGE_BUDGETS)} pages within budget on letter and a4 "
        f"in {args.chrome.name} with JavaScript off"
    )


if __name__ == "__main__":
    main()
