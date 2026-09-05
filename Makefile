.PHONY: help dev test build start contract menu site test-site

help:
	@echo "targets: dev test build start contract menu site test-site"

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

site:
	uv run --with weasyprint python site/generate.py

test-site:
	uv run --with pytest --with weasyprint pytest site/ -q
