.DEFAULT_GOAL := help
SCRIPT := disk_cleanup.py

help: ## list commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "%-10s %s\n", $$1, $$2}'

scan: ## read-only scan of ~ (about 90 s)
	python3 $(SCRIPT) scan

test: ## run tests against a fake home
	uvx pytest -q tests

lint: ## ruff check
	uvx ruff check --line-length 120 .
