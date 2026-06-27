# KATL web app — quality gates, build, and operational tasks.
#
# Modeled on ../mastodon_is_my_blog/web/Makefile, adapted to this app's real
# npm scripts (Vitest instead of Karma; eslint + knip + prettier wired in).
# Everything merges onto main, so `make check` is the pre-merge gate.

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install: ## Install dependencies from the lockfile (reproducible)
	npm ci

install-local: ## Install dependencies (updates lockfile if needed)
	npm install

# ---------------------------------------------------------------------------
# Quality gates  (these are what `make check` runs before a merge to main)
# ---------------------------------------------------------------------------

lint: ## ESLint (TypeScript + Angular templates)
	npm run lint

format: ## Auto-format src with Prettier
	npm run format

format-check: ## Verify formatting without writing (CI-friendly)
	npm run format:check

test: ## Run the Vitest suite once (Node, no browser)
	npm run test

coverage: ## Run tests with a coverage report
	npm run test:ci

dead-code: ## Find unused files, deps, and exports (knip)
	npm run dead-code

check: lint format-check test dead-code ## All quality gates — run before merging to main
	@echo "All quality gates passed."

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

build: ## Production build to dist/web
	npm run build

build-pages: ## Production build with the GitHub Pages base href
	npm run build -- --base-href=/keepachangelog-manager/

# ---------------------------------------------------------------------------
# Operational
# ---------------------------------------------------------------------------

serve: ## Dev server with live reload at http://localhost:4200
	npm start

serve-dist: build ## Build, then serve the production bundle statically on :4173
	npx http-server dist/web/browser -p 4173 -c-1

watch: ## Rebuild on change (development configuration)
	npm run watch

clean: ## Remove build output and caches
	rm -rf dist .angular coverage

# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

update: ## Update Angular and dedupe (review the diff before committing)
	npx ng update @angular/cli @angular/core
	npm dedupe

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: install install-local lint format format-check test coverage dead-code \
	check build build-pages serve serve-dist watch clean update help
