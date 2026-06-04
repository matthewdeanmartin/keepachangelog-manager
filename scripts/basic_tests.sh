#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="build/basic-tests"

run() {
    printf '==> %s\n' "$*"
    "$@"
}

assert_text_contains() {
    if [[ "$1" != *"$2"* ]]; then
        printf 'expected text to contain %s\n' "$2" >&2
        return 1
    fi
}

assert_empty() {
    if [[ -n "$1" ]]; then
        printf 'expected output to be empty but got: %s\n' "$1" >&2
        return 1
    fi
}

assert_missing() {
    if [[ -e "$1" ]]; then
        printf 'expected %s to be missing\n' "$1" >&2
        return 1
    fi
}

assert_same() {
    if ! cmp -s "$1" "$2"; then
        printf 'expected %s and %s to match\n' "$1" "$2" >&2
        return 1
    fi
}

cd "${ROOT_DIR}"
rm -rf "${TMP_DIR}"
trap 'rm -rf "${TMP_DIR}"' EXIT
mkdir -p "${TMP_DIR}/service" "${TMP_DIR}/exports"

cat > "${TMP_DIR}/CHANGELOG.md" <<'EOF'
# Changelog

## [Unreleased]
### Added
- New feature

### Changed
- Changed another feature

## [1.0.0] - 2022-03-14
### Removed
- Removed deprecated API call

### Fixed
- Fixed some bug

## [0.9.4] - 2022-03-13
### Deprecated
- Deprecated public API call
EOF

cp "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/service/CHANGELOG.md"
cp "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

cat > "${TMP_DIR}/unordered.md" <<'EOF'
# Changelog

## [Unreleased]
### Added
- Feature A

## [1.0.0] - 2024-01-01
### Added
- Initial release

## [2.0.0] - 2024-06-01
### Added
- Big change
EOF

cp "${TMP_DIR}/unordered.md" "${TMP_DIR}/unordered.original.md"

cat > "${TMP_DIR}/config.yml" <<EOF
project:
  components:
    - name: Service Component
      changelog: ${TMP_DIR}/service/CHANGELOG.md
EOF

run uv sync --frozen >/dev/null

run uv run changelogmanager --help >/dev/null
run uv run python -m changelogmanager --help >/dev/null
run uv run changelogmanager validate --help >/dev/null
run uv run changelogmanager create --help >/dev/null
run uv run changelogmanager config --help >/dev/null
run uv run changelogmanager config init --help >/dev/null
run uv run changelogmanager skill --help >/dev/null
run uv run changelogmanager skill export --help >/dev/null
run uv run changelogmanager add --help >/dev/null
run uv run changelogmanager remove --help >/dev/null
run uv run changelogmanager edit --help >/dev/null
run uv run changelogmanager version --help >/dev/null
run uv run changelogmanager release --help >/dev/null
run uv run changelogmanager to-json --help >/dev/null
run uv run changelogmanager to-yaml --help >/dev/null
run uv run changelogmanager to-html --help >/dev/null
run uv run changelogmanager github-release --help >/dev/null
run uv run changelogmanager github-pr --help >/dev/null
run uv run changelogmanager gitlab-release --help >/dev/null
run uv run changelogmanager backfill --help >/dev/null
run uv run changelogmanager from-commits --help >/dev/null
run uv run changelogmanager gui --help >/dev/null

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" validate --dry-run >/dev/null
validate_fix_output="$(uv run changelogmanager --input-file "${TMP_DIR}/unordered.md" validate --fix --no-format --dry-run)"
assert_text_contains "${validate_fix_output}" "Dry run:"
assert_same "${TMP_DIR}/unordered.md" "${TMP_DIR}/unordered.original.md"
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --reference previous --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --reference future --dry-run >/dev/null
run uv run changelogmanager --config "${TMP_DIR}/config.yml" --component "Service Component" version --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/generated/CHANGELOG.md" create --dry-run >/dev/null
assert_missing "${TMP_DIR}/generated/CHANGELOG.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" add --change-type added --message "Smoke test entry" --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

remove_list_output="$(uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" remove --list)"
assert_text_contains "${remove_list_output}" "[added] 0: New feature"
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" remove --change-type added --index 0 --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" edit --change-type added --index 0 --message "Edited smoke test entry" --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" release --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" release --override-version v1.1.0 --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" to-json --file-name "${TMP_DIR}/CHANGELOG.json" --dry-run >/dev/null
assert_missing "${TMP_DIR}/CHANGELOG.json"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" to-yaml --file-name "${TMP_DIR}/CHANGELOG.yaml" --dry-run >/dev/null
assert_missing "${TMP_DIR}/CHANGELOG.yaml"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" to-html --file-name "${TMP_DIR}/CHANGELOG.html" --dry-run >/dev/null
assert_missing "${TMP_DIR}/CHANGELOG.html"

config_json="$(uv run changelogmanager --config "${TMP_DIR}/config.yml" --json config)"
assert_text_contains "${config_json}" '"config_source": "explicit --config'
assert_text_contains "${config_json}" '"config"'

future_json="$(uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" --json version --reference future)"
assert_text_contains "${future_json}" '"version": "1.1.0"'

quiet_output="$(uv run changelogmanager --quiet --input-file "${TMP_DIR}/CHANGELOG.md" version --reference current)"
assert_empty "${quiet_output}"

run uv run changelogmanager skill export --path "${TMP_DIR}/exports" --dry-run >/dev/null
assert_missing "${TMP_DIR}/exports/keepachangelog-manager-cli"

