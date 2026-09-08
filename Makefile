.PHONY: help dev test build start contract menu menudata site test-site verify-print-chrome

help:
	@echo "targets: dev test build start contract menu menudata site test-site verify-print-chrome"

dev:
	$(MAKE) -C server dev & $(MAKE) -C web dev & wait

test:
	$(MAKE) -C server test
	$(MAKE) -C web test

build: contract
	$(MAKE) -C web build

start:
	$(MAKE) -C server start

contract:
	$(MAKE) -C server export-openapi
	$(MAKE) -C web generate-types

menu:
	$(MAKE) -C server generate-menu

menudata:
	uv run python menu/generate_menudata.py

site:
	uv run --with weasyprint==70.0 python site/generate.py

test-site:
	uv run --with pytest --with weasyprint==70.0 pytest site/ -q

# Prints every built page in the pinned Chrome for Testing shell with
# JavaScript off and fails if any page overflows its print budget on Letter
# or A4. Builds the site into a scratch directory first; pass a build via
# the script's --out flag to verify one that already exists.
verify-print-chrome:
	uv run --with weasyprint==70.0 --with playwright --with pypdf python site/verify_no_js_print.py
