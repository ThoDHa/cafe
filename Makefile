.PHONY: help menu test-menu site test-site verify-print-chrome

help:
	@echo "targets: menu test-menu site test-site verify-print-chrome"

menu:
	uv run --with jsonschema python menu/menu_generator.py

test-menu:
	uv run --with pytest --with jsonschema pytest menu/ -q

site:
	uv run --with weasyprint==70.0 --with openpyxl python site/generate.py

test-site:
	uv run --with pytest --with weasyprint==70.0 --with openpyxl pytest site/ -q

# Prints every built page in the pinned Chrome for Testing shell with
# JavaScript off and fails if any page overflows its print budget on Letter
# or A4. Builds the site into a scratch directory first; pass a build via
# the script's --out flag to verify one that already exists.
verify-print-chrome:
	uv run --with weasyprint==70.0 --with openpyxl --with playwright --with pypdf python site/verify_no_js_print.py