run uv run changelogmanager --error-format github --input-file "${TMP_DIR}/CHANGELOG.md" github-release --repository example/repo --github-token token --dry-run >/dev/null
run uv run changelogmanager --error-format llvm --input-file "${TMP_DIR}/CHANGELOG.md" github-release --repository example/repo --github-token token --release --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" github-pr --repository example/repo --head docs/changelog --base main --github-token token --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" gitlab-release --project example/group --gitlab-token token --dry-run >/dev/null

run env ROOT_DIR="${ROOT_DIR}" TMP_DIR="${TMP_DIR}" uv run python - <<'PY'
from __future__ import annotations

import argparse
import os
from pathlib import Path

from changelogmanager import cli, gui
from changelogmanager.change_types import TYPES_OF_CHANGE

tmp_dir = Path(os.environ["TMP_DIR"])
config_path = tmp_dir / "interactive-config.yml"
config_answers = {
    "commit_style": cli.COMMIT_STYLE_LABELS["conventional"],
    "versioning_scheme": cli.VERSIONING_SCHEMES["semver"]["label"],
    "enforce_preamble": "No",
    "component_name": "default",
    "changelog_path": "CHANGELOG.md",
}
skill_choices, _ = cli.skill_location_choices()
prompt_calls: list[list[str]] = []


def fake_prompt(prompts):
    names = [prompt.name for prompt in prompts]
    prompt_calls.append(names)
    if "commit_style" in names:
        return dict(config_answers)
    if names == ["location"]:
        return {"location": skill_choices[0]}
    raise AssertionError(f"Unexpected prompt flow: {names}")


original_prompt = cli.inquirer.prompt
original_isatty = cli.sys.stdin.isatty
cli.inquirer.prompt = fake_prompt
cli.sys.stdin.isatty = lambda: True
try:
    cli.command_config_init(
        argparse.Namespace(config=str(config_path), resolved_config_path=str(config_path)),
        cli.CliContext(
            changelog=cli.Changelog(file_path="CHANGELOG.md", versioning_scheme="semver")
        ),
    )
    config_text = config_path.read_text(encoding="utf-8")
    assert "components:" in config_text
    assert "changelog: CHANGELOG.md" in config_text
    assert cli.main(["skill", "export", "--dry-run"]) == 0
finally:
    cli.inquirer.prompt = original_prompt
    cli.sys.stdin.isatty = original_isatty

sample_changelog = tmp_dir / "CHANGELOG.md"
code, output = gui.run_cli(["--input-file", str(sample_changelog), "version"])
assert code == 0
assert "1.0.0" in output

saved_tk = gui.tk
saved_tk_error = gui.TK_IMPORT_ERROR
try:
    gui.tk = None
    gui.TK_IMPORT_ERROR = RuntimeError("forced missing tkinter")
    assert gui.run_gui() == 1
finally:
    gui.tk = saved_tk
    gui.TK_IMPORT_ERROR = saved_tk_error


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DummyWidget:
    def __init__(self):
        self.buffer = ""

    def insert(self, _position, text):
        self.buffer += text

    def see(self, _position):
        return None

    def update_idletasks(self):
        return None

    def delete(self, *_args):
        self.buffer = ""


messages: list[tuple[str, str]] = []


class DummyMessageBox:
    @staticmethod
    def showerror(title, message):
        messages.append((title, message))


saved_messagebox = gui.messagebox
saved_run_cli = gui.run_cli
saved_widget_tk = gui.tk
try:
    gui.messagebox = DummyMessageBox
    gui.run_cli = lambda argv: (0, f"ran {' '.join(argv)}\n")
    if gui.tk is None:
        gui.tk = type("DummyTk", (), {"END": "end"})

    app = gui.ChangelogManagerGUI.__new__(gui.ChangelogManagerGUI)
    app.config_var = DummyVar("")
    app.component_var = DummyVar("default")
    app.error_format_var = DummyVar("llvm")
    app.input_file_var = DummyVar(str(sample_changelog))
    app.version_ref_var = DummyVar("future")
    app.release_override_var = DummyVar("")
    app.to_json_file_var = DummyVar("CHANGELOG.json")
    app.add_type_var = DummyVar(TYPES_OF_CHANGE[0])
    app.add_message_var = DummyVar("")
    app.gh_repo_var = DummyVar("")
    app.gh_token_var = DummyVar("")
    app.gh_draft_var = DummyVar(True)
    app.dry_run_var = DummyVar(False)
    app.output_widgets = {
        "version": DummyWidget(),
        "add": DummyWidget(),
        "github-release": DummyWidget(),
    }
    app.changelog_view = None
    app.reload_changelog = lambda: None

    assert app.build_argv("version")[-2:] == ["--reference", "future"]
    assert app.build_argv("add") is None
    assert messages[-1][1] == "A message is required for the 'add' command."

    app.add_message_var.set("GUI smoke entry")
    add_argv = app.build_argv("add")
    assert add_argv is not None
    assert "--message" in add_argv

    assert app.build_argv("github-release") is None
    assert messages[-1][1] == "Repository and GitHub token are required for github-release."

    app.run_command("version")
    assert "$ changelogmanager" in app.output_widgets["version"].buffer
    assert "ran" in app.output_widgets["version"].buffer
finally:
    gui.messagebox = saved_messagebox
    gui.run_cli = saved_run_cli
    gui.tk = saved_widget_tk
PY

echo "Done"