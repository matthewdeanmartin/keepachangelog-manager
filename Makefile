UV = uv
PACKAGE = changelogmanager
BUILD_DIR = build
PYLINT_TEMPLATE = {path}:{line}: [{msg_id}({symbol}),{obj}] {msg}

.PHONY: help sync clean format format-check test flake8 pylint mypy bandit lint quality check build validate ruff gha-validate gha-pin gha-upgrade

help:
	@echo Available targets:
	@echo   sync          Install project and dev dependencies with uv
	@echo   format        Run black
	@echo   format-check  Check formatting with black
	@echo   test          Run pytest with coverage and JUnit output
	@echo   flake8        Run flake8 and write JUnit XML output
	@echo   pylint        Run pylint and write a text report
	@echo   mypy          Run mypy type checking
	@echo   ruff          Run ruff check
	@echo   bandit        Run bandit and write a JSON report
	@echo   lint          Run flake8, pylint, mypy and ruff
	@echo   quality       Run format, lint, bandit, test, and changelog validation checks
	@echo   check         Alias for quality
	@echo   build         Build source and wheel distributions with uv
	@echo   validate      Validate CHANGELOG.md with changelogmanager
	@echo   gha-validate  Validate GitHub Actions workflow safety checks
	@echo   gha-pin       Pin GitHub Actions to current SHAs
	@echo   gha-upgrade   Pin and validate GitHub Actions workflows
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

ruff:
	$(UV) run ruff check .

bandit:
	$(UV) run python -c "from pathlib import Path; Path('$(BUILD_DIR)').mkdir(exist_ok=True)"
	$(UV) run bandit --format json --output $(BUILD_DIR)/bandit-report.json --recursive $(PACKAGE)

lint: flake8 pylint mypy ruff

quality: format-check lint bandit test validate

check: quality

build:
	$(UV) build --no-sources

validate:
	$(UV) run changelogmanager --error-format github validate

gha-validate:
	@echo Validating GitHub Actions workflows
	$(UV) run python -c "import pathlib, yaml; [yaml.safe_load(path.read_text(encoding='utf-8')) for path in pathlib.Path('.github/workflows').glob('*.yml')]; print('YAML parse OK')"
	$(UV) run python -c "from pathlib import Path; import yaml; checks=[('publish_to_pypi.yml','build','pypi-publish'),('release.yml','build','deploy')]; exec(\"for workflow_name, upload_job, download_job in checks:\\n data=yaml.safe_load(Path('.github/workflows', workflow_name).read_text(encoding='utf-8'))\\n upload_steps=data['jobs'][upload_job]['steps']\\n download_steps=data['jobs'][download_job]['steps']\\n upload=next(step for step in upload_steps if step.get('uses','').startswith('actions/upload-artifact@'))\\n download=next(step for step in download_steps if step.get('uses','').startswith('actions/download-artifact@'))\\n assert upload['with']['name']==download['with']['name']=='packages'\\n assert upload['with']['path']==download['with']['path']=='dist/'\\n print(f'Artifact handoff OK for {workflow_name}:', upload['uses'], '->', download['uses'])\")"
	$(UV) tool run --from zizmor zizmor --no-progress --no-exit-codes .

gha-pin:
	@echo Pinning GitHub Actions to current SHAs
	$(UV) run python -c "import os, subprocess; token=os.environ.get('GITHUB_TOKEN'); \
result=None if token else subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, check=False); \
token=token or (result.stdout.strip() if result else ''); \
assert token, 'Set GITHUB_TOKEN or log in with gh auth login'; \
env=dict(os.environ, GITHUB_TOKEN=token); \
raise SystemExit(subprocess.run(['uv', 'tool', 'run', '--from', 'gha-update', 'gha-update'], env=env, check=False).returncode)"

gha-upgrade: gha-pin gha-validate
	@echo GitHub Actions upgrade complete
