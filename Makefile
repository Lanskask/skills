.DEFAULT_GOAL := help
SKILLS_WITH_TESTS := disk-cleanup book-to-course youtube-to-course

help: ## list commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

list: ## list the skills
	@ls skills

validate: ## check the plugin and marketplace manifests
	claude plugin validate .

test: ## run every skill's tests
	@for s in $(SKILLS_WITH_TESTS); do echo "== $$s"; $(MAKE) -C skills/$$s test || exit 1; done
