.PHONY: help dev test build start contract

help:
	@echo "targets: dev test build start contract"

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
