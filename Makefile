UV = uv
PACKAGE = changelogmanager
BUILD_DIR = build
PYLINT_TEMPLATE = {path}:{line}: [{msg_id}({symbol}),{obj}] {msg}

.PHONY: help sync clean format format-check test flake8 pylint mypy bandit lint quality build validate

help:
	@echo Available targets:
	@echo   sync          Install project and dev dependencies with uv
	@echo   format        Run black
	@echo   format-check  Check formatting with black
	@echo   test          Run pytest with coverage and JUnit output
	@echo   flake8        Run flake8 and write JUnit XML output
	@echo   pylint        Run pylint and write a text report
	@echo   mypy          Run mypy type checking
	@echo   bandit        Run bandit and write a JSON report
	@echo   lint          Run flake8, pylint and mypy
	@echo   quality       Run format, lint, bandit, test, and changelog validation checks
	@echo   build         Build source and wheel distributions with uv
	@echo   validate      Validate CHANGELOG.md with changelogmanager
	@echo   clean         Remove local build artifacts

sync:
	$(UV) sync

clean:
	$(UV) run python -c "from pathlib import Path; import shutil; [shutil.rmtree(path, ignore_errors=True) for path in ['$(BUILD_DIR)', 'dist', '.pytest_cache', '.ruff_cache'] if Path(path).exists()]; [Path(path).unlink() for path in ['coverage.xml'] if Path(path).exists()]"

format:
	$(UV) run black $(PACKAGE) tests

format-check:
	$(UV) run python -c "from pathlib import Path; Path('$(BUILD_DIR)').mkdir(exist_ok=True)"
	$(UV) run black --check $(PACKAGE) tests > $(BUILD_DIR)/black.txt

test:
	$(UV) run python -c "from pathlib import Path; Path('$(BUILD_DIR)').mkdir(exist_ok=True)"
	$(UV) run pytest --cov=$(PACKAGE) --cov-report=xml --junitxml=$(BUILD_DIR)/junit-test.xml -vv
	$(UV) run python -c "from pathlib import Path; Path('coverage.xml').replace('$(BUILD_DIR)/junit-coverage.xml')"

flake8:
	$(UV) run python -c "from pathlib import Path; Path('$(BUILD_DIR)').mkdir(exist_ok=True)"
	$(UV) run flake8 --format junit-xml --output-file $(BUILD_DIR)/flake8.xml $(PACKAGE)
	$(UV) run flake8 $(PACKAGE)

pylint:
	$(UV) run python -c "from pathlib import Path; Path('$(BUILD_DIR)').mkdir(exist_ok=True)"
	$(UV) run pylint $(PACKAGE) -r n --msg-template='$(PYLINT_TEMPLATE)' > $(BUILD_DIR)/pylint-report.txt

mypy:
	$(UV) run mypy $(PACKAGE)

bandit:
	$(UV) run python -c "from pathlib import Path; Path('$(BUILD_DIR)').mkdir(exist_ok=True)"
	$(UV) run bandit --format json --output $(BUILD_DIR)/bandit-report.json --recursive $(PACKAGE)

lint: flake8 pylint mypy

quality: format-check lint bandit test validate

build:
	$(UV) build --no-sources

validate:
	$(UV) run changelogmanager --error-format github validate
